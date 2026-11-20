"""Automatic QC-only environmental forecast workspace. No user-selected outbreak place."""
from datetime import date, timedelta
import json
import hashlib
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from .research import StrictModel, FacilityAssumption, unavailable
from .outbreak import OutbreakInput, inputs, create_movie
from ..repositories.forecast_runs import load_environmental_runs, FOLDER
from ..domain.source_calendar import historical_window
from ..repositories.first_admission import AllocationPolicy, ArrivalPolicy, MATRICES
from ..repositories.facility import load_facilities
from ..domain.bed_allotments import AllotmentFileError, MAX_FILE_BYTES, parse_allotments, read_table

router = APIRouter(prefix="/v1")
LIMITS = {
    "horizonDays": {"min": 1, "max": 28, "shortcuts": [7, 14, 28], "units": "elapsed days"},
    "extraCasesPerWeek": {"min": 0, "max": 100000, "units": "assumed added cases/week at full intensity"},
    "growthDays": {"min": 1, "max": 28, "units": "days"},
    "normalCapacity": {"min": 1, "max": 10000, "units": "assumed beds/site"},
    "surgeCapacity": {"min": 0, "max": 10000, "units": "assumed supported surge beds/site"},
    "holdingCapacity": {"min": 0, "max": 10000, "units": "assumed holding spaces/site"},
    "hospitalizationRate": {"min": 0, "max": 1, "units": "assumed fraction"},
    "baselineOccupancy": {"min": 0, "max": 1, "units": "assumed non-dengue occupancy fraction"},
    "lengthOfStayDays": {"min": 1, "max": 30, "units": "days"},
    "admissionDelayDays": {"min": 0, "max": 28, "units": "days"},
    "surgeActivationDay": {"min": 0, "max": 28, "units": "day index"},
}


class BedAllotment(StrictModel):
    """User-imported per-hospital assumption; never verified capacity or a vacancy."""
    facilityId: str = Field(pattern=r"^HOSP-\d{3}$")
    dengueBeds: int = Field(strict=True, ge=0, le=10000)
    nonDengueBeds: int = Field(strict=True, ge=0, le=10000)
    holdingSpaces: int = Field(strict=True, ge=0, le=10000)
    # Extra staffed beds on top of the hospital's beds; None keeps the scenario default (all for dengue).
    extraDengueBeds: int | None = Field(default=None, strict=True, ge=0, le=10000)
    extraNonDengueBeds: int | None = Field(default=None, strict=True, ge=0, le=10000)
    # Part of holdingSpaces kept for non-dengue patients; dengue overflow can use only the rest.
    nonDengueHoldingSpaces: int | None = Field(default=None, strict=True, ge=0, le=10000)

    @model_validator(mode="after")
    def check_total(self):
        if not 1 <= self.dengueBeds + self.nonDengueBeds <= 10000:
            raise ValueError("Each hospital needs 1-10,000 dengue plus non-dengue beds.")
        if (self.nonDengueHoldingSpaces or 0) > self.holdingSpaces:
            raise ValueError("Non-dengue holding spaces cannot exceed the hospital's holding spaces.")
        return self


class QCInput(StrictModel):
    startDate: date = date(2025, 1, 29)
    endDate: date = date(2025, 2, 26)
    mode: Literal["forecast", "hypothetical_shock"] = "forecast"
    extraCasesPerWeek: float = Field(default=0, ge=0, le=100000)
    growthDays: int = Field(default=14, strict=True, ge=1, le=28)
    normalCapacity: int = Field(default=20, strict=True, ge=1, le=10000)
    surgeCapacity: int = Field(default=10, strict=True, ge=0, le=10000)
    holdingCapacity: int = Field(default=5, strict=True, ge=0, le=10000)
    hospitalizationRate: float = Field(default=.15, ge=0, le=1)
    baselineOccupancy: float = Field(default=.75, ge=0, le=1)
    lengthOfStayDays: int = Field(default=4, strict=True, ge=1, le=30)
    admissionDelayDays: int = Field(default=0, strict=True, ge=0, le=28)
    surgeActivationDay: int = Field(default=7, strict=True, ge=0, le=28)
    acknowledgeAssumedCapacity: Literal[True] = True
    allocationPolicy: AllocationPolicy = "first_hospital"
    arrivalSplitPolicy: ArrivalPolicy = "markov_preference"
    compareAllocation: bool = False
    bedAllotments: list[BedAllotment] | None = Field(default=None, max_length=46)

    @model_validator(mode="before")
    @classmethod
    def resolve_choice_defaults(cls, data):
        if not isinstance(data, dict):
            return data
        values = dict(data)
        if "arrivalSplitPolicy" in values:
            values.setdefault("allocationPolicy", "first_hospital" if values["arrivalSplitPolicy"] in ("markov_preference", "markov_proximity") else "nearest")
        elif values.get("allocationPolicy") in ("nearest", "optimized"):
            values["arrivalSplitPolicy"] = "nearest_three_equal"
        return values

    @model_validator(mode="after")
    def check_window(self):
        if self.bedAllotments and len({a.facilityId for a in self.bedAllotments}) != len(self.bedAllotments):
            raise ValueError("Each hospital may appear only once in bed allotments.")
        if (self.arrivalSplitPolicy in MATRICES) != (self.allocationPolicy == "first_hospital"):
            raise ValueError("Select first-hospital placement for a Markov choice policy.")
        if not 1 <= (self.endDate - self.startDate).days <= 28:
            raise ValueError("Select a 1–28 elapsed-day date range.")
        if not 2024 <= self.startDate.year <= 2035:
            raise ValueError("Source-based reference windows begin in 2024; hypothetical date labels may extend through 2035.")
        if self.mode == "forecast" and (self.startDate.year > 2025 or self.extraCasesPerWeek != 0):
            raise ValueError("Forecast-reference mode uses historical data through 2025 and no added shock. Choose hypothetical mode for future/off-season stress tests.")
        return self


