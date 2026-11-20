# How SurgeWise forecasts dengue cases and estimates hospital bed demand

SurgeWise uses a **shallow random forest** to forecast weekly dengue cases in Quezon City (QC). Its **Markov chain** estimates which hospital would receive each admission. The simulation then calculates how many patients would need a bed on each day of their stay. XGBoost was among the models evaluated during development. The selected weekly forecaster is `RF_shallow`. [Forecast methods and validation](../production/README.md#archive-accuracy-and-reproduction)

## Which case data does Simulation use?

| Simulation selection | Where the cases come from |
| --- | --- |
| Historical replay, 2012–2022 | The default plays back the imputed weekly dataset. A Gaussian process helped estimate each barangay’s share of reported weekly QC cases using annual barangay counts as constraints. Cases assigned to the 142 mapped barangays enter the hospital simulation. The app reports the unassigned remainder separately. |
| Historical forecast, 2021–2022 | Select the random forest under **Historical case source** to see what a model trained through 2020 would have predicted from the information available before the selected window. |
| Future forecast | The released forest was refitted through 2022. With the bundled archive, its first forecast week follows week 52 of 2022. Choosing a later planning date moves the hospital simulation calendar. A surge multiplier, when enabled, is a user-selected scenario assumption. |

The case forecast covers up to six weeks. Hospital playback uses a 7-, 14-, 21- or 28-day window and advances in seven-day steps. [Historical inputs and forecast handoff](../production/README.md#hospital-simulation-and-historical-replay)

## How the random forest predicts cases

The forest predicts **one weekly count for each of the 142 barangays** at each requested forecast horizon. Its inputs include recent barangay and city case counts, whether those counts are rising or falling, neighboring barangays’ trends, the time of year, population and historical case patterns. [Forecast features](../production/surgewise/features.py)

The fitted model has **32 decision trees**, each at most six levels deep. For a particular barangay and target week, each tree follows a series of learned rules and returns an expected case count. The app averages the 32 estimates to get that barangay’s forecast. It adds all 142 barangay forecasts to get the QC total. Because the predictions are averages, expected cases can be fractional. [Forest prediction and city aggregation](../production/surgewise/predictor.py)

On the 2022 chronological test, the forest’s weekly QC forecast missed by **22.3 cases on average**, compared with **25.1** for repeating the last observed count. On a separate blocked test, repeating the last count did better, with an average error of **20.7 cases** versus **25.5** for the forest. These scores measure accuracy against reported citywide cases. Accuracy against actual hospital bed occupancy has yet to be established. [Archive test results](../apps/web/public/data/qc-archive-forecast-validation.json)

## How cases become beds

The engine calculates demand **daily**. The defaults assume that **15% of cases need admission in the modeled QC network**, admission occurs with **zero days of delay**, patients stay **four days**, and the simulation starts with **zero dengue inpatients**. The admission rate, delay and length of stay are editable. [Simulation settings](../services/engine/api/qc_simulation.py)

1. **Cases become admissions.** The engine spreads each barangay’s cases evenly over its reporting interval. For example, 70 cases in a seven-day week gives 10 cases per day. At the default 15% admission rate, that gives **1.5 expected admissions per day** from that barangay.
2. **The Markov chain distributes admissions among hospitals.** Each barangay has a row of probabilities across the 46 hospitals that sums to 100%. In the default matrix, the weight halves for every 3 km of straight-line distance. A mapped preferred hospital gets a 1.5× weight before the row is normalized. A hospital with a 20% share in this example receives **1.5 × 0.20 = 0.3 expected admissions per day** from that origin. The engine adds each hospital’s contributions from all barangays. [Hospital-choice probabilities](first-admission-matrix.md#using-the-chain-in-the-simulation)
3. **Admissions become bed demand.** With a four-day stay, today’s expected bed demand equals today’s admissions plus the previous three days’ admissions. In the example, after four days at 1.5 admissions per day, that barangay contributes **6 expected occupied beds across the network** before hospital-level rounding. The displayed weekly change compares unrounded bed demand on the selected day with demand seven days earlier. [Bed-demand calculation](../services/engine/domain/bed_forecast.py)

## Reading a simulation result

For the example **643.2 projected cases, 46 total beds needed, 0 additional beds needed** at day 28, the three values answer different questions under the default first-hospital policy.

| Displayed value | What it means |
| --- | --- |
| **643.2 projected cases** | Expected cases accumulated across the modeled QC barangays through day 28. |
| **46 total beds needed** | Whole dengue beds required **on day 28**. The engine rounds up each hospital’s expected bed demand, then adds those whole-bed requirements across hospitals. |
| **0 additional beds needed** | Every hospital’s assumed dengue capacity covers its modeled demand on day 28. A hospital that needs 10 beds and has 6 dengue slots would contribute 4 additional beds to the citywide shortfall. |

Open **Simulation → Bed details** to inspect a hospital’s expected demand, assumed capacity, shortfall and change from the previous week. Actual staffed capacity, current dengue occupancy and vacancies require hospital data. [Bed totals and shortfall definitions](first-admission-matrix.md#using-the-chain-in-the-simulation)
