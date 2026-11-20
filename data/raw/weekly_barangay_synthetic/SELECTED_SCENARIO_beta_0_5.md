# Selected scenario: beta = +0.5

This selection supersedes beta = 0 as the group's chosen experimental scenario. The previous Final_Audit_Weekly_Barangay_Baseline audit remains applicable only to beta = 0. The existing generation notebook and trial report already document all three scenarios; the algorithm was not refitted or recalibrated to select this scenario.

## Presentation wording

We generated synthetic weekly barangay allocations under a positive settlement-rainfall interaction scenario (beta = +0.5). This assumes that more built-up barangays have a relatively stronger allocation response during wetter periods, using rainfall lagged by four source blocks. The coefficient and lag are scenario assumptions, not effects estimated from observed weekly barangay cases. IPF and controlled rounding preserve available annual barangay counts and explicitly scaled QC weekly targets. The resulting allocations are not observed weekly surveillance data.

## Implemented seed

K(b,y,w) = exp[0.5 * z(settlement proportion b,y) * z(city rainfall lagged by four source blocks)].

Settlement is standardized across known-count barangays within each year. Lagged city rainfall is standardized over available blocks within each year. The first four source records lack prior rainfall; their interaction is neutral and flagged in the rainfall audit. Beta = +0.5 does not mean a 50% increase in cases. Annual counts are fixed; the interaction changes the within-year distribution, followed by fitting to the scaled weekly targets. The magnitude 0.5 is illustrative and is not scientifically calibrated for QC.

## Selected output and verification

File: synthetic_weekly_positive_beta_0_5.csv.
118,144 rows; 116,116 populated synthetic count rows and 2,028 missing weekly rows associated with 39 blank annual barangay-year entries. Integer annual and scaled weekly margins were rechecked and match exactly. The source discrepancy remains: this does not preserve the original QC weekly counts. Original missing annual entries were not imputed.

## Presentation and training cautions

Call this the selected positive-interaction scenario, not the best or validated scenario. Do not claim greater real forecasting accuracy because a model fits these synthetic targets. Disclosing the assumption makes the scenario transparent but does not validate actual local weekly timing. Report observed citywide model performance separately and use the beta = 0 / negative-interaction results as sensitivity comparisons. The 2010-2015 settlement inputs are extrapolated; annual totals and whole-year scaling make this a retrospective reconstruction experiment. The prior baseline plot cell filters beta = 0 and must be changed before plotting the selected scenario.

CSV SHA-256: 0c9316e52784aba8ad4860e5b7e903c1262c4cf8c9ecaa1527905a24f8e733d0
