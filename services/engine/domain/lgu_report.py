"""LGU briefing and daily register derived from one validated QC simulation."""
import csv
import io
import math
from datetime import date


def display_number(value):
    if value is None:
        return "Unavailable"
    if 0 < value < .01:
        return "<0.01"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def short_date(value):
    return date.fromisoformat(value).strftime("%d %b %Y").lstrip("0")


def availability(value):
    if not math.isfinite(value) or value < 0:
        raise ValueError("Missing or invalid staffed availability")
    status = "Full" if value == 0 else "Low availability" if value <= 10 else "No flag"
    return value, status


def daily_records(movie):
    names = {h["id"]: h["name"] for h in movie["context"]["hospitals"]}
    params = movie["parameters"]
    sites = {f["facilityId"]: f for f in params["facilities"]}
    days = movie["days"][1:]  # Day zero is the initial state, before the first placement.
    if not days or [d["dayIndex"] for d in days] != list(range(1, movie["durationDays"] + 1)):
        raise ValueError("Incomplete daily results")
    for day in days:
        facilities = day["facilities"]
        if len(facilities) != len(sites) or {f["facilityId"] for f in facilities} != sites.keys():
            raise ValueError("Incomplete hospital records")
        for f in facilities:
            ident = f["facilityId"]
            forecast = f["bedForecast"]
            beds, status = availability(f["remainingSupportedCapacity"])
            yield {
                "scenario_id": movie["scenarioId"], "day": day["dayIndex"],
                "interval_start_qc": day["intervalStart"], "snapshot_qc": day["snapshotAt"],
                "hospital_id": ident, "hospital": names[ident],
                "staffed_dengue_capacity": forecast["assumedSupportedDengueCapacity"],
                "activated_extra_dengue_beds": f["activatedSurgeCapacity"],
                "staffed_beds_reserved_for_other_care": f["assumedNonDengueCensus"],
                "expected_first_choice_arrivals": f.get("firstAdmissionsToday"),
                "staffed_beds_needed_before_rerouting": forecast["staffedBedsRequired"],
                "staffed_beds_short_before_rerouting": forecast["additionalStaffedBedsNeeded"],
                "expected_in_staffed_beds": f["supportedCensus"], "remaining_staffed_dengue_beds": beds,
                "availability_flag": status, "dengue_holding_capacity": sites[ident]["holdingCapacity"],
                "expected_in_holding": f["holdingCensus"], "expected_unplaced_today": f.get("unplacedToday"),
            }


