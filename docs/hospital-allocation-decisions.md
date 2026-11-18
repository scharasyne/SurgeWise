# How SurgeWise allocates first dengue admissions to QC hospitals

Decision record · 19 November 2026 · Quezon City (QC) preparedness research

**Agreed rule.** Only some QC barangays have an identifiable preferred emergency hospital in the published survey. If Figure 4 shows a clear match, the preference scenario gives that hospital extra weight on top of straight-line proximity. **For every barangay without a clear match, record hospital preference as unknown (`null`) and allocate its modeled admissions across all 46 hospitals using straight-line proximity alone.** This includes gray areas and ambiguous matches. Unknown describes the available survey evidence. The distance penalty and the size of any preference boost are project assumptions. [Chua et al. (2021), survey coverage in §4.1][coverage] · [Figure 4 and §4.3][fig4]

**Implementation status.** The QC workspace currently defaults to an equal split across the nearest three hospitals for its arrival projection. The separate working-tree first-admission export already calculates a positive distance-based share for every hospital. The Figure 4 adjustment and the comparisons below are the agreed design for an extension. Selection of a final multiplier remains open. [Workspace defaults](../services/engine/api/qc_simulation.py) · [Existing choice policies](../services/engine/domain/hospital_demand.py) · [Offline export and assumptions](first-admission-matrix.md)

## What a probability means

One row represents a barangay. Each cell answers **“Given that one dengue case from this barangay will be admitted somewhere in the modeled QC network, what is the probability of first admission at this hospital?”** First apply the scenario admission fraction to projected cases. Then allocate those admissions across hospitals. Include all 142 barangays. A hotspot is a barangay with many cases in the selected period, so it can contribute more admissions without changing its destination probabilities. Daily barangay demand is allocated from a QC forecast using annual barangay evidence. [Barangay forecast methods](barangay-xgboost-ranking.md) · [Forecast and bed-demand assumptions](future-seasonal-simulation.md)

The first-order Markov chain makes one destination decision from the current barangay. In the full 188-state matrix, barangay-to-barangay transitions are zero, and each hospital has a self-transition of one. This records the end of the first-admission episode. Length of stay is handled separately. All 46 PhilHealth hospital/infirmary records are assumed eligible for this exercise, and all modeled admissions stay within the network. Actual dengue eligibility and staffed capacity are unknown. The September 2026 register identifies facilities and their accredited beds. Supplementary maternity sites and the legacy NHFR registry are outside this choice set. [First-admission matrix](first-admission-matrix.md) · [Hospital inventory and field definitions](hospital-dataset-source-of-truth.md)

## Proximity applies to every hospital

Measure distance in kilometers from a representative point inside each barangay polygon to each provisional hospital point using the Haversine formula. Road routes, travel times and verified entrance locations are outside scope. Every hospital starts with the same base weight. For barangay $b$ and hospital $h$, let $d_{bh}$ be that distance and $L>0$ the **half-distance** in kilometers. The proximity weight is $w_{bh}=2^{-d_{bh}/L}$. Equal distances give equal weights. An extra $L$ kilometers halves the weight, and a farther hospital always retains a positive share. [Project geometry method](../services/engine/domain/outbreak.py) · [Tai et al. (2004), straight-line distances and hospital bypass][tai] · [Leyso & Umezaki (2024), Philippine inpatient accessibility][leyso]

| Distance setting discussed | Rationale and limits |
| --- | --- |
| **3 km** in the worked export | An illustrative project choice. Two otherwise identical hospitals at 2 and 5 km receive weights in a 2:1 ratio. No reviewed study established this value for first dengue admissions in QC. The **1.5 and 6 km** alternatives explored stronger and weaker proximity assumptions. [Worked example](first-admission-matrix.md) |
| **About 10 km** as an external comparison | Dotse-Gborgbortsi et al. estimated 6.7% lower origin–hospital birth flows per additional straight-line kilometer in Ghana. Our conversion of that estimate gives $0.933^{10}\approx0.50$. This benchmarks a weaker distance effect in a different population and type of care. [Dotse-Gborgbortsi et al. (2020)][ghana] |
| **5 and 30 km** in a Philippine study | Leyso and Umezaki used full inpatient accessibility weight through 5 km and reduced it to zero at 30 km. Those are boundaries of their chosen accessibility function. SurgeWise uses exponential decay to preserve all 46 destinations. [Leyso & Umezaki (2024), equation 3 and limitations][leyso] |

## How Figure 4 changes a barangay row

Use the published emergency-preference figure as the source. Its seven fill colors identify hospitals. The H markers indicate hospital locations and ownership. The survey covered 19 tertiary hospitals, with respondents from 76 of 142 QC barangays, primarily from middle- and upper-income groups. Figure 4 supplies neither a vote share nor a dengue admission count for a colored area. Gray has no defined category in the legend. The reported coverage cannot establish why any particular polygon is gray. [Chua et al. (2021), §§4.1–4.3][fig4]

| Figure 4 evidence | Recorded preference | Adjustment in that barangay |
| --- | --- | --- |
| Color and boundary confidently matched to a barangay, and named hospital matched to a register ID | Record the barangay ID, hospital ID, and figure or passage supporting the match | Multiply that hospital's weight by the scenario multiplier $m$. Give every other hospital a multiplier of 1. |
| Gray polygon, ambiguous boundary or color, or unresolved hospital match | Record the preferred hospital as `null` (unknown) | Use a multiplier of 1 for all hospitals. The resulting probabilities still vary with distance. |

