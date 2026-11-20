"""Expected overflow placements using each origin barangay's first-hospital rankings."""
import numpy as np


def _fraction(available, requested):
    return np.divide(np.minimum(available, requested), requested,
                     out=np.zeros_like(requested), where=requested > 0)


def _place(pending, capacity, probabilities):
    """Serve first choices, then simultaneously offer each origin's excess to its best open sites."""
    requested = pending.sum(axis=0)
    share = _fraction(capacity, requested)
    local = pending * share
    denied = pending * (1 - share)
    free = np.maximum(0, capacity - requested)
    original = denied.sum(axis=1)
    waiting = original.copy()
    redirected = np.zeros_like(pending)
    while np.any(waiting > 0) and np.any(free > 0):
        scores = np.where(free > 0, probabilities, 0)
        best = scores.max(axis=1, keepdims=True)
        tied = (scores == best) & (best > 0)
        offers = tied * (waiting / np.maximum(1, tied.sum(axis=1)))[:, None]
        requested = offers.sum(axis=0)
        if not np.any(requested):
            break
        share = _fraction(free, requested)
        redirected += offers * share
        # At least one site fills, or all feasible offers are accepted.
        waiting = np.where(best[:, 0] > 0, (offers * (1 - share)).sum(axis=1), waiting)
        free = np.maximum(0, free - requested)

    # Within one origin, every denied first destination has the same fallback ranking.
    residual = denied * _fraction(waiting, original)[:, None]
    return local + redirected, residual, redirected.any(axis=0)


class RankedHospitalChoice:
    def __init__(self, origins, facilities, probabilities, origin_mix):
        self.ids = [f["facilityId"] for f in facilities]
        origins = [b["id"] for b in origins]
        rows = [dict(probabilities[b]) for b in origins]
        self.probabilities = np.array([[row[h] for h in self.ids] for row in rows])
        self.origin_mix = np.array([[origin_mix[h].get(b, 0.0) for h in self.ids] for b in origins])

    def place_day(self, first_arrivals, staffed_capacity, holding_capacity):
        first = self.origin_mix * first_arrivals
        staffed, waiting, redirected_staff = _place(first, staffed_capacity, self.probabilities)
        holding, unresolved, redirected_hold = _place(waiting, holding_capacity, self.probabilities)
        supported_totals = staffed.sum(axis=0)
        held_totals = holding.sum(axis=0)
        unplaced_totals = unresolved.sum(axis=0)
        local = {}
        actual_origins = {}
        diverted_staffed = redirected_staff.any()
        for j, h in enumerate(self.ids):
            local[h] = {"firstAdmissionsToday": first_arrivals[j], "supportedPlacementsToday": float(supported_totals[j]),
                        "holdingPlacementsToday": float(held_totals[j]), "unplacedToday": float(unplaced_totals[j])}
            # Only these sites can have a different mix from their original first arrivals.
            if redirected_staff[j] or redirected_hold[j] or (diverted_staffed and held_totals[j] > 0):
                actual_origins[h] = {"supported": staffed[:, j].tolist() if supported_totals[j] else [],
                                     "holding": holding[:, j].tolist() if held_totals[j] else []}
        return local, actual_origins