def facility_assumptions(params, hospitals):
    """Uniform per-hospital capacity, replaced per hospital by any imported allotment."""
    allotments = {a.facilityId: a for a in params.bedAllotments or []}
    if not set(allotments).issubset({h["id"] for h in hospitals}):
        raise HTTPException(422, detail={"code": "INVALID_BED_ALLOTMENT",
            "message": "Bed allotments name a hospital outside the approved QC network. Import the file again."})
    facilities = []
    for h in hospitals:
        a = allotments.get(h["id"])
        if a is None:
            facilities.append(FacilityAssumption(facilityId=h["id"], assumedDengueEligible=True,
                normalCapacity=params.normalCapacity, surgeCapacity=params.surgeCapacity, holdingCapacity=params.holdingCapacity))
        else:
            total = a.dengueBeds + a.nonDengueBeds
            facilities.append(FacilityAssumption(facilityId=h["id"], assumedDengueEligible=True, normalCapacity=total,
                surgeCapacity=params.surgeCapacity if a.extraDengueBeds is None else a.extraDengueBeds,
                surgeNonDengueCapacity=a.extraNonDengueBeds or 0,
                holdingCapacity=a.holdingSpaces - (a.nonDengueHoldingSpaces or 0), baselineOccupancy=a.nonDengueBeds / total))
    return facilities


