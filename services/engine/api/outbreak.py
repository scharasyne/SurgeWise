"""Validated, immutable map movies from approved historical QC reference runs."""
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import platform
import shapely
import pyproj
import scipy
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from .research import StrictModel, FacilityAssumption, forecast, annual_data, unavailable
from ..domain import outbreak, patient_flow, spatial, optimizer, ranked_placement, bed_forecast, hospital_demand, barangay_forecast, source_calendar, seasonal_forecast
from production.surgewise import predictor, features
from ..repositories import seasonal_runs, first_admission, production_runs
from ..repositories.first_admission import AllocationPolicy, ArrivalPolicy, MATRICES
from ..domain.outbreak import make_context, build_movie, VERSION
from ..repositories.facility import load_facilities, DATASET_ID, HOSPITAL_SHA256
from ..repositories.forecast_runs import FOLDER, load_runs, load_environmental_runs
from ..upri_data import ROOT, sha256
from ..repositories.barangay_runs import BarangayRankingUnavailable

router = APIRouter(prefix="/v1")
_CODE_MODULES = [("first_admission", first_admission), ("outbreak", outbreak), ("patient_flow", patient_flow), ("spatial", spatial),
    ("ranked_placement", ranked_placement), ("optimizer", optimizer), ("bed_forecast", bed_forecast), ("hospital_demand", hospital_demand),
    ("barangay_forecast", barangay_forecast), ("source_calendar", source_calendar),
    ("seasonal_forecast", seasonal_forecast), ("seasonal_runs", seasonal_runs), ("production_runs", production_runs),
    ("production_predictor", predictor), ("production_features", features)]
_LOADED_CODE_HASHES = {name: sha256(module.__file__) for name, module in _CODE_MODULES}


@router.get("/outbreak-demo")
def illustrative_movie():
    """Named server-configured hypothetical preset, never a real vacancy network."""
    try:
        runs = load_runs("QUEZON_CITY")
        run = next((r for r in runs if r["issueBlock"] == {"YR": 2025, "WN": 4}), runs[0])
        geo = inputs(run["id"], 2025)[1]
        seed = max(geo["barangays"], key=lambda b: b["weight"])
        return create_movie(OutbreakInput(
            forecastRunId=run["id"], scenarioKind="hypothetical_shock",
            acknowledgeHypotheticalHospitalNetwork=True, acknowledgeHypotheticalDates=True,
            startDate="2025-01-27", endDate="2025-02-24", seedBarangayId=seed["id"],
            extraCasesPerWeek=700, initialRadiusKm=.5, expansionKmPerDay=.35, growthDays=14,
            shockProfile="ramp", hospitalizationRate=.15, lengthOfStayDays=4, baselineOccupancy=.75,
            admissionDelayDays=0, surgeActivationDay=7,
            facilities=[FacilityAssumption(facilityId=h["facilityId"], assumedDengueEligible=True,
                normalCapacity=20, surgeCapacity=10, holdingCapacity=5) for h in seed["nearestHospitals"]]))
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        raise unavailable() from None


