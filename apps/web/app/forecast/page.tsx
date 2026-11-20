'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ENGINE_STARTING_MESSAGE, fetchResearch } from '@/lib/engine-connection';
import WorkspaceSelect from '@/components/workspace-select';
import './forecast.css';

type Week = { year: number; week: number };
type Estimate = Week & { horizon: number; expected_cases: number; scenario_expected_cases: number; scenario_multiplier: number };
type Forecast = {
  model: string; trained_through: number; feature_history_through: number; as_of: Week;
  city: Estimate[]; barangays: (Estimate & { barangay_code: string; barangay: string })[];
};

const formatWeek = ({ year, week }: Week) => `${year} · week ${week}`;
const cases = new Intl.NumberFormat('en', { maximumFractionDigits: 2 });
const horizons = Array.from({ length: 6 }, (_, i) => ({
  value: String(i + 1), label: i === 0 ? '1 week' : `${i + 1} weeks`,
}));

async function readObservations(file: File | null) {
  if (!file) return {};
  if (file.size > 2 * 1024 * 1024) throw Error('Choose an observations file smaller than 2 MiB.');
  let data;
  try { data = JSON.parse(await file.text()); }
  catch { throw Error('The observations file must contain valid JSON.'); }
  if (!data || !Array.isArray(data.city_updates) || !data.city_updates.length ||
      Object.keys(data).some(key => !['city_updates', 'local_updates'].includes(key))) {
    throw Error('Supply a JSON object with a nonempty city_updates list and optional local_updates.');
  }
  return data;
}

export default function ForecastPage() {
  const [weeks, setWeeks] = useState('6');
  const [multiplier, setMultiplier] = useState('1');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Forecast | null>(null);
  const [place, setPlace] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setResult(null); setError(''); setStatus('Preparing forecast…');
    try {
      const observations = await readObservations(file);
      const response = await fetchResearch('/api/research/predict', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ ...observations, weeks_ahead: Number(weeks), multiplier: Number(multiplier) }),
      }, state => setStatus(state === 'starting' ? ENGINE_STARTING_MESSAGE :
        state === 'connecting' ? 'Connecting to the forecast engine…' : 'Calculating weekly forecasts…'));
      const data = await response.json();
      if (!response.ok) {
        const issue = Array.isArray(data.detail) ? data.detail[0] : null;
        throw Error(data.error || data.detail?.message ||
          (issue && `${issue.loc.slice(1).join('.')}: ${issue.msg}`) || 'Forecast request failed.');
      }
      if (!controller.signal.aborted) { setPlace(''); setResult(data); }
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Forecast unavailable.');
    } finally {
      if (!controller.signal.aborted) setStatus('');
    }
  }

  const rows = place ? result?.barangays.filter(row => row.barangay_code === place) : result?.city;
  const scenario = result?.city.some(row => row.scenario_multiplier !== 1);
  const placeOptions = [{ value: '', label: 'Quezon City total' }, ...(result?.barangays ?? [])
    .filter(row => row.horizon === 1).map(row => ({ value: row.barangay_code, label: row.barangay }))];

  return <main className="weekly-forecast">
    <h1>Weekly dengue forecast</h1>
    <p>Estimate Quezon City cases for the weeks following your latest observation. The bundled history ends at morbidity week 52 of 2022.</p>
    <form onSubmit={run} onChange={() => { setResult(null); setError(''); }}>
      <fieldset disabled={!!status}>
        <legend>Forecast settings</legend>
        <div className="weekly-fields">
          <div><label htmlFor="forecast-horizon">Forecast horizon</label>
            <WorkspaceSelect id="forecast-horizon" label="Forecast horizon" value={weeks} options={horizons}
              onChange={value => { setWeeks(value); setResult(null); setError(''); }} /></div>
          <label>Scenario multiplier (×)
            <input type="number" min="1" step="any" required value={multiplier} onChange={e => setMultiplier(e.target.value)} />
          </label>
        </div>
        <details>
          <summary>{file ? `Observations from ${file.name}` : 'Add newer observations'}</summary>
          <p>Upload weekly QC city counts starting at 2023 week 1, or supply at least 53 consecutive recent weeks. Use the 52-week morbidity calendar. Optional barangay counts must match a supplied city week.</p>
          <p>JSON file format (example values)</p>
          <pre>{'{"city_updates":[{"year":2023,"week":1,"city_cases":55}],\n "local_updates":[{"year":2023,"week":1,"barangay_code":"PH1307404001","cases":2}]}'}</pre>
          <label>Weekly observations (.json)
            <input ref={upload} type="file" accept=".json,application/json" onChange={e => setFile(e.target.files?.[0] ?? null)} />
          </label>
          {file && <button type="button" onClick={() => {
            if (upload.current) upload.current.value = '';
            setFile(null); setResult(null); setError('');
          }}>Use bundled history</button>}
        </details>
        <button className="btn" type="submit">Run forecast</button>
      </fieldset>
    </form>
    {status && <p role="status">{status}</p>}
    {error && <p role="alert">{error}</p>}
    {result && <section aria-label="Forecast results">
      <h2>Forecast cases</h2>
      <p>Observations end at <strong>{formatWeek(result.as_of)}</strong>{file ? ' (uploaded observations)' : ' (bundled history)'}.
        {' '}Model {result.model} was trained through {result.trained_through}. Annual features and seasonal profiles use data through {result.feature_history_through}.</p>
      {file && <p>New observations update the model’s case history. Accuracy for later years has yet to be established.</p>}
      <WorkspaceSelect label="Forecast area" value={place} onChange={setPlace} options={placeOptions} />
      <table>
        <caption>{placeOptions.find(option => option.value === place)?.label} · expected weekly cases</caption>
        <thead><tr><th scope="col">Morbidity week</th><th scope="col">Forecast cases</th>{scenario && <th scope="col">Hypothetical scenario ({result.city[0].scenario_multiplier}×)</th>}</tr></thead>
        <tbody>{rows?.map(row => <tr key={row.horizon}><th scope="row">{formatWeek(row)}</th>
          <td>{cases.format(row.expected_cases)}</td>{scenario && <td>{cases.format(row.scenario_expected_cases)}</td>}
        </tr>)}</tbody>
      </table>
    </section>}
  </main>;
}