For two matches that can be checked by name, the authors explicitly associate **U.P. Campus with East Avenue Medical Center** and **Teachers Village East with Philippine Heart Center**. A hospital's position in the legend, the number of polygons of a given color, or the citywide list of popular hospitals cannot supply individual vote shares. Use a common $m$ for known favorites because preference strength by barangay is unavailable. The multiplier explores extra weight beyond proximity, which may already explain some reported choices. [Chua et al. (2021), Figure 4][fig4] · [Figures 7–8 and accompanying text][matches]

Let $a_{bh}$ equal $m$ for the mapped favorite and 1 otherwise. Normalize **after** applying the adjustment. This follows the multinomial logit form used in studies of hospital choice. The exponential distance weight and Figure 4 multiplier specify SurgeWise's particular scenario. [Smith et al. (2018), equation 1][smith]

$$
P_{bh}=\frac{w_{bh}a_{bh}}{\sum_{j=1}^{46}w_{bj}a_{bj}}.
$$

**Illustrative three-hospital row.** Suppose proximity gives A, B and C shares of 40%, 40% and 20%. If B is the mapped favorite and $m=1.5$, the adjusted weights are 40, 60 and 20. Dividing by 120 gives **33⅓%, 50% and 16⅔%**. An otherwise identical gray barangay keeps 40%, 40% and 20%. All 46 probabilities in a production-sized scenario must be finite, positive and sum to one within numerical tolerance.

## How to compare bed demand

**Compare like with like.** Use $m=1$ as the proximity-only baseline and the same $m>1$ for all identifiable favorites within a given comparison run. The suggested sensitivity settings are **1.25×, 1.5× and 2×**. With only two equidistant choices, these give the favorite about **56%, 60% and 67%**, respectively. They are transparent assumptions. The team still needs to choose the reported settings before inspecting results. Hold $L$ fixed while testing $m$, then repeat at another $L$ to examine distance sensitivity. Testing distance decay against alternative settings follows the approach of Delamater et al. [Delamater et al. (2019)][delamater]

Hold the QC forecast, barangay shares, facility list, dates, admission fraction, admission delay, starting census and stay length fixed across paired runs. For each day, sum each barangay's expected admissions times its destination probabilities. For each hospital, sum the arrivals still within their assumed stay. The worked 28-day export assumes **15% admissions, zero delay, zero initial dengue census and a four-day stay**. It applies the 2026 register to a historical 2025 forecast. These are scenario inputs and the output is expected occupied dengue beds if arrivals can be admitted. Actual placements under finite capacity require separate capacity assumptions. [Worked scenario](first-admission-matrix.md) · [Rolling bed-demand calculation](../services/engine/domain/bed_forecast.py)

Report each hospital's baseline and adjusted **peak expected beds**, their difference in beds, and any change in rank. Also report how many of the 142 barangays had a traceable favorite matched to a register ID. As arithmetic checks, gray rows must match their baseline, daily hospital arrivals must sum to the same QC admission demand, and the citywide daily bed total must agree across paired runs under the shared stay assumptions. Any comparison of the proximity-only ranking with Figure 4 should use the comparable surveyed hospitals. Once a favorite helps construct a row, agreement with it is an in-sample result.

## References

- Chua, C. A., Lao, F. G. G., Peralta, M. H., & Regidor, J. R. (2021). *An exploratory study on GIS-based suitability analysis of tertiary hospitals in Quezon City from the transportation perspective*. 27th Annual Conference of the Transportation Science Society of the Philippines. [Conference proceedings](https://ncts.upd.edu.ph/tssp/archives/1529)
- Delamater, P. L., Shortridge, A. M., & Kilcoyne, R. C. (2019). Using floating catchment area (FCA) metrics to predict health care utilization patterns. *BMC Health Services Research, 19*, 144. [Article][delamater]
- Dotse-Gborgbortsi, W., Dwomoh, D., Alegana, V., Hill, A., Tatem, A. J., & Wright, J. (2020). The influence of distance and quality on utilisation of birthing services at health facilities in Eastern Region, Ghana. *BMJ Global Health, 4*(Suppl. 5), e002020. [Article][ghana]
- Leyso, N. L., & Umezaki, M. (2024). Spatial inequality in the accessibility of healthcare services in the Philippines. *GeoJournal, 89*, 120. [Article][leyso]
- Smith, H., Currie, C., Chaiwuttisak, P., & Kyprianou, A. (2018). Patient choice modelling: How do patients choose their hospitals? *Health Care Management Science, 21*, 259–268. [Article][smith]
- Tai, W.-T. C., Porell, F. W., & Adams, E. K. (2004). Hospital choice of rural Medicare beneficiaries: Patient, hospital attributes, and the patient–physician relationship. *Health Services Research, 39*(6), 1903–1922. [Article][tai]

[fig4]: https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=10
[coverage]: https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=9
[matches]: https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=13
[delamater]: https://doi.org/10.1186/s12913-019-3969-5
[ghana]: https://doi.org/10.1136/bmjgh-2019-002020
[leyso]: https://doi.org/10.1007/s10708-024-11098-3
[smith]: https://doi.org/10.1007/s10729-017-9399-1
[tai]: https://doi.org/10.1111/j.1475-6773.2004.00324.x
