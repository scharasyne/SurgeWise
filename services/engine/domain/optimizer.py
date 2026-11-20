"""Continuous expected-patient transportation LP, not clinical referral/routing."""
import math
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


def transport_plan(demands, capacities, costs):
    n, m = len(demands), len(capacities)
    if not n or not m or len(costs) != n or any(len(row) != m for row in costs):
        raise ValueError("Invalid transportation dimensions")
    if any(not math.isfinite(v) or v < 0 for v in [*demands, *capacities, *(v for row in costs for v in row)]):
        raise ValueError("Invalid transportation value")
    total = min(sum(demands), sum(capacities))
    if total <= 0:
        return [[0.0] * m for _ in demands]
    indices = np.arange(n * m)
    constraints = coo_matrix((np.ones(2 * n * m),
        (np.concatenate([np.repeat(np.arange(n), m), n + np.tile(np.arange(m), n)]), np.concatenate([indices, indices]))),
        shape=(n + m, n * m)).tocsr()
    result = linprog(np.asarray(costs).ravel(), A_ub=constraints, b_ub=[*demands, *capacities],
        A_eq=coo_matrix(np.ones((1, n * m))).tocsr(), b_eq=[total], bounds=(0, None), method="highs",
        options={"primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise ValueError("Transportation optimization infeasible")
    return np.maximum(0, result.x.reshape(n, m)).tolist()


def overflow_plan(demand, capacity, costs, first_columns, optimize):
    """Protect each site's first choices before routing only the excess to remaining slots."""
    remaining = demand.copy()
    free = capacity.copy()
    placements = [[0.0] * len(free) for _ in remaining]
    for i, column in enumerate(first_columns):
        here = min(remaining[i], free[column])
        placements[i][column] = here
        remaining[i] -= here
        free[column] -= here
    if not any(remaining) or not any(free):
        return placements
    if optimize:
        origins = [i for i, excess in enumerate(remaining) if excess > 0]
        destinations = [j for j, slots in enumerate(free) if slots > 0]
        extra = transport_plan([remaining[i] for i in origins], [free[j] for j in destinations],
                               [[costs[i][j] for j in destinations] for i in origins])
        for i, row in zip(origins, extra):
            for j, placed in zip(destinations, row):
                placements[i][j] += placed
        return placements
    for i, pending in enumerate(remaining):
        for j in sorted(range(len(free)), key=lambda j: (costs[i][j], j)):
            if pending <= 0:
                break
            amount = min(pending, free[j])
            placements[i][j] += amount
            pending -= amount
            free[j] -= amount
    return placements


def daily_plan(groups, states, admission_rate, occupancy, day, activation_day, overflow_policy=None):
    ids = [s["config"]["facilityId"] for s in states]
    demand = [g["cases"] * admission_rate for g in groups]
    from .patient_flow import non_dengue_share
    support = [max(0, s["config"]["normalCapacity"] * (1 - non_dengue_share(s["config"], occupancy))
        + (s["config"]["surgeCapacity"] if day >= activation_day else 0) - sum(c for _, c in s["cohorts"])) for s in states]
    costs = [[g["facilityCostsKm"][ident] for ident in ids] for g in groups]
    first_columns = [ids.index(g["firstFacilityId"]) for g in groups] if overflow_policy else []
    def plan(demands, capacities):
        if overflow_policy:
            return overflow_plan(demands, capacities, costs, first_columns, overflow_policy == "optimized")
        return transport_plan(demands, capacities, costs)
    supported = plan(demand, support)
    remaining = [max(0, d - sum(row)) for d, row in zip(demand, supported)]
    holding = plan(remaining, [max(0, s["config"]["holdingCapacity"] - s["holding"]) for s in states])
    return [{"supported": dict(zip(ids, a)), "holding": dict(zip(ids, b))} for a, b in zip(supported, holding)]
