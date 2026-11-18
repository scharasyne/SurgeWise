import csv
from collections import defaultdict

import pytest

from scripts.build_first_admission_matrix import build, choice_row


def test_hypothetical_distance_weights():
    assert choice_row([3, 6, 9], 3) == pytest.approx([4/7, 2/7, 1/7])
    assert choice_row([0, 0], 3) == [.5, .5]


@pytest.mark.parametrize("distances,scale", [([], 3), ([float("nan")], 3), ([-1], 3),
                                             ([1], 0), ([1], float("inf")), ([1, 20], .0001)])
def test_invalid_distance_or_unrepresentable_share(distances, scale):
    with pytest.raises(ValueError):
        choice_row(distances, scale)


def test_complete_chain_and_hospital_day_balance(tmp_path):
    manifest = build(tmp_path, "qc-weather-residual-v2-QUEZON_CITY-2025-4", 3, .15, 4)

    def read(name):
        with (tmp_path / name).open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    matrix = {r["barangayId"]: r for r in read("first_hospital_probabilities.csv")}
    hospital_ids = {f"HOSP-{n}" for n in range(614, 660)}
    states = {r["fromState"]: r for r in read("markov_chain.csv")}
    assert len(matrix) == 142
    assert set(states) == set(matrix) | hospital_ids
    for origin, row in states.items():
        assert all(row[b] == "0" for b in matrix)
        shares = [float(row[h]) for h in hospital_ids]
        assert sum(shares) == pytest.approx(1)
        if origin in matrix:
            assert min(shares) > 0
            assert all(row[h] == matrix[origin][h] for h in hospital_ids)
        else:
            assert all(float(row[h]) == (h == origin) for h in hospital_ids)

    case_days = defaultdict(dict)
    for row in read("barangay_demand.csv"):
        cases = float(row["modeledCases"])
        admissions = float(row["expectedAdmissions"])
        assert admissions == pytest.approx(cases * manifest["assumptions"]["admissionFraction"])
        case_days[row["scenarioDate"]][row["barangayId"]] = admissions
    assert len(case_days) == 28
    assert all(set(b) == set(matrix) for b in case_days.values())
    history = defaultdict(list)
    results = read("daily_hospital_beds.csv")
    assert len(results) == len({(r["hospitalId"], r["scenarioDate"]) for r in results}) == 28 * 46
    for row in sorted(results, key=lambda r: r["scenarioDate"]):
        h = row["hospitalId"]
        origin_counts = case_days[row["scenarioDate"]]
        incoming = sum(n * float(matrix[b][h]) for b, n in origin_counts.items())
        history[h].append(incoming)
        assert float(row["expectedFirstAdmissions"]) == pytest.approx(incoming)
        assert float(row["expectedOccupiedDengueBedsIfAdmitted"]) == pytest.approx(sum(history[h][-4:]))
