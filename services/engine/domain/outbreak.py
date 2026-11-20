"""Hypothetical spatial expansion, distances and dates, separate from observations."""
from datetime import datetime, timedelta, timezone
import math

from pyproj import Transformer
from shapely import transform
from shapely.geometry import Point, shape

from .patient_flow import simulate_flow
from .spatial import annual_weights
from .bed_forecast import add_bed_forecasts
from .hospital_demand import hospital_shares
from .source_calendar import align_historical_run, day_schedule

VERSION = "qc-first-admission-bed-allocation-v4"


def expansion_ring(center, radius_km):
    lon, lat = map(math.radians, center)
    angular = radius_km / 6371.0088
    points = []
    for i in range(73):
        bearing = 2 * math.pi * i / 72
        y = math.asin(math.sin(lat) * math.cos(angular) + math.cos(lat) * math.sin(angular) * math.cos(bearing))
        x = lon + math.atan2(math.sin(bearing) * math.sin(angular) * math.cos(lat), math.cos(angular) - math.sin(lat) * math.sin(y))
        points.append([math.degrees(x), math.degrees(y)])
    return points


def distance_km(a, b):
    """Haversine between [longitude, latitude] representative/provisional points."""
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    term = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, term))))


def make_context(run, annual, geojson, hospitals, cutoff_year=None, use_xgboost=False):
    records = {r["ADM4_PCODE"]: r for r in annual}
    places = run.get("weeklyByBarangay")
    if places is None:
        year, weights = annual_weights(annual, min(run.get("spatialWeightsIssueYear", run["issueBlock"]["YR"]), cutoff_year or 9999))
        weight_map = dict(weights)
    else:
        if not places.keys() <= records.keys():
            raise ValueError("Synthetic forecast contains unknown QC barangays")
        year = None
        total = sum(sum(values) for values in places.values())
        weight_map = {ident: sum(values) / total if total else 0 for ident, values in places.items()}
    ranking = None
    predicted = {}
    if use_xgboost and places is None:
        from ..repositories.barangay_runs import approved_ranking
        issue_year = min(run.get("spatialWeightsIssueYear", run["issueBlock"]["YR"]), cutoff_year or 9999)
        ranked_run, ranking = approved_ranking(issue_year)
        predicted = {r["barangayId"]: r for r in ranked_run["records"]}
        if set(predicted) != set(records):
            raise ValueError("Annual XGBoost ranking/geometry coverage mismatch")
        year = ranked_run["featureCutoffYear"]
        weight_map = {ident: row["weight"] for ident, row in predicted.items()}
        ranking = {**ranking, "candidateIds": ranked_run["topCandidateIds"]}
    to_utm = Transformer.from_crs(4326, 32651, always_xy=True).transform
    to_wgs = Transformer.from_crs(32651, 4326, always_xy=True).transform
    features = geojson["features"]
    if len(features) != 142 or {f["properties"]["ADM4_PCODE"] for f in features} != set(records):
        raise ValueError("Incomplete QC geometry join")
    barangays = []
    hospital_points = {h["id"]: Point(h["longitude"], h["latitude"]) for h in hospitals}
    for feature in features:
        if places is not None and feature["properties"]["ADM4_PCODE"] not in places:
            continue
        geometry = shape(feature["geometry"])
        if not geometry.is_valid or geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Invalid source polygon")
        # A point-on-surface in local projected CRS, never an invented facility point.
        point = transform(transform(geometry, to_utm, interleaved=False).representative_point(), to_wgs, interleaved=False)
        coordinates = [point.x, point.y]
        ident = feature["properties"]["ADM4_PCODE"]
        nearest = sorted([{"facilityId": h["id"], "distanceKm": distance_km(coordinates, [h["longitude"], h["latitude"]])}
                          for h in hospitals], key=lambda r: (r["distanceKm"], r["facilityId"]))
        barangays.append({"id": ident, "name": records[ident]["Barangay"], "coordinates": coordinates,
            "sourceADM4_PCODE": feature["properties"].get("sourceADM4_PCODE"), "weight": weight_map[ident],
            "observedAnnualCases": records[ident][f"DC_{year}"] if year is not None else None,
            "predictedAnnualCases": predicted.get(ident, {}).get("predictedAnnualCases"),
            "burdenRank": predicted.get(ident, {}).get("burdenRank"),
            "isHighBurdenCandidate": predicted.get(ident, {}).get("isHighBurdenCandidate", False),
            "nearestHospitals": nearest[:3],
            "hospitalsWithinBarangay": [entry for entry in nearest if geometry.covers(hospital_points[entry["facilityId"]])]})
    return {"schemaVersion": "1.2", "referenceForecastRunId": run["id"], "weightYear": year,
        **({"missingBarangays": [{"id": ident, "name": records[ident]["Barangay"]} for ident in sorted(records.keys() - places.keys())]} if places is not None else {}), "hotspotRanking": ranking,
        "barangays": sorted(barangays, key=lambda b: b["id"]),
        "hospitals": [{"id": h["id"], "name": h["name"], "coordinates": [h["longitude"], h["latitude"]],
            "coordinateStatus": h["coordinateStatus"], "sourceAsOf": h["sourceAsOf"], "coordinateSourceUrl": h["coordinateSourceUrl"],
            "primarySourceUrl": h["primarySourceUrl"],
            "accreditedBeds": h["accreditedBeds"], "normalStaffedCapacity": None, "dengueUsableBeds": None,
            "dengueInpatientEligible": None} for h in hospitals],
        "distanceMethod": "Haversine km from projected polygon point-on-surface to provisional hospital point; not road distance, travel time or verified entrance."}


