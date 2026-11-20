# SurgeWise web inference

The web app can request **1–6 weeks ahead** from the selected random forest (`RF_shallow`). Send `{"weeks_ahead": 4}` to `POST /predict` for four successive weeks. The response includes four city totals and 568 barangay rows, with a baseline and an optional surge scenario for every row. An empty request selects six weeks.

**The last observed week sets the forecast dates.** With the bundled history, `as_of` is 2022 week 52 and a four-week simulation covers 2023 weeks 1–4. To simulate forward from a later week, send observed city counts through that week. Include either consecutive updates from 2023 week 1 or at least 53 consecutive recent weeks so the model can calculate its 52-week lags. The backend uses the project's 52-week morbidity calendar, including when a forecast crosses a year boundary.

For later-year simulations, the fitted trees, annual barangay features, and GP seasonal profiles still use the release's history through 2022. New observations update lag and growth features. Predictive accuracy for those later years has yet to be established.

## Integrate with a Python backend

Place the `surgewise/` package on the backend's import path. In a Python 3.12+ environment, install the production dependencies from this directory.

```sh
python -m pip install -r requirements.txt
```

Call the predictor from the app's existing forecast route. All results stay in memory. Assets are loaded on first use and cached within each worker.

```python
from surgewise.predictor import predict

forecast = predict(weeks_ahead=2, city_updates=[{"year": 2023, "week": 1, "city_cases": 55}])
weekly_city_totals = forecast["city"]       # Weeks 2–3
barangay_estimates = forecast["barangays"]  # 284 barangay-week rows
```

## Integrate over HTTP

For an app using Node, PHP, or another backend, run the included WSGI service on the same Linux host. Start it from this directory.

```sh
gunicorn --bind 127.0.0.1:8000 surgewise.api:application
```

Have your backend send a JSON object to `POST /predict`. A first deployment check is:

```sh
curl -sS http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' -d '{}' \
  | python -c 'import sys,json; r=json.load(sys.stdin); print(r["model"], len(r["barangays"]), r["city"][0]["expected_cases"])'
```

Expected output is `RF_shallow 852` followed by approximately `63.79985` expected city cases in week 1.

### Request fields

| Field | Accepted input |
| --- | --- |
| `weeks_ahead` | Integer from 1 to 6. Defaults to 6. A request for 4 returns horizons 1, 2, 3 and 4. |
| `city_updates` | Consecutive observations with `year`, `week`, and `city_cases`, as described above. Defaults to the bundled history when omitted. |
| `local_updates` | Optional observed counts with `year`, `week`, `barangay_code`, and `cases`. Each barangay-week must be unique and covered by a city update. Codes are in `surgewise/data/barangays.csv`. |
| `multiplier` | Scenario factor of at least 1. Defaults to 1. |
| `start`, `duration` | First forecast horizon and number of horizons affected. Both are integers and the window must fit within the requested forecast. Start defaults to 1 and duration defaults to the remaining forecast weeks. |
| `ramp` | Set to `true` to increase the factor in equal steps and reach `multiplier` at the end of the scenario window. Defaults to `false`. |

For example, this request uses actual observations for week 1, forecasts weeks 2–5, and applies a 1.5× scenario to forecast horizons 2 and 3 (calendar weeks 3 and 4).

```json
{
  "weeks_ahead": 4,
  "city_updates": [{"year": 2023, "week": 1, "city_cases": 55}],
  "local_updates": [{"year": 2023, "week": 1, "barangay_code": "PH1307404001", "cases": 2}],
  "multiplier": 1.5,
  "start": 2,
  "duration": 2
}
```

A successful response identifies the last observed morbidity week in `as_of`, the requested `weeks_ahead`, and the annual and GP data cutoff in `feature_history_through`. It also contains `model`, `trained_through`, `city`, and `barangays`. Both result lists have `year`, `week`, `horizon`, `expected_cases`, `scenario_multiplier`, and `scenario_expected_cases`. Barangay rows also include `barangay_code` and `barangay`. Display `expected_cases` as the model forecast and `scenario_expected_cases` as the simulation. Invalid observations or scenario parameters return HTTP 400 and an `error` message. The Python callable raises `ValueError` for invalid values.

## Display weekly GP estimates

The release includes the full 2012–2022 GP reconstruction in `surgewise/data/gp_cases.csv`. The forecast model used reconstructed weekly barangay counts as training targets where reported annual totals were available. Completed-year reconstructions also supply lag and seasonal features. The display endpoint reads the full table, including estimates for barangays with missing annual totals.

| Web app view | Request |
| --- | --- |
| Map of all 142 barangays for one week | `GET /gp-history?year=2022&week=52` |
| Full history for Alicia | `GET /gp-history?barangay_code=PH1307404001` |
| One year of weekly estimates for Alicia | `GET /gp-history?year=2022&barangay_code=PH1307404001` |

A Python backend can call `gp_history(year=2022, week=52)` from `surgewise.history`. Each response contains:

- `barangays` has the mapped areas. Join map features by `barangay_code`. Plot `gp_expected_cases` by `year` and `week` under **GP-estimated weekly cases**. To show uncertainty, shade the range from `gp_rate_q025` to `gp_rate_q975` and label it **95% GP scenario range**. These estimates use retrospective annual totals and observed weekly city counts.
- `city` has one record per returned week. Use `observed_city_week_cases` for the reported city total. The GP estimates across all mapped barangays plus `unassigned_expected_cases` reconcile to that total, within rounding precision. City records cover the full city even when a single barangay is selected.

For a forward simulation, plot `expected_cases` from `POST /predict` as **Forecast cases**. The historical GP scenario range applies to the reconstruction only.

## Release files

| File under `surgewise/` | Purpose |
| --- | --- |
| `models/forest.npz` | Learned tree splits, missing-value directions and leaf predictions from the fitted forest |
| `models/model.json` | Selected variant, forecast year, training cutoff and feature order |
| `data/history.npz` | Historical city and local series, annual features, seasonal profiles and adjacency weights. Missing local observations are encoded as NaN. |
| `data/barangays.csv` | Barangay codes and names in the model's row order |
| `data/gp_cases.csv`, `history.py` | Full weekly GP dataset and lookup for historical displays |
| `features.py`, `predictor.py` | Feature construction, forest prediction, aggregation and simulation |
| `api.py` | JSON HTTP endpoint |
