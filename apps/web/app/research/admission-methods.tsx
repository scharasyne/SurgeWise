import Link from 'next/link';
import { ArrowRight, ArrowUpRight, BedDouble, ChartNoAxesCombined, Hospital, Plus, Users } from 'lucide-react';
import AdmissionExplorer from './admission-explorer';

const sourceRoot = 'https://github.com/scharasyne/SurgeWise/blob/f8508ddb3184b3e5cc32627132c98f1548adf873';
const survey = 'https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=10';

const steps = [
  { label: 'Forecast cases', detail: 'Daily cases by barangay', Icon: ChartNoAxesCombined },
  { label: 'Expected admissions', detail: 'Apply admission rate and delay', Icon: Users },
  { label: 'First hospital', detail: 'Split arrivals by probability', Icon: Hospital },
  { label: 'Beds needed', detail: 'Count overlapping stays', Icon: BedDouble },
  { label: 'Additional beds', detail: 'Count each hospital’s shortfall', Icon: Plus },
];

export default function AdmissionMethods() {
  return <div className="rs-admission-methods">
    <ol className="rs-admission-steps" aria-label="How the bed allocation model works">
      {steps.map(({ label, detail, Icon }, i) => <li key={label}>
        <Icon size={19} aria-hidden="true" /><strong>{label}</strong><small>{detail}</small>
        {i < steps.length - 1 && <ArrowRight className="rs-flow-arrow" size={14} aria-hidden="true" />}
      </li>)}
    </ol>

    <article className="rs-card rs-choice">
      <h3>Where might a patient be admitted?</h3>
      <p>Start with a patient whose admission will take place within the 46-hospital QC network. Each barangay has its own set of 46 hospital probabilities. Nearby hospitals get more weight, equally distant hospitals start with equal weight, and even the farthest hospital keeps a positive chance.</p>
      <p>The survey map identifies an in-network preferred hospital for <strong>14 barangays</strong> after matching its colors and boundaries. The other <strong>128 have unknown preference</strong> and use distance alone.</p>
      <AdmissionExplorer />
      <details className="rs-disclosure rs-math">
        <summary>How distance and preference become a probability</summary>
        <p>Measure the straight-line distance <i>d</i> in kilometers from a representative point inside the barangay to the hospital’s provisional location. Every extra 3 km halves the starting weight. For example, a hospital 2 km away gets twice the weight of one 5 km away.</p>
        <div className="rs-equation">Distance weight = 2<sup>−d / 3</sup></div>
        <p>Multiply the mapped preferred hospital’s weight by 1.5. Every other hospital gets 1×. For an unknown preference, all 46 get 1×. Divide each adjusted weight by their sum.</p>
        <div className="rs-equation">P(first hospital | barangay, in-network admission) = hospital’s adjusted weight / sum of all 46 adjusted weights</div>
        <p>Both 3 km and 1.5× are project assumptions. The multiplier acts on the weight, so a 50% increase in weight produces a smaller relative increase in the final probability.</p>
      </details>
      <details className="rs-disclosure">
        <summary>Inside the 188-state first-order Markov chain</summary>
        <p>The starting state is one of 142 barangays. The next state depends only on that origin under the selected assumptions. One step records the first hospital. The 46 hospital states are absorbing, so the model records no transfers. A separate length-of-stay calculation determines when a bed is released.</p>
        <div className="rs-table-wrap"><table className="rs-table rs-matrix-blocks">
          <caption>Transition matrix · 142 barangays + 46 hospitals</caption>
          <thead><tr><th scope="col">From</th><th scope="col">To a barangay</th><th scope="col">To a hospital</th></tr></thead>
          <tbody>
            <tr><th scope="row">Barangay</th><td>0</td><td>One of 46 destination probabilities</td></tr>
            <tr><th scope="row">Hospital</th><td>0</td><td>1 for itself, 0 for every other hospital</td></tr>
          </tbody>
        </table></div>
        <a className="rs-link" href={sourceRoot + '/data/processed/qc_first_admission_preference_v1/markov_chain.csv'}>View the full preference-adjusted matrix (CSV) <ArrowUpRight size={13} aria-hidden="true" /></a>
      </details>
    </article>

    <article className="rs-card">
      <h3>When does a hospital need more beds?</h3>
      <p>Suppose a hospital starts empty, has four staffed dengue beds, and each admission needs a bed for three days. On Wednesday, Monday’s two patients and Tuesday’s three still need beds when one more arrives.</p>
      <table className="rs-stay-table">
        <caption>Illustrative three-day stay at one hospital</caption>
        <thead><tr><th scope="col">Hospital demand</th>{['Mon', 'Tue', 'Wed'].map(d => <th scope="col" key={d}>{d}</th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">New arrivals</th><td>2</td><td>3</td><td>1</td></tr>
          <tr><th scope="row">Beds needed</th><td>2</td><td>5</td><td>6</td></tr>
          <tr><th scope="row">Beds short</th><td>0</td><td>1</td><td><strong>2</strong></td></tr>
        </tbody>
      </table>
      <p><strong>Beds needed now</strong> adds up demand rounded up to a whole staffed bed at each hospital. <strong>Beds short now</strong> adds up the extra staffed beds each hospital would need beyond its assumed capacity. Spare beds elsewhere cannot cover this hospital’s shortfall under first-hospital allocation.</p>
      <details className="rs-disclosure rs-math">
        <summary>Daily arrivals, length of stay and shortage equations</summary>
        <div className="rs-equation">
          <div>Arrivals(h, t) = Σ<sub>b</sub> Cases(b, t − delay) × rate × P(h | b, admission)</div>
          <div>Beds(h, t) = Σ<sub>k = 0…stay − 1</sub> Arrivals(h, t − k)</div>
        </div>
        <p>Here <i>b</i> is a barangay, <i>h</i> is a hospital and <i>t</i> is a day. Use zero for arrivals before the start of this empty-census example.</p>
        <dl>
          <dt>Daily arrivals at a hospital</dt><dd>For each barangay, multiply its forecast cases by the assumed admission fraction and its probability of choosing this hospital. Shift the arrivals forward by the admission delay, then add all barangays’ contributions.</dd>
          <dt>Expected beds needed today</dt><dd>Add today’s expected arrivals to earlier arrivals still within their assumed stay. With a four-day stay and zero starting dengue census, sum today and the previous three days in the scenario.</dd>
          <dt>Assumed staffed dengue capacity</dt><dd>Normal staffed beds × (1 − fraction occupied by other patients) + activated staffed surge beds. Holding spaces are counted separately.</dd>
          <dt>Additional beds at one hospital</dt><dd>Round up max(0, expected beds needed − assumed staffed dengue capacity). Sum these whole-bed shortfalls across hospitals.</dd>
          <dt>Shortage attributed to a barangay</dt><dd>Multiply each hospital’s unrounded shortfall by the barangay’s share of that hospital’s expected arrivals, then add across hospitals. A barangay accounting for 75% of arrivals at a hospital short by four beds accounts for three of those beds.</dd>
        </dl>
      </details>
      <details className="rs-disclosure">
        <summary>What changed in the saved 28-day comparison?</summary>
        <p>In the historical QC example starting 29 January 2025 under the project’s calendar assumption, St. Luke’s peak expected dengue bed demand went from <strong>0.480</strong> with distance alone to <strong>0.513</strong> with preference. Both round up to one staffed bed. Both runs assume 15% admissions, zero delay, an empty starting census and a four-day stay. Changing the hospital probabilities preserves the city’s expected admissions and expected bed demand each day. <a href={sourceRoot + '/data/processed/qc_first_admission_preference_v1/peak_bed_comparison.csv'}>See all 46 peak estimates</a></p>
      </details>
      <Link className="rs-link" href="/outbreak-response" prefetch={false}>Compare hospital-choice assumptions in Simulation <ArrowRight size={14} aria-hidden="true" /></Link>
    </article>

    <details className="rs-disclosure rs-disclosure-card rs-allocation-evidence">
      <summary>Evidence, assumptions and unknowns</summary>
      <dl>
        <dt>Survey evidence</dt><dd>Chua et al. (2021) studied 19 QC tertiary hospitals and surveyed residents from 76 barangays. Figure 4 maps stated emergency preferences. The project could match both the barangay and an in-network hospital for 14 of 142 origins. <a href={survey}>Read Figure 4</a> · <a href={sourceRoot + '/data/reference/qc_emergency_hospital_preferences_figure4.csv'}>Inspect the barangay matches</a></dd>
        <dt>Unknown preference</dt><dd>For 128 barangays, the figure has no clear match, the map and text disagree, or the named hospital is outside the register. Gray has no defined meaning in the legend. Each of these barangays uses distance alone. <a href={sourceRoot + '/docs/first-admission-matrix.md#figure-4-review'}>See the review of Figure 4</a></dd>
        <dt>Scenario assumptions</dt><dd>The model assumes all 46 listed facilities can receive a dengue admission. It uses straight-line distances and excludes road routes and destinations outside the network. Research on distance decay motivates testing how weights change with distance. The 3 km and 1.5× settings have no local dengue calibration. <a href="https://doi.org/10.1186/s12913-019-3969-5">Delamater et al. (2019)</a> · <a href={sourceRoot + '/docs/hospital-allocation-decisions.md'}>Read the allocation decisions</a></dd>
        <dt>Unknown in practice</dt><dd>Observed dengue admissions by origin and hospital, verified entrances and live staffed vacancies are unavailable. Forecast backtests score case counts. Actual admission flows would be needed to validate the hospital probabilities. The September 2026 PhilHealth register reports accredited beds. <a href="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf">Read the PhilHealth register</a></dd>
      </dl>
    </details>
  </div>;
}
