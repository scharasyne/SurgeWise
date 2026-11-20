"""Weekly GP reconstructions for historical charts and barangay maps."""

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data" / "gp_cases.csv"
DISPLAY_COLUMNS = [
    "year", "week", "barangay_code", "barangay", "source_date_corrected",
    "gp_expected_cases", "gp_rate_q025", "gp_rate_median", "gp_rate_q975", "annual_status",
]


@lru_cache(maxsize=1)
def _tables():
    columns = [c if c != "week" else "source_week" for c in DISPLAY_COLUMNS]
    weekly = pd.read_csv(DATA, usecols=[*columns, "observed_city_week_cases"])
    weekly = weekly.rename(columns={"source_week": "week"})
    unassigned = weekly.barangay_code.eq("UNASSIGNED")
    barangays = weekly.loc[~unassigned, DISPLAY_COLUMNS].sort_values(["year", "week", "barangay_code"])
    city = weekly.loc[unassigned, ["year", "week", "source_date_corrected", "observed_city_week_cases", "gp_expected_cases"]]
    city = city.rename(columns={"gp_expected_cases": "unassigned_expected_cases"}).sort_values(["year", "week"])
    return barangays, city


def gp_history(*, year=None, week=None, barangay_code=None):
    """Get one map week, a year of estimates, or a barangay time series."""
    if year is None and barangay_code is None:
        raise ValueError("Supply a year or barangay_code")
    barangays, city = _tables()
    if year is not None:
        if year not in city.year.values:
            raise ValueError("GP history covers 2012 through 2022")
        barangays = barangays.loc[barangays.year.eq(year)]
        city = city.loc[city.year.eq(year)]
    if week is not None:
        if week not in range(1, 53):
            raise ValueError("week must be between 1 and 52")
        barangays = barangays.loc[barangays.week.eq(week)]
        city = city.loc[city.week.eq(week)]
    if barangay_code is not None:
        barangays = barangays.loc[barangays.barangay_code.eq(barangay_code)]
        if barangays.empty:
            raise ValueError("Unknown barangay_code")
    return {"barangays": barangays.to_dict("records"), "city": city.to_dict("records")}


def city_history():
    """One city record per archived morbidity week, including its corrected date."""
    return _tables()[1].to_dict("records")
