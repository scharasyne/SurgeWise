from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict
try:
    from .repositories.facility import load_facilities, FacilityDatasetError, DATASET_ID
except ImportError:
    from repositories.facility import load_facilities, FacilityDatasetError, DATASET_ID
from typing import Literal
from services.engine.api.research import router as research_router
from services.engine.api.limits import BodySizeLimit
from services.engine.api.outbreak import router as outbreak_router
from services.engine.api.qc_simulation import router as qc_simulation_router
from services.engine.api.future_simulation import router as future_simulation_router

app = FastAPI(title="SurgeWise Forecast and Simulation API", version="0.1.0")
app.include_router(research_router)
app.include_router(outbreak_router)
app.include_router(qc_simulation_router)
app.include_router(future_simulation_router)
app.add_middleware(BodySizeLimit)

class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    area: Literal["NCR", "QUEZON_CITY"]
    forecast_run_id: str
    surge_multiplier: float = Field(default=1, ge=1, le=3)
    hospitalization_rate: float = Field(default=.15, ge=0, le=1)
    length_of_stay_days: int = Field(default=4, ge=1, le=30)
    baseline_occupancy: float = Field(default=.75, ge=0, le=1)

@app.get("/health")
def health():
    return {"status": "ok", "stage": "foundation"}

@app.post("/simulate")
def simulate(params: SimulationInput):
    raise HTTPException(status_code=503, detail="Requires verified dated case forecasts and facility capacities. No synthetic predictions will be substituted.")


@app.get("/v1/facilities")
def facilities():
    try:
        records = load_facilities()
    except FacilityDatasetError:
        raise HTTPException(status_code=503, detail={"code": "FACILITY_DATASET_UNAVAILABLE", "message": "Approved QC facility dataset failed validation. No legacy fallback."}) from None
    return {"schemaVersion": "1.0", "datasetId": DATASET_ID, "scope": "QUEZON_CITY", "measurementKind": "source_reported", "asOf": "2026-09-30", "units": "beds", "facilities": records}


@app.get("/readiness")
def readiness():
    facilities = []
    try:
        facilities = load_facilities()
        facility_ready = True
    except FacilityDatasetError:
        facility_ready = False
    from services.engine.repositories.forecast_runs import load_runs
    try:
        forecast_ready = bool(load_runs("QUEZON_CITY"))
    except (OSError, ValueError, KeyError, TypeError):
        forecast_ready = False
    from services.engine.repositories.seasonal_runs import approved_model, SeasonalArtifactError
    seasonal = {"ready": True}
    try:
        approved_model()
    except SeasonalArtifactError as error:
        seasonal = {"ready": False, "code": "SEASONAL_ARTIFACTS_UNAVAILABLE", "message": str(error)}
    from services.engine.repositories.barangay_runs import approved_ranking, BarangayRankingUnavailable
    from services.engine.api.future_simulation import today_qc
    ranking = {"ready": True}
    try:
        approved_ranking(today_qc().year)
    except BarangayRankingUnavailable as error:
        ranking = {"ready": False, "code": "BARANGAY_RANKING_UNAVAILABLE", "message": str(error)}
    from services.engine.repositories.synthetic_barangay import approved_runs
    try:
        synthetic = {"ready": True, "origins": len(approved_runs())}
    except ValueError as error:
        synthetic = {"ready": False, "code": "SYNTHETIC_FORECAST_UNAVAILABLE", "message": str(error)}
    from services.engine.repositories import first_admission
    from services.engine.upri_data import ROOT, sha256
    import json
    try:
        geometry = ROOT / first_admission.GEOMETRY_PATH
        identifiers = [{"id": f["properties"]["ADM4_PCODE"]} for f in json.loads(geometry.read_bytes())["features"]]
        first_admission.load_matrix("markov_preference", identifiers, [f["id"] for f in facilities], sha256(geometry))
        preference = {"ready": True}
    except (OSError, ValueError, KeyError, TypeError):
        preference = {"ready": False, "code": "FIRST_ADMISSION_MATRIX_UNAVAILABLE"}
    return {"schemaVersion": "1.0", "defaultWorkspace": "synthetic-barangay-simulation",
        "defaultWorkspaceReady": synthetic["ready"] and facility_ready and preference["ready"],
        "firstAdmissionPreference": preference,
        "syntheticBarangayForecast": synthetic, "ready": False, "historicalSourceBlockReplayReady": forecast_ready and facility_ready,
        "seasonalForecast": seasonal,
        "barangayRanking": ranking,
        "qcWorkspaceReady": forecast_ready and facility_ready and ranking["ready"],
        "futureWorkspaceReady": facility_ready and ranking["ready"] and seasonal["ready"],
        "facilities": {"ready": facility_ready, "datasetId": DATASET_ID},
        "blockers": ["Exact source week/calendar alignment and historical publication delays unresolved; live and calendar-dated forecasting unavailable.",
        "Dengue eligibility and staffed capacity unknown; /v1/scenarios requires explicit hypothetical assumptions.",
        "Annual barangay totals disagree with city weekly totals; weekly spatial splits are modeled allocations only."]}