def report_summary(movie, records):
    params = movie["parameters"]
    days = movie["days"][1:]
    final = days[-1]
    hospital_rows = {}
    for r in records:
        hospital_rows.setdefault(r["hospital_id"], []).append(r)
    watchlist = []
    for ident, rows in hospital_rows.items():
        flagged = [r for r in rows if r["availability_flag"] != "No flag"]
        if not flagged:
            continue
        full = next((r for r in flagged if r["availability_flag"] == "Full"), None)
        unplaced = [r["expected_unplaced_today"] for r in rows]
        watchlist.append({
            "id": ident, "hospital": rows[0]["hospital"], "status": "Full" if full else "Low availability",
            "firstFlag": flagged[0]["snapshot_qc"][:10], "firstFull": full["snapshot_qc"][:10] if full else None,
            "daysFlagged": len(flagged), "minimumBeds": min(r["remaining_staffed_dengue_beds"] for r in rows),
            "peakShortage": max(r["staffed_beds_short_before_rerouting"] for r in rows),
            "peakHolding": max(r["expected_in_holding"] for r in rows),
            "totalUnplaced": sum(unplaced) if None not in unplaced else None,
        })
    watchlist.sort(key=lambda f: (f["status"] != "Full", f["firstFull"] or f["firstFlag"], f["hospital"]))
    full_count = sum(f["status"] == "Full" for f in watchlist)

    def peak(label, field):
        highest = max(days, key=lambda d: d["bedForecast"][field])
        value = highest["bedForecast"][field]
        return [label, display_number(value), short_date(highest["date"]) if value else "Across the full run"]

    future = bool(movie.get("seasonalModelSha256"))
    shock = "Baseline cases"
    if future and params["surgeEnabled"]:
        shock = (f'{params["surgeMultiplier"]:g}× baseline at peak, starting on day {params["surgeOnsetDay"]}, '
                 f'{params["growthDays"]} days to peak')
    elif params["extraCasesPerWeek"]:
        shock = f'+{params["extraCasesPerWeek"]:g} weekly cases at peak, {params["growthDays"]} days to peak'
    sites = params["facilities"]
    # The first saved day's dengue capacity may already include activated surge.
    first = days[0]["facilities"]
    starting = sum(f["bedForecast"]["assumedSupportedDengueCapacity"] - f["activatedSurgeCapacity"] for f in first)
    normal = sum(f["normalCapacity"] for f in sites)
    choices = {"markov_preference": "Distance and mapped preferred hospital", "markov_proximity": "Distance only",
               "nearest": "Nearest hospital first", "nearest_three_equal": "Equal shares at the three nearest hospitals"}
    policies = {"first_hospital": "Record shortage at the first hospital", "next_probability": "Try the next highest-probability hospital with space",
                "nearest": "Nearest available hospital", "optimized": "Optimized placement"}
    return {
        "scenarioId": movie["scenarioId"], "runTimestamp": movie["runTimestamp"], "forecastRunId": params["forecastRunId"],
        "mode": "Future forecast" if future else "Historical replay",
        "window": f'{short_date(params["startDate"])} – {short_date(params["endDate"])}',
        "days": len(days), "hospitalCount": len(sites), "recordCount": len(records),
        "metrics": [
            ["Projected dengue cases", display_number(final["cumulativeCases"]), "Across the full run"],
            ["Expected demand for admission", display_number(final["cumulativeArrivals"]), "Includes demand that remained unplaced"],
            peak("Peak staffed beds needed", "hospitalBedsRequired"), peak("Peak beds short", "hospitalBedsShort"),
        ],
        "followUp": (f'{len(watchlist)} of {len(sites)} hospitals reached 10 or fewer available beds. '
                     f'{full_count} reached zero.' if watchlist else
                     f'All {len(sites)} hospitals stayed above 10 available staffed dengue beds throughout the run.'),
        "watchlist": watchlist,
        "settings": [
            ["Case scenario", shock],
            ["Admissions", f'{params["hospitalizationRate"] * 100:g}% of cases'],
            ["Admission delay and stay", f'{params["admissionDelayDays"]} days to admission · {params["lengthOfStayDays"]} days in a bed'],
            ["First hospital choice", choices[params["arrivalSplitPolicy"]]],
            ["When a hospital is full", policies[params["allocationPolicy"]]],
            ["Starting dengue census", "Zero patients in staffed beds or holding"],
            ["Initial staffed bed allocation", f'{display_number(starting)} dengue · {display_number(normal - starting)} other care'],
            ["Additional staffed dengue beds", f'{sum(f["surgeCapacity"] for f in sites):,} scheduled on day {params["surgeActivationDay"]}'],
            ["Temporary dengue holding", f'{sum(f["holdingCapacity"] for f in sites):,} spaces across the network'],
        ],
        "note": "These are planning estimates. Staffed capacity and holding spaces are scenario assumptions. Confirm current availability with hospitals before taking action.",
        "definitions": "Full means zero staffed dengue beds remain after placement. Low availability means more than zero and at most 10. Dates refer to the closing snapshot at midnight in Quezon City. Bed need and shortage are rounded at each hospital before rerouting. Holding is the highest daily holding census. Unplaced is total expected demand attributed to the first-choice hospital over the run.",
    }


def report_csv(records):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode("utf-8-sig")
