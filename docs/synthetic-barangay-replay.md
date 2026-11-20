# QC synthetic weekly barangay replay

On the brgy-forecasting branch, open **Simulation → Synthetic barangay replay**. Use a saved date window and advance playback. Select a barangay on the map or open **Results → All barangays** to see the four weekly point estimates. The date controls can select part of a source week. Weekly columns always show the entire source block's baseline forecast. Window totals include only selected days and any configured stress overlay.

The default is the retrospective RandomForest selected using 2022 in the [Drive experiment](https://drive.google.com/drive/folders/1gfU3DU0itB6u1X5DNw-yOhCjeg_fqmxM). Training used 2010–2021 synthetic barangay counts. The beta +0.5 generation scenario uses complete annual totals and whole-year scaling. Its scores measure agreement with those synthetic targets. Accuracy against real weekly barangay cases and forecast intervals are unknown.

The branch serves the original fitted model's **saved predictions** for 196 origins during 2022–2025. Each origin contains four horizons per included barangay. Depending on origin, 135–142 of the 142 QC IDs have predictions. The API and export identify missing places by name and code. The hospital simulator computes demand only for covered places. It divides each prediction over the days in its target block under the January 1, 52-block calendar assumption. Each day uses the covered sum, with no spatial redistribution of missing places. Hospital admissions, staffing and choice of facility remain scenario assumptions.

## Hospital planning

Open **Set up scenario** to choose the saved forecast period, case scenario and hospital assumptions. The default routes admissions to their first hospital using distance and the mapped preference where available. Turn on the comparison in Results to compare those placements with distance alone under the same dated demand and capacity assumptions. Each hospital retains its own shortage. The map shows up to three of the largest modeled placement flows per selection.

For each source week, each covered barangay contributes its own predicted cases multiplied by the assumed admission rate and its hospital-choice probabilities. Admission delay shifts the arrival date. Occupied beds include arrivals still within their assumed stay, so a shortage can reflect demand from two forecast weeks. A barangay’s contribution to a hospital’s shortage follows its share of that occupied demand. The saved JSON includes the choice matrix digest and the origin shares for each forecast horizon.

## API and artifacts

GET or POST to `/v1/synthetic-barangay-simulation` (Next.js proxy `/api/research/synthetic-barangay-simulation`). GET opens the 2025 source week 4 origin. POST accepts the QC window and assumption controls. Saved predictions are selected from the most recent single origin covering the entire requested window. Unsupported dates return 422. Missing or damaged prediction bytes return 503. Readiness reports `syntheticBarangayForecast` and `defaultWorkspaceReady`. The existing environmental replay contract remains at `/v1/qc-simulation` and the separate seasonal planning contract at `/v1/future-simulation`.

The compact derivative in `data/processed/upri_noah/synthetic-barangay-rf.json.gz` contains the RandomForest prediction column and provenance. The server reads it offline. Model identity, source hashes, training input hashes, feature order, software versions, origin, four targets, coverage and per-place predictions travel with the result and JSON export. The CSV also contains synthetic reference labels and predictions from comparison models, which do not supply demand here.

To rebuild, download the three original files from the linked starter experiment into one directory. From the project root run:

```bash
.venv/bin/python scripts/import_synthetic_barangay.py \
  --metadata /path/to/experiment_metadata.json \
  --model /path/to/RandomForest.joblib \
  --predictions /path/to/predictions_synthetic_targets.csv
```

The importer checks all three upstream SHA-256 digests, local QC codes, horizon alignment, unique keys, nonnegative finite counts and completeness before replacing the derivative. The runtime pins the digest of its decompressed contents. The joblib was produced with scikit-learn 1.6.1. Serving the exported predictions avoids a runtime dependency on its serialized estimator or preprocessing environment. This integration supports saved origins only.
