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

## Preference-adjusted export

Open the [142 × 46 destination table](../data/processed/qc_first_admission_preference_v1/first_hospital_probabilities.csv) to look up a barangay. The [188 × 188 chain](../data/processed/qc_first_admission_preference_v1/markov_chain.csv) includes the absorbing hospitals. The [preference crosswalk](../data/reference/qc_emergency_hospital_preferences_figure4.csv) explains why each barangay received its adjustment. A blank `preferredHospitalId` means unknown. The column `figureHospitalLabel` can still name a hospital from the paper even when the active network has no matching destination.

The paired example uses a 3 km half-distance in both runs and a **1.5× weight** for each resolved favorite in the adjusted run. The model normalizes each row after applying that weight. Among modeled in-network admissions from **U.P. Campus**, East Avenue Medical Center goes from **3.50% to 5.17%**. For **Batasan Hills**, where the preference is unknown, the same hospital keeps its **2.09%** share and the other 45 shares also stay identical. All shares describe hypothetical first admissions. [Proximity-only table](../data/processed/qc_first_admission_v1/first_hospital_probabilities.csv) · [Model choices and benchmarks](hospital-allocation-decisions.md)

Across this 28-day example, St. Luke’s has the largest increase in peak expected dengue beds, from **0.480 to 0.513**. Citywide peak expected demand is **21.74 beds** in both scenarios because the same arrivals each have the same length of stay. Fractional differences describe expected demand across possible admissions. A staffing decision would also need the existing census, staffed capacity and uncertainty. The offline export can be used independently of the workspace’s nearest-three arrival policy. [All 46 peak comparisons](../data/processed/qc_first_admission_preference_v1/peak_bed_comparison.csv) · [Adjusted hospital-day arrivals and beds](../data/processed/qc_first_admission_preference_v1/daily_hospital_beds.csv)

### Figure 4 review

Figure 4 shows stated emergency preferences across income classes in Chua et al. (2021). We compared its colored polygons with the project’s named barangay boundaries, then matched the hospital labels to the active QC register. Each resolved barangay has the same multiplier in a scenario. The paper provides no barangay-specific effect size for dengue admissions. [Chua et al., Figure 4 and §4.3](https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=10) · [QC facility inventory](hospital-dataset-source-of-truth.md)

| Crosswalk status | Barangays | How the chain treats them |
| --- | ---: | --- |
| Matched fill, barangay and hospital ID | 14 | Apply the illustrative boost to that one hospital. |
| No clear fill, including gray or obscured polygons | 120 | Proximity only. Gray has no defined meaning in the legend. |
| Figure hospital absent from the 46 destinations | 5 | Commonwealth, Fairview, Holy Spirit, North Fairview and San Bartolome align with the FEU–NRMF fill. Keep the source label and use proximity only. |
| Map and paper text give inconsistent or ambiguous evidence | 3 | Both Teachers Village barangays and Matandang Balara use proximity only. Section 4.6 names Teachers Village East for Philippine Heart Center while the mint area aligns with West. Section 4.7 discusses Matandang Balara for Capitol although the area appears gray in Figure 4. |

For the digitization, we used the supplied 1,136 × 1,578 pixel Figure 4 crop (SHA-256 `68e4ed82656e8663510ba2bc4cef24fd5a5f3bf39853389e838ac42c3b8eec65`) and the checked-in [QC polygons](../apps/web/public/data/qc-barangays.geojson) (SHA-256 `886381cbcb97c405d3a260cd74fa256ba9e963e64e5fc972570003cdc79b51b9`). We aligned polygon outlines to the gray boundary strokes, sampled polygon interiors on a two-pixel grid and compared fills to the legend. Repeating the comparison at horizontal and vertical offsets of −4, 0 and +4 pixels retained the same dominant fill for all 14 accepted matches. The paper also names U.P. Campus and Pasong Tamo in its emergency discussion. The crosswalk records our interpretation of the published map. The 128 unknowns describe **usable in-network preference evidence**, and differ from the paper’s count of barangays represented in the survey. [Survey coverage, §4.1](https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=9) · [Emergency comparisons, §§4.6–4.7](https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=13)

<details>
<summary>Reproduce the polygon overlay on the supplied crop</summary>

Pixel coordinates start at the top left. For longitude `lon` and latitude `lat` in the versioned QC GeoJSON, apply this fitted affine transformation. Coordinates refer to the specific crop whose checksum appears above.

```text
x = 11 + 1086 * (lon - 120.989817435) / (121.134971792 - 120.989817435)
y = 140 + 1404 * (14.777701209 - lat) / (14.777701209 - 14.589617128)
u = (x - 550) / 600
v = (y - 800) / 800
pixelX = x + 4.765331 + 0.010451 * u - 5.494612 * v
pixelY = y - 9.040716 + 5.774984 * u + 6.476539 * v
```

Use the seven fill swatches in the legend and the gray polygon fill as RGB references. Count a sample when all three channels differ from a reference by at most six. Unclassified samples include text, hospital markers and boundary edges. The dominant fill is counted among classified interior samples. The project used the fit, the shift check and the paper’s text together to resolve the crosswalk. Pixel shares describe image coverage and never enter the hospital-choice calculation.

</details>

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
python -m scripts.build_first_admission_preference
python -m scripts.build_first_admission_preference --multiplier 2 --output /tmp/qc-first-admission-pref-2x
python -m scripts.build_first_admission_matrix --half-distance-km 6 --output /tmp/qc-first-admission-6km
python -m pytest -q services/engine/tests/test_first_admission_matrix.py services/engine/tests/test_first_admission_preference.py
```

`--admission-fraction`, `--stay-days` and `--run-id` select other assumptions or approved 28-day environmental forecast references. Pass a separate output directory for each scenario. The default command also verifies an existing matching export against a fresh calculation.

For a different distance or forecast, generate that proximity baseline first and pass its directory using `--baseline` to the preference exporter. The preference manifest records the exact baseline manifest and CSV hashes and the crosswalk hash so the comparison can be reproduced.
