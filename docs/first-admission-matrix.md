# Where might a QC dengue case go for first admission?

This hypothetical scenario starts with a dengue case whose admission will take place in the listed QC network. The starting state is the barangay of origin. One transition records the first hospital. Every barangay participates, including those with few forecast cases. A hotspot here means a barangay with many cases over the selected period. The term describes case burden and imposes no inclusion threshold.

## Reading the export

| File in `data/processed/qc_first_admission_v1/` | What one row means |
| --- | --- |
| `first_hospital_probabilities.csv` | One barangay and the probabilities for a single in-network admission to each of 46 hospitals. Multiply a value by 100 to read it as a percentage. |
| `markov_chain.csv` | One starting state in the full 188-state transition matrix. A barangay can go to a hospital. A hospital has a 1 in its own column because recording that first destination ends the episode. |
| `barangay_demand.csv` | One barangay on one scenario date, with its allocated expected cases and expected new admissions before destination choice. |
| `daily_hospital_beds.csv` | One hospital on one scenario date, with new expected admissions from all origins and expected occupied dengue beds if all arrivals receive a bed. Hospital IDs and names form the key to the matrix columns. |
| `manifest.json` | Scenario settings, source years, forecast and register identifiers, code and data checksums, measurement definitions and creation time. |

## How a cell gets its value

For each barangay, measure straight-line distances from its representative point to all 46 provisional hospital points. Give each hospital a weight of `2 ** (-distanceKm / halfDistanceKm)`. Divide each weight by the sum of that barangay's 46 weights. This gives equal probabilities for equal distances. With the illustrative 3 km setting, an otherwise identical destination 3 km farther away gets half the relative weight. Real admission choices, travel times and clinical eligibility are unknown.

For example, among projected in-network admissions from Batasan Hills, the baseline assigns 8.32% to Rosario Maclang Bautista General Hospital. If the weight halves every 1.5 km that share becomes 21.88%. At 6 km it becomes 4.44%. These are three possible answers under different assumptions. Comparing the columns shows how much the conclusion depends on distance.

Chua and colleagues surveyed hospital preferences for emergency and non-emergency care at QC tertiary hospitals. Their respondents emphasized travel time in emergencies and reputation or past experience for non-emergency care. This suggests questions for local interviews or a stated-choice survey. The study does not estimate distance weights for QC dengue admissions. The 3 km parameter is an illustrative choice. [QC hospital preference study](https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf)

## From cases to beds

The export combines the saved QC environmental forecast issued for 2025 source block 4 with the approved annual XGBoost barangay shares available at that cutoff. The 28 daily labels run from January 29 through February 25 under the project's assumed source calendar. The facility list comes from the September 30, 2026 PhilHealth register. Using this later network makes the result a what-if exercise on historical demand.

1. Allocate the QC case forecast across days of each target block and across barangays using the existing engine. The daily barangay numbers are modeled allocations.
2. Apply the existing workspace's illustrative 15% admission fraction and zero admission delay. The other 85% of modeled cases generate no admission in this scenario.
3. Multiply each barangay's expected admissions by its destination probabilities. Sum over all barangays for each hospital. This model assumes all admissions occur within the 46 facilities and all destinations accept the arriving demand.
4. Assume zero dengue patients at the start and a fixed four-day stay. Count each arrival on its admission day and the next three days. For example, three arrivals Monday and two Tuesday with no earlier patients occupy five beds Tuesday. On Friday, only Tuesday's two remain if there have been no new arrivals. Fractional outputs represent expected counts. The result measures dengue bed demand over the 28-day window. Existing patients, other diagnoses, staffing, vacancies and diversion require separate inputs.

The transition probabilities depend only on the current barangay. A hospital self-loop records the completed destination decision. Repeated matrix multiplication keeps that record at the same hospital and cannot determine length of stay.

## Reproduce

From the repository root with the engine environment and approved QC data artifacts available, run:

```sh
python -m scripts.build_first_admission_matrix
python -m scripts.build_first_admission_matrix --half-distance-km 6 --output /tmp/qc-first-admission-6km
python -m pytest -q services/engine/tests/test_first_admission_matrix.py
```

`--admission-fraction`, `--stay-days` and `--run-id` select other assumptions or approved 28-day environmental forecast references. Pass a separate output directory for each scenario. The default command also verifies an existing matching export against a fresh calculation.
