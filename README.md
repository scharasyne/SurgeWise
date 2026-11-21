# SurgeWise

**From dengue forecasts to hospital preparedness.**

SurgeWise is a map-based public-health research and planning prototype for **Quezon City, Philippines**. It brings together dengue surveillance, reconstructed barangay-level case estimates, short-term forecasts, probabilistic hospital assignment, and configurable bed-capacity simulations.

The question behind the project is simple: **When dengue cases rise, where might additional patients need care—and which hospitals could come under pressure first?**

> **Research prototype — not a live clinical system.** SurgeWise does not report real-time dengue cases, actual hospital vacancies, confirmed weekly barangay infections, or clinically validated admission predictions. Outputs are retrospective forecasts or **hypothetical planning scenarios**, not medical, referral, or operational directives.

## Contents

- [What SurgeWise does](#what-surgewise-does)
- [How the system works](#how-the-system-works)
- [Try it locally](#try-it-locally)
- [Using the application](#using-the-application)
- [Forecast evaluation and interpretation](#forecast-evaluation-and-interpretation)
- [Data sources and provenance](#data-sources-and-provenance)
- [Repository structure](#repository-structure)
- [API and reproducibility](#api-and-reproducibility)
- [Testing](#testing)
- [Limitations and roadmap](#limitations-and-roadmap)
- [Research use and acknowledgments](#research-use-and-acknowledgments)

## What SurgeWise does

| Component | What it provides | Important distinction |
| --- | --- | --- |
| **Dengue surveillance and research** | Historical QC/NCR case information, maps, evidence, and forecast comparisons | Not a live 2026 surveillance feed |
| **Barangay-level reconstruction** | Estimated weekly dengue cases for QC's **142 barangays** (2012–2022) | Reconstructed estimates, **not observed weekly barangay reports** |
| **Dengue forecasting** | A bundled Random Forest model producing **1–6-week-ahead** expected cases for 142 barangays | Forecast originates after the model archive's final observed week in **2022** unless new observations are supplied; it is not a live 2026 forecast |
| **Hospital choice** | First-admission probabilities from each barangay to **46 QC hospitals/infirmaries** | Hypothetical geographic and preference-based choices; not actual patient flows |
| **Hospital pressure simulation** | Projected demand, supported placements, temporary holding, and unresolved demand | Depends on user-set hospitalization, length-of-stay, capacity, and overflow assumptions |
| **Scenario comparison** | Explore changes to case surges, hospital capacity, and allocation rules | An assumed surge is **not** a predicted outbreak onset |

The repository also contains an **independent UPRI-NOAH research pipeline** for QC and NCR city/regional historical forecasts. Its results and time/calendar rules are **not interchangeable** with the GP–Random Forest barangay release described below.

## How the system works

```text
OBSERVED DATA                              MODELS                           PLANNING OUTPUT

Annual QC dengue cases by barangay ──┐
                                    ├─► Proportional allocation
Weekly QC citywide dengue cases ─────┘            │
                                                  ▼
                                     Gaussian Process + IPF
                                     (weekly barangay estimates)
                                                  │
                                                  ▼
                                       Random Forest forecast
                                       (142 barangays, 1–6 weeks)
                                                  │
                                                  ▼
                                  Assumed hospitalization and stay
                                                  │
                                                  ▼
                                    First-order Markov hospital choice
                                    (142 origins × 46 destinations)
                                                  │
                                                  ▼
                                  Capacity-constrained bed simulation
                                                  │
                                                  ▼
                                Supported / holding / unresolved demand
```

### 1. Reconstruct missing weekly barangay cases: Gaussian Process + IPF

**Problem.** The available historical records include annual dengue case totals for each QC barangay and weekly dengue totals for the entire city, but **no observed weekly-by-barangay series** covering the model's training period. Training a local weekly forecaster directly on observed targets was therefore impossible.

**Our approach:**

1. **Proportional starting point.** For a barangay and week in a given year, take the barangay's share of the annual citywide total and multiply by the observed citywide cases for that week: `initial barangay-week estimate = (annual barangay cases / annual city cases) × city cases that week`.
2. **Spatial and temporal Gaussian Process.** Generate correlated fluctuations so geographically closer barangays and temporally closer weeks can vary together. The release uses an RBF spatial length scale of **2 km**, temporal length scale of **4 weeks**, a **0.7 spatial-kernel / 0.3 independent** mixture, and log-scale variation **σ = 0.5**.
3. **Iterative Proportional Fitting (IPF).** Repeatedly scale rows and columns so each simulated allocation agrees with **both** the reported annual barangay totals and the weekly citywide totals. An explicit residual/`UNASSIGNED` category handles small source-total differences where applicable.
4. **Monte Carlo averaging.** Run **300 constrained simulations per year** and average their balanced estimates into the `gp_expected_cases` reconstruction. Preserve separate simulation-based ranges rather than treating them as validated predictive intervals.

**Why IPF matters:** Gaussian draws alone can change known totals. IPF ensures the reconstructed distribution remains consistent with the surveillance totals we actually have. **It cannot establish the true allocation within a week.** 

### 2. Forecast dengue cases: Random Forest

The bundled **`RF_shallow`** model is an ensemble of decision trees that predicts nonnegative **expected weekly case counts** for each of QC's 142 barangays for up to six forecast weeks. City totals are calculated by summing the barangay predictions.

Features include previous citywide and reconstructed local dengue activity, lags and rolling averages, annual barangay burden, seasonal indicators, population/area/density features, and neighboring barangay information. **Weather is not an input to this specific GP–RF release**; other archived research models use weather separately.

The model uses only permitted historical information for forecast-time features. Retrospective GP reconstructions, however, were built using complete annual totals, so the reconstructed *targets* remain inherently assumption-dependent. The model was refitted through **2022** for the packaged release.

### 3. Estimate hospital destinations: First-order Markov Chain

A case requiring admission starts in its **barangay of origin**. A first-order Markov transition assigns probabilities to **46 QC hospitals/infirmaries**, conditional on the modeled admission occurring within that network. The implementation stores a **142 × 46 first-hospital probability matrix** and an equivalent chain with absorbing hospital states.

The baseline choice weights decay with **straight-line distance** (illustratively, they halve every **3 km**); an optional preference-based version adjusts weights for matched hospitals before renormalizing them. These preferences are scenario assumptions informed by external research, **not estimated dengue referral records**.

The Markov Chain answers **“Where might someone first seek admission?”** It does **not** forecast how long a patient occupies a bed. Length of stay and discharge are handled by the separate patient-flow simulation.

See [`docs/first-admission-matrix.md`](docs/first-admission-matrix.md) and [`docs/hospital-allocation-decisions.md`](docs/hospital-allocation-decisions.md).

### 4. Translate forecast cases into bed demand

The simulator converts expected cases into hypothetical admissions using **editable** assumptions for hospitalization fraction, admission delay, length of stay, baseline occupancy, surge beds, and holding spaces. It then compares demand against configured hospital capacity.

Two first-admission/overflow policies are available:

- **Record the shortage at the first hospital:** keep modeled demand at its first selected hospital and report shortages there.
- **Try the next most likely hospital with space:** redistribute overflow using origin-specific hospital probabilities and remaining assumed capacity, then consider temporary holding spaces.

Results distinguish **supported demand** (within assumed staffed capacity), **holding demand** (temporary spaces), and **unresolved demand** (not accommodated under the modeled constraints). An optimizer or allocation comparison is **scenario-based** and cannot demonstrate actual improvements in admissions or outcomes without operational validation.

Default scenario settings in the QC workspace include **15% hospitalization**, **4-day stay**, and **60% baseline occupancy**. These are **editable assumptions**, not observed QC dengue clinical rates.

## Try it locally

### Prerequisites

- **Node.js 22.18+** and npm (Node 24 is used by the documented frontend tests).
- **Python 3.13** is the repository's `.python-version` recommendation; the packaged production predictor also supports Python 3.12+.
- A checkout containing the **bundled release artifacts, pinned datasets, and manifests**. Do not move or edit hash-validated data files without following the source audit.
- Internet access for installing dependencies; map tiles also require network connectivity.

The web frontend and Python engine are separate processes. Run them in **two terminals**, from the repository root.

**Terminal 1 — FastAPI engine**

```bash
python -m venv .venv
# Activate the virtual environment for your shell, then:
python -m pip install -r services/engine/requirements-dev.txt
python -m uvicorn services.engine.main:app --reload --reload-dir services/engine --port 8000
```

Check [http://localhost:8000/health](http://localhost:8000/health) and [http://localhost:8000/readiness](http://localhost:8000/readiness). **Health means the server is running; readiness reports whether the audited datasets and model artifacts are usable.**

**Terminal 2 — Next.js web app**

```bash
cd apps/web
cp .env.example .env.local
npm ci
npm run dev
```

The example environment contains:

```dotenv
ENGINE_BASE_URL=http://127.0.0.1:8000
```

Open **[http://localhost:3000](http://localhost:3000)**. `ENGINE_BASE_URL` is a **server-only** web-app setting; configure it in `apps/web/.env.local`, not just in the repository root. On Windows PowerShell, use `Copy-Item .env.example .env.local` and, if script execution is restricted, use `npm.cmd` instead of `npm`.

**Startup notes:** `npm run dev` uses the repository's lock-protected launcher; do not start a second `next dev` process against its cache. Keep the backend's reload watcher scoped to `services/engine` to avoid monitoring `node_modules` and `.next`.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| Dashboard loads but forecast/simulation is unavailable | Start FastAPI, verify `ENGINE_BASE_URL`, then inspect `/readiness`. |
| `ENGINE_NOT_CONFIGURED` or frontend engine connection error | Confirm `apps/web/.env.local`, restart Next.js, and verify the engine URL. |
| Model or data integrity error | Check bundled artifacts and original pinned bytes; **do not** overwrite expected hashes just to bypass validation. |
| Maps do not show street tiles | Check internet access; hospital source tables can still work without map tiles. |
| Simulation cannot start or has no output | Review the selected archive period, documented assumptions, allowed date/horizon, and source-readiness status. |

For hosted environments, see [`docs/render-deployment.md`](docs/render-deployment.md).

## Using the application

| Page | What to do |
| --- | --- |
| **`/dashboard`** | Explore NCR/QC geography and the 46-record canonical QC hospital register; inspect source details and provisional locations. |
| **`/outbreak-response`** | Choose **Historical replay** (2012–2022 GP reconstruction; held-out RF replay available for 2021–2022) or **Future forecast** (1–6 weeks after the archived origin), configure a surge/bed scenario, run, and inspect hospital/barangay outcomes. |
| **`/research`** | Explore audited UPRI-NOAH case histories, separate QC/NCR source-block retrospective forecasts, annual barangay observations, source limitations, and first-admission probabilities. |
| **`/`** | Project landing page. `/simulate` redirects to the outbreak workspace; `/forecast` redirects to its future-forecast mode. |

**Suggested demonstration:** open the dashboard → inspect hospital evidence → run a historical QC case replay → adjust hospitalization and bed assumptions → compare first-hospital vs. next-available placement → review supported, holding, and unresolved demand → open Research to examine provenance and validation.

### Hospital inventory caveat

The canonical source is the **PhilHealth register dated September 30, 2026**: **46 QC hospital/infirmary records totaling 9,389 accredited beds**. This is **not** 9,389 available dengue beds. All 46 displayed points are provisional, and none is independently verified as an emergency entrance. A separate NHFR extract is retained only for audit/crosswalk purposes; it must not be added to the active network or substituted as a silent fallback.

See [`docs/hospital-dataset-source-of-truth.md`](docs/hospital-dataset-source-of-truth.md).

## Forecast evaluation and interpretation

The GP–Random Forest release used **2012 as historical feature warm-up**. Its 520 target weeks from **2013–2022** were divided into an **80/10/10 split** by *week*, keeping all barangays for a given week together:

| Partition | Period | Weeks | Role |
| --- | --- | ---: | --- |
| Historical warm-up | 2012 | 52 | Previous-year/lag context; excluded from scored targets |
| Training | 2013–2020 | 416 (80%) | Fit models |
| Validation | Blocked selection from 2021–2022 | 52 (10%) | Choose model/configuration |
| Test | Remaining blocked selection from 2021–2022 | 52 (10%) | Retrospective held-out evaluation |

The blocked split assigns complete multi-week groups, **not randomly shuffled barangay rows**. A separate chronological protocol uses 2021 for validation and 2022 for testing. The randomized late-period test is **not a strictly forward-in-time prospective study**.

| Check | Selected Random Forest result | What it means |
| --- | ---: | --- |
| Blocked test: reconstructed barangay weekly cases | **0.277 MAE** per barangay-week | Agreement with **GP-estimated** targets, **not** actual weekly barangay observations |
| Blocked test: aggregated QC weekly cases | **25.51 MAE** cases/week | Historical city-level error; a local-persistence baseline achieved **20.67 MAE** on the same test |
| Cross-source comparison: 2023 weeks 1–6 (UPRI-NOAH) | **7.59% MAPE** and **4.49 MAE** cases/week | Aggregated QC predictions compared with six observed **citywide** weeks; **not** verified barangay-level accuracy |

The selected model was chosen among machine-learning candidates using validation six-week cumulative city MAE. A simple persistence baseline performed better than RF on the randomized test, and the six-week 2023 comparison has been examined during development; it should **not** be described as a pristine external holdout or generalizable 92.41% forecasting accuracy.

**Reproduction:** [`production/README.md`](production/README.md) describes the packaged predictor, API, 2012–2022 historical replay, and evaluation scores. For full notebook and model-selection source, examine the embedded [`SurgeWise_80_10_10.zip`](production/SurgeWise_80_10_10.zip).

### The separate UPRI-NOAH research pipeline

The `/research` page uses a **source-verified UPRI-NOAH workbook** and its own 1–4-**source-block** expanding-origin retrospective comparisons for QC and NCR. It preserves the original `(YR, WN)` block identifiers because the source's calendar/week semantics have unresolved differences. It includes persistence, seasonal-naive, cases-only, and weather-feature comparisons. **These results are not GP-imputed weekly barangay ground truth and are not the bundled RF six-week forecast.**

For provenance and methods, see [`docs/upri-integration-audit.md`](docs/upri-integration-audit.md), [`docs/upri-verification.md`](docs/upri-verification.md), and [`docs/data-sources.md`](docs/data-sources.md).

## Data sources and provenance

| Source | Role | Main caveat |
| --- | --- | --- |
| **QC annual barangay dengue records (2010–2025)** | Observed annual case burden for 142 barangays | Annual totals do not reveal actual weekly local patterns; missing values are preserved. |
| **Eligado et al. citywide weekly cases (2012–2022)** | Weekly city constraints for the archived GP reconstruction | Separate source from the annual totals; small discrepancies require explicit reconciliation. |
| **UPRI-NOAH dengue/environmental dataset** | Independently audited city/regional cases, weather, 2023 comparison, and separate research views | Pin the source version, preserve its native time identifiers, and distinguish it from the GP archive. |
| **QC barangay GeoPackage / population references** | Local geography, adjacency, density, and spatial features | Spatial allocation and inferred risk are modeled, not observed weekly surveillance. |
| **PhilHealth hospital register (2026-09-30)** | Active 46-site QC facility inventory and accredited bed totals | Accredited beds ≠ staffed, vacant, dengue-eligible beds. Locations are provisional. |
| **QC hospital preference research** | Optional adjustment to assumed first-hospital choice weights | The paper does not estimate dengue-specific hospital-choice probabilities. |

UPRI source materials are pinned to upstream commit [`02926278d570db8950da368d44db544ae0097615`](https://github.com/pelitro-rcw/dengue-environmental-dataset/tree/02926278d570db8950da368d44db544ae0097615). Audited originals are under `data/raw/upri_noah/`; manifests and separate derived results are under `data/processed/upri_noah/`. Do not casually rewrite, reformat, or re-save hash-validated source files.

Full documentation: [`docs/data-sources.md`](docs/data-sources.md) · [`docs/upri-integration-audit.md`](docs/upri-integration-audit.md) · [`docs/first-admission-matrix.md`](docs/first-admission-matrix.md).

## Repository structure

```text
.
├── apps/web/                  # Next.js, React, MapLibre frontend and web API routes
│   ├── app/                   # Landing, dashboard, research, outbreak-response
│   └── public/data/           # Shipped public geography / vetted derivatives
├── services/engine/           # FastAPI backend
│   ├── api/                   # Forecast, simulation, research, report endpoints
│   ├── domain/                # Case allocation, patient flow, bed models, policies
│   ├── repositories/          # Approved sources, forecast runs, persistence
│   └── tests/                 # Python regression and API tests
├── production/                # Packaged RF model, historical GP lookup, release archive
│   ├── surgewise/             # Inference code and bundled model/data assets
│   └── SurgeWise_80_10_10.zip # GP notebook, training and holdout evaluation source
├── data/
│   ├── raw/upri_noah/         # Original pinned source materials
│   ├── reference/             # Hospital, map and UPRI reference evidence
│   └── processed/             # Audited outputs and probability matrices
├── scripts/                   # Audit, ingestion, evaluation and export utilities
├── docs/                      # Technical methods, governance and deployment
└── artifacts/frontend/        # Example interface screenshots
```

## API and reproducibility

The engine exposes interactive OpenAPI documentation at **`http://localhost:8000/docs`**. Important routes include:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` · `GET /readiness` | Service connectivity vs. audited model/data readiness |
| `GET /v1/facilities` | Canonical QC hospital inventory |
| `POST /v1/predict` | Packaged RF 1–6-week barangay forecast; optional assumed surge multiplier |
| `GET /v1/forecast-runs` · `GET /v1/research-evidence` | Audited historical source-block runs and evidence |
| `POST /v1/qc-simulation` | GP historical replay / linked archived forecast and hospital simulation |
| `POST /v1/scenarios` | Versioned UPRI research scenario with explicit hypothetical capacity inputs |
| `GET /v1/outbreak-scenarios/{id}/report.pdf` | Export a supported modeled outbreak report |

A minimal archived-origin forecast request (engine running):

```bash
curl -X POST http://127.0.0.1:8000/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{"weeks_ahead": 2}'
```

This uses the **archive ending in 2022**, and the returned 2023 horizons are an example historical forecast, **not predictions for the present date**. New city observations can update lag features, but the fitted model and older annual/spatial features remain tied to the release through 2022 unless properly retrained.

UPRI pipeline reproduction, if necessary, starts with auditing (not silently cleaning) original data:

```bash
python -m pip install -r services/engine/requirements-ingest.txt
python scripts/audit_upri.py
python scripts/integrate_upri.py
python scripts/build_qc_environmental_forecasts.py
```

Read [`docs/upri-verification.md`](docs/upri-verification.md) before regenerating anything: cross-platform newline conversion can invalidate pinned SHA-256s, and changing the files does not resolve the source-calendar concerns. The original upstream R validation workflow was **not** rerun as part of the documented integration.

## Testing

From the repository root:

```bash
python -m pytest -q
python -m compileall -q scripts services/engine

cd apps/web
npm test
npm run lint
npx tsc --noEmit
npm run build
```

For additional source integrity, hospital migration, and workspace verification, follow [`docs/test-and-release-checklist.md`](docs/test-and-release-checklist.md). Automated checks do not replace end-to-end browser, security, statistical, or clinical validation.

## Limitations and roadmap

**Current limitations**

- **No weekly barangay ground truth:** GP-IPF produces plausible reconstructions consistent with reported totals, not verified local surveillance. GP hyperparameters were **assumed**, not calibrated from local weekly labels.
- **No live forecasting:** The production RF release was refitted through 2022. A later displayed scenario date must not be represented as a verified real-world prediction for that date.
- **Partial forecast evidence:** The blocked test is retrospective; persistence can outperform RF. The small 2023 citywide comparison does not establish per-barangay skill or future generalization.
- **No clinical calibration:** Hospitalization, admission delay, length of stay, dengue eligibility, staffed capacity, and occupancy are hypothetical inputs. Hospital preference probabilities are not confirmed patient movements.
- **No verified live hospital capacity or entrances:** 9,389 refers to accredited beds, not empty beds. Current coordinates are provisional; simulations are not a patient referral tool.
- **Source limitations remain visible:** QC/NCR UPRI calendar semantics, source-total discrepancies, and archival publication-timing assumptions require investigation.

**Priority next steps**

1. Obtain **actual weekly barangay observations**, if possible, to validate the reconstructed series and fit spatial/temporal hyperparameters against real local outcomes.
2. Run rigorous **rolling-origin, time-ordered evaluations**, including persistence/seasonal baselines, and assess post-2022 data under a frozen protocol; propagate reconstruction uncertainty into forecasts.
3. Acquire **hospital-specific admissions, observed dengue occupancy, staffing, length of stay, and operational bed availability**, with appropriate permissions and data governance.
4. Validate and update **hospital eligibility, coordinate/entrance information, patient choice, and overflow assumptions** before operational use.
5. Establish a properly governed **current surveillance ingestion and periodic retraining workflow**, resolve calendar/source discrepancies, and pilot the tool with QC public-health and hospital stakeholders.
6. Complete deployment, accessibility, security, licensing, and field usability reviews before any production deployment.

## Research use and acknowledgments

SurgeWise was developed as a **PJDSC public-health analytics project** focused on dengue preparedness in Quezon City. The team acknowledges the underlying dengue surveillance researchers and source publishers, including UPRI-NOAH, the Quezon City data sources, PhilHealth, and the authors of the epidemiological downscaling, spatial dengue, and hospital-preference studies cited in the project documentation.

**Citation and reuse:** Please attribute each dataset and paper according to its **own** license and documented provenance. UPRI materials declare **ODC-ODbL 1.0**; verify derivative obligations before redistribution. This repository snapshot does **not** contain a top-level `LICENSE` file, so no repository-wide code license is asserted here. Maintainers should add one only after agreeing on the intended permissions.

**Responsible-use principle:** SurgeWise is intended to help explore **what could happen under stated assumptions**, not to substitute for hospital administrators, verified clinical information, official surveillance, or emergency decision-making.
