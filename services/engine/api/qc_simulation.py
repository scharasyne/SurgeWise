"""Historical QC simulation driven by production barangay forecasts."""
from datetime import date, timedelta
import json
import hashlib
import math
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from .research import StrictModel, FacilityAssumption, unavailable
from .outbreak import OutbreakInput, inputs, create_movie
from ..repositories import gp_runs
from ..repositories.weekly_handoff import ARCHIVE_ONLY_NOTE, ID_PATTERN, load_weekly_run
from ..repositories.forecast_runs import ForecastRunNotFound
from ..repositories.production_runs import evidence
from ..domain.source_calendar import historical_window
from ..repositories.facility import load_facilities
from ..domain.bed_allotments import AllotmentFileError, MAX_FILE_BYTES, capacity_mismatch, parse_allotments, read_table

router = APIRouter(prefix="/v1")
LIMITS = {
    "horizonDays": {"min": 1, "max": 28, "shortcuts": [7, 14, 28], "units": "elapsed days"},
    "extraCasesPerWeek": {"min": 0, "max": 100000, "units": "assumed added cases/week at full intensity"},
    "growthDays": {"min": 1, "max": 28, "units": "days"},
    "surgeCapacity": {"min": 0, "max": 10000, "units": "assumed supported surge beds/site"},
    "holdingCapacity": {"min": 0, "max": 10000, "units": "assumed holding spaces/site"},
    "hospitalizationRate": {"min": 0, "max": 1, "units": "assumed fraction"},
    "baselineOccupancy": {"min": 0, "max": 1, "units": "assumed staffed-bed share reserved for other care"},
    "lengthOfStayDays": {"min": 1, "max": 30, "units": "days"},
    "admissionDelayDays": {"min": 0, "max": 28, "units": "days"},
    "surgeActivationDay": {"min": 0, "max": 28, "units": "day index"},
}


class HospitalCapacity(StrictModel):
    """User-imported per-hospital assumption; never verified capacity or a vacancy."""
    facilityId: str = Field(pattern=r"^HOSP-\d{3}$")
    holdingSpaces: int | None = Field(default=None, strict=True, ge=0, le=10000)
    # Extra staffed beds on top of the hospital's beds; None keeps the scenario default (all for dengue).
    extraDengueBeds: int | None = Field(default=None, strict=True, ge=0, le=10000)
    extraNonDengueBeds: int | None = Field(default=None, strict=True, ge=0, le=10000)
    # Part of holdingSpaces kept for non-dengue patients; dengue overflow can use only the rest.
    nonDengueHoldingSpaces: int | None = Field(default=None, strict=True, ge=0, le=10000)

    @model_validator(mode="after")
    def check_holding(self):
        if (self.nonDengueHoldingSpaces or 0) > (self.holdingSpaces or 0):
            raise ValueError("Non-dengue holding spaces cannot exceed the hospital's holding spaces.")
        return self


class BedAllotment(HospitalCapacity):
    dengueBeds: int = Field(strict=True, ge=0, le=10000)
    nonDengueBeds: int = Field(strict=True, ge=0, le=10000)

    @model_validator(mode="after")
    def check_total(self):
        if not 1 <= self.dengueBeds + self.nonDengueBeds <= 10000:
            raise ValueError("Each hospital needs 1-10,000 dengue plus non-dengue beds.")
        return self


class StaffedBedTotal(HospitalCapacity):
    """A hospital-specific total that follows the scenario reservation percentage."""
    staffedBeds: int = Field(strict=True, ge=1, le=10000)


