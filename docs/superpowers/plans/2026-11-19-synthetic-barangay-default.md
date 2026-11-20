# Synthetic barangay forecast implementation plan

Approved design: ../specs/2026-11-19-synthetic-barangay-default-design.md

1. Verify Drive artifact hashes, selected RandomForest, forecast keys, per-origin coverage, and exact January 2025 predictions. Add failing regression tests for the API and UI defaults.
2. Import the prediction column with a deterministic script, validate four horizons per covered barangay, and pin a compact derivative in the repository. Preserve source files externally and support an offline runtime.
3. Feed dated per-place values into movie generation, including partial weeks and the last source block of each year. Use the same daily demand for baseline, optimization and bed forecasts. Expose missing IDs, weekly values, model provenance and absent intervals. Keep existing v1 replay requests compatible through a distinct synthetic route.
4. Point the QC workspace's initial request, POST and evidence display at synthetic replay. Show all four forecast horizons, selected-window ranks and coverage. Retain the explicit seasonal planning tab.
5. Exercise real saved outputs, date validation, partial coverage and API/BFF/UI integration, then run existing engine/web checks and update handoffs.
