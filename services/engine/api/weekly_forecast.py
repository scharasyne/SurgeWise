"""Observation-based QC forecasts from the bundled production release."""
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from production.surgewise import predictor

from ..repositories.weekly_handoff import ARCHIVE_ONLY_NOTE, save_handoff

router = APIRouter(prefix="/v1")


class ForecastFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class CityObservation(ForecastFields):
    year: int
    week: int
    city_cases: float


class LocalObservation(ForecastFields):
    year: int
    week: int
    barangay_code: str
    cases: float


class WeeklyForecastInput(ForecastFields):
    prepare_hospital_simulation: bool = False
    weeks_ahead: int = Field(default=predictor.HORIZON, ge=1, le=predictor.HORIZON)
    city_updates: list[CityObservation] = Field(default_factory=list)
    local_updates: list[LocalObservation] = Field(default_factory=list)
    multiplier: float = 1
    start: int = 1
    duration: int | None = None
    ramp: bool = False


@router.post("/predict")
def weekly_forecast(params: WeeklyForecastInput):
    try:
        # Distinguish unreadable release assets from invalid observation windows.
        predictor.assets()
    except (OSError, ValueError, EOFError, BadZipFile):
        raise HTTPException(503, detail={"code": "FORECAST_MODEL_UNAVAILABLE",
            "message": "Could not load the bundled weekly forecast model and history."}) from None
    try:
        inputs = params.model_dump(exclude={"prepare_hospital_simulation"})
        result = predictor.predict(**inputs)
    except ValueError as error:
        raise HTTPException(400, detail={"code": "INVALID_FORECAST_INPUT", "message": str(error)}) from None
    if params.prepare_hospital_simulation:
        if params.city_updates or params.local_updates:
            return {**result, "hospitalSimulation": {"unavailableReason": ARCHIVE_ONLY_NOTE}}
        try:
            result["hospitalSimulation"] = save_handoff(result, inputs["city_updates"], inputs["local_updates"])
        except (OSError, ValueError):
            raise HTTPException(503, detail={"code": "FORECAST_HANDOFF_UNAVAILABLE",
                "message": "Could not save the weekly forecast for hospital simulation."}) from None
    return result