class QCInput(StrictModel):
    reconstructHistory: bool = True
    weeklyForecastId: str | None = Field(default=None, pattern="^" + ID_PATTERN + "$")
    startDate: date = gp_runs.FIRST_DAY
    endDate: date = gp_runs.FIRST_DAY + timedelta(days=28)
    mode: Literal["forecast", "hypothetical_shock"] = "forecast"
    extraCasesPerWeek: float = Field(default=0, ge=0, le=100000)
    growthDays: int = Field(default=14, strict=True, ge=1, le=28)
    surgeCapacity: int = Field(default=10, strict=True, ge=0, le=10000)
    holdingCapacity: int = Field(default=5, strict=True, ge=0, le=10000)
    hospitalizationRate: float = Field(default=.15, ge=0, le=1)
    baselineOccupancy: float = Field(default=.6, ge=0, le=1)
    lengthOfStayDays: int = Field(default=4, strict=True, ge=1, le=30)
    admissionDelayDays: int = Field(default=0, strict=True, ge=0, le=28)
    surgeActivationDay: int = Field(default=7, strict=True, ge=0, le=28)
    acknowledgeAssumedCapacity: Literal[True] = True
    allocationPolicy: Literal["first_hospital", "next_probability"] = "first_hospital"
    arrivalSplitPolicy: Literal["markov_preference", "markov_proximity"] = "markov_preference"
    compareAllocation: bool = False
    bedAllotments: list[BedAllotment | StaffedBedTotal] | None = Field(default=None, max_length=46)

    @model_validator(mode="after")
    def check_window(self):
        if self.bedAllotments and len({a.facilityId for a in self.bedAllotments}) != len(self.bedAllotments):
            raise ValueError("Each hospital may appear only once in bed allotments.")
        if not 1 <= (self.endDate - self.startDate).days <= 28:
            raise ValueError("Select a 1–28 elapsed-day date range.")
        if not 2012 <= self.startDate.year <= 2035:
            raise ValueError("Historical replay begins in 2012; hypothetical date labels may extend through 2035.")
        if self.mode == "forecast" and ((self.startDate.year > 2025 and not self.weeklyForecastId) or self.extraCasesPerWeek != 0):
            raise ValueError("Use an archive date in 2012–2022 for historical replay and hypothetical mode for added cases.")
        return self


def facility_assumptions(params, hospitals):
    """Use each approved accredited total as the scenario bed stock; only its partition can change."""
    allotments = {a.facilityId: a for a in params.bedAllotments or []}
    if not set(allotments).issubset({h["id"] for h in hospitals}):
        raise HTTPException(422, detail={"code": "INVALID_BED_ALLOTMENT",
            "message": "Bed allotments name a hospital outside the approved QC network. Import the file again."})
    facilities = []
    for h in hospitals:
        a = allotments.get(h["id"])
        total = h["accreditedBeds"]
        if a:
            supplied = a.dengueBeds + a.nonDengueBeds if isinstance(a, BedAllotment) else a.staffedBeds
            mismatch = capacity_mismatch(supplied, h)
            if mismatch:
                raise HTTPException(422, detail={"code": "INVALID_BED_ALLOTMENT", "message": mismatch})
        if isinstance(a, BedAllotment):
            other = a.nonDengueBeds
        else:
            dengue = math.floor(round(total * (1 - params.baselineOccupancy), 10) + 0.5)
            other = total - dengue
        holding = a.holdingSpaces if a and a.holdingSpaces is not None else params.holdingCapacity
        # Nearest whole number to 2/5 of the holding total, with an explicit split taking priority.
        dengue_holding = (2 * holding + 2) // 5
        if a and a.nonDengueHoldingSpaces is not None:
            dengue_holding = holding - a.nonDengueHoldingSpaces
        facilities.append(FacilityAssumption(facilityId=h["id"], assumedDengueEligible=True,
            normalCapacity=total, baselineOccupancy=other / total,
            surgeCapacity=a.extraDengueBeds if a and a.extraDengueBeds is not None else params.surgeCapacity,
            surgeNonDengueCapacity=(a.extraNonDengueBeds or 0) if a else 0,
            holdingCapacity=dengue_holding))
    return facilities