class OutbreakInput(StrictModel):
    forecastRunId: str = Field(min_length=1, max_length=120)
    scenarioKind: Literal["hypothetical_shock", "historical_replay"]
    autoHotspots: bool = False
    allocationPolicy: AllocationPolicy = "nearest"
    arrivalSplitPolicy: ArrivalPolicy = "nearest"
    surgeEnabled: bool = False
    surgeOnsetDay: int = Field(default=0, strict=True, ge=0, le=27)
    surgeMultiplier: float = Field(default=1, ge=1, le=10)
    acknowledgeHypotheticalHospitalNetwork: Literal[True]
    acknowledgeHypotheticalDates: Literal[True]
    startDate: date
    endDate: date
    seedBarangayId: str = Field(pattern=r"^PH1307404\d{3}$")
    extraCasesPerWeek: float = Field(ge=0, le=100000)
    initialRadiusKm: float = Field(ge=.1, le=20)
    expansionKmPerDay: float = Field(ge=0, le=5)
    growthDays: int = Field(strict=True, ge=1, le=28)
    shockProfile: Literal["step", "ramp"]
    hospitalizationRate: float = Field(ge=0, le=1)
    lengthOfStayDays: int = Field(strict=True, ge=1, le=30)
    baselineOccupancy: float = Field(ge=0, le=1)
    admissionDelayDays: int = Field(strict=True, ge=0, le=28)
    surgeActivationDay: int = Field(strict=True, ge=0, le=28)
    facilities: list[FacilityAssumption] = Field(min_length=1, max_length=46)

    @model_validator(mode="after")
    def validate_dates(self):
        if not 1 <= (self.endDate - self.startDate).days <= 28:
            raise ValueError("Choose an end date 1–28 elapsed days after onset.")
        if not 2012 <= self.startDate.year <= 2035:
            raise ValueError("Scenario onset must be between 2012 and 2035; future dates remain hypothetical.")
        if self.scenarioKind == "historical_replay" and (self.extraCasesPerWeek != 0 or self.surgeEnabled):
            raise ValueError("Historical reference mode cannot contain a hypothetical added shock.")
        if self.surgeEnabled and self.surgeOnsetDay >= (self.endDate - self.startDate).days:
            raise ValueError("Surge onset must be within the selected future window.")
        if self.allocationPolicy in {"first_hospital", "next_probability"} and self.arrivalSplitPolicy not in MATRICES:
            raise ValueError("First-hospital placement requires Markov destination choice.")
        if self.arrivalSplitPolicy in MATRICES and (not self.autoHotspots or len(self.facilities) != 46):
            raise ValueError("First-admission chains require the full 46-site QC barangay forecast.")
        return self


def inputs(ident, cutoff_year=None, use_xgboost=False):
    run = production_runs.load_production_run(ident) if ident.startswith("qc-rf-") else forecast(ident)
    if run["area"] != "QUEZON_CITY":
        raise HTTPException(422, detail={"code": "QC_DEMAND_REQUIRED", "message": "Spatial movies require QC demand, not NCR totals."})
    manifest = json.loads((FOLDER / "manifest.json").read_text())
    path = ROOT / "apps/web/public/data/qc-barangays.geojson"
    if sha256(path) != manifest["outputs"][path.relative_to(ROOT).as_posix()]:
        raise ValueError("Geometry checksum mismatch")
    hospitals = load_facilities()
    try:
        context = make_context(run, annual_data()["records"], json.loads(path.read_text()), hospitals, cutoff_year, use_xgboost)
    except BarangayRankingUnavailable as error:
        raise HTTPException(503, detail={"code": "BARANGAY_RANKING_UNAVAILABLE", "message": str(error)}) from None
    except ValueError as error:
        if "No complete annual year" in str(error):
            raise HTTPException(422, detail={"code": "ANNUAL_WEIGHTS_UNAVAILABLE", "message": "No complete annual burden year is available before this scenario cutoff. Choose a later hypothetical onset; missing counts cannot be treated as zero."}) from None
        raise
    return run, context, manifest


@router.get("/outbreak-context/{ident}")
def context(ident: str):
    try:
        return inputs(ident)[1]
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None


def approved_matrix(policy, geo, ids, manifest):
    try:
        return first_admission.load_matrix(policy, geo["barangays"], ids, manifest["outputs"][first_admission.GEOMETRY_PATH])
    except (OSError, ValueError) as error:
        raise HTTPException(503, detail={"code": "FIRST_ADMISSION_MATRIX_UNAVAILABLE",
            "message": "The QC first-admission matrix is missing or failed validation. Restore the approved probability table."}) from error


