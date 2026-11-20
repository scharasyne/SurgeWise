from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from services.engine.repositories.production_runs import production_run, ProductionForecastUnavailable
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
from services.engine.api.weekly_forecast import router as weekly_forecast_router

from services.engine.api.lgu_reports import router as report_router

app = FastAPI(title="SurgeWise Forecast and Simulation API", version="0.1.0")
app.include_router(weekly_forecast_router)
app.include_router(research_router)
app.include_router(outbreak_router)
app.include_router(report_router)
app.include_router(qc_simulation_router)
app.include_router(future_simulation_router)
app.add_middleware(BodySizeLimit, route_limits={"/v1/predict": 2 * 1024 * 1024})

@app.exception_handler(ProductionForecastUnavailable)
async def production_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": {"code": "PRODUCTION_FORECAST_UNAVAILABLE", "message": str(error)}})


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
    try:
        load_facilities()
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
    try:
        production = {"ready": True, "model": production_run(today_qc(), 1, planning=True)["model"]}
    except ProductionForecastUnavailable:
        production = {"ready": False, "code": "PRODUCTION_FORECAST_UNAVAILABLE"}
    from services.engine.repositories import gp_runs
    try:
        gp_runs.reconstruction_run(gp_runs.FIRST_DAY, 1)
        gp_runs.holdout_run(gp_runs.RF_START, 1)
        archive = {"ready": True, "firstYear": 2012, "lastYear": 2022}
    except (OSError, ValueError, KeyError, IndexError):
        archive = {"ready": False, "code": "ARCHIVE_REPLAY_UNAVAILABLE"}
    return {"schemaVersion": "1.0", "ready": False, "archiveReplay": archive, "historicalSourceBlockReplayReady": forecast_ready and facility_ready,
        "seasonalForecast": seasonal,
        "barangayRanking": ranking,
        "productionForecast": production,
        "qcWorkspaceReady": archive["ready"] and facility_ready,
        "futureWorkspaceReady": facility_ready and production["ready"],
        "facilities": {"ready": facility_ready, "datasetId": DATASET_ID},
        "blockers": ["Exact source week/calendar alignment and historical publication delays unresolved; live and calendar-dated forecasting unavailable.",
        "Dengue eligibility and staffed capacity unknown; /v1/scenarios requires explicit hypothetical assumptions.",
        "Annual barangay totals disagree with city weekly totals; weekly spatial splits are modeled allocations only."]}
