'use client';

import { useEffect, useState } from 'react';
import { Download, FileSpreadsheet } from 'lucide-react';
import { fetchResearch } from '@/lib/engine-connection';
import { formatScenarioDate } from '@/lib/playback';

interface FlaggedHospital {
  id: string; hospital: string; status: 'Full' | 'Low availability';
  firstFlag: string; firstFull: string | null; daysFlagged: number;
  minimumBeds: number; peakShortage: number; peakHolding: number; totalUnplaced: number | null;
}
interface Briefing {
  scenarioId: string; forecastRunId: string; runTimestamp: string;
  mode: string; window: string; days: number; hospitalCount: number; recordCount: number;
  followUp: string; watchlist: FlaggedHospital[]; note: string; definitions: string;
  metrics: [string, string, string][]; settings: [string, string][];
}

function number(value: number | null) {
  if (value === null) return 'Unavailable';
  if (value > 0 && value < .01) return '<0.01';
  return value.toLocaleString('en-PH', { maximumFractionDigits: 2 });
}

async function reportFile(base: string, format: string, signal?: AbortSignal) {
  const response = await fetchResearch(`${base}.${format}`, { signal });
  if (response.status === 404) throw Error('The saved run could not be found. Run the simulation again to create a report.');
  if (!response.ok) throw Error('The saved report could not be loaded. Please try again.');
  return response;
}

export default function LguReport({ id }: { id: string }) {
  const [report, setReport] = useState<Briefing | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [downloading, setDownloading] = useState('');
  const [downloadError, setDownloadError] = useState('');
  const base = `/api/research/outbreak-scenarios/${id}/report`;
  useEffect(() => {
    const controller = new AbortController();
    reportFile(base, 'json', controller.signal).then(response => response.json()).then(value => {
      if (!controller.signal.aborted) setReport(value);
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [base, attempt]);

  async function download(format: 'pdf' | 'csv') {
    setDownloadError('');
    setDownloading(format);
    try {
      const res = await reportFile(base, format);
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = res.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1] ?? `qc-dengue-${id.slice(0, 12)}.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : 'Download failed. Please try again.');
    } finally {
      setDownloading('');
    }
  }

  return <main className="lgu-report">
    <header><p>Quezon City · Local government briefing</p><h1>Dengue bed capacity report</h1>
      {report && <p>{report.mode} · {report.window} · {report.days}-day simulation</p>}
    </header>
    {!report && (error ? <div role="alert"><p>{error}</p><button onClick={() => { setError(''); setAttempt(v => v + 1); }}>Retry report</button></div> : <p role="status">Loading the saved simulation…</p>)}
    {report && <>
      <div className="lgu-actions">
        <button onClick={() => download('pdf')} disabled={!!downloading}><Download size={16} />{downloading === 'pdf' ? 'Preparing PDF…' : 'Download PDF briefing'}</button>
        <button onClick={() => download('csv')} disabled={!!downloading}><FileSpreadsheet size={16} />{downloading === 'csv' ? 'Preparing CSV…' : 'Download daily records (CSV)'}</button>
      </div>
      {downloadError && <p role="alert">{downloadError}</p>}
      <section aria-labelledby="lgu-summary"><h2 id="lgu-summary">Simulation summary</h2>
        <dl className="lgu-metrics">{report.metrics.map(([label, value, detail]) => <div key={label}>
          <dt>{label}</dt><dd><strong>{value}</strong><small>{detail}</small></dd>
        </div>)}</dl>
        <p>{report.note}</p>
      </section>
      <section aria-labelledby="lgu-watch"><h2 id="lgu-watch">Hospitals for follow-up</h2>
        <p>{report.followUp}</p>
        {report.watchlist.length > 0 && <div className="lgu-scroll" role="region" aria-label="Flagged hospitals" tabIndex={0}><table>
          <thead><tr>{['Hospital', 'Status', 'First flag', 'First full', 'Days flagged', 'Fewest beds left', 'Peak beds short', 'Peak holding', 'Total unplaced'].map(h => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{report.watchlist.map(h => <tr key={h.id}><th scope="row">{h.hospital}<small className="lgu-hospital-id">{h.id}</small></th>
            <td><span className="lgu-flag" data-full={h.status === 'Full'}>{h.status}</span></td>
            <td>{formatScenarioDate(h.firstFlag)}</td><td>{h.firstFull ? formatScenarioDate(h.firstFull) : 'Never full'}</td>
            {[h.daysFlagged, h.minimumBeds, h.peakShortage, h.peakHolding, h.totalUnplaced].map((v, i) => <td key={i}>{number(v)}</td>)}
          </tr>)}</tbody></table></div>}
        <p className="lgu-caption">{report.definitions}</p>
      </section>
      <section aria-labelledby="lgu-settings"><h2 id="lgu-settings">Scenario settings</h2>
        <dl className="lgu-settings">{report.settings.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      </section>
      <section aria-labelledby="lgu-record"><h2 id="lgu-record">Run record</h2>
        <p>The CSV contains {report.recordCount.toLocaleString('en-PH')} daily hospital records from {report.hospitalCount} hospitals.</p>
        <dl className="lgu-settings"><div><dt>Scenario ID</dt><dd>{report.scenarioId}</dd></div><div><dt>Forecast run</dt><dd>{report.forecastRunId}</dd></div>
          <div><dt>Run timestamp</dt><dd>{report.runTimestamp}</dd></div></dl>
      </section>
    </>}
  </main>;
}
