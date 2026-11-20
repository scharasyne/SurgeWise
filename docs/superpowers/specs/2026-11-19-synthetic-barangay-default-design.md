# Synthetic weekly barangay model as branch default

Status: approved for implementation on 2026-11-19.

## Intent and scope

On `brgy-forecasting`, use the Drive experiment's selected RandomForest to provide 1–4-week barangay predictions in the QC forecast workspace and its downstream hospital simulation. Display these as a synthetic-data research experiment. Preserve unrelated working-tree changes and existing historical artifacts. Leave merging to the user.

## Approaches

The user selected making synthetic barangay forecasts the branch default, with QC demand summed from those predictions. The alternative was a separate synthetic experiment mode retaining the observed-data QC model as the default. RandomForest is selected by the supplied experiment metadata; XGBoostRF remains a comparison artifact.

## Evidence and boundaries

Drive folder: https://drive.google.com/drive/folders/1vwLkZAg6iKpK-HlCJkygcsz-MlkFmVc5

Experiment: `synthetic_barangay_rf_xgbrf/20261118_154549_934553_starter`. Its metadata selects RandomForest using 2022, trains on 2010–2021, and provides test predictions for 2023 and an extension for 2024–2025. The selected synthetic generation scenario is beta +0.5. Inputs include synthetic barangay case lags, citywide weather lags, settlement proportion, seasonality and barangay code.

The labels use complete annual totals, whole-year scaling and retrospective standardization. Chronological train/test splitting does not remove that hindsight. Scores describe agreement with synthetic allocations, not real weekly barangay forecasting accuracy. No forecast uncertainty intervals were estimated. Synthetic city totals need not equal observed QC weekly totals. Missing labels remain unknown. This source cannot establish prospective or live 2026 forecasts.

## Integration design

- Pin source artifacts and checksums, model selection, feature order, training period, software versions and interpretation. Inspect the supplied serialized model and preprocessing compatibility before inference; never silently retrain or substitute XGBoostRF.
- Import approved saved predictions into dated server-owned forecast runs for supported origins. Verify schema, finite nonnegative counts, unique barangay/origin/horizon keys, target ordering and the official 142-barangay ID crosswalk. Expose actual coverage and missing barangays. Inference beyond saved origins requires the exact preprocessing and inputs; otherwise return unavailable.
- Use each barangay's own weekly prediction, uniformly split within the existing declared source-block dating assumption. Sum the same available predictions for QC demand; show partial coverage explicitly and never silently scale it to all QC. Rank modeled barangay burden over the selected simulation window rather than presenting annual XGBoost ranks as weekly forecasts.
- Feed these dated barangay trajectories into the existing patient-flow, hospital and allocation services. Keep the PhilHealth hospital source, provisional coordinate status and assumed capacity/clinical parameters. Preserve deterministic conservation and comparison on identical inputs.
- Update the default workspace, evidence panels, map/table labels and exports consistently. Show synthetic model identity, origin, coverage and training provenance. Keep source observations separate. Return uncertainty as unavailable; do not reuse city residual intervals or fabricate zero-width intervals.
- Preserve historical and seasonal model artifacts and legacy-route safety gates. Do not relabel saved historical targets as future forecasts. Any affected workspace lacking synthetic inputs returns an actionable unavailable state instead of silently using another model.

## Acceptance criteria and checks

Focused tests must fail meaningfully before implementation, then pass for artifact integrity, ID mapping, missing coverage, unsupported dates, invalid/duplicate counts, four consecutive horizons, per-barangay trajectories and QC sum conservation. Test synthetic labeling and unavailable intervals in API/UI/export paths. Verify identical-input allocation comparisons and existing historical safety gates. Run relevant Python and frontend tests, syntax, lint, types and build; report checks not run. Record test evidence and review in the repository handoff and one wiki session note.

## Inspection checkpoint before implementation

The exact serialized pipeline structure, local compatibility with scikit-learn 1.6.1/Python 3.13.18 from the experiment, prediction CSV columns and per-origin coverage remain unverified. Resolve them by inspection and focused tests before loading or publishing new approved runs. A missing source is a blocker, never permission to invent data.

The completed checks and the selected offline replay approach are documented in [the implementation guide](../../synthetic-barangay-replay.md).
