# Weekly barangay reconstruction notebook — 2026-11-20

User request: create a detailed executable notebook in `notebooks/`, inspect the
linked UPRI/dengue and GIS settlement datasets, explain weekly generation math,
audit missing entries, and demonstrate mathematically justified recovery such as
median imputation. Routine main-session test-first work; no merge or deployment.

## Design and choices

Reuse the pinned UPRI annual table and QC weekly workbook. Retain downloaded
Drive originals under separate raw source directories with acquisition hashes.
The Drive annual table and workbook are byte-identical to the pinned originals.
Keep the original settlement master and its separate Tracker-backcast scenario.
Use the latter only when reconstructing the existing synthetic trial. Do not
silently harmonize the 2015/2016 product discontinuity.

Annual-preserving allocation scales QC weekly totals to the available annual
subtotal; QC-preserving allocation instead scales the annual spatial weights.
Both cannot preserve contradictory totals. Explain both; implement the existing
annual-preserving policy and a separately labeled median-imputed sensitivity.
Retain missing values in the source-preserving output. Imputed entries are
assumptions, never recovered observations. Beta and rainfall lag are assumptions.
Use IPF for floating margins and transportation-based controlled rounding for
integer margins. Independently reconstructed integers can differ from the Drive
trial because several valid rounded tables exist; compare expectations and
margin invariants separately from cell equality.

## Implementation plan and acceptance

1. Write focused tests before implementing `scripts/generate_weekly_barangay.py`.
   Test literal median results, observed-zero preservation, all-missing donors,
   donor cutoffs, mismatched/zero margins, nonconvergence, structural zeros,
   controlled rounding and incomplete calendars/ambiguous GIS joins. Run pytest
   and record meaningful failures before implementation.
2. Implement pure validation, explicit name crosswalk, median count/share donor
   recovery, largest remainder, IPF, controlled rounding and a CLI with explicit
   root/output arguments. No API, model or production artifacts change.
3. Create `notebooks/06_weekly_barangay_reconstruction.ipynb` with actual source
   inventories, missingness, reconciliation, GIS geometry/CRS audits, formulas,
   worked examples, masking evaluation, sensitivity plots, reference comparisons
   and deterministic exports under `data/processed/weekly_barangay_reconstruction/`.
4. Execute every cell with the project kernel, run focused and Python regression
   checks, compileall and whitespace checks, and review outputs against criteria.
   Record software, source/code/output hashes and uncertainty. Update repo handoff,
   one vault session note, relevant wiki memory and log. Leave merging to user.

## Edge cases and claim boundaries

Null is not zero. Never impute identifiers with a median. Use only the existing
explicit two-name project crosswalk; retain source null codes. All-missing donors
stay unknown. Backward-only donor mode cannot use later years. Missing QC weekly
counts or settlement cells block allocation. A zero QC grand total with positive
annual demand blocks allocation. Invalid numbers and duplicate keys fail. Rainfall
initial lag gaps use neutral interactions with flags, not invented measurements.
No observed weekly barangay ground truth exists; masking checks annual recovery
only. Whole-year statistics and backcasts prohibit prospective forecast claims.