@router.post("/qc-simulation/bed-allotments")
async def bed_allotments(request: Request):
    """Read an uploaded CSV/.xlsx of per-hospital allotments and match it to the approved hospitals."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(413, detail={"code": "ALLOTMENT_FILE_TOO_LARGE", "message": "The file is larger than 1 MB."})
    content = await request.body()
    try:
        hospitals = load_facilities()
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None
    try:
        result = parse_allotments(read_table(content), hospitals)
    except AllotmentFileError as error:
        raise HTTPException(422, detail={"code": "ALLOTMENT_FILE_INVALID", "message": str(error)}) from None
    return {**result, "hospitalCount": len(hospitals), "measurementKind": "assumption",
        "caveat": "Hospital totals come from the PhilHealth register. The split and temporary spaces are planning assumptions."}


def select_reference(runs, start, end=None):
    # Explicit UI dating assumption only, never asserted as reconciled source metadata.
    eligible = [r for r in runs if historical_window(r)[0] <= start < historical_window(r)[1]
                and (end is None or end <= historical_window(r)[1])]
    if not eligible:
        raise HTTPException(422, detail={"code": "HISTORICAL_WINDOW_UNAVAILABLE",
            "message": "The selected dates are outside the saved historical forecast targets. Choose an available historical window; a forecast from another month will not be relabeled.",
            "availableWindows": [{"startDate": historical_window(r)[0].isoformat(), "endDate": historical_window(r)[1].isoformat()} for r in runs]})
    return max(eligible, key=lambda r: (r["issueBlock"]["YR"], r["issueBlock"]["WN"]))


def linked_run(ident):
    try:
        run = load_weekly_run(ident)
        if run["issueBlock"] != {"YR": 2022, "WN": 52} or run["observationSource"].startswith("User-supplied"):
            raise HTTPException(422, detail={"code": "ARCHIVE_CASE_HISTORY_REQUIRED", "message": ARCHIVE_ONLY_NOTE})
        return run
    except ForecastRunNotFound:
        raise HTTPException(404, detail={"code": "FORECAST_NOT_FOUND", "message": "This saved weekly forecast is unavailable."}) from None
    except (OSError, ValueError):
        raise unavailable() from None


@router.get("/qc-simulation")
def default_workspace(weeklyForecastId: str | None = None):
    if weeklyForecastId is None:
        return workspace(QCInput())
    run = linked_run(weeklyForecastId)
    start = date.fromisoformat(run["scenarioStart"])
    return workspace(QCInput(weeklyForecastId=weeklyForecastId, startDate=start,
                             endDate=start + timedelta(days=len(run["dailyPredictions"])), mode="hypothetical_shock"))


@router.post("/qc-simulation")
def workspace(params: QCInput):
    try:
        duration = (params.endDate - params.startDate).days
        if params.weeklyForecastId:
            run = linked_run(params.weeklyForecastId)
            if (params.startDate.isoformat() != run["scenarioStart"] or duration != len(run["dailyPredictions"])
                    or params.mode != "hypothetical_shock" or params.extraCasesPerWeek):
                raise HTTPException(422, detail={"code": "FORECAST_WINDOW_MISMATCH",
                    "message": "Use the linked weekly forecast's dates and case scenario."})
        elif gp_runs.FIRST_DAY <= params.startDate and params.endDate <= gp_runs.END_EXCLUSIVE:
            use_forest = params.startDate >= gp_runs.RF_START and not params.reconstructHistory
            loader = gp_runs.holdout_run if use_forest else gp_runs.reconstruction_run
            try:
                run = loader(params.startDate, duration)
            except (OSError, ValueError, KeyError, IndexError):
                raise HTTPException(503, detail={"code": "ARCHIVE_REPLAY_UNAVAILABLE",
                    "message": "The selected historical input failed verification. Restore the archive GP data or rebuild the historical RF replay."}) from None
        else:
            raise HTTPException(422, detail={"code": "HISTORICAL_WINDOW_UNAVAILABLE",
                "message": "Choose historical replay dates within 2012–2022."})
        geo = inputs(run["id"], params.startDate.year, True)[1]
        # No place is requested from the browser; all QC weights determine rankings.
        automatic_origin = max(geo["barangays"], key=lambda b: b["weight"])["id"]
        model = OutbreakInput(
            forecastRunId=run["id"], scenarioKind="historical_replay" if params.mode == "forecast" else "hypothetical_shock",
            autoHotspots=True, acknowledgeHypotheticalHospitalNetwork=True, acknowledgeHypotheticalDates=True,
            allocationPolicy=params.allocationPolicy, arrivalSplitPolicy=params.arrivalSplitPolicy,
            startDate=params.startDate, endDate=params.endDate, seedBarangayId=automatic_origin,
            extraCasesPerWeek=params.extraCasesPerWeek, initialRadiusKm=.5, expansionKmPerDay=0,
            growthDays=params.growthDays, shockProfile="ramp", hospitalizationRate=params.hospitalizationRate,
            lengthOfStayDays=params.lengthOfStayDays, baselineOccupancy=params.baselineOccupancy,
            admissionDelayDays=params.admissionDelayDays, surgeActivationDay=params.surgeActivationDay,
            facilities=facility_assumptions(params, geo["hospitals"]))
        result = create_movie(model)
        core_hash = result["resultSha256"]
        # These are presentation/evidence fields from approved artifacts, never browser facts.
        result = {**result, "controlValues": params.model_dump(mode="json"), "inputLimits": LIMITS,
            "historicalWindows": [{"startDate": gp_runs.FIRST_DAY.isoformat(), "endDate": gp_runs.END_EXCLUSIVE.isoformat(),
                "kind": "training_archive", "forecastAvailableFrom": gp_runs.RF_START.isoformat()}],
            "forecastEvidence": evidence(run), "scope": "QUEZON_CITY", "mapContext": "PHILIPPINES_GEOMETRY_ONLY",
            "referenceSelectionAssumption": run["availabilityAssumption"],
            "rangeInterpretation": run["intervalCaveat"], "forecastBacktest": []}
        final = result["days"][-1]
        result["periodSummary"] = {"expectedCases": final["cumulativeCases"], "caseRange": None,
            "barangays": sorted(final["barangays"], key=lambda b: (-b["cumulativeCases"], b["barangayId"]))}
        result["assumptions"] += " " + placement_assumption(params)
        if params.compareAllocation:
            result["firstAdmissionComparison"] = compare_first_admissions(model, result)
        result["simulationResultSha256"] = core_hash
        result.pop("resultSha256", None)
        result["resultSha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
        return result
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None

def placement_assumption(params):
    if params.allocationPolicy == "first_hospital":
        return "Modeled demand stays at the first hospital selected by the Markov probabilities."
    return ("Each hospital serves its first-choice demand up to available staffed capacity. Overflow tries the "
            "highest-probability available hospital for its origin barangay. Equal probabilities split demand evenly, "
            "and competing arrivals share the remaining capacity proportionally. Temporary holding follows staffed beds.")


def compare_first_admissions(model, movie):
    other_policy = "markov_proximity" if model.arrivalSplitPolicy == "markov_preference" else "markov_preference"
    other = create_movie(model.model_copy(update={"arrivalSplitPolicy": other_policy}))
    return [{"arrivalSplitPolicy": value["parameters"]["arrivalSplitPolicy"],
             "cumulativeUnresolved": value["days"][-1]["cumulativeUnresolved"],
             "peakBedsShort": value["bedProjection"]["peakHospitalBedsShort"],
             "peakShortageDate": value["bedProjection"]["peakHospitalShortageDate"],
             "peakExpectedBeds": max(d["bedForecast"]["expectedBeds"] for d in value["days"])}
            for value in sorted([movie, other], key=lambda v: v["parameters"]["arrivalSplitPolicy"], reverse=True)]