def spatial_trajectory(run, context, seed_id, extra_weekly, radius_start, radius_speed, growth_days, duration, profile="ramp"):
    if any(not math.isfinite(v) for v in [extra_weekly, radius_start, radius_speed, growth_days, duration]) or not 1 <= duration <= 28 or extra_weekly < 0 or radius_start <= 0 or radius_speed < 0 or growth_days < 1:
        raise ValueError("Invalid expansion assumptions")
    weights = [b["weight"] for b in context["barangays"]]
    reference = [p["meanCases"] for p in run["weeklyPredictions"]]
    if len(reference) != 4 or any(not math.isfinite(v) or v < 0 for v in [*weights, *reference]) or not math.isclose(sum(weights), 1, abs_tol=1e-9):
        raise ValueError("Invalid historical reference or spatial weights")
    seed = next((b for b in context["barangays"] if b["id"] == seed_id), None)
    if seed is None:
        raise ValueError("Unknown QC seed barangay")
    distances = {b["id"]: distance_km(seed["coordinates"], b["coordinates"]) for b in context["barangays"]}
    days = []
    for day in range(1, 29):
        baseline = run["weeklyPredictions"][(day - 1) // 7]["meanCases"] / 7 if day <= duration else 0.0
        factor = 1.0 if profile == "step" else min(1.0, day / growth_days)
        shock = extra_weekly / 7 * factor if day <= duration else 0.0
        radius = radius_start + radius_speed * (day - 1)
        kernel = {b["id"]: math.exp(-.5 * (distances[b["id"]] / radius)**2)
                  if distances[b["id"]] <= radius else 0.0 for b in context["barangays"]}
        normalizer = sum(kernel.values())
        rows = [{"barangayId": b["id"], "baselineCases": baseline * b["weight"],
                 "shockCases": shock * kernel[b["id"]] / normalizer} for b in context["barangays"]]
        for row in rows:
            row["expectedCases"] = row["baselineCases"] + row["shockCases"]
        days.append({"dayIndex": day, "baselineCases": baseline, "shockCases": shock, "expectedCases": baseline + shock,
            "assumedRadiusKm": radius, "barangays": rows})
    return days


def allocated_forecast_trajectory(run, context, config, duration):
    """Each place receives its own dated forecast allocation, without neighbor events.

    Weekly/daily forecasts are QC-wide. Spatial shares can be estimated by an
    annual barangay model; resulting weekly paths remain modeled allocations.
    """
    if any(not math.isfinite(b["weight"]) or b["weight"] < 0 for b in context["barangays"]) or not math.isclose(sum(b["weight"] for b in context["barangays"]), 1, abs_tol=1e-9):
        raise ValueError("Spatial forecast shares must sum to one")
    days = []
    for i in range(28):
        baseline = (run["dailyPredictions"][i]["meanCases"] if run.get("dailyPredictions")
                    else run["weeklyPredictions"][i // 7]["meanCases"] / 7) if i < duration else 0.0
        factor = 1.0
        if config.get("surgeEnabled") and i >= config.get("surgeOnsetDay", 0):
            factor += (config["surgeMultiplier"] - 1) * min(1.0, (i - config["surgeOnsetDay"] + 1) / config["growthDays"])
        additive = config["extraCasesPerWeek"] / 7 * (1.0 if config["shockProfile"] == "step"
                    else min(1.0, (i + 1) / config["growthDays"])) if i < duration else 0.0
        shock = baseline * (factor - 1) + additive
        rows = [{"barangayId": b["id"], "baselineCases": baseline * b["weight"],
                 "shockCases": shock * b["weight"], "expectedCases": (baseline + shock) * b["weight"]}
                for b in context["barangays"]]
        if any(not math.isfinite(b["expectedCases"]) or b["expectedCases"] < 0 for b in rows):
            raise ValueError("Invalid per-place forecast allocation")
        days.append({"dayIndex": i + 1, "baselineCases": baseline, "shockCases": shock,
                     "expectedCases": baseline + shock, "surgeFactor": factor, "assumedRadiusKm": 0.0, "barangays": rows})
    return days


def synthetic_trajectory(run, config, duration):
    """Slice each saved local horizon by its source block's actual day count."""
    places = run["weeklyByBarangay"]
    origin = run["issueBlock"]["YR"] * 52 + run["issueBlock"]["WN"] - 1
    days = []
    schedule = day_schedule(config["startDate"], duration)
    for i in range(28):
        horizon = None
        local = dict.fromkeys(places, 0.0)
        shock = 0.0
        if i < duration:
            _, block, divisor = schedule[i]
            horizon = block - origin - 1
            if horizon not in range(4):
                raise ValueError("Date outside the four saved forecast horizons")
            local = {code: values[horizon] / divisor for code, values in places.items()}
            rise = 1 if config["shockProfile"] == "step" else min(1, (i + 1) / config["growthDays"])
            shock = config["extraCasesPerWeek"] * rise / 7
        total = math.fsum(local.values())
        if shock and not total:
            raise ValueError("Cannot apportion an added shock with zero covered demand")
        rows = []
        for code, value in local.items():
            extra = shock * value / total if shock else 0.0
            rows.append({"barangayId": code, "baselineCases": value, "shockCases": extra, "expectedCases": value + extra})
        days.append({"dayIndex": i + 1, "baselineCases": total, "shockCases": shock, "expectedCases": total + shock,
                     "forecastHorizon": horizon + 1 if horizon is not None else None,
                     "surgeFactor": 1.0, "assumedRadiusKm": 0.0, "barangays": rows})
    return days


def first_destination_mix(origin_demand, shares, eligible):
    """Return each hospital's share of demand and the origins of its arrivals."""
    contributions = {h: {} for h in eligible}
    for origin, options in shares.items():
        for h, probability in options:
            contributions[h][origin] = origin_demand[origin] * probability
    total = math.fsum(origin_demand.values())
    volumes = {h: math.fsum(parts.values()) for h, parts in contributions.items()}
    fractions = {h: volume / total if total else 0.0 for h, volume in volumes.items()}
    origins = {h: {b: v / volumes[h] for b, v in parts.items() if v > 0} for h, parts in contributions.items()}
    return fractions, origins


def build_movie(run, context, config, first_admission_shares=None):
    duration = (config["endDate"] - config["startDate"]).days
    synthetic = "weeklyByBarangay" in run
    if synthetic:
        days = synthetic_trajectory(run, config, duration)
        totals = {code: 0.0 for code in run["weeklyByBarangay"]}
        for day in days[:duration]:
            for row in day["barangays"]:
                totals[row["barangayId"]] += row["expectedCases"]
        progression_method = "synthetic_weekly_barangay_random_forest"
        assumptions = ("RandomForest synthetic weekly barangay forecasts are divided evenly across source-block days. "
                       "QC demand sums covered barangays. Added shocks use each day's relative forecast burden. ")
        window_ranks = [code for code in sorted(totals, key=lambda k: (-totals[k], k))[:10] if totals[code] > 0]
    elif config.get("autoHotspots"):
        if not run.get("dailyPredictions"):
            run = align_historical_run(run, config["startDate"], duration)
        days = allocated_forecast_trajectory(run, context, config, duration)
        progression_method = ("dated_QC_forecast_allocated_by_xgboost_annual_burden_shares" if context.get("hotspotRanking")
                              else "dated_QC_forecast_allocated_by_prior_annual_barangay_shares")
        assumptions = ("Each barangay progresses directly from its dated QC forecast allocation using prior annual spatial shares. "
                       "No geographic seed, expansion radius, neighbor activation or contagion chain affects forecast demand. "
                       "These are modeled barangay allocations, not separately trained local forecasts. "
                       "Configured citywide shocks are separate assumptions. ")
    else:
        days = spatial_trajectory(run, context, config["seedBarangayId"], config["extraCasesPerWeek"],
                                  config["initialRadiusKm"], config["expansionKmPerDay"], config["growthDays"],
                                  duration, config["shockProfile"])
        progression_method = "explicit_hypothetical_radial_shock"
        assumptions = ("Historical reference blocks mapped onto hypothetical dates; annual weights use only complete years before "
                       "the reference/scenario cutoff with one extra full-year lag. Additive shock uses an explicit hypothetical radial "
                       "kernel; radius speed and case ramp are user assumptions, not inferred transmission. ")
    hospital_map = {h["id"]: h for h in context["hospitals"]}
    eligible = {f["facilityId"] for f in config["facilities"]}
    barangay_map = {b["id"]: b for b in context["barangays"]}
    split_policy = config.get("arrivalSplitPolicy", "nearest")
    policy = config.get("allocationPolicy", "nearest")
    if policy == "first_hospital":
        if first_admission_shares is None or not config.get("autoHotspots"):
            raise ValueError("First-hospital placement needs validated QC choices and automatic barangay demand")
        shares = first_admission_shares
        if synthetic:
            mixes = {h: first_destination_mix({b: v[h - 1] for b, v in run["weeklyByBarangay"].items()}, shares, eligible)
                     for h in range(1, 5)}
            daily_fractions = [mixes[d["forecastHorizon"]][0] if d["forecastHorizon"] else {} for d in days]
            context = {**context, "firstAdmissionOriginSharesByHorizon": {str(h): mix[1] for h, mix in mixes.items()}}
        else:
            fractions, origins = first_destination_mix({b: row["weight"] for b, row in barangay_map.items()}, shares, eligible)
            daily_fractions = [fractions] * len(days)
            context = {**context, "firstAdmissionOriginShares": origins}
        groups = [[{"originId": None, "cases": d["expectedCases"] * split[h], "facilityOrder": [h]}
                   for h in sorted(split)] for d, split in zip(days, daily_fractions, strict=True)]
    else:
        orders = {b["id"]: sorted(eligible, key=lambda h: (distance_km(b["coordinates"], hospital_map[h]["coordinates"]), h))
                  for b in context["barangays"]}
        shares = {b: hospital_shares(order, split_policy) for b, order in orders.items()}
        groups = [[{"originId": b["barangayId"], "cases": b["expectedCases"] * share,
                    "facilityOrder": [ident, *[h for h in orders[b["barangayId"]] if h != ident]]}
                   for b in d["barangays"] for ident, share in shares[b["barangayId"]]] for d in days]
    if policy == "optimized":
        groups = [[{"originId": b["barangayId"], "cases": b["expectedCases"], "facilityOrder": orders[b["barangayId"]]}
                   for b in d["barangays"]] for d in days]
        for groups_for_day in groups:
            for group in groups_for_day:
                group["facilityCostsKm"] = {ident: distance_km(barangay_map[group["originId"]]["coordinates"], hospital_map[ident]["coordinates"]) for ident in eligible}
    flow = simulate_flow([p["meanCases"] for p in run["weeklyPredictions"]], config["facilities"],
        config["hospitalizationRate"], config["lengthOfStayDays"], config["baselineOccupancy"],
        config["admissionDelayDays"], config["surgeActivationDay"], daily_groups=groups, assignment_method=config.get("allocationPolicy", "nearest"))
    cumulative = {b["id"]: 0.0 for b in context["barangays"]}
    cumulative_shock = {b["id"]: 0.0 for b in context["barangays"]}
    baseline_total = shock_total = 0.0
    zone = timezone(timedelta(hours=8))
    onset = datetime.combine(config["startDate"], datetime.min.time(), zone)
    for d in flow[:duration + 1]:
        index = d["dayIndex"]
        if synthetic and policy == "first_hospital":
            source_index = index - config["admissionDelayDays"] - 1
            d["arrivalForecastHorizon"] = days[source_index]["forecastHorizon"] if source_index >= 0 else None
        start, end = onset + timedelta(days=max(0, index - 1)), onset + timedelta(days=index)
        if index:
            source = days[index - 1]
            rows = source["barangays"]
            baseline_total += source["baselineCases"]
            shock_total += source["shockCases"]
            for b in rows:
                cumulative[b["barangayId"]] += b["expectedCases"]
                cumulative_shock[b["barangayId"]] += b["shockCases"]
                b["cumulativeCases"] = cumulative[b["barangayId"]]
            d.update({k: v for k, v in source.items() if k != "dayIndex"})
        else:
            d.update({"expectedCases": 0.0, "baselineCases": 0.0, "shockCases": 0.0, "assumedRadiusKm": 0.0,
                "barangays": [{"barangayId": b["id"], "expectedCases": 0.0, "baselineCases": 0.0, "shockCases": 0.0, "cumulativeCases": 0.0} for b in context["barangays"]]})
        d.update({"date": end.date().isoformat(), "snapshotAt": end.isoformat(),
            "intervalStart": start.isoformat(), "intervalEnd": end.isoformat(),
            "cumulativeCases": baseline_total + shock_total, "cumulativeBaselineCases": baseline_total, "cumulativeShockCases": shock_total})
        seed = barangay_map[config["seedBarangayId"]]
        d["expansionRing"] = expansion_ring(seed["coordinates"], d["assumedRadiusKm"]) if index and config["extraCasesPerWeek"] > 0 and not config.get("autoHotspots") else []
        ranking_field = "cumulativeCases" if config.get("autoHotspots") else "expectedCases"
        d["hotspotIds"] = [b["barangayId"] for b in sorted(d["barangays"], key=lambda b: (-b[ranking_field], b["barangayId"]))[:10] if b[ranking_field] > 0]
        if synthetic and index:
            d["hotspotIds"] = window_ranks
        elif config.get("autoHotspots") and context.get("hotspotRanking") and index:
            d["hotspotIds"] = context["hotspotRanking"]["candidateIds"]
        for facility in d["facilities"]:
            candidates = [{"barangayId": ident, "distanceKm": distance_km(
                hospital_map[facility["facilityId"]]["coordinates"], barangay_map[ident]["coordinates"])}
                for ident in d["hotspotIds"]]
            facility["nearestHotspot"] = min(candidates, key=lambda row: (row["distanceKm"], row["barangayId"])) if candidates else None
        if run.get("calibrationResidualPaths"):
            d["caseRange"] = period_case_range(run, index, d["cumulativeShockCases"])
            if run.get("dailyPredictions") and index:
                # Fixed hypothetical surge scales the baseline error path too.
                factors = [d0.get("surgeFactor", 1.0) for d0 in days[:index]]
                errors = sorted(abs(sum(e * f for e, f in zip(p["errors"][:index], factors))) for p in run["dailyResidualPaths"])
                radius = errors[min(len(errors), math.ceil((len(errors) + 1) * .8)) - 1]
                d["caseRange"].update({"lowerCases": max(0, d["cumulativeCases"] - radius), "upperCases": d["cumulativeCases"] + radius})
            h = max(0, (index - 1) // 7)
            p = run["weeklyPredictions"][h]
            d["dailyCaseRange"] = {"lowerCases": (p["lowerCases"] / 7 + d["shockCases"]) if index else 0.0,
                "upperCases": (p["upperCases"] / 7 + d["shockCases"]) if index else 0.0}
            if run.get("dailyPredictions") and index:
                row = run["dailyPredictions"][index - 1]
                factor = days[index - 1].get("surgeFactor", 1.0)
                additive = max(0, d["shockCases"] - d["baselineCases"] * (factor - 1))
                d["dailyCaseRange"] = {"lowerCases": row["lowerCases"] * factor + additive, "upperCases": row["upperCases"] * factor + additive}
            for b in d["barangays"]:
                weight = barangay_map[b["barangayId"]]["weight"]
                b["caseRange"] = {k: (v - d["cumulativeShockCases"]) * weight + cumulative_shock[b["barangayId"]]
                    for k, v in d["caseRange"].items() if k in {"lowerCases", "upperCases"}}
                b["caseRange"] = {k: max(0.0, v) for k, v in b["caseRange"].items()}
        merged_routes = {}
        for route in d["assignments"]:
            key = (route["barangayId"], route["facilityId"])
            merged = merged_routes.setdefault(key, {"barangayId": key[0], "facilityId": key[1], "supportedPlacements": 0.0, "holdingPlacements": 0.0})
            merged["supportedPlacements"] += route["supportedPlacements"]
            merged["holdingPlacements"] += route["holdingPlacements"]
        d["assignments"] = list(merged_routes.values())
        for route in d["assignments"]:
            route["distanceKm"] = distance_km(barangay_map[route["barangayId"]]["coordinates"], hospital_map[route["facilityId"]]["coordinates"])
    bed_projection = add_bed_forecasts(flow[:duration + 1], days, run, context, config, shares)
    encoding = "origin_hospital_routes"
    if first_admission_shares is not None:
        encoding = "hospital_totals_with_horizon_origin_shares" if synthetic else "hospital_totals_with_origin_shares"
    return {"assignmentEncoding": encoding,
        "days": flow[:duration + 1], "context": context, "durationDays": duration, "bedProjection": bed_projection,
        "progressionMethod": progression_method,
        "mapScaleMaxDailyCases": max(b["expectedCases"] for d in days[:duration] for b in d["barangays"]),
        "measurementKind": "forecast" if synthetic else "modeled_allocation", "capacityMeasurementKind": "assumption",
        "calendarStatus": "JAN_1_SOURCE_BLOCK_ASSUMPTION" if synthetic else "USER_SELECTED_HYPOTHETICAL_DATES_NOT_SOURCE_WEEK_ALIGNMENT",
        "assumptions": assumptions + "Zero initial dengue census, fixed LOS and occupancy; supported placements, finite holding and unresolved demand are separate from case forecasts.",
        "disclaimer": "Hypothetical spread and hospital-demand planning movie. No observed daily/weekly barangay spread, clinical eligibility, hospital vacancy or road-route claim. All hospital points are provisional; 2026 inventory is a hypothetical planning network."}


def period_case_range(run, elapsed_days, assumed_extra_cases=0):
    """Joint-horizon errors from complete past paths, preserving temporal covariance."""
    fractions = [min(7, max(0, elapsed_days - 7 * h)) / 7 for h in range(4)]
    errors = sorted(abs(sum(p["errors"][:elapsed_days])) for p in run["dailyResidualPaths"]) if run.get("dailyResidualPaths") else sorted(abs(sum(v * f for v, f in zip(p["residuals"], fractions))) for p in run["calibrationResidualPaths"])
    if len(errors) < 20:
        raise ValueError("Insufficient pre-origin range evidence")
    rank = min(len(errors), math.ceil((len(errors) + 1) * .8))
    radius = errors[rank - 1]
    reference = sum(d["meanCases"] for d in run["dailyPredictions"][:elapsed_days]) if run.get("dailyPredictions") else sum(p["meanCases"] * f for p, f in zip(run["weeklyPredictions"], fractions))
    return {"lowerCases": max(0, reference - radius) + assumed_extra_cases,
        "upperCases": reference + radius + assumed_extra_cases, "coverageTarget": .8,
        "calibrationSamples": len(errors), "method": "Pre-origin joint residual trajectories; conditional on fixed annual spatial weights. Allocation and hospital uncertainty not calibrated."}
