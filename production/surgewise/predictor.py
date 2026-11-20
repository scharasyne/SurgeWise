"""In-memory prediction with the selected forest and its frozen feature data."""

import json
import math
from functools import lru_cache
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd

from .features import HORIZON, WEEKS, feature_blocks

PACKAGE = Path(__file__).resolve().parent


def load_arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name] for name in archive.files}


@lru_cache(maxsize=1)
def assets():
    """Load read-only release data once per worker process."""
    metadata = json.loads((PACKAGE / "models/model.json").read_text())
    forest = load_arrays(PACKAGE / "models/forest.npz")
    history = load_arrays(PACKAGE / "data/history.npz")
    places = pd.read_csv(PACKAGE / "data/barangays.csv")
    return metadata, forest, history, places


def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a number")
    try:
        valid = math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be finite and at least {minimum}")
    return float(value)


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an integer")
    return int(value)


def observations(rows, label, first_year):
    """Index observations on the model's 52-week morbidity calendar."""
    if not isinstance(rows, (list, tuple)):
        raise ValueError(f"{label} must be a list of observations")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Each {label} observation must be an object")
        year = integer(row.get("year"), "year")
        week = integer(row.get("week"), "week")
        if not first_year <= year <= 9999 or not 1 <= week <= WEEKS:
            raise ValueError(f"Supply a morbidity week 1–52 in year {first_year} or later")
        yield year * WEEKS + week - 1, row


def calendar_week(index):
    year, offset = divmod(index, WEEKS)
    return {"year": year, "week": offset + 1}


def request_history(snapshot, codes, first_year, city_updates, local_updates):
    """Join updates to the snapshot, or use a complete recent lag window."""
    first_update = first_year * WEEKS
    totals = {}
    for index, row in observations(city_updates, "city_updates", first_year):
        if index in totals:
            raise ValueError("Duplicate year and week in city_updates")
        totals[index] = number(row.get("city_cases"), "city_cases")
    indices = sorted(totals)
    start = indices[0] if indices else first_update
    if indices and indices[-1] - start + 1 != len(indices):
        raise ValueError("City updates must cover consecutive morbidity weeks")
    if start != first_update and len(indices) < WEEKS + 1:
        raise ValueError("Supply the latest 53 consecutive city weeks for the model's 52-week lag, "
                         "or supply all updates starting at 2023 week 1")

    city = np.array([totals[i] for i in indices], dtype=float)
    local = np.full((len(indices), len(codes)), np.nan)
    positions = {code: index for index, code in enumerate(codes)}
    for index, row in observations(local_updates, "local_updates", first_year):
        if index not in totals:
            raise ValueError("Each local update must match a supplied city week")
        code = row.get("barangay_code")
        if not isinstance(code, str) or code not in positions:
            raise ValueError("Unknown barangay_code in local_updates")
        position = positions[code]
        if np.isfinite(local[index - start, position]):
            raise ValueError(f"Duplicate local observation for {code} in the same week")
        local[index - start, position] = number(row.get("cases"), "cases")

    if start == first_update:
        city = np.concatenate([snapshot["city"], city])
        local = np.vstack([snapshot["local"], local])
        start -= len(snapshot["city"])
    return city, local, start


def forest_predict(forest, matrix):
    """Follow each fitted tree to its leaf, then average the leaf predictions."""
    result = np.zeros(len(matrix))
    for root in forest["roots"]:
        nodes = np.full(len(matrix), root)
        while True:
            rows = np.flatnonzero(forest["children_left"][nodes] != -1)
            if not len(rows):
                break
            active = nodes[rows]
            values = matrix[rows, forest["feature"][active]]
            left = np.where(
                np.isnan(values), forest["missing_go_to_left"][active],
                values <= forest["threshold"][active],
            )
            nodes[rows] = np.where(left, forest["children_left"][active], forest["children_right"][active])
        result += forest["value"][nodes]
    return np.maximum(result / len(forest["roots"]), 0)


def predict(*, weeks_ahead=HORIZON, city_updates=(), local_updates=(),
            multiplier=1.0, start=1, duration=None, ramp=False):
    """Forecast horizons 1 through weeks_ahead after the last observed week."""
    weeks_ahead = integer(weeks_ahead, "weeks_ahead")
    if not 1 <= weeks_ahead <= HORIZON:
        raise ValueError(f"weeks_ahead must be between 1 and {HORIZON}")
    multiplier = number(multiplier, "multiplier", minimum=1)
    start = integer(start, "start")
    duration = weeks_ahead - start + 1 if duration is None else integer(duration, "duration")
    if not 1 <= start <= weeks_ahead or not 1 <= duration <= weeks_ahead - start + 1:
        raise ValueError("The scenario must fit within the requested forecast window")
    if not isinstance(ramp, bool):
        raise ValueError("ramp must be true or false")

    metadata, forest, snapshot, places = assets()
    city, local, first_index = request_history(
        snapshot, places.barangay_code, metadata["forecast_year"], city_updates, local_updates
    )
    origin = len(city) - 1

    def local_at(index):
        observed = local[index]
        estimate = city[index] * snapshot["shares"][(first_index + index) % WEEKS]
        return np.where(np.isfinite(observed), observed, estimate)

    annual = {name: snapshot[name] for name in metadata["annual_features"]}
    recent = np.stack([local_at(origin - lag) for lag in range(12)])
    features, _, _ = feature_blocks(
        origin, city, recent, local_at(origin - WEEKS), annual, snapshot["weights"],
        snapshot["past"], snapshot["shares"], weeks_ahead=weeks_ahead, first_week_offset=first_index % WEEKS,
    )
    matrix = features[metadata["columns"]].to_numpy()
    if np.isinf(matrix).any():
        raise ValueError("Observation counts exceed the model's numeric range")
    counts = forest_predict(forest, matrix).reshape(weeks_ahead, len(places))

    barangays, city_totals = [], []
    for horizon, row in enumerate(counts, start=1):
        factor = 1.0
        elapsed = horizon - start + 1
        if 1 <= elapsed <= duration:
            factor += (multiplier - 1) * (elapsed / duration if ramp else 1)
        total = float(row.sum())
        if not math.isfinite(total * factor):
            raise ValueError("Scenario total exceeds the numeric range")
        period = dict(calendar_week(first_index + origin + horizon), horizon=horizon, scenario_multiplier=factor)
        city_totals.append(dict(period, expected_cases=total, scenario_expected_cases=total * factor))
        for place, count in zip(places.itertuples(index=False), row.tolist()):
            barangays.append(dict(
                period, barangay_code=place.barangay_code, barangay=place.barangay,
                expected_cases=count, scenario_expected_cases=count * factor,
            ))
    return dict(
        model=metadata["model"], trained_through=metadata["trained_through"],
        as_of=calendar_week(first_index + origin), weeks_ahead=weeks_ahead,
        feature_history_through=metadata["forecast_year"] - 1,
        city=city_totals, barangays=barangays,
    )
