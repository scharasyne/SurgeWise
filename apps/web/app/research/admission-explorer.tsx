'use client';

import { useState } from 'react';
import WorkspaceSelect from '@/components/workspace-select';
import evidence from './data/first-admission.v1.json';

const originOptions = evidence.barangays.map(({ id, name }) => ({ value: id, label: name }));
const campus = 'PH1307404124';
const batasan = evidence.barangays.find(b => b.name === 'Batasan Hills')!.id;
const eastAvenue = 'HOSP-628';
const percent = (value: number) => (value * 100).toFixed(2) + '%';

export default function AdmissionExplorer() {
  const [selected, setSelected] = useState(campus);
  const origin = evidence.barangays.find(b => b.id === selected)!;
  // The exporter omits a duplicate row only after verifying exact equality.
  const adjusted = origin.withPreference ?? origin.distanceOnly;
  const hospitals = evidence.hospitals.map((h, i) => ({
    ...h, km: origin.km[i], base: origin.distanceOnly[i], adjusted: adjusted[i],
  })).sort((a, b) => b.adjusted - a.adjusted || a.id.localeCompare(b.id));
  const focus = hospitals.find(h => h.id === (origin.preferredId ?? eastAvenue))!;
  const chart = hospitals.filter((h, i) => i < 3 || h.id === focus.id);
  const scale = Math.max(...chart.map(h => Math.max(h.base, h.adjusted)));

  return <div className="rs-admission-explorer">
    <div className="rs-origin-toolbar">
      <div className="rs-control">
        <label htmlFor="rs-admission-origin">Barangay of origin</label>
        <WorkspaceSelect id="rs-admission-origin" label="Barangay of origin" value={selected} options={originOptions} onChange={setSelected} />
      </div>
      <button className="text-button rs-example-button" type="button" onClick={() => setSelected(origin.preferredId ? batasan : campus)}>
        {origin.preferredId ? 'Try an unknown preference' : 'Try a mapped preference'}
      </button>
    </div>

    <div className="rs-choice-reading" aria-live="polite" aria-atomic="true">
      <strong>{origin.preferredId ? 'Mapped preferred hospital' : 'Unknown hospital preference'}</strong>
      {origin.preferredId
        ? <p>{origin.name} has a mapped preference for {focus.name}. At {focus.km.toFixed(2)} km, its share rises from <b>{percent(focus.base)}</b> to <b>{percent(focus.adjusted)}</b> when its weight is multiplied by {evidence.preferredMultiplier}.</p>
        : <p>{origin.name} uses distance alone for all 46 hospitals in both scenarios. For example, East Avenue Medical Center is {focus.km.toFixed(2)} km away and receives <b>{percent(focus.base)}</b> in both.</p>}
    </div>

    <figure className="rs-share-chart">
      <figcaption><strong>First-hospital probability in {origin.name}</strong>
        <span>Three largest shares with preference applied{chart.length > 3 ? ', plus the example hospital' : ''}. Both columns use the same scale.</span>
      </figcaption>
      <table>
        <thead><tr><th scope="col">Hospital</th><th scope="col">Distance only</th><th scope="col">With preference</th></tr></thead>
        <tbody>{chart.map(h => <tr key={h.id}>
          <th scope="row">{h.name}<small>{h.km.toFixed(2)} km{h.id === origin.preferredId ? ' · Preferred' : ''}</small></th>
          {[h.base, h.adjusted].map((value, i) => <td key={i}>
            {percent(value)}<span className="rs-share-track" aria-hidden="true"><i style={{ width: (100 * value / scale) + '%' }} /></span>
          </td>)}
        </tr>)}</tbody>
      </table>
    </figure>
    <p className="rs-note">Read a 5% share as five expected first arrivals per 100 in-network admissions from this barangay. Both scenarios use the same cases, admission rate, delay, length of stay and capacity. The choice rule redistributes demand across hospitals.</p>
    <details className="rs-disclosure">
      <summary>All 46 hospital probabilities for {origin.name}</summary>
      <div className="rs-table-wrap rs-table-scroll" tabIndex={0} role="region" aria-label={'Hospital probabilities for ' + origin.name}>
        <table className="rs-table rs-destinations">
          <thead><tr><th scope="col">Hospital</th><th scope="col">Distance (km)</th><th scope="col">Distance only</th><th scope="col">Preference weight</th><th scope="col">With preference</th></tr></thead>
          <tbody>{hospitals.map(h => <tr key={h.id}>
            <td>{h.name}</td><td>{h.km.toFixed(2)}</td><td>{percent(h.base)}</td>
            <td>{h.id === origin.preferredId ? evidence.preferredMultiplier : 1}×</td><td>{percent(h.adjusted)}</td>
          </tr>)}</tbody>
          <tfoot><tr><th scope="row">All hospitals</th><td></td><td>{percent(origin.distanceOnly.reduce((a, b) => a + b, 0))}</td>
            <td></td><td>{percent(adjusted.reduce((a, b) => a + b, 0))}</td></tr></tfoot>
        </table>
      </div>
      <p>Each row of the model sums to 100% before display rounding. Every destination in this table belongs to the selected barangay’s row.</p>
    </details>
  </div>;
}