@router.post("/qc-simulation/bed-allotments")
async def bed_allotments(request: Request):
    """Read an uploaded CSV/.xlsx of per-hospital allotments and match it to the approved hospitals."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(413, detail={"code": "ALLOTMENT_FILE_TOO_LARGE", "message": "The file is larger than 1 MB."})
    content = await request.body()
    try:
        hospitals = [{"id": h["id"], "name": h["name"]} for h in load_facilities()]
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None
    try:
        result = parse_allotments(read_table(content), hospitals)
    except AllotmentFileError as error:
        raise HTTPException(422, detail={"code": "ALLOTMENT_FILE_INVALID", "message": str(error)}) from None
    return {**result, "hospitalCount": len(hospitals), "measurementKind": "assumption",
        "caveat": "Imported allotments are user planning assumptions, not verified staffed beds, vacancies or PhilHealth figures."}


def select_reference(runs, start, end=None):
    # Explicit UI dating assumption only, never asserted as reconciled source metadata.
    eligible = [r for r in runs if historical_window(r)[0] <= start < historical_window(r)[1]
                and (end is None or end <= historical_window(r)[1])]
    if not eligible:
        raise HTTPException(422, detail={"code": "HISTORICAL_WINDOW_UNAVAILABLE",
            "message": "The selected dates are outside the saved historical forecast targets. Choose an available historical window; a forecast from another month will not be relabeled.",
            "availableWindows": [{"startDate": historical_window(r)[0].isoformat(), "endDate": historical_window(r)[1].isoformat()} for r in runs]})
    return max(eligible, key=lambda r: (r["issueBlock"]["YR"], r["issueBlock"]["WN"]))


@router.get("/qc-simulation")
def default_workspace():
    return workspace(QCInput())


@router.post("/qc-simulation")
def workspace(params: QCInput):
    try:
        historical_runs = load_environmental_runs()
        run = select_reference(historical_runs, params.startDate, params.endDate)
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
            "historicalWindows": [{"startDate": historical_window(r)[0].isoformat(), "endDate": historical_window(r)[1].isoformat()} for r in historical_runs],
            "forecastEvidence": {key: run[key] for key in ["id", "issueBlock", "model", "environmentalInputs", "observedCasesAtOrigin", "observedSourceYearToDateCases", "intervalCoverageTarget", "intervalCaveat", "spatialCaveat", "availabilityAssumption"]},
            "scope": "QUEZON_CITY", "mapContext": "PHILIPPINES_GEOMETRY_ONLY",
            "referenceSelectionAssumption": "Use only saved forecast target blocks covering the entire selected window, under the explicit Jan-1 52-block assumption. Partial windows preserve their actual source-block offset. Other months are rejected. Original WN dating remains unresolved.",
            "rangeInterpretation": "80% target empirical city forecast residual ranges, conditional on fixed annual barangay shares. Spatial allocation uncertainty and hospital admission/capacity uncertainty are not calibrated.",
            "forecastBacktest": json.loads((FOLDER / "qc-environmental-forecasts.json").read_text())["backtest"]["scores"]}
        final = result["days"][-1]
        result["periodSummary"] = {"expectedCases": final["cumulativeCases"], "caseRange": final["caseRange"],
            "barangays": sorted(final["barangays"], key=lambda b: (-b["cumulativeCases"], b["barangayId"]))}
        result["assumptions"] = "QC-wide historical case + lagged rainfall/temperature/humidity model; fixed prior annual barangay weights. Daily counts are uniformly disaggregated source-block forecasts. Zero initial dengue census, constant assumed non-dengue occupancy, configured admission fraction/delay and fixed LOS; observed source case totals are not observed hospital admissions. No user-selected infection origin or calibrated transmission model. All 46 registered hospitals are hypothetical eligible sites with separately assumed capacity. " + ("Markov first admissions retain demand at each chosen hospital." if params.allocationPolicy == "first_hospital" else "Minimum-distance capacity-constrained LP; holding solved after supported placements." if params.allocationPolicy == "optimized" else "Deterministic nearest-supported-capacity baseline, then finite holding.")
        result["assumptions"] = result["assumptions"].replace("fixed prior annual barangay weights", "fixed XGBoost annual barangay burden forecast shares")
        result["forecastEvidence"]["spatialCaveat"] = "XGBoost annual barangay burden supplies modeled shares and ten high-burden candidates. Annual ranking is evaluated separately; weekly hotspot and spatial-allocation uncertainty are not validated."
        if params.compareAllocation and params.allocationPolicy == "first_hospital":
            result["firstAdmissionComparison"] = compare_first_admissions(model, result)
        elif params.compareAllocation:
            counterpart = create_movie(model.model_copy(update={"allocationPolicy": "optimized" if params.allocationPolicy == "nearest" else "nearest"}))
            def metrics(movie):
                last = movie["days"][-1]
                return {"cumulativeUnresolved": last["cumulativeUnresolved"], "holdingCensus": last["holdingCensus"],
                    "maxNormalOccupancyPct": max(f["normalOccupancyPct"] for d in movie["days"] for f in d["facilities"]),
                    "expectedPatientKm": sum((r["supportedPlacements"] + r["holdingPlacements"]) * r["distanceKm"] for d in movie["days"] for r in d["assignments"])}
            result["allocationComparison"] = {params.allocationPolicy: metrics(result), counterpart["parameters"]["allocationPolicy"]: metrics(counterpart),
                "caveat": "Identical cases, dates, capacity and clinical assumptions; LP maximizes supported placement then minimizes straight-line patient-km. These are modeled comparisons, not demonstrated real-world strain reductions."}
        result["simulationResultSha256"] = core_hash
        result.pop("resultSha256", None)
        result["resultSha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
        return result
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None

def compare_first_admissions(model, movie):
    other_policy = "markov_proximity" if model.arrivalSplitPolicy == "markov_preference" else "markov_preference"
    other = create_movie(model.model_copy(update={"arrivalSplitPolicy": other_policy}))
    return [{"arrivalSplitPolicy": value["parameters"]["arrivalSplitPolicy"],
             "peakBedsShort": value["bedProjection"]["peakHospitalBedsShort"],
             "peakShortageDate": value["bedProjection"]["peakHospitalShortageDate"],
             "peakExpectedBeds": max(d["bedForecast"]["expectedBeds"] for d in value["days"])}
            for value in sorted([movie, other], key=lambda v: v["parameters"]["arrivalSplitPolicy"], reverse=True)]
