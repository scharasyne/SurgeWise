"""Production dengue forecasts and hypothetical surge planning with case-to-bed projections."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from .qc_simulation import QCInput, LIMITS, compare_first_admissions, facility_assumptions, placement_assumption
from .research import unavailable
from .outbreak import OutbreakInput, inputs, create_movie
from ..repositories.production_runs import production_run, evidence, INTERVAL_NOTE

router = APIRouter(prefix="/v1")


def today_qc():
    return datetime.now(timezone(timedelta(hours=8))).date()


class FutureInput(QCInput):
    startDate: date = Field(default_factory=today_qc)
    endDate: date = Field(default_factory=lambda: today_qc() + timedelta(days=28))
    mode: Literal["hypothetical_shock"] = "hypothetical_shock"
    horizonDays: int = Field(default=28, strict=True, ge=1, le=28)
    weatherProfile: Literal["typical"] = "typical"
    surgeEnabled: bool = True
    surgeOnsetDay: int = Field(default=0, strict=True, ge=0, le=27)
    surgeMultiplier: float = Field(default=2, ge=1, le=10)
    growthDays: int = Field(default=7, strict=True, ge=1, le=28)

    @model_validator(mode="before")
    @classmethod
    def set_window(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Future scenario input must be a JSON object.")
        values = dict(value)
        start = values.get("startDate", today_qc())
        if isinstance(start, str):
            start = date.fromisoformat(start)
        horizon = values.get("horizonDays", 28)
        if isinstance(start, date) and type(horizon) is int:
            derived = start + timedelta(days=horizon)
            supplied = values.get("endDate", derived)
            if isinstance(supplied, str):
                supplied = date.fromisoformat(supplied)
            if supplied != derived:
                raise ValueError("End date must equal start plus the selected 1–28-day horizon.")
            values["endDate"] = derived
        return values

    @model_validator(mode="after")
    def validate_future(self):
        if self.startDate < today_qc():
            raise ValueError("Use the historical tab for past dates; future planning starts today or later.")
        if self.extraCasesPerWeek != 0:
            raise ValueError("Future planning uses the explicit surge multiplier, not an additive historical shock.")
        if self.surgeEnabled and self.surgeOnsetDay >= self.horizonDays:
            raise ValueError("Choose a surge onset between day 0 and horizon minus one.")
        return self


@router.get("/future-simulation")
def default_future():
    return future_workspace(FutureInput())


@router.post("/future-simulation")
def future_workspace(params: FutureInput):
    try:
        as_of = today_qc()
        run = production_run(params.startDate, params.horizonDays, planning=True)
        _, geo, _ = inputs(run["id"], params.startDate.year, True)
        model = OutbreakInput(forecastRunId=run["id"], scenarioKind="hypothetical_shock", autoHotspots=True,
            acknowledgeHypotheticalHospitalNetwork=True, acknowledgeHypotheticalDates=True,
            allocationPolicy=params.allocationPolicy, arrivalSplitPolicy=params.arrivalSplitPolicy, surgeEnabled=params.surgeEnabled,
            surgeOnsetDay=params.surgeOnsetDay, surgeMultiplier=params.surgeMultiplier,
            startDate=params.startDate, endDate=params.endDate,
            seedBarangayId=max(geo["barangays"], key=lambda b: b["weight"])["id"],
            extraCasesPerWeek=0, initialRadiusKm=.5, expansionKmPerDay=0,
            growthDays=params.growthDays, shockProfile="ramp", hospitalizationRate=params.hospitalizationRate,
            lengthOfStayDays=params.lengthOfStayDays, baselineOccupancy=params.baselineOccupancy,
            admissionDelayDays=params.admissionDelayDays, surgeActivationDay=params.surgeActivationDay,
            facilities=facility_assumptions(params, geo["hospitals"]))
        movie = create_movie(model)
        final = movie["days"][-1]
        has_added_surge = params.surgeEnabled and params.surgeMultiplier > 1
        result = {**movie, "workspaceTab": "future", "controlValues": params.model_dump(mode="json"),
            "inputLimits": {**LIMITS, "surgeMultiplier": {"min": 1, "max": 10, "units": "times the production baseline"},
                "surgeOnsetDay": {"min": 0, "max": params.horizonDays - 1, "units": "day index"}},
            "scope": "QUEZON_CITY", "mapContext": "PHILIPPINES_GEOMETRY_ONLY",
            "forecastEvidence": evidence(run),
            "futureForecast": {"asOfDate": as_of.isoformat(), "selectedModel": run["model"],
                "trainingCutoffBlock": {"YR": run["trainedThrough"], "WN": 52}, "modelSha256": run["modelSha256"],
                "parameterAudit": {"startDate": params.startDate.isoformat(), "endDateExclusive": params.endDate.isoformat(),
                    "horizonDays": params.horizonDays,
                    "surgeOnsetDate": (params.startDate + timedelta(days=params.surgeOnsetDay)).isoformat() if has_added_surge else None,
                    "fullMultiplierDate": (params.startDate + timedelta(days=params.surgeOnsetDay + params.growthDays - 1)).isoformat() if has_added_surge else None,
                    "fullMultiplierReached": has_added_surge and params.surgeOnsetDay + params.growthDays <= params.horizonDays,
                    "maximumAppliedMultiplier": max(d.get("surgeFactor", 1) for d in movie["days"]),
                    "staffedSurgeActivationSnapshotDate": (params.startDate + timedelta(days=params.surgeActivationDay)).isoformat(),
                    "staffedSurgeActivationWithinWindow": params.surgeActivationDay <= params.horizonDays,
                    "admissionDelayDays": params.admissionDelayDays, "lengthOfStayDays": params.lengthOfStayDays},
                "sourcePeriodStart": run["dailyPredictions"][0]["sourceDate"],
                "sourcePeriodEnd": run["dailyPredictions"][-1]["sourceDate"]},
            "forecastBacktest": [],
            "referenceSelectionAssumption": "Scenario day one uses the first forecast week after the latest QC observations. Changing the planning start moves the hospital timeline. It does not advance the model's observation history.",
            "rangeInterpretation": INTERVAL_NOTE,
            "periodSummary": {"expectedCases": final["cumulativeCases"], "caseRange": None,
                "barangays": sorted(final["barangays"], key=lambda b: (-b["cumulativeCases"], b["barangayId"]))},
            "assumptions": movie["assumptions"] + " " + placement_assumption(params),
            "simulationResultSha256": movie["resultSha256"]}
        if params.compareAllocation:
            result["firstAdmissionComparison"] = compare_first_admissions(model, movie)
        result.pop("resultSha256", None)
        result["resultSha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
        return result
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None