@router.post("/outbreak-scenarios")
def create_movie(params: OutbreakInput):
    try:
        if any(sha256(module.__file__) != _LOADED_CODE_HASHES[name] for name, module in _CODE_MODULES):
            raise HTTPException(503, detail={"code": "ENGINE_RESTART_REQUIRED",
                "message": "Simulation code changed while this worker was running. Restart the engine and reload the forecast; no outdated result was substituted."})
        run, geo, manifest = inputs(params.forecastRunId, params.startDate.year, params.autoHotspots)
        if "scenarioStart" in run and (not params.autoHotspots or params.startDate.isoformat() != run["scenarioStart"]
                or (params.endDate - params.startDate).days != len(run["dailyPredictions"])
                or params.allocationPolicy not in {"first_hospital", "next_probability"} or params.arrivalSplitPolicy not in MATRICES):
            raise HTTPException(422, detail={"code": "FORECAST_WINDOW_MISMATCH",
                "message": "Use this production run with its registered scenario dates and hospital-choice policy."})
        if params.autoHotspots and not run.get("dailyPredictions"):
            first, last = source_calendar.historical_window(run)
            if params.startDate < first or params.endDate > last:
                raise HTTPException(422, detail={"code": "HISTORICAL_WINDOW_UNAVAILABLE",
                    "message": f"This saved forecast covers [{first}, {last}) under the declared calendar assumption. Select dates within its targets."})
        if params.surgeEnabled and not run.get("dailyPredictions"):
            raise HTTPException(422, detail={"code": "SEASONAL_FORECAST_REQUIRED", "message": "Multiplicative future surges require the seasonal future engine."})
        approved = {h["id"] for h in geo["hospitals"]}
        ids = [f.facilityId for f in params.facilities]
        if len(set(ids)) != len(ids) or not set(ids).issubset(approved):
            raise HTTPException(422, detail={"code": "INVALID_FACILITY_SELECTION"})
        if params.seedBarangayId not in {b["id"] for b in geo["barangays"]}:
            raise HTTPException(422, detail={"code": "UNKNOWN_QC_BARANGAY"})
        parameters = params.model_dump(mode="json")
        parameters["facilities"] = sorted(parameters["facilities"], key=lambda f: f["facilityId"])
        identity = {"parameters": parameters, "methodVersion": VERSION, "facilityDatasetId": DATASET_ID,
            "softwareVersions": {"python": platform.python_version(), "shapely": shapely.__version__, "pyproj": pyproj.__version__, "scipy": scipy.__version__},
            "facilitySourceSha256": HOSPITAL_SHA256, "forecastArtifactSha256": run.get("runSha256") if "scenarioStart" in run else sha256(FOLDER / "forecast-runs.json"),
            "environmentalForecastSha256": sha256(FOLDER / "qc-environmental-forecasts.json") if run["model"] == "cases_weather" else None,
            "seasonalModelSha256": run.get("seasonalModelSha256"), "forecastRunSha256": run.get("runSha256"),
            "spatialForecastSha256": geo["hotspotRanking"]["artifactSha256"] if geo.get("hotspotRanking") else None,
            "referenceSourceSha256": run["sourceSha256"], "sourceHashes": manifest["outputs"],
            "codeHashes": dict(_LOADED_CODE_HASHES)}
        shares = proximity_shares = None
        if params.arrivalSplitPolicy in MATRICES:
            shares, favorites = approved_matrix(params.arrivalSplitPolicy, geo, ids, manifest)
            proximity_shares = shares if params.arrivalSplitPolicy == "markov_proximity" else approved_matrix(
                "markov_proximity", geo, ids, manifest)[0]
            identity["firstAdmissionProximitySha256"] = MATRICES["markov_proximity"][1]
            geo["barangays"] = [{**b, "mappedFavoriteHospitalId": favorites[b["id"]]} for b in geo["barangays"]]
            identity["firstAdmissionPreferenceSha256"] = first_admission.PREFERENCE_HASH
            identity["firstAdmissionMatrixSha256"] = MATRICES[params.arrivalSplitPolicy][1]
        ident = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        folder = FOLDER / "scenarios/movies"
        target = folder / (ident + ".json")
        if target.exists():
            return saved_movie(ident)
        config = params.model_dump()
        config["facilities"] = sorted(config["facilities"], key=lambda f: f["facilityId"])
        schema_version = "1.0"
        if shares is not None:
            schema_version = "1.1" if params.allocationPolicy == "first_hospital" else "1.2"
        if params.allocationPolicy == "next_probability":
            schema_version = "1.3"
        result = {"schemaVersion": schema_version, "scenarioId": ident, **identity, **build_movie(run, geo, config, shares),
            "runTimestamp": datetime.now(timezone.utc).isoformat(), "seed": None,
            "randomness": "Deterministic expected values; no stochastic draws", "geography": "QUEZON_CITY",
            "units": {"cases": "expected reported cases per daily interval", "patients": "expected patients", "distance": "km straight line"}}
        if proximity_shares is not None:
            first_admission.add_choice_breakdowns(result["bedProjection"]["placePeaks"], geo, proximity_shares, params.arrivalSplitPolicy)
        result["resultSha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / (uuid4().hex + ".tmp")
        temp.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        try:
            # Exclusive publication of a fully written artifact: concurrent identical
            # requests cannot replace the first run's timestamp or result checksum.
            target.hardlink_to(temp)
        except FileExistsError:
            return saved_movie(ident)
        finally:
            temp.unlink(missing_ok=True)
        return result
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None


@router.get("/outbreak-scenarios/{ident}")
def saved_movie(ident: str):
    if len(ident) != 64 or any(c not in "0123456789abcdef" for c in ident):
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND"})
    path = FOLDER / "scenarios/movies" / (ident + ".json")
    if not path.exists():
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND"})
    try:
        result = json.loads(path.read_text())
        expected = result.pop("resultSha256")
        if hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest() != expected:
            raise ValueError("Saved movie checksum mismatch")
        if not result["parameters"]["forecastRunId"].startswith("qc-rf-") and result["forecastArtifactSha256"] != sha256(FOLDER / "forecast-runs.json"):
            raise ValueError("Forecast version changed")
        if result.get("environmentalForecastSha256") and result["environmentalForecastSha256"] != sha256(FOLDER / "qc-environmental-forecasts.json"):
            raise ValueError("Environmental forecast version changed")
        if result.get("seasonalModelSha256"):
            from ..repositories.seasonal_runs import approved_model, load_seasonal_run
            if approved_model()[1]["modelSha256"] != result["seasonalModelSha256"] or load_seasonal_run(result["parameters"]["forecastRunId"])["runSha256"] != result["forecastRunSha256"]:
                raise ValueError("Seasonal model/forecast version changed")
        # Revalidate all canonical inputs, including polygon and annual table hashes.
        _, current_context, manifest = inputs(result["parameters"]["forecastRunId"], date.fromisoformat(result["parameters"]["startDate"]).year, result["parameters"].get("autoHotspots", False))
        policy = result["parameters"].get("arrivalSplitPolicy")
        if policy in MATRICES:
            approved_matrix(policy, current_context, [h["id"] for h in current_context["hospitals"]], manifest)
            if "firstAdmissionProximitySha256" in result:
                if policy != "markov_proximity":
                    approved_matrix("markov_proximity", current_context, [h["id"] for h in current_context["hospitals"]], manifest)
                if result["firstAdmissionProximitySha256"] != MATRICES["markov_proximity"][1]:
                    raise ValueError("Saved distance-only matrix version mismatch")
            if (result.get("firstAdmissionMatrixSha256") != MATRICES[policy][1]
                    or result.get("firstAdmissionPreferenceSha256") != first_admission.PREFERENCE_HASH):
                raise ValueError("Saved first-admission matrix version mismatch")
        if result.get("spatialForecastSha256") != (current_context["hotspotRanking"]["artifactSha256"] if current_context.get("hotspotRanking") else None):
            raise ValueError("Saved spatial model version mismatch")
        if result["sourceHashes"] != manifest["outputs"] or result["scenarioId"] != ident:
            raise ValueError("Saved movie source version mismatch")
        result["resultSha256"] = expected
        return result
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise unavailable() from None
