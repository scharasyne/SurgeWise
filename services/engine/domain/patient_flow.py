"""Deterministic 28-day expected-value cohorts with finite supported/holding space.

Fractional expected patients are modeled quantities. No observed occupancy or
clinical eligibility is inferred from accreditation or specialty.
"""
import math


def non_dengue_share(facility, occupancy):
    """Per-hospital non-dengue share when the scenario supplies one, else the scenario-wide share."""
    share = facility.get("baselineOccupancy")
    return occupancy if share is None else share


def simulate_flow(weekly, facilities, admission_rate, los, occupancy, delay=0, activation_day=0, daily_groups=None, assignment_method="nearest", divert_overflow=False, ranked_choice=None):
    if len(weekly) != 4 or any(not math.isfinite(v) or v < 0 for v in weekly):
        raise ValueError("Four finite nonnegative QC forecast blocks required")
    if not facilities or not 0 <= admission_rate <= 1 or not 0 <= occupancy <= 1 or not 1 <= los <= 30 or not 0 <= delay <= 28 or not 0 <= activation_day <= 28:
        raise ValueError("Invalid patient-flow assumptions")
    for f in facilities:
        if any(type(f[k]) is not int or f[k] < 0 for k in ["normalCapacity", "surgeCapacity", "holdingCapacity"]) or f["normalCapacity"] == 0:
            raise ValueError("Explicit finite positive normal capacity required")
        if type(f.get("surgeNonDengueCapacity", 0)) is not int or f.get("surgeNonDengueCapacity", 0) < 0:
            raise ValueError("Invalid extra non-dengue beds")
        share = f.get("baselineOccupancy")
        if share is not None and (not isinstance(share, (int, float)) or not math.isfinite(share) or not 0 <= share <= 1):
            raise ValueError("Invalid per-hospital non-dengue share")
    ids = {f["facilityId"] for f in facilities}
    if len(ids) != len(facilities):
        raise ValueError("Duplicate facility IDs")
    if daily_groups is not None:
        if len(daily_groups) != 28:
            raise ValueError("Exactly 28 daily group arrays required")
        for groups in daily_groups:
            for group in groups:
                order = group["facilityOrder"]
                valid_order = (len(order) == 1 and order[0] in ids if assignment_method in {"first_hospital", "next_probability"}
                               else set(order) == ids and len(order) == len(ids))
                if not math.isfinite(group["cases"]) or group["cases"] < 0 or not valid_order:
                    raise ValueError("Invalid spatial demand or hospital ordering")
    if assignment_method not in {"nearest", "optimized", "first_hospital", "next_probability"} or (assignment_method != "nearest" and daily_groups is None):
        raise ValueError("Invalid assignment method or missing spatial costs")
    if (assignment_method == "next_probability") != (ranked_choice is not None):
        raise ValueError("Ranked overflow requires the originating barangay probabilities")
    states = [{"config": f, "cohorts": [], "holding": 0.0} for f in facilities]
    arrivals_total = discharged_total = unmet_total = 0.0
    days = []
    for day in range(29):
        groups = []
        if day > delay:
            groups = daily_groups[day - delay - 1] if daily_groups is not None else [{
                "originId": None, "cases": weekly[(day - delay - 1) // 7] / 7,
                "facilityOrder": [f["facilityId"] for f in facilities]}]
        arrivals = sum(g["cases"] for g in groups) * admission_rate
        discharged = 0.0
        for s in states:
            discharged += sum(count for exit_day, count in s["cohorts"] if exit_day <= day)
            s["cohorts"] = [(exit_day, count) for exit_day, count in s["cohorts"] if exit_day > day]
            f = s["config"]
            extra = f["surgeCapacity"] if day >= activation_day else 0
            residual = f["normalCapacity"] * (1 - non_dengue_share(f, occupancy)) + extra - sum(c for _, c in s["cohorts"])
            promote = min(s["holding"], max(0, residual))
            s["holding"] -= promote
            if promote:
                s["cohorts"].append((day + los, promote))
        remaining, assignments = 0.0, []
        first_routes = []
        by_id = {s["config"]["facilityId"]: s for s in states}
        local = {ident: {"firstAdmissionsToday": 0.0, "supportedPlacementsToday": 0.0,
                         "holdingPlacementsToday": 0.0, "unplacedToday": 0.0} for ident in ids} if assignment_method == "first_hospital" or divert_overflow else {}
        if ranked_choice is not None:
            first_arrivals = {g["facilityOrder"][0]: g["cases"] * admission_rate for g in groups}
            staffed_capacity = [max(0, s["config"]["normalCapacity"] * (1 - non_dengue_share(s["config"], occupancy))
                + (s["config"]["surgeCapacity"] if day >= activation_day else 0) - sum(c for _, c in s["cohorts"])) for s in states]
            holding_capacity = [max(0, s["config"]["holdingCapacity"] - s["holding"]) for s in states]
            local, actual_origins = ranked_choice.place_day([first_arrivals.get(h, 0.0) for h in ranked_choice.ids],
                                                          staffed_capacity, holding_capacity)
            for h, counts in local.items():
                if counts["supportedPlacementsToday"]:
                    by_id[h]["cohorts"].append((day + los, counts["supportedPlacementsToday"]))
                by_id[h]["holding"] += counts["holdingPlacementsToday"]
                remaining += counts["unplacedToday"]
            groups = []  # Ranked placements have already been applied to the cohorts.
        plans = None
        if (assignment_method == "optimized" or divert_overflow) and groups:
            from .optimizer import daily_plan
            plans = daily_plan(groups, states, admission_rate, occupancy, day, activation_day,
                               overflow_policy=assignment_method if divert_overflow else None)
        # Explicit group order, then caller-supplied approved distance order.
        # This is a nearest-capacity greedy baseline, not an optimizer or referral.
        for group_index, group in enumerate(groups):
            pending = group["cases"] * admission_rate
            routes = {}
            for ident in group["facilityOrder"]:
                if pending <= 0:
                    break
                s = by_id[ident]
                f = s["config"]
                extra = f["surgeCapacity"] if day >= activation_day else 0
                residual = f["normalCapacity"] * (1 - non_dengue_share(f, occupancy)) + extra - sum(c for _, c in s["cohorts"])
                proposed = plans[group_index]["supported"][ident] if plans is not None else pending
                placed = min(pending, max(0, residual), proposed)
                if placed:
                    s["cohorts"].append((day + los, placed))
                    routes[ident] = {"supportedPlacements": placed, "holdingPlacements": 0.0}
                pending -= placed
            for ident in group["facilityOrder"]:
                if pending <= 0:
                    break
                s = by_id[ident]
                proposed = plans[group_index]["holding"][ident] if plans is not None else pending
                held = min(pending, max(0, s["config"]["holdingCapacity"] - s["holding"]), proposed)
                s["holding"] += held
                pending -= held
                if held:
                    routes.setdefault(ident, {"supportedPlacements": 0.0, "holdingPlacements": 0.0})["holdingPlacements"] += held
            remaining += pending
            if local:
                ident = group["facilityOrder"][0]
                local[ident]["firstAdmissionsToday"] += group["cases"] * admission_rate
                for destination, counts in routes.items():
                    local[destination]["supportedPlacementsToday"] += counts["supportedPlacements"]
                    local[destination]["holdingPlacementsToday"] += counts["holdingPlacements"]
                    if divert_overflow:
                        first_routes.append({"firstFacilityId": ident, "facilityId": destination, **counts})
                local[ident]["unplacedToday"] += pending
                continue
            assignments.extend({"barangayId": group["originId"], "facilityId": ident, **counts} for ident, counts in routes.items())
        snapshots = []
        for s in states:
            f = s["config"]
            n, surge = f["normalCapacity"], f["surgeCapacity"] if day >= activation_day else 0
            # Extra non-dengue beds are assumed full of other patients: they add capacity but no dengue room.
            extra_other = f.get("surgeNonDengueCapacity", 0) if day >= activation_day else 0
            share = non_dengue_share(f, occupancy)
            census = sum(c for _, c in s["cohorts"])
            total = n * share + census
            snapshots.append({**local.get(f["facilityId"], {}), "facilityId": f["facilityId"], "normalCapacity": n, "activatedSurgeCapacity": surge,
                "supportedCapacity": n + surge + extra_other, "remainingSupportedCapacity": max(0, n + surge - total),
                "activatedNonDengueSurgeCapacity": extra_other,
                "assumedNonDengueCensus": n * share + extra_other,
                "normalDengueCensus": min(census, n * (1 - share)),
                "surgeDengueCensus": max(0, census - n * (1 - share)), "supportedCensus": census,
                "holdingCensus": s["holding"], "normalOccupancyPct": 100 * total / n,
                "supportedOccupancyPct": 100 * (total + extra_other) / (n + surge + extra_other),
                "onSiteRelativeToNormalPct": 100 * (total + s["holding"]) / n})
        arrivals_total += arrivals
        discharged_total += discharged
        unmet_total += remaining
        inpatient = sum(f["supportedCensus"] for f in snapshots)
        holding = sum(f["holdingCensus"] for f in snapshots)
        error = arrivals_total - discharged_total - unmet_total - inpatient - holding
        if abs(error) > 1e-7:
            raise ValueError("Patient-flow conservation failure")
        days.append({"dayIndex": day, "arrivals": arrivals, "discharges": discharged,
            "cumulativeArrivals": arrivals_total, "cumulativeDischarges": discharged_total,
            "unresolvedToday": remaining, "cumulativeUnresolved": unmet_total,
            "supportedCensus": inpatient, "holdingCensus": holding, "balanceError": error, "facilities": snapshots,
            "assignments": assignments})
        if ranked_choice is not None:
            days[-1]["placementsByOrigin"] = actual_origins
        if divert_overflow:
            days[-1]["firstHospitalRoutes"] = first_routes
    return days
