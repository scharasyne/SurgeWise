'use client';
import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  Activity,
  ArrowLeft,
  BedDouble,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Download,
  History,
  Hourglass,
  Info,
  MapPin,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  SlidersHorizontal,
  TrendingUp,
  TriangleAlert,
  X,
  Layers,
  Compass,
  Plus,
  Minus,
  ChevronDown,
  ChevronUp,
  Expand,
  Shrink,
  Flag,
  FileText,
  ExternalLink,
  ChartNoAxesCombined,
  Satellite,
  Upload,
  MapIcon,
} from 'lucide-react';
import type {
  BedAllotmentImport,
  BedForecast, HospitalChoice, MovieBarangay, MovieHospital,
  MovieContext,
  QCControls,
  QCWorkspaceResult,
} from '@/lib/outbreak-types';
import {
  formatScenarioDate,
  nextPlaybackDay,
  validateDateWindow,
} from '@/lib/playback';
import { addDateDays, CASE_BANDS } from '@/lib/case-bands';
import { probabilityFacts, probabilityNote, probabilityPercent } from '@/lib/hospital-probabilities';
import { SIMULATION_LINES } from '@/lib/simulation-connections';
import WorkspaceLoader from '@/components/workspace-loader';
import {
  ENGINE_STARTING_MESSAGE,
  fetchResearch,
  type EngineConnectionStatus,
} from '@/lib/engine-connection';
import WorkspaceSelect from '@/components/workspace-select';
import HospitalSearch from '@/components/hospital-search';
import type { CityBoundaryStatus, SimulationMapController, SimulationMapStatus } from '@/lib/simulation-map';

const OutbreakMap = dynamic(() => import('@/components/outbreak-map'), {
  ssr: false, loading: () => <WorkspaceLoader label="Preparing simulation map" />,
});
const PhilippinesOverview = dynamic(
  () => import('@/components/philippines-overview'),
  { ssr: false }
);
const format = (n: number | undefined | null) =>
  n == null ? '—' : n.toLocaleString('en-PH', { maximumFractionDigits: 1 });
const formatFractional = (n: number) => n > 0 && n < 0.01 ? '<0.01' : n.toLocaleString('en-PH', { maximumFractionDigits: 2 });
const range = (r: { lowerCases: number; upperCases: number } | undefined) =>
  r ? `${format(r.lowerCases)}–${format(r.upperCases)}` : 'Unavailable';
const factorName: Record<string, string> = {
  RF_NASA: 'Rainfall',
  'Temp_ERA5-Land': 'Temperature',
  'RH_ERA5-Land': 'Relative humidity',
};
const dateLabel = (date: string | undefined) =>
  date ? formatScenarioDate(date) : '—';

type WorkspaceTab = 'historical' | 'future';
type DetailTab =
  | 'overview'
  | 'hotspots'
  | 'place-beds'
  | 'city-beds'
  | 'barangays'
  | 'compare'
  | 'methods';
type PanelView = 'scenario' | 'results' | 'hospitals' | 'layers' | null;
/** Editable fields of one hospital's bed allotment in the Bed capacity tab. */
type HospitalBedField = 'dengueBeds' | 'nonDengueBeds' | 'holdingTotal' | 'dengueHolding' | 'nonDengueHolding';
const GUIDE_STORAGE_KEY = 'surgewise.qc-guide-dismissed';
const GLOSSARY = {
  expected: [
    'Expected cases',
    'Modeled dengue cases for Quezon City from the forecast model. Not observed counts.',
  ],
  range: [
    'Case range',
    'Experimental range targeting 80% coverage. Retrospective checks covered fewer weeks, so treat it as exploratory.',
  ],
  hotspot: [
    'High-burden candidate (hotspot)',
    'One of the ten barangays with the highest predicted annual dengue burden. Not a confirmed outbreak.',
  ],
  accredited: [
    'Accredited beds',
    'Beds in the PhilHealth register. Not the same as staffed, free or dengue-usable beds.',
  ],
  staffed: [
    'Staffed beds required',
    'Beds needed for projected dengue admissions, from the admission fraction, delay and length of stay you set.',
  ],
  census: [
    'Supported census',
    'Expected dengue patients in assumed normal plus activated surge beds.',
  ],
  holding: [
    'Unstaffed holding',
    'Expected patients in temporary holding spaces, which are not staffed beds.',
  ],
  unresolved: [
    'Unresolved demand',
    'Cumulative expected patients the modeled hospital capacity could not place.',
  ],
} as const;
function InspectorFacts({ rows }: { rows: Array<[string, ReactNode]> }) {
  return <dl className="qs-inspector-facts">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}
function HospitalProbabilityPicker({ origin, choices, hospitals, distanceOnly }: {
  origin: MovieBarangay; choices: HospitalChoice[]; hospitals: MovieHospital[]; distanceOnly: boolean;
}) {
  const [id, setId] = useState('');
  const choice = choices.find(row => row.facilityId === id);
  const names = new Map(hospitals.map(h => [h.id, h.name]));
  const options = choices.flatMap(row => {
    const name = names.get(row.facilityId);
    return name ? [{ id: row.facilityId, name, note: probabilityPercent(row.share) + ' first-admission probability' }] : [];
  });
  return <div className="qs-probability-picker">
    <HospitalSearch label="Inspect probability by hospital" placeholder="Search hospitals by name" value={id} onChange={setId} options={options} />
    {choice && <div role="status"><InspectorFacts rows={probabilityFacts(choice)} />
      <small>{probabilityNote(choice, origin, distanceOnly)}</small></div>}
  </div>;
}
const percent = (value: number | undefined | null) => value == null ? 'Unavailable' : `${format(value)}%`;
function BedUse({ forecast, day, occupancyPct }: { forecast?: BedForecast; day: number; occupancyPct?: number }) {
  if (!forecast) return null;
  const pct = forecast.demandUtilizationPct;
  return <section className={`qc-bed-use${pct != null && pct > 100 ? ' over-capacity' : ''}`} aria-label="Projected bed demand and capacity percentage">
    <h4>Projected bed demand · day {day}</h4>
    <InspectorFacts rows={[
      ['Expected beds needed', format(forecast.expectedBeds)],
      ['Assumed dengue slots', format(forecast.assumedSupportedDengueCapacity)],
      ['Demand against assumed slots', pct == null ? forecast.assumedSupportedDengueCapacity === 0 ? 'No dengue slots assumed' : 'Unavailable' : `${format(pct)}% of modeled dengue slots`],
    ]} />
    {pct != null && <div className="qc-bed-use-track" aria-hidden="true"><div style={{ width: `${Math.min(100, pct)}%` }} /></div>}
    <p>Expected dengue bed demand ÷ assumed dengue-care slots × 100. Above 100% means demand exceeds that scenario capacity, before diversions.</p>
    {occupancyPct != null && <p>Dengue placements and beds reserved for other care together account for {format(occupancyPct)}% of staffed capacity. Holding spaces are counted separately.</p>}
    <p>Scenario estimates; actual staffed beds and occupancy are unknown.</p>
  </section>;
}
async function fetchWorkspace(
  controls: QCControls | undefined,
  tab: WorkspaceTab,
  signal: AbortSignal,
  onStatus: (status: EngineConnectionStatus) => void
): Promise<QCWorkspaceResult> {
  const response = await fetchResearch(
    `/api/research/${tab === 'future' ? 'future-simulation' : 'qc-simulation'}`,
    controls
      ? {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          // Future runs use the engine default, including when controlValues echoes a prior profile.
          body: JSON.stringify(tab === 'future' ? { ...controls, weatherProfile: undefined } : controls),
          signal,
        }
      : { signal },
    onStatus
  );
  const data = await response.json();
  if (!response.ok)
    throw Error(
      data.error ||
        data.detail?.message ||
        data.detail?.code ||
        (Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join(' ')
          : `Request failed (${response.status})`)
    );
  return data;
}

export default function QCSimulationWorkspace() {
  const [tab, setTab] = useState<WorkspaceTab>('historical');
  const [planningAsOf, setPlanningAsOf] = useState<string>();
  const [data, setData] = useState<QCWorkspaceResult | null>(null);
  const [controls, setControls] = useState<QCControls | null>(null);
  const [context, setContext] = useState<MovieContext | null>(null);
  const [day, setDay] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(2);
  const [selected, setSelected] = useState(''),
    [hospital, setHospital] = useState('');
  const [showHotspotDetails, setShowHotspotDetails] = useState(false);
  const [hospitalInspection, setHospitalInspection] = useState(0);
  const hospitalPanel = useRef<HTMLElement>(null);
  const [links, setLinks] = useState(false),
    [reduced, setReduced] = useState(false);
  const [view, setView] = useState<'qc' | 'philippines'>('qc');
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  const [caseMetric, setCaseMetric] = useState<'daily' | 'cumulative'>(
    'cumulative'
  );
  const [historicalWindows, setHistoricalWindows] = useState<
    { startDate: string; endDate: string }[]
  >([]);
  const [connectionStatus, setConnectionStatus] =
    useState<EngineConnectionStatus>('connecting');
  // New UI state is declared after the original hooks so existing hook order is unchanged.
  const [detailTab, setDetailTab] = useState<DetailTab>('overview');
  const [showGuide, setShowGuide] = useState(false);
  const [panelView, setPanelView] = useState<PanelView>(null);
  const [openInfo, setOpenInfo] = useState('');
  const [introToast, setIntroToast] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [wideResults, setWideResults] = useState(false);
  const [mapStatus, setMapStatus] = useState<SimulationMapStatus>('loading');
  const [buildings3d, setBuildings3d] = useState(false);
  const [showHospitals, setShowHospitals] = useState(true);
  const [locatorOpen, setLocatorOpen] = useState(false);
  // Appended last so the existing hook order (relied on by tests) is unchanged.
  const [satellite, setSatellite] = useState(false);
  const [timelineHidden, setTimelineHidden] = useState(false);
  const [numberDrafts, setNumberDrafts] = useState<Partial<Record<keyof QCControls, string>>>({});
  const [startDateDraft, setStartDateDraft] = useState<string | null>(null);
  const [showProbabilities, setShowProbabilities] = useState(true);
  const [settingsSection, setSettingsSection] = useState<'scenario' | 'capacity'>('scenario');
  const [allotmentImport, setAllotmentImport] = useState<{ status: 'idle' | 'loading' | 'error' | 'done'; fileName?: string; message?: string; result?: BedAllotmentImport }>({ status: 'idle' });
  const [capacityHospital, setCapacityHospital] = useState('');
  const [hospitalDraft, setHospitalDraft] = useState<{ field: HospitalBedField; text: string } | null>(null);
  // The exact slider percent per hospital; beds are whole numbers, so several percents can round to the same count.
  const [sharePercent, setSharePercent] = useState<{ hospital: string; beds?: number; holding?: number }>({ hospital: '' });
  // NCR city outlines, as on Dashboard. Appended last to keep the existing hook order.
  const [showCityBoundaries, setShowCityBoundaries] = useState(false);
  const [submittedRun, setSubmittedRun] = useState(false);
  const [cityBoundaryStatus, setCityBoundaryStatus] = useState<CityBoundaryStatus>('loading');
  const allotmentFile = useRef<HTMLInputElement>(null);
  const workspace = useRef<HTMLElement>(null);
  const panelHeading = useRef<HTMLHeadingElement>(null);
  const panelTrigger = useRef<HTMLElement | null>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const guideTrigger = useRef<HTMLButtonElement>(null);
  const scenarioTrigger = useRef<HTMLButtonElement>(null);
  const playbackMenu = useRef<HTMLDetailsElement>(null);
  const expandedRef = useRef(false);
  const previousPanel = useRef<PanelView>(null);
  const panelRef = useRef(panelView); panelRef.current = panelView;
  const mapController = useRef<SimulationMapController | null>(null);
  const setMapController = useCallback((value: SimulationMapController | null) => { mapController.current = value; }, []);
  const guideClose = useRef<HTMLButtonElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const reducedRef = useRef(false);
  const tabRef = useRef<WorkspaceTab>('historical');
  const savedForms = useRef<Partial<Record<WorkspaceTab, QCControls>>>({});
  const controlsScroll = useRef<HTMLFormElement>(null);
  const calculate = useCallback(
    async (
      values?: QCControls,
      action: 'preview' | 'run' | 'compare' = 'preview',
      targetTab: WorkspaceTab = tabRef.current
    ) => {
      if (values) {
        const invalid = validateDateWindow(values.startDate, values.endDate);
        if (invalid) {
          setError(invalid);
          return;
        }
      }
      const token = ++generation.current;
      setAllotmentImport({ status: 'idle' });
      setHospitalDraft(null);
      setSharePercent({ hospital: '' });
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      setLoading(true);
      setData(null);
      setContext(null);
      setNumberDrafts({});
      setStartDateDraft(null);
      setControls(values ?? null);
      setPlaying(false);
      setDay(0);
      setError('');
      try {
        const result = await fetchWorkspace(
          values,
          targetTab,
          controller.signal,
          (status) => {
            if (token === generation.current) setConnectionStatus(status);
          }
        );
        if (token !== generation.current) return;
        setSubmittedRun(action !== 'preview');
        setData(result);
        setContext(result.context);
        setControls(result.controlValues);
        setCaseMetric('cumulative');
        savedForms.current[targetTab] = result.controlValues;
        if (result.historicalWindows)
          setHistoricalWindows(result.historicalWindows);
        if (result.futureForecast) {
          setPlanningAsOf(result.futureForecast.asOfDate);
        }
        setSelected(result.periodSummary.barangays[0].barangayId);
        setHospital('');
        setShowHotspotDetails(false);
        setPlaying(action === 'run' && !reducedRef.current);
        return result;
      } catch (e) {
        if (token === generation.current)
          setError(
            e instanceof Error ? e.message : 'QC simulation unavailable.'
          );
      } finally {
        if (token === generation.current) setLoading(false);
      }
    },
    []
  );
  useEffect(() => {
    const requestGeneration = generation,
      requestController = activeRequest;
    void calculate();
    return () => {
      requestGeneration.current++;
      requestController.current?.abort();
    };
  }, [calculate]);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      setReduced(media.matches);
      if (media.matches) setPlaying(false);
    };
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    reducedRef.current = reduced;
    if (reduced) setPlaying(false);
  }, [reduced]);
  useEffect(() => {
    if (!playing || !data) return;
    const timer = window.setInterval(
      () => setDay((d) => nextPlaybackDay(d, data.durationDays)),
      1000 / speed
    );
    return () => window.clearInterval(timer);
  }, [playing, data, speed]);
  useEffect(() => {
    if (data && day >= data.durationDays) setPlaying(false);
  }, [day, data]);
  useEffect(() => {
    // A short first-use hint replaces the blocking, automatically opened guide.
    try { if (window.localStorage.getItem(GUIDE_STORAGE_KEY)) setIntroToast(false); } catch { /* Help remains available. */ }
  }, []);
  useEffect(() => {
    if (showGuide) guideClose.current?.focus();
  }, [showGuide]);
  useEffect(() => {
    hospitalPanel.current?.scrollTo({ top: 0 });
  }, [panelView]);
  // The arrival message is shown once: it hides after a few seconds, or as soon as the timeline moves.
  useEffect(() => {
    if (day > 0) setIntroToast(false);
  }, [day]);
  useEffect(() => {
    if (!introToast || !data) return;
    const timer = window.setTimeout(() => setIntroToast(false), 10000);
    return () => window.clearTimeout(timer);
  }, [introToast, data]);
  function openGuide() {
    setShowGuide(true);
  }
  function closeGuide() {
    setShowGuide(false); setIntroToast(false);
    requestAnimationFrame(() => guideTrigger.current?.focus());
    try {
      window.localStorage.setItem(GUIDE_STORAGE_KEY, '1');
    } catch {
      /* The non-blocking hint may appear again next visit. */
    }
  }
  function update(patch: Partial<QCControls>) {
    activeRequest.current?.abort();
    setLoading(false);
    generation.current++;
    setAllotmentImport(previous => previous.status === 'loading' ? { status: 'idle' } : previous);
    setControls((c) => (c ? { ...c, ...patch } : c));
    setData(null);
    setPlaying(false);
    setDay(0);
    setError('');
  }
  function switchTab(next: WorkspaceTab) {
    if (next === tabRef.current) return;
    controlsScroll.current?.scrollTo({ top: 0 });
    if (controls && !dateError) savedForms.current[tabRef.current] = controls;
    tabRef.current = next;
    setTab(next);
    void calculate(savedForms.current[next], 'preview', next);
  }
  function windowControls(
    days: number,
    start = controls?.startDate
  ): QCControls | null {
    if (!controls || !start) return null;
    const base = {
      ...controls,
      startDate: start,
      endDate: addDateDays(start, days),
      compareAllocation: false,
    };
    return tab === 'future'
      ? {
          ...base,
          horizonDays: days,
          surgeOnsetDay: Math.min(base.surgeOnsetDay ?? 0, days - 1),
        }
      : base;
  }
  const selectedDays = controls
    ? (controls.horizonDays ??
      Math.round(
        (Date.parse(controls.endDate) - Date.parse(controls.startDate)) /
          86400000
      ))
    : 28;
  function updateDays(days: number) {
    const next = windowControls(days);
    if (next) update(next);
  }
  function updateStart(start: string) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start)) {
      setStartDateDraft(start);
      update({});
      return;
    }
    setStartDateDraft(null);
    const next = windowControls(
      Number.isFinite(selectedDays) && selectedDays > 0 ? selectedDays : 28,
      start
    );
    if (next) update(next);
  }
  const earliestStart = tab === 'future' ? planningAsOf : '2024-01-29';
  const latestStart = tab === 'future' ? '2035-12-31' : '2025-12-31';
  function dateProblem() {
    if (!controls) return null;
    if (startDateDraft !== null) return 'Enter a valid start date.';
    if ((earliestStart && controls.startDate < earliestStart) || controls.startDate > latestStart) {
      return earliestStart
        ? `Choose a start date from ${formatScenarioDate(earliestStart)} to ${formatScenarioDate(latestStart)}.`
        : `Choose a start date by ${formatScenarioDate(latestStart)}.`;
    }
    if (tab === 'historical' && historicalWindows.length &&
      !historicalWindows.some(w => w.startDate <= controls.startDate && controls.endDate <= w.endDate)) {
      return 'Choose a start date and duration within a saved forecast period.';
    }
    return validateDateWindow(controls.startDate, controls.endDate);
  }
  const dateError = dateProblem();

  function formIsReady() {
    if (controlsScroll.current?.checkValidity() === false || dateError) {
      setPanelView('scenario');
      requestAnimationFrame(() => controlsScroll.current?.reportValidity());
      return false;
    }
    return true;
  }
  function runSimulation() {
    if (!controls || !formIsReady()) return;
    openDetail('overview');
    void calculate({ ...controls, compareAllocation: false }, 'run');
  }
  function compareAllocations() {
    if (!controls || !formIsReady()) return;
    void calculate({ ...controls, compareAllocation: true }, 'compare').then(result => {
      if (!result) return;
      setDay(result.durationDays); setDetailTab('compare'); setPanelView('results');
    });
  }
  const scenario = day > 0 ? data : null;
  const activeRun = submittedRun || playing || day > 0 ? data : null;
  const connectionsEnabled = !!activeRun;
  const snapshot = scenario?.days[day];
  const area = context?.barangays.find((b) => b.id === selected);
  const selectedPeriod = scenario?.periodSummary.barangays.find(
    (b) => b.barangayId === selected
  );
  // Choice weights are fixed for the loaded scenario, including its day-zero preview.
  const selectedPlaceRow = data?.bedProjection?.placePeaks?.find(
    (b) => b.barangayId === selected
  );
  const selectedBedProjection = scenario ? selectedPlaceRow : undefined;
  const resultSplit = data?.bedProjection?.arrivalSplitPolicy;
  const markovResult = resultSplit === 'markov_preference' || resultSplit === 'markov_proximity';
  const choiceRow = markovResult && selectedPlaceRow?.hospitals.length ? selectedPlaceRow : undefined;
  const selectedDaily =
    scenario?.days.slice(1).map((d) => ({
      dayIndex: d.dayIndex,
      date: d.date,
      expectedCases:
        d.barangays.find((b) => b.barangayId === selected)?.expectedCases ?? 0,
    })) ?? [];
  const maxSelectedDaily = Math.max(
    1,
    ...selectedDaily.map((d) => d.expectedCases)
  );
  const nearest = area?.nearestHospitals ?? [];
  const nearestHospital = context?.hospitals.find(
    (h) => h.id === nearest[0]?.facilityId
  );
  const localHospitals = area?.hospitalsWithinBarangay ?? [];
  const source = data?.forecastEvidence;
  const fullPeriod = scenario?.periodSummary;
  const finalDay = scenario?.days.at(-1);
  const hotspotRanking = context?.hotspotRanking;
  const markerHotspotIds = data ? (hotspotRanking?.candidateIds ?? data.days.at(-1)?.hotspotIds) : undefined;
  const caseColorMaximum = Math.max(
    1,
    ...(scenario?.days.flatMap((d) =>
      d.barangays
        .filter((b) => markerHotspotIds?.includes(b.barangayId))
        .map((b) =>
          caseMetric === 'daily' ? b.expectedCases : b.cumulativeCases
        )
    ) ?? [])
  );
  const surgeActive = !!snapshot && snapshot.shockCases > 0;
  const surgeStatus = !scenario
    ? 'Simulation not started'
    : surgeActive
      ? 'Configured surge active'
      : tab === 'future' &&
          controls?.surgeEnabled &&
          (controls.surgeMultiplier ?? 1) > 1
        ? 'Configured surge scheduled'
        : 'Baseline forecast · no added surge';
  const rankedHotspotIds = markerHotspotIds;
  const hotspotRows =
    markerHotspotIds?.flatMap((id) => {
      const row = fullPeriod?.barangays.find((b) => b.barangayId === id);
      return row ? [row] : [];
    }) ?? [];
  const inspectedHospital = context?.hospitals.find((h) => h.id === hospital);
  const hospitalHotspot = finalDay?.facilities.find(
    (f) => f.facilityId === hospital
  )?.nearestHotspot;
  const hospitalHotspotArea = context?.barangays.find(
    (b) => b.id === hospitalHotspot?.barangayId
  );
  const hospitalHotspotCases = fullPeriod?.barangays.find(
    (b) => b.barangayId === hospitalHotspot?.barangayId
  );
  const displayedHospitals = inspectedHospital
    ? [
        {
          hospital: inspectedHospital,
          share: null,
          distanceKm: hospitalHotspot?.distanceKm ?? null,
        },
      ]
    : (selectedPlaceRow?.hospitals.slice(0, 3) ?? []).flatMap(choice => {
        const site = context?.hospitals.find(h => h.id === choice.facilityId);
        return site ? [{ hospital: site, share: choice.share, distanceKm: choice.breakdown?.distanceKm }] : [];
      });
  function inspectHospital(id: string) {
    setHospital(id);
    setShowHotspotDetails(false);
    setPanelView('hospitals');
    setHospitalInspection((value) => value + 1);
    hospitalPanel.current?.scrollTo({ top: 0, behavior: 'instant' });
    const closest = finalDay?.facilities.find(
      (f) => f.facilityId === id
    )?.nearestHotspot;
    if (closest) setSelected(closest.barangayId);
  }
  function inspectHotspot(id: string) {
    setSelected(id);
    setHospital('');
    setShowHotspotDetails(true);
    setPanelView('hospitals');
    setHospitalInspection((value) => value + 1);
  }
  const maxCases = Math.max(
    1,
    ...(data?.days.map((d) => d.expectedCases) ?? [])
  );
  const maxBeds = Math.max(
    1,
    ...(data?.days.map(
      (d) => d.bedForecast?.upperBeds ?? d.bedForecast?.expectedBeds ?? 0
    ) ?? [])
  );
  const futureValidation =
    data?.futureForecast?.validation.filter(
      (r) => r.model === data.futureForecast?.selectedModel
    ) ?? [];
  const coverageValues = data?.futureForecast
    ? futureValidation.map((r) => r.empiricalRangeCoverage)
    : (data?.forecastBacktest.map((r) => r.empiricalRangeCoverage) ?? []);
  // Results were cleared by a settings change and have not been recalculated yet.
  const stale = !!controls && !data && !loading && !error;
  const scenarioDetail = !controls
    ? 'Loading settings…'
    : tab === 'future'
      ? (controls.surgeEnabled ? `Surge up to ${format(controls.surgeMultiplier)}× baseline cases` : 'Baseline cases')
      : controls.mode === 'hypothetical_shock'
        ? `Stress overlay · +${format(controls.extraCasesPerWeek)} cases/week`
        : 'Data-based historical forecast replay';
  const chainComparison = scenario?.firstAdmissionComparison;
  const firstHospital = controls?.allocationPolicy === 'first_hospital';
  const staffedBeds = firstHospital ? snapshot?.bedForecast?.hospitalBedsRequired : snapshot?.bedForecast?.staffedBedsRequired;
  const dailyShortfalls = new Map(snapshot?.barangays.map(b => [b.barangayId, b.expectedBedsShort]));
  const selectedShortfall = dailyShortfalls.get(selected);
  const preferredHospital = context?.hospitals.find(h => h.id === area?.mappedFavoriteHospitalId);
  const shortHospitals = (snapshot?.facilities ?? []).filter(f => (f.bedForecast?.additionalStaffedBedsNeeded ?? 0) > 0)
    .sort((a, b) => b.bedForecast!.additionalStaffedBedsNeeded - a.bedForecast!.additionalStaffedBedsNeeded);
  const detailTabs: { id: DetailTab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'hotspots', label: 'Ranked barangays' },
    { id: 'place-beds', label: 'Bed demand by barangay' },
    { id: 'city-beds', label: 'City-wide bed demand' },
    { id: 'barangays', label: 'All barangays' },
    ...(chainComparison
      ? [{ id: 'compare' as const, label: 'Hospital-choice comparison' }]
      : []),
    { id: 'methods', label: 'Methods & sources' },
  ];
  const activeDetail: DetailTab =
    detailTab === 'compare' && !chainComparison ? 'overview' : detailTab;
  const panelProps = (id: DetailTab) => ({
    role: 'region', id: `qc-detail-panel-${id}`,
    'aria-label': detailTabs.find(item => item.id === id)?.label,
    hidden: activeDetail !== id,
  });
  function openPanel(next: PanelView) {
    if (typeof document !== 'undefined') panelTrigger.current = document.activeElement as HTMLElement;
    setPanelView(next);
  }
  function closePanel() {
    setPanelView(null); setWideResults(false);
    const target = panelTrigger.current;
    if (target?.isConnected && !target.closest('#qs-context-panel')) target.focus();
    else scenarioTrigger.current?.focus();
  }
  function openDetail(next: DetailTab) { setDetailTab(next); openPanel('results'); }
  function download() {
    if (!data) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data)], { type: 'application/json' })
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `qc-${data.scenarioId}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function numeric(key: keyof QCControls, label: string, minimum: number, maximum: number, units: string, step = 1, scale = 1) {
    if (!controls) return null;
    const horizon = key === 'horizonDays';
    const reservation = key === 'baselineOccupancy';
    const value = horizon ? selectedDays : reservation ? (1 - controls.baselineOccupancy) * 100 : Number(controls[key]) * scale;
    const draft = numberDrafts[key];
    const helpId = `scenario-${key}-hint`;
    return (
      <label className="qc-number-field" key={key}>
        <span>{label}</span>
        <input aria-label={label} type="number" min={minimum} max={maximum} step={step} required
          aria-describedby={helpId} aria-invalid={draft !== undefined || undefined}
          value={draft ?? (Number.isFinite(value) ? Number(value.toFixed(8)) : '')}
          onFocus={event => event.currentTarget.select()}
          onChange={event => {
            const input = event.currentTarget;
            const text = input.value.replace(/^0+(?=\d)/, '');
            // Browsers keep "02" when its numeric value already equals React's value.
            if (text !== input.value) input.value = text;
            const valid = text !== '' && input.validity.valid;
            setNumberDrafts(previous => {
              const next = { ...previous };
              if (valid) delete next[key]; else next[key] = text;
              return next;
            });
            if (!valid) update({});
            else if (horizon) updateDays(Number(text));
            else update({ [key]: reservation ? (100 - Number(text)) / 100 : Number(text) / scale });
          }} />
        <small id={helpId}>{draft !== undefined ? 'Enter ' : ''}{minimum.toLocaleString()}–{maximum.toLocaleString()} {units}</small>
      </label>
    );
  }
  const hospitalCount = context?.hospitals.length;
  const allotments = controls?.bedAllotments ?? [];
  const allotmentById = new Map(allotments.map(a => [a.facilityId, a]));
  const hospitalsUsingDefaults = hospitalCount === undefined ? undefined : hospitalCount - allotments.length;
  function reservedDengue(total: number) {
    return Math.round(Number((total * (1 - (controls?.baselineOccupancy ?? 0.6))).toFixed(10)));
  }
  function hospitalBeds(h: MovieHospital) {
    const a = allotmentById.get(h.id);
    const total = h.accreditedBeds;
    const holding = a?.holdingSpaces ?? controls!.holdingCapacity;
    const dengue = a && 'dengueBeds' in a ? a.dengueBeds : reservedDengue(total);
    return {
      facilityId: h.id,
      dengueBeds: dengue,
      nonDengueBeds: total - dengue,
      holdingSpaces: holding,
      nonDengueHoldingSpaces: a?.nonDengueHoldingSpaces ?? holding - Math.round(holding * 0.4),
      extraDengueBeds: a?.extraDengueBeds ?? null,
      extraNonDengueBeds: a?.extraNonDengueBeds ?? null,
    };
  }
  const selectedHospital = context?.hospitals.find(h => h.id === capacityHospital);
  const hospitalRows = (controls && context ? context.hospitals : []).map(h => ({ name: h.name, ...hospitalBeds(h) }));
  const networkBeds = hospitalRows.reduce((sum, b) => ({
    dengue: sum.dengue + b.dengueBeds, nonDengue: sum.nonDengue + b.nonDengueBeds,
    holding: sum.holding + b.holdingSpaces,
    extra: sum.extra + (b.extraDengueBeds ?? controls?.surgeCapacity ?? 0) + (b.extraNonDengueBeds ?? 0),
  }), { dengue: 0, nonDengue: 0, holding: 0, extra: 0 });
  const selectedAllotment = allotmentById.get(capacityHospital);
  const usesDefaultShare = !selectedAllotment || 'staffedBeds' in selectedAllotment;
  // A total and its dengue / non-dengue split: editing the total keeps the dengue part
  // (capped at the new total) for explicit splits. Default splits reapply the percentage; editing one part sets the other to the remainder.
  function splitValue(field: HospitalBedField, value: number, total: number, dengue: number) {
    if (field === 'holdingTotal') { const d = Math.min(dengue, value); return { dengue: d, other: value - d }; }
    if (field === 'dengueBeds' || field === 'dengueHolding') return value <= total ? { dengue: value, other: total - value } : null;
    return value <= total ? { dengue: total - value, other: value } : null;
  }
  function setHospitalBed(field: HospitalBedField, text: string) {
    if (!controls || !selectedHospital) return;
    const value = Number(text);
    const current = hospitalBeds(selectedHospital);
    const next = { ...current };
    let valid = text !== '' && Number.isInteger(value) && value >= 0 && value <= 10000;
    if (valid && (field === 'dengueBeds' || field === 'nonDengueBeds')) {
      const split = splitValue(field, value, current.dengueBeds + current.nonDengueBeds, current.dengueBeds);
      if (split) { next.dengueBeds = split.dengue; next.nonDengueBeds = split.other; }
      valid = !!split && next.dengueBeds + next.nonDengueBeds >= 1;
    } else if (valid) {
      const dengueHolding = current.holdingSpaces - current.nonDengueHoldingSpaces;
      const split = splitValue(field, value, current.holdingSpaces, dengueHolding);
      if (split) { next.holdingSpaces = split.dengue + split.other; next.nonDengueHoldingSpaces = split.other; }
      valid = !!split;
    }
    if (!valid) {
      setHospitalDraft({ field, text });
      update({});
      return;
    }
    setHospitalDraft(null);
    const { dengueBeds, nonDengueBeds, ...rest } = next;
    if (field === 'dengueBeds' || field === 'nonDengueBeds') {
      update({ bedAllotments: [...allotments.filter(a => a.facilityId !== capacityHospital),
        { ...next, holdingSpaces: selectedAllotment?.holdingSpaces, nonDengueHoldingSpaces: selectedAllotment?.nonDengueHoldingSpaces }] });
      return;
    }
    const entry = usesDefaultShare
      ? { ...rest, staffedBeds: dengueBeds + nonDengueBeds } : next;
    update({ bedAllotments: [...allotments.filter(a => a.facilityId !== capacityHospital), entry].sort((a, b) => a.facilityId.localeCompare(b.facilityId)) });
  }
  // Slider for the dengue share of a hospital's beds or holding spaces: 60% of 100 beds = 60 dengue + 40 non-dengue.
  function shareSlider(kind: 'beds' | 'holding') {
    if (!selectedHospital) return null;
    const b = hospitalBeds(selectedHospital);
    const total = kind === 'beds' ? b.dengueBeds + b.nonDengueBeds : b.holdingSpaces;
    const dengue = kind === 'beds' ? b.dengueBeds : b.holdingSpaces - b.nonDengueHoldingSpaces;
    const chosen = sharePercent.hospital === capacityHospital ? sharePercent[kind] : undefined;
    // Keep the chosen percent while it still produces the current counts; typing a count moves the slider instead.
    const percent = kind === 'beds' && usesDefaultShare ? Math.round((1 - (controls?.baselineOccupancy ?? 0.6)) * 100)
      : chosen !== undefined && Math.round((total * chosen) / 100) === dengue ? chosen
      : total > 0 ? Math.round((dengue / total) * 100) : 0;
    const label = kind === 'beds' ? 'Share of beds for dengue' : 'Share of holding spaces for dengue';
    return (
      <div className="qc-share-slider">
        <div className="qc-share-heading"><span>{label}</span><strong>{percent}%</strong></div>
        <input type="range" aria-label={label} min={0} max={100} step={1} value={percent} disabled={total === 0}
          aria-valuetext={`${percent}% for dengue: ${dengue} of ${total}`}
          style={{ '--qc-share': `${percent}%` } as CSSProperties}
          onChange={event => {
            const next = Number(event.target.value);
            setSharePercent(previous => ({ ...(previous.hospital === capacityHospital ? previous : { hospital: capacityHospital }), [kind]: next }));
            setHospitalBed(kind === 'beds' ? 'dengueBeds' : 'dengueHolding', String(Math.round((total * next) / 100)));
          }} />
        <div className="qc-share-scale" aria-hidden="true"><span>Dengue {dengue}</span><span>Non-dengue {total - dengue}</span></div>
      </div>
    );
  }
  function resetHospital() {
    const rest = allotments.filter(a => a.facilityId !== capacityHospital);
    setHospitalDraft(null);
    update({ bedAllotments: rest.length ? rest : null });
  }
  function hospitalField(field: HospitalBedField, label: string, hint: string, strong = false) {
    if (!selectedHospital) return null;
    const b = hospitalBeds(selectedHospital);
    const totalBeds = b.dengueBeds + b.nonDengueBeds;
    const values: Record<HospitalBedField, number> = {
      dengueBeds: b.dengueBeds, nonDengueBeds: b.nonDengueBeds,
      holdingTotal: b.holdingSpaces, dengueHolding: b.holdingSpaces - b.nonDengueHoldingSpaces, nonDengueHolding: b.nonDengueHoldingSpaces,
    };
    const max = field === 'dengueBeds' || field === 'nonDengueBeds' ? totalBeds
      : field === 'dengueHolding' || field === 'nonDengueHolding' ? b.holdingSpaces : 10000;
    const draft = hospitalDraft?.field === field ? hospitalDraft.text : undefined;
    const helpId = `hospital-${field}-hint`;
    return (
      <label className="qc-number-field">
        <span className={strong ? 'qc-field-strong' : undefined}>{label}</span>
        <input aria-label={label} type="number" min={0} max={max} step={1} required
          aria-describedby={helpId} aria-invalid={draft !== undefined || undefined}
          value={draft ?? values[field]} onFocus={event => event.currentTarget.select()}
          onChange={event => setHospitalBed(field, event.currentTarget.value)} />
        <small id={helpId}>{draft !== undefined ? 'Enter a whole number · ' : ''}{hint}</small>
      </label>
    );
  }
  async function importAllotments(file: File) {
    const token = generation.current;
    setAllotmentImport({ status: 'loading', fileName: file.name });
    try {
      const response = await fetch('/api/bed-allotments', { method: 'POST', headers: { 'content-type': 'application/octet-stream' }, body: file });
      const data = await response.json().catch(() => null);
      if (token !== generation.current) return;
      if (!response.ok || !data) {
        setAllotmentImport({ status: 'error', fileName: file.name, message: data?.detail?.message ?? data?.error ?? `Import failed (${response.status}).` });
        return;
      }
      const result = data as BedAllotmentImport;
      if (result.errors.length || !result.allotments.length) {
        // Nothing is applied from a file with problems, so no row is silently dropped.
        setAllotmentImport({ status: 'error', fileName: file.name, result,
          message: result.errors.length ? `${result.errors.length} ${result.errors.length === 1 ? 'row needs' : 'rows need'} fixing. Nothing was applied.` : 'The file has no hospital rows. Nothing was applied.' });
        return;
      }
      update({ bedAllotments: result.allotments.map(a => ({
        facilityId: a.facilityId, holdingSpaces: a.holdingSpaces, nonDengueHoldingSpaces: a.nonDengueHoldingSpaces,
        extraDengueBeds: a.extraDengueBeds, extraNonDengueBeds: a.extraNonDengueBeds,
        ...('staffedBeds' in a ? { staffedBeds: a.staffedBeds } : { dengueBeds: a.dengueBeds, nonDengueBeds: a.nonDengueBeds }),
      })) });
      setSharePercent({ hospital: '' });
      setHospitalDraft(null);
      setAllotmentImport({ status: 'done', fileName: file.name, result });
    } catch {
      if (token !== generation.current) return;
      setAllotmentImport({ status: 'error', fileName: file.name, message: 'Could not reach the simulation engine. Try again.' });
    }
  }
  function clearAllotments() {
    update({ bedAllotments: null });
    setAllotmentImport({ status: 'idle' });
  }
  function downloadAllotmentTemplate() {
    if (!context || !controls) return;
    // Neutralise spreadsheet formulas and quote separators in names.
    const cell = (value: string | number) => {
      let text = String(value);
      if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
      return /[",;\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const rows = [...context.hospitals].sort((a, b) => a.id.localeCompare(b.id)).map(h => {
      const b = hospitalBeds(h);
      return [h.id, h.name, b.dengueBeds + b.nonDengueBeds, b.dengueBeds, b.nonDengueBeds, b.holdingSpaces, b.holdingSpaces - b.nonDengueHoldingSpaces, b.nonDengueHoldingSpaces, b.extraDengueBeds ?? '', b.extraNonDengueBeds ?? ''];
    });
    const csv = [['facility_id', 'hospital_name', 'accredited_beds', 'dengue_beds', 'non_dengue_beds', 'holding_spaces', 'dengue_holding_spaces', 'non_dengue_holding_spaces', 'extra_dengue_beds', 'extra_non_dengue_beds'], ...rows].map(row => row.map(cell).join(',')).join('\r\n');
    const link = document.createElement('a');
    // A byte-order mark lets Excel open the UTF-8 file with the right characters.
    link.href = URL.createObjectURL(new Blob(['﻿' + csv + '\r\n'], { type: 'text/csv;charset=utf-8' }));
    link.download = 'surgewise-bed-allotments.csv';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
  function chooseSettingsSection(section: 'scenario' | 'capacity') {
    setSettingsSection(section);
    controlsScroll.current?.scrollTo({ top: 0 });
  }
  // Summary card for the right panel: icon, label, one big value, a short note and an optional explanation toggle.
  function summaryCard(
    id: string,
    icon: ReactNode,
    label: string,
    value: string,
    note: string,
    info: string,
    tone = ''
  ) {
    const open = openInfo === id;
    return (
      <div key={id} className={`qc-total-card${tone ? ` ${tone}` : ''}`}>
        <span className="qc-total-icon" aria-hidden="true">
          {icon}
        </span>
        <div className="qc-total-text">
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{note}</small>
        </div>
        <button
          className="text-button qc-info-button"
          aria-label={`About: ${label}`}
          aria-expanded={open}
          onClick={() => setOpenInfo(open ? '' : id)}
        >
          <Info size={16} />
        </button>
        {open && <p className="qc-total-info">{info}</p>}
      </div>
    );
  }

  useEffect(() => { if (panelView) panelHeading.current?.focus({ preventScroll: true }); }, [panelView]);
  useEffect(() => {
    function exitExpanded() {
      if (!expandedRef.current) return;
      expandedRef.current = false; setExpanded(false); setPanelView(previousPanel.current);
      requestAnimationFrame(() => fullscreenButton.current?.focus());
    }
    function changed() { if (document.fullscreenElement !== workspace.current) exitExpanded(); }
    function escape(event: globalThis.KeyboardEvent) {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      if (playbackMenu.current?.open) { playbackMenu.current.open = false; return; }
      if (expandedRef.current && !document.fullscreenElement) exitExpanded();
      else if (!document.fullscreenElement) { setPanelView(null); panelTrigger.current?.focus(); }
    }
    function outsidePlayback(event: PointerEvent) {
      if (playbackMenu.current && !playbackMenu.current.contains(event.target as Node)) playbackMenu.current.open = false;
    }
    document.addEventListener('fullscreenchange', changed); document.addEventListener('keydown', escape);
    document.addEventListener('pointerdown', outsidePlayback);
    return () => { document.removeEventListener('fullscreenchange', changed); document.removeEventListener('keydown', escape); document.removeEventListener('pointerdown', outsidePlayback); };
  }, []);
  async function toggleFullscreen() {
    if (!workspace.current) return;
    if (expandedRef.current) {
      if (document.fullscreenElement === workspace.current) { await document.exitFullscreen(); return; }
      expandedRef.current = false; setExpanded(false); setPanelView(previousPanel.current); return;
    }
    previousPanel.current = panelRef.current;
    try { if (workspace.current.requestFullscreen) await workspace.current.requestFullscreen(); } catch { /* In-app fullscreen remains available. */ }
    expandedRef.current = true; setExpanded(true); setPanelView(null);
  }
  const timing = data?.futureForecast?.parameterAudit;
  const peakDay = data?.bedProjection?.peakDayIndex;
  const canJumpToPeak = !!scenario && Number.isInteger(peakDay) && peakDay! >= 1 && peakDay! <= (data?.durationDays ?? 0);
  const mapControlsDisabled = mapStatus === 'loading' || mapStatus === 'unavailable';
  const panelTitles = { scenario: 'Set up scenario', results: 'Results', hospitals: inspectedHospital ? 'Hospital details' : 'Barangay details', layers: 'Map layers' };
  const settings = (<><div
              className="qc-workspace-tabs"
              role="tablist"
              aria-label="Simulation workspace"
            >
              {(['historical', 'future'] as const).map((value) => (
                <button
                  key={value}
                  id={`qc-tab-${value}`}
                  role="tab"
                  type="button" className="text-button"
                  aria-selected={tab === value}
                  aria-controls="qc-tab-panel"
                  tabIndex={tab === value ? 0 : -1}
                  onClick={() => switchTab(value)}
                  onKeyDown={(event) => {
                    if (
                      !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(
                        event.key
                      )
                    )
                      return;
                    event.preventDefault();
                    const next =
                      event.key === 'Home'
                        ? 'historical'
                        : event.key === 'End'
                          ? 'future'
                          : value === 'historical'
                            ? 'future'
                            : 'historical';
                    switchTab(next);
                    document.getElementById(`qc-tab-${next}`)?.focus();
                  }}
                >
                  {tab === value && <Check size={14} strokeWidth={2.5} aria-hidden="true" />}
                  {value === 'historical' ? 'Historical replay' : 'Future forecast'}
                </button>
              ))}
            </div>
            <div className="qc-settings-sections" role="tablist" aria-label="Scenario settings sections">
              {(['scenario', 'capacity'] as const).map(value => (
                <button key={value} type="button" className="text-button" id={`qc-section-${value}`} role="tab" aria-selected={settingsSection === value}
                  aria-controls={`qc-section-panel-${value}`} tabIndex={settingsSection === value ? 0 : -1} onClick={() => chooseSettingsSection(value)}
                  onKeyDown={event => {
                    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                    event.preventDefault();
                    const next = event.key === 'Home' ? 'scenario' : event.key === 'End' ? 'capacity' : value === 'scenario' ? 'capacity' : 'scenario';
                    chooseSettingsSection(next);
                    document.getElementById(`qc-section-${next}`)?.focus();
                  }}>
                  {value === 'scenario' ? <><SlidersHorizontal size={14} aria-hidden="true" />Scenario</> : <><BedDouble size={14} aria-hidden="true" />Bed capacity</>}
                </button>
              ))}
            </div>
            <form ref={controlsScroll} className="qs-settings-scroll qc-controls" id="qc-settings-form"
              onSubmit={event => { event.preventDefault(); runSimulation(); }}
              onInvalid={event => {
                const target = event.target as HTMLElement;
                // Show the tab holding an invalid field so the browser can point to it.
                if (target.closest('#qc-section-panel-capacity')) setSettingsSection('capacity');
                else if (target.closest('#qc-section-panel-scenario')) setSettingsSection('scenario');
                const section = target.closest('details');
                if (section) section.open = true;
              }}>
              <div
                key={`${tab}-${controls ? 'ready' : 'pending'}`}
                id="qc-tab-panel"
                className="qc-mode-form"
                role="tabpanel"
                aria-labelledby={`qc-tab-${tab}`}
                aria-busy={loading}
              >
                {controls ? (
                  <>
                    <div role="tabpanel" id="qc-section-panel-scenario" aria-labelledby="qc-section-scenario" hidden={settingsSection !== 'scenario'}>
                    <fieldset className="qc-fieldset">
                      <legend><CalendarDays aria-hidden="true" size={16} /> Forecast period</legend>
                      {tab === 'historical' && historicalWindows.length > 0 && (
                        <label>Saved forecast period
                          <WorkspaceSelect label="Saved forecast period"
                            value={historicalWindows.findLast(w => w.startDate <= controls.startDate && controls.endDate <= w.endDate)?.startDate ?? ''}
                            onChange={value => { if (value) updateStart(value); }}
                            options={[{ value: '', label: 'Choose a period' }, ...historicalWindows.map(w => ({
                              value: w.startDate, label: `${formatScenarioDate(w.startDate)} – ${formatScenarioDate(addDateDays(w.endDate, -1))}`,
                            }))]} />
                        </label>
                      )}
                      <div className="qs-field-pair qs-date-pair">
                        <label>Start date
                          <input aria-label="Start date" type="date" required
                            min={earliestStart} max={latestStart}
                            value={startDateDraft ?? controls.startDate} onChange={e => updateStart(e.target.value)} />
                        </label>
                        {numeric('horizonDays', 'Duration', 1, 28, 'days')}
                      </div>
                      <div className="qc-horizons" role="group" aria-label="Duration presets">
                        {[2, 7, 12, 14, 28].map(days => {
                          const active = numberDrafts.horizonDays === undefined && selectedDays === days;
                          return <button className="text-button" type="button" key={days} aria-pressed={active}
                            disabled={loading} onClick={() => {
                              setNumberDrafts(previous => { const next = { ...previous }; delete next.horizonDays; return next; });
                              updateDays(days);
                            }}>{active && <Check aria-hidden="true" size={12} />}{days} days</button>;
                        })}
                      </div>
                      {dateError ? <p className="qs-input-error" role="status">{dateError}</p> :
                        numberDrafts.horizonDays === undefined && controls.endDate && <p className="qs-window-note">Final snapshot <strong>{formatScenarioDate(controls.endDate)}</strong></p>}
                    </fieldset>

                    <fieldset className="qc-fieldset">
                      <legend><TrendingUp aria-hidden="true" size={16} /> {tab === 'future' ? 'Projected dengue cases' : 'Case forecast'}</legend>
                      {tab === 'historical' ? (
                        <>
                          <label>Case scenario
                            <WorkspaceSelect label="Case scenario" value={controls.mode} onChange={value =>
                              update({ mode: value as QCControls['mode'], extraCasesPerWeek: value === 'forecast' ? 0 : 700 })}
                              options={[{ value: 'forecast', label: 'Historical forecast' },
                                { value: 'hypothetical_shock', label: 'Historical forecast with added cases' }]} />
                          </label>
                          {controls.mode === 'hypothetical_shock' && <div className="qs-field-pair">
                            {numeric('extraCasesPerWeek', 'Extra weekly cases at peak', 0, 100000, 'cases/week')}
                            {numeric('growthDays', 'Time to peak', 1, 28, 'days')}
                          </div>}
                        </>
                      ) : (
                        <>
                          <label className="qc-surge-toggle"><input type="checkbox" checked={controls.surgeEnabled ?? true}
                            onChange={e => update({ surgeEnabled: e.target.checked })} /> Add a hypothetical surge</label>
                          {controls.surgeEnabled && <div className="qs-field-pair">
                            {numeric('surgeMultiplier', 'Peak case multiplier', 1, 10, '× baseline', 0.1)}
                            {numeric('surgeOnsetDay', 'Days before surge starts', 0, Math.max(0, selectedDays - 1), 'days')}
                            {numeric('growthDays', 'Time to peak', 1, 28, 'days')}
                          </div>}
                        </>
                      )}
                    </fieldset>

                    <fieldset className="qc-fieldset">
                      <legend><BedDouble aria-hidden="true" size={16} /> Hospital planning</legend>
                      <label>When a hospital is full
                        <WorkspaceSelect label="When a hospital is full" value={controls.allocationPolicy} onChange={value =>
                          update({ allocationPolicy: value as QCControls['allocationPolicy'], compareAllocation: false })}
                          options={[
                            { value: 'first_hospital', label: 'Record the shortage at that hospital' },
                            { value: 'next_probability', label: 'Try the next most likely hospital with space' },
                          ]} />
                        {controls.allocationPolicy !== 'first_hospital' && <small>If the first hospital is full, try hospitals in order of probability for that barangay. Staffed dengue beds fill before temporary holding spaces.</small>}
                      </label>
                      <label>How patients choose a hospital
                        <WorkspaceSelect label="How patients choose a hospital" value={controls.arrivalSplitPolicy ?? 'markov_preference'} onChange={value =>
                          update({ arrivalSplitPolicy: value as QCControls['arrivalSplitPolicy'], compareAllocation: false })}
                          options={[
                            { value: 'markov_preference', label: 'Distance and preferred hospital' },
                            { value: 'markov_proximity', label: 'Distance only' },
                          ]} />
                        <small>{controls.arrivalSplitPolicy === 'markov_preference'
                          ? 'In 14 barangays, the mapped preferred hospital gets 1.5× weight. The other 128 use distance alone.'
                          : 'Each additional 3 km halves a hospital’s weight.'}</small>
                      </label>
                      <button type="button" className="text-button qc-capacity-summary" onClick={() => chooseSettingsSection('capacity')}>
                        <BedDouble size={16} aria-hidden="true" />
                        <span><strong>Bed capacity</strong><small>{hospitalCount === undefined ? 'Loading hospital reservations…' : `${hospitalCount} hospitals · ${networkBeds.dengue.toLocaleString()} reserved for dengue · ${networkBeds.nonDengue.toLocaleString()} for other care`}</small></span>
                        <ChevronRight size={14} aria-hidden="true" />
                      </button>
                      <details className="qc-assumptions">
                        <summary>Admissions and length of stay</summary>
                        <div className="qs-field-pair">
                          {numeric('hospitalizationRate', 'Cases admitted', 0, 100, '%', 1, 100)}
                          {numeric('admissionDelayDays', 'Delay before admission', 0, 28, 'days')}
                          {numeric('lengthOfStayDays', 'Hospital stay', 1, 30, 'days')}
                        </div>
                      </details>
                    </fieldset>
                    </div>
                    <div role="tabpanel" id="qc-section-panel-capacity" aria-labelledby="qc-section-capacity" hidden={settingsSection !== 'capacity'}>
                    <fieldset className="qc-fieldset">
                      <legend><BedDouble aria-hidden="true" size={16} /> Bed totals</legend>
                      {numeric('baselineOccupancy', 'Default dengue reservation', 0, 100, '% of the hospital bed total')}
                      {numeric('holdingCapacity', 'Default holding spaces per hospital', 0, 10000, 'temporary spaces')}
                      <p className="qc-capacity-intro">Each hospital keeps its PhilHealth accredited bed total (30 Sep 2026). The simulation initially reserves 40% for dengue and 60% for other care, rounded per hospital. Actual staffing is unknown.</p>
                      <p className="qc-capacity-intro">Holding spaces are a separate planning assumption. Each hospital starts with five temporary spaces, two for dengue and three for other care.</p>
                      {hospitalCount !== undefined && (
                        <dl className="qc-capacity-totals">
                          <div><dt>All {hospitalCount} hospitals</dt><dd>{(networkBeds.dengue + networkBeds.nonDengue).toLocaleString()} beds</dd></div>
                          <div><dt>Reserved for dengue</dt><dd>{networkBeds.dengue.toLocaleString()}</dd></div>
                          <div><dt>Reserved for other care</dt><dd>{networkBeds.nonDengue.toLocaleString()}</dd></div>
                          <div><dt>Holding spaces</dt><dd>{networkBeds.holding.toLocaleString()}</dd></div>
                          <div><dt>Extra staffed beds</dt><dd>{networkBeds.extra.toLocaleString()}</dd></div>
                        </dl>
                      )}
                      {hospitalRows.length > 0 && <details className="qc-reservations">
                        <summary>View reservations for all {hospitalRows.length} hospitals</summary>
                        <div className="qc-reservation-scroll" tabIndex={0} role="region" aria-label="Hospital bed reservations">
                          <table className="qc-import-table">
                            <thead><tr><th scope="col">Hospital</th><th scope="col">Accredited beds</th><th scope="col">Reserved for dengue</th><th scope="col">Reserved for other care</th></tr></thead>
                            <tbody>{hospitalRows.map(b => <tr key={b.facilityId}><th scope="row">{b.name}</th><td>{(b.dengueBeds + b.nonDengueBeds).toLocaleString()}</td><td>{b.dengueBeds.toLocaleString()}</td><td>{b.nonDengueBeds.toLocaleString()}</td></tr>)}</tbody>
                          </table>
                        </div>
                      </details>}
                    </fieldset>
                    <fieldset className="qc-fieldset">
                      <legend><MapPin aria-hidden="true" size={16} /> Hospital-specific beds</legend>
                      <p className="qc-capacity-intro">
                        Adjust one hospital’s bed reservations and temporary holding spaces, or import a file for several hospitals.
                      </p>
                      <div className="qs-field-label">Hospital
                        <HospitalSearch label="Hospital to adjust" value={capacityHospital} disabled={!context}
                          onChange={value => { setCapacityHospital(value); setHospitalDraft(null); }}
                          options={[...(context?.hospitals ?? [])]
                            .sort((a, b) => a.name.localeCompare(b.name))
                            .map(h => ({ id: h.id, name: h.name, note: allotmentById.has(h.id) ? 'Has its own values' : undefined }))} />
                      </div>
                      {selectedHospital && (
                        <div className="qc-hospital-editor">
                          <p className="qc-hospital-status">
                            {allotmentById.has(capacityHospital) ? (usesDefaultShare ? 'Hospital total · default reservation percentage.' : 'Hospital-specific reservation.') : 'Using the default reservation percentage.'}
                            {allotmentById.has(capacityHospital) && (
                              <button type="button" className="text-button qc-import-clear" onClick={resetHospital}><RotateCcw size={12} aria-hidden="true" />Use defaults</button>
                            )}
                          </p>
                          <div className="qc-split-group">
                            <dl className="qc-source-total"><dt>Accredited beds</dt><dd>{selectedHospital.accreditedBeds.toLocaleString()}</dd></dl>
                            {shareSlider('beds')}
                            <div className="qs-field-pair">
                              {hospitalField('dengueBeds', 'Reserved for dengue', 'starting staffed dengue capacity')}
                              {hospitalField('nonDengueBeds', 'Reserved for other care', 'set aside for other patients')}
                            </div>
                          </div>
                          <div className="qc-split-group">
                            {hospitalField('holdingTotal', 'Total holding spaces', 'temporary, unstaffed', true)}
                            {shareSlider('holding')}
                            <div className="qs-field-pair">
                              {hospitalField('dengueHolding', 'Holding for dengue', 'for dengue overflow')}
                              {hospitalField('nonDengueHolding', 'Holding for non-dengue', 'kept for other patients')}
                            </div>
                          </div>
                        </div>
                      )}
                      <div className="qc-import-block">
                        <strong>Import many hospitals</strong>
                        <span>CSV or Excel (.xlsx). Importing replaces every hospital-specific value.</span>
                        <div className="qc-import-actions">
                          <button type="button" className="text-button qc-import-button" disabled={allotmentImport.status === 'loading'} onClick={() => allotmentFile.current?.click()}>
                            <Upload size={15} aria-hidden="true" />{allotmentImport.status === 'loading' ? 'Importing…' : 'Import CSV or Excel'}
                          </button>
                          <button type="button" className="text-button qc-template-button" disabled={!context} onClick={downloadAllotmentTemplate}>
                            <Download size={15} aria-hidden="true" />Download template
                          </button>
                          <input ref={allotmentFile} className="qs-sr-only" type="file" tabIndex={-1} aria-hidden="true"
                            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importAllotments(file); }} />
                        </div>
                      </div>
                      <div aria-live="polite">
                        {allotmentImport.status === 'error' && (
                          <div className="qc-import-result qc-import-error" role="alert">
                            <strong>{allotmentImport.fileName}</strong>
                            <span>{allotmentImport.message}</span>
                            {!!allotmentImport.result?.errors.length && (
                              <ul>
                                {allotmentImport.result.errors.slice(0, 8).map(item => <li key={item.row}>Row {item.row}: {item.message}</li>)}
                                {allotmentImport.result.errors.length > 8 && <li>…and {allotmentImport.result.errors.length - 8} more rows.</li>}
                              </ul>
                            )}
                          </div>
                        )}
                        {allotments.length > 0 && (
                          <div className="qc-import-result">
                            <strong>{allotmentImport.status === 'done' && allotmentImport.fileName ? `${allotmentImport.fileName} imported` : 'Hospital-specific values'}</strong>
                            <span>{allotments.length} {allotments.length === 1 ? 'hospital has its' : 'hospitals have their'} own values{hospitalsUsingDefaults ? ` · ${hospitalsUsingDefaults} use the defaults` : ''}</span>
                            <details>
                              <summary>Review hospital-specific values</summary>
                              <table className="qc-import-table">
                                <thead><tr><th scope="col">Hospital</th><th scope="col">Total beds</th><th scope="col">Dengue</th><th scope="col">Non-dengue</th><th scope="col">Holding</th></tr></thead>
                                <tbody>
                                  {allotments.map(a => {
                                    const b = hospitalRows.find(h => h.facilityId === a.facilityId);
                                    if (!b) return null;
                                    return <tr key={a.facilityId}><th scope="row">{context?.hospitals.find(h => h.id === a.facilityId)?.name ?? a.facilityId}</th><td>{(b.dengueBeds + b.nonDengueBeds).toLocaleString()}</td><td>{b.dengueBeds.toLocaleString()}</td><td>{b.nonDengueBeds.toLocaleString()}</td><td>{b.holdingSpaces.toLocaleString()}</td></tr>;
                                  })}
                                </tbody>
                              </table>
                            </details>
                            <button type="button" className="text-button qc-import-clear" onClick={clearAllotments}><X size={13} aria-hidden="true" />Clear all hospital-specific values</button>
                          </div>
                        )}
                      </div>
                      <small className="qc-import-note">
                        Match each row by facility_id or hospital_name. Enter accredited_beds alone to use the default percentage,
                        or enter both dengue_beds and non_dengue_beds to specify the split. Each row must match its registered hospital total.
                        Holding and extra capacity columns are optional. Counts are whole beds.
                      </small>
                    </fieldset>
                    </div>
                  </>
                ) : (
                  <p role="status">
                    {loading
                      ? 'Loading the selected engine and case ranges…'
                      : 'Model data unavailable.'}
                  </p>
                )}
              </div>
            </form>
            <footer className="qc-controls-footer">
            {controls && (
              <div className={`qc-run-bar${stale ? ' stale' : ''}`}>
                {stale && (
                  <p className="qc-run-hint">
                    Run to apply your changes.
                  </p>
                )}
                <button
                  className="qc-primary text-button" type="submit" form="qc-settings-form"
                  disabled={loading || !!dateError}
                >
                  <Play size={14} />{' '}
                  {loading ? 'Calculating…' : 'Run simulation'}
                </button>

              </div>
            )}{' '}
          </footer></>);
  const overview = (<div
              className="qc-panel-view qc-overview"
              hidden={activeDetail !== 'overview'}
            >
              <section
                className={`qc-scenario-card${stale ? ' stale' : ''}`}
                aria-label="Current scenario"
              >
                <span className="qc-total-icon" aria-hidden="true">
                  <SlidersHorizontal size={20} />
                </span>
                <div className="qc-total-text">
                  <span>
                    {tab === 'future'
                      ? 'Future forecast'
                      : 'Historical replay'}
                  </span>
                  <strong>
                    {controls
                      ? `${dateLabel(controls.startDate)} – ${dateLabel(controls.endDate)}`
                      : 'Loading…'}
                  </strong>
                  <small>
                    {Number.isFinite(selectedDays)
                      ? `${selectedDays} days · `
                      : ''}
                    {scenarioDetail} ·{' '}
                    {firstHospital ? 'first-hospital placement' : 'overflow by hospital-choice probability'}
                  </small>
                </div>
                {stale && (
                  <p className="qc-run-hint">
                    Settings changed. Open Scenario and run again.
                  </p>
                )}
              </section>
              <h3 className="qc-panel-subheading">
                {scenario && snapshot
                  ? `Day ${day} of ${scenario.durationDays} · ${formatScenarioDate(snapshot.date)}`
                  : 'Day totals · press Play to start'}
              </h3>
              {!scenario && (
                <p className="qc-panel-tip">
                  Simulation not started. Play or advance the day to display
                  modeled values. Base cases for{' '}
                  {controls?.startDate ?? 'the selected date'}: unavailable; no
                  verified daily observation is available for that date. Dated
                  hospital inventory and source evidence remain available.
                </p>
              )}
              <section
                className="qc-totals"
                aria-label="Observed cases and simulation totals"
              >
                {summaryCard(
                  'observed',
                  <History size={20} />,
                  scenario
                    ? tab === 'future'
                      ? 'Observed historical source cases'
                      : 'Observed cases already'
                    : 'Base cases for selected date',
                  scenario
                    ? format(source?.observedSourceYearToDateCases)
                    : 'Unavailable',
                  scenario
                    ? `Source-year to ${source ? `${source.issueBlock.YR}/WN ${source.issueBlock.WN}` : 'origin'} · ${tab === 'future' ? 'not a current surveillance count' : `latest block ${format(source?.observedCasesAtOrigin)}`}`
                    : 'No authoritative daily base count for this date; historical source totals are separate evidence.',
                  'Observed counts come from the historical UPRI-NOAH source data. A simulated date has no authoritative daily base count, so modeled values start from the forecast.',
                  'observed'
                )}
                {summaryCard(
                  'new',
                  <Activity size={20} />,
                  `New expected cases · day ${day}`,
                  format(snapshot?.expectedCases),
                  `Daily range ${range(snapshot?.dailyCaseRange)}`,
                  'Modeled new dengue cases in QC on the selected day (not observed).'
                )}
                {summaryCard(
                  'cumulative',
                  <TrendingUp size={20} />,
                  'Cumulative cases',
                  format(snapshot?.cumulativeCases),
                  `Range ${range(snapshot?.caseRange)} · expected cases`,
                  'Modeled cases accumulated from day 1 to the selected day.'
                )}
                {summaryCard(
                  'census',
                  <BedDouble size={20} />,
                  'Supported census',
                  format(snapshot?.supportedCensus),
                  'Expected patients',
                  GLOSSARY.census[1]
                )}
                {summaryCard(
                  'holding',
                  <Hourglass size={20} />,
                  'Unstaffed holding',
                  format(snapshot?.holdingCensus),
                  'Expected patients',
                  GLOSSARY.holding[1]
                )}
                {summaryCard(
                  'unresolved',
                  <TriangleAlert size={20} />,
                  'Unresolved demand',
                  format(snapshot?.cumulativeUnresolved),
                  'Cumulative expected patients',
                  GLOSSARY.unresolved[1],
                  'alert'
                )}
              </section>
              <h3 className="qc-panel-subheading">Whole selected window</h3>
              <section
                className="qc-totals"
                aria-label="Case summary and range validation"
              >
                {summaryCard(
                  'window',
                  <CalendarDays size={20} />,
                  'QC expected cases · full selected range',
                  format(fullPeriod?.expectedCases),
                  `${controls?.startDate && controls.endDate ? `${formatScenarioDate(controls.startDate)} – ${formatScenarioDate(controls.endDate)}` : 'Choose a date window'} · source-week/calendar alignment is an explicit assumption.`,
                  GLOSSARY.expected[1]
                )}
                {summaryCard(
                  'window-range',
                  <TrendingUp size={20} />,
                  'Experimental empirical case range · 80% target',
                  range(fullPeriod?.caseRange),
                  'Conditional on historical spatial weights',
                  GLOSSARY.range[1]
                )}
                {data && coverageValues.length > 0 && (
                  <p className="qc-range-caution">
                    Range validation: observed weekly coverage{' '}
                    {format(Math.min(...coverageValues) * 100)}–
                    {format(Math.max(...coverageValues) * 100)}%{' '}
                    {data.futureForecast
                      ? 'on 2024–2025 seasonal holdouts (52 weeks/year)'
                      : 'across eight retrospective origins/horizon'}
                    . The 80% target was not achieved; these are exploratory
                    ranges.
                  </p>
                )}
              </section>
              <div className="qc-panel-notes">
                <strong>Notes</strong>
                <ul>
                  <li>
                    {tab === 'future'
                      ? 'Projected dengue cases drive admissions and bed demand under the selected hospital assumptions.'
                      : 'Historical replay: source-based case/environment forecasts for retrospective periods.'}{' '}
                    No place selection is required. QC calculations; Philippines
                    geography is context only.
                  </li>
                  <li>
                    Every number here is a research estimate from historical
                    data and stated assumptions. It is not live surveillance,
                    real bed availability or clinical advice.
                  </li>
                  <li>
                    Methods, validation tables and sources are in the{' '}
                    <b>Methods & sources</b> result view.
                  </li>
                </ul>
              </div>
            </div>);
  const analysis = (<section className="qc-details" aria-label="Simulation details">
            <div {...panelProps('hotspots')}>
              <section
                className="qc-hotspot-key"
                aria-label="Hotspot locations, projected cases and nearest hospitals"
              >
                <h2>Top projected-burden barangays</h2>
                <p>
                  {hotspotRanking
                    ? `Annual burden forecast for ${hotspotRanking.forecastYear}; source/training cutoff ${hotspotRanking.trainingCutoffYear}. Top ten is a research ranking, not a validated outbreak threshold.`
                    : 'Hotspot ranking awaits approved model data.'}{' '}
                  Window cases: {controls?.startDate} to {controls?.endDate}{' '}
                  (end exclusive).
                </p>
                <div className="qc-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Candidate location</th>
                        <th>XGBoost annual burden</th>
                        <th>Projected window cases</th>
                        <th>Nearest hospital</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hotspotRows.map((row, index) => {
                        const b = context!.barangays.find(
                          (b) => b.id === row.barangayId
                        )!;
                        const closest = b.nearestHospitals[0];
                        const h = context!.hospitals.find(
                          (h) => h.id === closest?.facilityId
                        );
                        return (
                          <tr
                            key={b.id}
                            className={selected === b.id ? 'selected' : ''}
                          >
                            <td>
                              <button
                                aria-pressed={selected === b.id}
                                onClick={() => inspectHotspot(b.id)}
                              >
                                {index + 1}. {b.name}
                              </button>
                            </td>
                            <td>
                              {format(b.predictedAnnualCases)}
                              <small>
                                Annual forecast · {hotspotRanking?.forecastYear}
                              </small>
                            </td>
                            <td>
                              {format(row.cumulativeCases)}
                              <small>Range {range(row.caseRange)}</small>
                            </td>
                            <td>
                              {h ? (
                                <button onClick={() => inspectHospital(h.id)}>
                                  {h.name}
                                </button>
                              ) : (
                                'Unavailable'
                              )}
                              <small>
                                {closest
                                  ? `${closest.distanceKm.toFixed(2)} km · straight-line`
                                  : 'Distance unavailable'}
                              </small>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {hotspotRanking && (
                  <details className="qc-hotspot-validation">
                    <summary>
                      Annual XGBoost ranking definition & validation
                    </summary>
                    <p>
                      {hotspotRanking.criterion}. Forecast year{' '}
                      {hotspotRanking.forecastYear}; source-label cutoff{' '}
                      {hotspotRanking.trainingCutoffYear}. Shares are held fixed
                      for the selected window.
                    </p>
                    <div className="qc-table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Evaluation year</th>
                            <th>Model</th>
                            <th>Annual-case MAE</th>
                            <th>Matched observed top 10</th>
                          </tr>
                        </thead>
                        <tbody>
                          {hotspotRanking.validation.map((row) => (
                            <tr key={`${row.targetYear}-${row.model}`}>
                              <td>{row.targetYear}</td>
                              <td>{row.model}</td>
                              <td>{format(row.maeAnnualCases)}</td>
                              <td>
                                {row.top10Overlap}/{row.topCount}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>
                      {hotspotRanking.limitations} Baselines can outperform
                      XGBoost on the ranking metric; no superiority claim is
                      made.
                    </p>
                  </details>
                )}
                {scenario && !finalDay?.hotspotIds.length && (
                  <p>
                    No positive projected hotspot burden in this date window.
                  </p>
                )}
                {!scenario && (
                  <p>
                    Hotspot ranks and case projections appear after the
                    simulation starts.
                  </p>
                )}
                {area && (
                  <div className="qc-selected-place">
                    <strong>Selected barangay: {area.name}</strong>
                    <span>
                      {format(selectedPeriod?.cumulativeCases)} projected cases
                      in the window ·{' '}
                      {format(
                        snapshot?.barangays.find(
                          (b) => b.barangayId === area.id
                        )?.cumulativeCases
                      )}{' '}
                      accumulated to day {day}
                    </span>
                    <span>
                      Nearest hospital:{' '}
                      {context?.hospitals.find(
                        (h) => h.id === nearest[0]?.facilityId
                      )?.name ?? 'Unavailable'}
                      {nearest[0]
                        ? ` · ${nearest[0].distanceKm.toFixed(2)} km`
                        : ''}
                    </span>
                    <small>
                      Progression uses this barangay’s dated allocated forecast.
                      All places update together; no infection chain is modeled.
                      XGBoost predicts annual barangay burden; its modeled
                      shares allocate QC weekly forecasts. Independent weekly
                      barangay forecasts remain unavailable.
                    </small>
                    {scenario && (
                      <svg
                        viewBox="0 0 440 75"
                        role="img"
                        aria-label={`Daily projected case allocation for ${area.name}`}
                      >
                        {selectedDaily.map((d) => {
                          const cases = d.expectedCases;
                          const height = (cases / maxSelectedDaily) * 60;
                          return (
                            <rect
                              key={d.dayIndex}
                              x={
                                8 +
                                ((d.dayIndex - 1) * 424) / scenario.durationDays
                              }
                              y={68 - height}
                              width={Math.max(
                                2,
                                424 / scenario.durationDays - 3
                              )}
                              height={height}
                              fill={d.dayIndex === day ? '#225d61' : '#5f9a8e'}
                            >
                              <title>{`${d.date}: ${format(cases)} expected cases in ${area.name}`}</title>
                            </rect>
                          );
                        })}
                      </svg>
                    )}
                  </div>
                )}
              </section>
            </div>
            <div {...panelProps('place-beds')}>
              <section
                className="qc-local-bed-forecast"
                aria-label="Bed demand from selected barangay"
              >
                <h2>
                  Bed demand from {area?.name ?? 'the selected barangay'}
                </h2>
                <div
                  className={`qc-surge-status${surgeActive ? ' active' : ''}`}
                  role="status"
                >
                  {surgeStatus} ·{' '}
                  {snapshot
                    ? formatScenarioDate(snapshot.date)
                    : controls?.startDate
                      ? formatScenarioDate(controls.startDate)
                      : 'select dates'}
                  <small>
                    Configured scenario status, not an observed outbreak
                    declaration.
                  </small>
                </div>
                <p>
                  Case model:{' '}
                  {data?.futureForecast
                    ? 'XGBoost seasonal projection'
                    : 'audited historical cases/weather replay'}
                  . Bed need is a conditional admissions/LOS calculation; no
                  observed hospital occupancy targets were available for model
                  training.
                </p>
                <p>
                  {markovResult && area && (preferredHospital ? `Preferred emergency hospital: ${preferredHospital.name}. ` : 'Hospital preference is unknown. This barangay uses proximity alone. ')}
                  Demand from this barangay only, divided using the configured
                  hospital-choice assumption. Required staffed beds are
                  calculated from projected cases, admission fraction, delay and
                  length of stay. Actual staffed capacity and vacancies are
                  unknown.
                </p>
                {selectedShortfall != null && <p><strong>{formatFractional(selectedShortfall)} expected beds short</strong> from this barangay on day {day}, across its first hospitals.</p>}
                {selectedBedProjection ? (
                  <div className="qc-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Hospital</th>
                          <th>Assumed arrival share</th>
                          <th>Expected admissions</th>
                          <th>No-added-surge peak beds</th>
                          <th>With-surge peak beds</th>
                          <th>Peak extra beds from surge</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedBedProjection.hospitals.map((row) => {
                          const h = context?.hospitals.find(
                            (h) => h.id === row.facilityId
                          );
                          return (
                            <tr key={row.facilityId}>
                              <td>
                                <button
                                  onClick={() =>
                                    inspectHospital(row.facilityId)
                                  }
                                >
                                  {h?.name ?? row.facilityId}
                                </button>
                              </td>
                              <td>{formatFractional(row.share * 100)}%</td>
                              <td>{format(row.expectedAdmissions)}</td>
                              <td>
                                {format(row.baselinePeakStaffedBedsRequired)}
                              </td>
                              <td>{format(row.peakStaffedBedsRequired)}</td>
                              <td>
                                {format(row.additionalStaffedBedsDueToSurge)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p>
                    Start or advance the simulation to show this place’s
                    bed-demand projections.
                  </p>
                )}
                {selectedBedProjection && (
                  <div
                    className="qc-nearby-bed-use"
                    aria-label="Bed demand at the three highest-share destinations"
                  >
                    {selectedBedProjection.hospitals.slice(0, 3).map((row) => {
                      const h = context?.hospitals.find(
                        (h) => h.id === row.facilityId
                      );
                      const stat = snapshot?.facilities.find(
                        (f) => f.facilityId === row.facilityId
                      );
                      return (
                        <article key={row.facilityId}>
                          <button
                            onClick={() => inspectHospital(row.facilityId)}
                          >
                            {h?.name ?? row.facilityId}
                          </button>
                          <p>
                            Assumed arrival split: {formatFractional(row.share * 100)}%
                            from this place. This is not bed utilization.
                          </p>
                          <BedUse
                            forecast={stat?.bedForecast}
                            day={day}
                            occupancyPct={stat?.supportedOccupancyPct}
                          />
                          <small>
                            Hospital-wide demand from all barangays; peak demand
                            percentage{' '}
                            {scenario?.bedProjection?.hospitalPeaks.find(
                              (f) => f.facilityId === row.facilityId
                            )?.peakDemandUtilizationPct == null
                              ? 'unavailable'
                              : `${format(scenario.bedProjection?.hospitalPeaks.find((f) => f.facilityId === row.facilityId)?.peakDemandUtilizationPct)}%`}{' '}
                            of assumed dengue slots.
                          </small>
                        </article>
                      );
                    })}
                  </div>
                )}
                <small>
                  Hospital cards include all barangays’
                  demand; local rows above show only this place. Site-specific
                  staffing rounds up to whole beds. These are demand estimates,
                  not available beds.
                </small>
              </section>
            </div>
            <div {...panelProps('city-beds')}>
              <section
                className="qc-bed-forecast"
                aria-label="Bed demand forecast"
              >
                <div className="qc-section-heading">
                  Bed forecast · required dengue staffing, occupancy & shortfall
                </div>
                <div className="qc-bed-summary">
                  <div>
                    <span>Peak staffed beds required</span>
                    <strong>
                      {format(scenario?.bedProjection?.staffedBedsRequired)}
                    </strong>
                    <small>
                      Peak day {scenario?.bedProjection?.peakDayIndex ?? '—'} ·{' '}
                      {scenario?.bedProjection?.peakDate ?? '—'}
                    </small>
                  </div>
                  <div>
                    <span>Peak low–high case sensitivity</span>
                    <strong>
                      {format(
                        scenario?.bedProjection?.peakLowerStaffedBedsRequired
                      )}
                      –
                      {format(
                        scenario?.bedProjection?.peakUpperStaffedBedsRequired
                      )}
                    </strong>
                    <small>Fixed admission fraction and LOS</small>
                  </div>
                  <div>
                    <span>Additional staffed beds needed</span>
                    <strong>
                      {format(
                        scenario?.bedProjection?.peakAdditionalStaffedBedsNeeded
                      )}
                    </strong>
                    <small>Peak network shortfall vs assumed capacity</small>
                  </div>
                  <div>
                    <span>Peak extra beds due to surge</span>
                    <strong>
                      {format(
                        scenario?.bedProjection
                          ?.peakAdditionalStaffedBedsDueToSurge
                      )}
                    </strong>
                    <small>
                      No-added-surge peak:{' '}
                      {format(
                        scenario?.bedProjection?.baselinePeakStaffedBedsRequired
                      )}{' '}
                      beds
                    </small>
                  </div>
                </div>
                <div className="qc-chart-heading">
                  <strong>Daily unconstrained bed demand</strong>
                  <span>Expected beds · shaded case-range sensitivity</span>
                </div>
                <svg
                  viewBox="0 0 900 100"
                  role="img"
                  aria-label="Forecast daily bed demand and case-range sensitivity, separate from real vacancies"
                >
                  {scenario && (
                    <>
                      <polygon
                        points={[
                          ...scenario.days.map(
                            (d, i) =>
                              `${12 + (i * 876) / scenario.durationDays},${90 - ((d.bedForecast?.upperBeds ?? d.bedForecast?.expectedBeds ?? 0) / maxBeds) * 78}`
                          ),
                          ...[...scenario.days]
                            .reverse()
                            .map(
                              (d) =>
                                `${12 + (d.dayIndex * 876) / scenario.durationDays},${90 - ((d.bedForecast?.lowerBeds ?? d.bedForecast?.expectedBeds ?? 0) / maxBeds) * 78}`
                            ),
                        ].join(' ')}
                        fill="#5f9a8e33"
                      />
                      <polyline
                        points={scenario.days
                          .map(
                            (d, i) =>
                              `${12 + (i * 876) / scenario.durationDays},${90 - ((d.bedForecast?.expectedBeds ?? 0) / maxBeds) * 78}`
                          )
                          .join(' ')}
                        fill="none"
                        stroke="#2f7d70"
                        strokeWidth={2}
                      />
                      <line
                        x1={12 + (day * 876) / scenario.durationDays}
                        x2={12 + (day * 876) / scenario.durationDays}
                        y1={8}
                        y2={92}
                        stroke="#225d61"
                        strokeDasharray="3 4"
                      />
                    </>
                  )}
                </svg>
                <p>
                  Day {day}:{' '}
                  {format(staffedBeds)} staffed
                  dengue beds required;{' '}
                  {format(snapshot?.bedForecast?.hospitalBedsShort)}{' '}
                  additional staffed beds needed across hospitals{firstHospital ? '' : ' before diversion'}. Each site’s shortage is rounded up separately.
                </p>
                {snapshot && <section aria-label="Hospital bed shortages">
                  <h3>Hospital bed shortages{firstHospital ? '' : ' before diversion'} · day {day}</h3>
                  {shortHospitals.length ? <div className="qc-table-scroll"><table><thead><tr>
                    <th>Hospital</th><th>Expected beds needed</th><th>Assumed dengue slots</th><th>In supported beds</th><th>Beds short</th>
                  </tr></thead><tbody>{shortHospitals.map(f => <tr key={f.facilityId}>
                    <td><button onClick={() => inspectHospital(f.facilityId)}>{context?.hospitals.find(h => h.id === f.facilityId)?.name ?? f.facilityId}</button></td>
                    <td>{format(f.bedForecast?.expectedBeds)}</td><td>{format(f.bedForecast?.assumedSupportedDengueCapacity)}</td>
                    <td>{format(f.supportedCensus)}</td><td><strong>{format(f.bedForecast?.additionalStaffedBedsNeeded)}</strong></td></tr>)}</tbody></table></div>
                    : <p>Assumed dengue slots cover expected bed demand at every hospital today.</p>}
                </section>}
                <p>
                  Initial dengue census is assumed zero. Real staffed
                  beds/current occupancy and observed hospital admissions are
                  unavailable; bed ranges are case-demand sensitivity, not
                  validated occupancy intervals.
                </p>
              </section>
            </div>
            <div {...panelProps('barangays')}>
              <section className="qc-hotspots">
                <div className="qc-section-heading">
                  Automatically ranked QC barangays · full selected date range
                </div>
                <p>
                  Annual XGBoost burden predictions supply modeled shares;
                  observed annual source counts below are from{' '}
                  {context?.weightYear ?? '—'}. Forecast ranges omit
                  spatial-model uncertainty. Positive demand is not hotspot
                  membership.{' '}
                  <button onClick={() => setShowAll((v) => !v)}>
                    {showAll ? 'Show top 10' : 'Show all 142 barangays'}
                  </button>
                </p>
                <div className="qc-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Barangay</th>
                        <th>Observed annual cases</th>
                        <th>Expected window cases</th>
                        <th>Conditional case range</th>
                        {firstHospital && <th>Attributed beds short · day {day}</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {fullPeriod?.barangays
                        .slice(0, showAll ? 142 : 10)
                        .map((row) => {
                          const b = context!.barangays.find(
                            (b) => b.id === row.barangayId
                          )!;
                          const bedsShort = dailyShortfalls.get(row.barangayId);
                          return (
                            <tr
                              key={b.id}
                              className={selected === b.id ? 'selected' : ''}
                            >
                              <td>
                                <button onClick={() => inspectHotspot(b.id)}>
                                  {b.name}
                                </button>
                              </td>
                              <td>
                                {format(b.observedAnnualCases)} (
                                {context?.weightYear})
                              </td>
                              <td>{format(row.cumulativeCases)}</td>
                              <td>{range(row.caseRange)}</td>
                              {firstHospital && <td>{bedsShort == null ? '—' : formatFractional(bedsShort)}</td>}
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
                {!scenario && (
                  <p>The ranked table appears after the simulation starts.</p>
                )}
              </section>
            </div>
            {chainComparison && <div {...panelProps('compare')}><section className="qc-comparison">
              <h2>First-hospital bed shortages</h2>
              <p>Both runs use the same forecast, hospital capacities and length of stay. Only the hospital-choice weights change.</p>
              <div className="qc-table-scroll"><table><thead><tr><th>Hospital choice</th><th>Peak beds short{firstHospital ? '' : ' before diversion'}</th><th>First day at peak shortage</th><th>Peak expected beds</th><th>Unplaced by final day</th></tr></thead>
                <tbody>{chainComparison.map(row => <tr key={row.arrivalSplitPolicy}><td>{row.arrivalSplitPolicy === 'markov_preference' ? 'Distance and preferred hospital' : 'Distance only'}</td>
                  <td>{format(row.peakBedsShort)}</td><td>{row.peakShortageDate ? formatScenarioDate(row.peakShortageDate) : 'No shortage'}</td><td>{format(row.peakExpectedBeds)}</td><td>{formatFractional(row.cumulativeUnresolved)}</td></tr>)}</tbody>
              </table></div></section></div>}
            <div {...panelProps('methods')}>
              <section
                className="qc-methods"
                aria-label="Forecast ranges, date assumptions and reproducibility"
              >
                <h2>Forecast ranges, date assumptions and reproducibility</h2>
                <p>{data?.referenceSelectionAssumption}</p>
                <p>{data?.rangeInterpretation}</p>
                <p>{source?.intervalCaveat}</p>
                <p>{source?.spatialCaveat}</p>
                <p>{data?.assumptions}</p>
                {data?.futureForecast ? (
                  <>
                    <p>{data.futureForecast.stalenessCaveat}</p>
                    {data.futureForecast.usesWeather && <p>The current case model still uses historical weather inputs. Future simulations use its default seasonal profile.</p>}
                    {timing && <details className="qc-environment">
                      <summary>Forecast period and surge timing</summary>
                      <p>{timing.horizonDays} elapsed days from {formatScenarioDate(timing.startDate)} to the final snapshot on {formatScenarioDate(timing.endDateExclusive)}.</p>
                      <p>{timing.surgeOnsetDate
                        ? `The added surge starts on ${formatScenarioDate(timing.surgeOnsetDate)}. The largest multiplier applied is ${format(timing.maximumAppliedMultiplier)}×. ${timing.fullMultiplierReached ? 'The requested peak falls within this period.' : 'The period ends before the requested peak.'}`
                        : 'This run has no added case surge.'}</p>
                      <p>Extra staffed beds are scheduled for {formatScenarioDate(timing.staffedSurgeActivationSnapshotDate)}{timing.staffedSurgeActivationWithinWindow ? '.' : ', outside this period.'} The assumed admission delay is {timing.admissionDelayDays} days and the stay is {timing.lengthOfStayDays} days.</p>
                      <p>The seasonal pattern repeats from historical evidence. The largest gap from the source data is {timing.sourceYearGap} years. {timing.centralGapEvaluated
                        ? 'The seasonal baseline was evaluated at this gap.'
                        : 'The baseline has no matched evaluation for this gap.'} {!timing.rangeEvaluatedAtRequestedGap && 'Range coverage is unverified for this scenario and year gap.'}</p>
                    </details>}
                    <p>
                      Selection: {data.futureForecast.selection.criterion}.
                      Calibration MAE: XGBoost{' '}
                      {format(
                        data.futureForecast.selection.scores.seasonal_xgboost
                      )}
                      , original boosted{' '}
                      {format(
                        data.futureForecast.selection.scores
                          .seasonal_boosted_trees
                      )}
                      , seasonal baseline{' '}
                      {format(
                        data.futureForecast.selection.scores.seasonal_baseline
                      )}
                      . XGBoost is a requested planning model; comparisons below
                      do not establish superiority. There are no observed
                      admissions or occupancy targets to validate a direct bed
                      model.
                    </p>
                    <div className="qc-table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Evaluation year</th>
                            <th>Model</th>
                            <th>n</th>
                            <th>MAE cases/week</th>
                            <th>RMSE</th>
                            <th>Weighted absolute error</th>
                            <th>Mean bias</th>
                            <th>Range coverage</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.futureForecast.validation.map((m) => (
                            <tr key={`${m.year}-${m.model}`}>
                              <td>{m.year}</td>
                              <td>{m.model}</td>
                              <td>{m.n}</td>
                              <td>{format(m.mae)}</td>
                              <td>{format(m.rmse)}</td>
                              <td>{format(m.wapePct)}%</td>
                              <td>{format(m.meanBias)}</td>
                              <td>{format(m.empiricalRangeCoverage * 100)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>{data.futureForecast.rangeEvidencePolicy}</p>
                    {data.futureForecast.leadYearGapValidation && (
                      <details>
                        <summary>
                          Forecast accuracy when source data are older
                        </summary>
                        <p>
                          Frozen XGBoost configuration, evaluated with one, two
                          or three source-year gaps. No later-year labels enter
                          training or weather analogs. Range coverage was
                          evaluated only at gap 1; these stale-source
                          comparisons assess central cases.
                        </p>
                        <div className="qc-table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Evaluation year</th>
                                <th>Last training year</th>
                                <th>Year gap</th>
                                <th>Model</th>
                                <th>MAE cases/week</th>
                                <th>Weighted error</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.futureForecast.leadYearGapValidation.map(
                                (row) => (
                                  <tr
                                    key={`${row.year}-${row.sourceYearGap}-${row.model}`}
                                  >
                                    <td>{row.year}</td>
                                    <td>{row.lastTrainingYear}</td>
                                    <td>{row.sourceYearGap}</td>
                                    <td>{row.model}</td>
                                    <td>{format(row.mae)}</td>
                                    <td>{format(row.wapePct)}%</td>
                                  </tr>
                                )
                              )}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    )}
                    {data.futureForecast.calendarDiagnostics && (
                      <details>
                        <summary>
                          Accuracy by month, season and number of days
                        </summary>
                        <p>
                          {
                            data.futureForecast.calendarDiagnostics
                              .targetDefinition
                          }{' '}
                          {
                            data.futureForecast.calendarDiagnostics
                              .evaluationDesign
                          }{' '}
                          These are retrospective diagnostics. Negative bias
                          means underprediction; weighted absolute error is an
                          error percentage, not an accuracy score.
                        </p>
                        <p>
                          XGBoost configuration:{' '}
                          {data.futureForecast.xgboostVariant}. Selection used
                          only 2018–2023; 2024–2025 were excluded from
                          selection. These evaluation years have already been
                          examined during development.
                        </p>
                        <h3>Window length · XGBoost</h3>
                        <div className="qc-table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Year</th>
                                <th>Days</th>
                                <th>Windows</th>
                                <th>MAE cases/window</th>
                                <th>Weighted error</th>
                                <th>Range coverage</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.futureForecast.calendarDiagnostics.windowLengths
                                .filter(
                                  (row) =>
                                    row.model ===
                                    data.futureForecast?.selectedModel
                                )
                                .map((row) => (
                                  <tr key={`${row.year}-${row.days}`}>
                                    <td>{row.year}</td>
                                    <td>{row.days}</td>
                                    <td>{row.n}</td>
                                    <td>{format(row.mae)}</td>
                                    <td>{format(row.wapePct)}%</td>
                                    <td>
                                      {format(row.empiricalRangeCoverage * 100)}
                                      %
                                    </td>
                                  </tr>
                                ))}
                            </tbody>
                          </table>
                        </div>
                        <h3>Seasonal source quarters · XGBoost</h3>
                        <p>
                          Each quarter contains 13 native source weeks. These
                          are calendar groupings, not official wet/dry-season
                          labels.
                        </p>
                        <div className="qc-table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Year</th>
                                <th>Quarter</th>
                                <th>Weeks</th>
                                <th>MAE cases/week</th>
                                <th>Weighted error</th>
                                <th>Mean bias</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.futureForecast.calendarDiagnostics.sourceQuarters
                                .filter(
                                  (row) =>
                                    row.model ===
                                    data.futureForecast?.selectedModel
                                )
                                .map((row) => (
                                  <tr key={`${row.year}-${row.sourceQuarter}`}>
                                    <td>{row.year}</td>
                                    <td>{row.sourceQuarter}</td>
                                    <td>{row.n}</td>
                                    <td>{format(row.mae)}</td>
                                    <td>{format(row.wapePct)}%</td>
                                    <td>{format(row.meanBias)}</td>
                                  </tr>
                                ))}
                            </tbody>
                          </table>
                        </div>
                        <h3>Assumed calendar months · XGBoost</h3>
                        <div className="qc-table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Year/month</th>
                                <th>Days</th>
                                <th>Predicted cases</th>
                                <th>Source-derived cases</th>
                                <th>Absolute error</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.futureForecast.calendarDiagnostics.monthly
                                .filter(
                                  (row) =>
                                    row.model ===
                                    data.futureForecast?.selectedModel
                                )
                                .map((row) => (
                                  <tr key={`${row.year}-${row.month}`}>
                                    <td>
                                      {row.year}/
                                      {String(row.month).padStart(2, '0')}
                                    </td>
                                    <td>{row.calendarDays}</td>
                                    <td>{format(row.expectedCases)}</td>
                                    <td>{format(row.sourceDerivedCases)}</td>
                                    <td>{format(row.absoluteError)}</td>
                                  </tr>
                                ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    )}
                  </>
                ) : (
                  <div className="qc-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th>n</th>
                          <th>Weather MAE</th>
                          <th>Cases-only MAE</th>
                          <th>Persistence MAE</th>
                          <th>Empirical range coverage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data?.forecastBacktest.map((m) => (
                          <tr key={m.horizon}>
                            <td>{m.horizon} source blocks</td>
                            <td>{m.n}</td>
                            <td>{format(m.weatherMae)}</td>
                            <td>{format(m.casesOnlyMae)}</td>
                            <td>{format(m.persistenceMae)}</td>
                            <td>{format(m.empiricalRangeCoverage * 100)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p>
                  Source:{' '}
                  <a href="https://github.com/pelitro-rcw/dengue-environmental-dataset/tree/02926278d570db8950da368d44db544ae0097615">
                    UPRI-NOAH dengue/environmental dataset
                  </a>
                  , ODC-ODbL 1.0. Philippines regions provide geographic
                  context; all case and hospital-demand calculations are
                  QC-only.
                </p>
                <p>
                  Scenario {data?.scenarioId}
                  <br />
                  Computed {data?.runTimestamp}
                  <br />
                  Workspace result SHA-256 {data?.resultSha256}
                </p>

              </section>
            </div>
          </section>);
  const probabilityPlace = showProbabilities && showHotspotDetails && showHospitals && !hospital ? choiceRow : undefined;
  const selectedPlace = area && !inspectedHospital && (showHotspotDetails || panelView === 'hospitals') ? (
    <section className="qs-inspector-block" aria-label="Selected hotspot details" aria-live="polite">
      {selectedShortfall != null && <p className="qs-inspector-note"><strong>{formatFractional(selectedShortfall)} expected beds short</strong> attributable to this barangay on day {day}. Each hospital’s gap is shared in proportion to its modeled arrivals.</p>}
      <div className="qs-place-heading"><span>{markerHotspotIds?.includes(area.id) ? 'Annual high-burden candidate' : 'Selected barangay · outside the top candidates'}</span><h3>{area.name}</h3></div>
      {markovResult && <div className="qs-choice-control">
        <label><input type="checkbox" checked={!!probabilityPlace} disabled={!choiceRow}
          onChange={event => {
            setShowProbabilities(event.target.checked);
            if (event.target.checked) { setShowHospitals(true); setShowHotspotDetails(true); }
          }} /> Show all {context?.hospitals.length} hospital probabilities</label>
        {probabilityPlace && <small>{connectionsEnabled
          ? 'Hover, tap or focus an arrow to see its probability breakdown.'
          : 'Run the simulation or start playback to show the arrows.'}</small>}
        {choiceRow && context && <HospitalProbabilityPicker key={area.id} origin={area} choices={choiceRow.hospitals}
          hospitals={context.hospitals} distanceOnly={resultSplit === 'markov_proximity'} />}
      </div>}
      <h4>Projected cases</h4>
      <InspectorFacts rows={[
        ['Full selected window', format(selectedPeriod?.cumulativeCases)],
        [`Accumulated to day ${day}`, format(snapshot?.barangays.find(b => b.barangayId === area.id)?.cumulativeCases)],
        ['Experimental window range', range(selectedPeriod?.caseRange)],
      ]} />
      <p className="qs-inspector-note">Modeled allocation, not observed weekly barangay surveillance. The case range is conditional on the spatial weights.</p>
      <details className="qs-inspector-disclosure"><summary>Annual ranking & model context</summary>
        <InspectorFacts rows={[
          ['Annual model', hotspotRanking?.model ?? 'Unavailable'],
          ['Forecast year', hotspotRanking?.forecastYear ?? 'Unavailable'],
          ['Predicted annual cases', scenario ? format(area.predictedAnnualCases) : 'Start playback to view'],
          ['Annual burden rank', area.burdenRank == null ? 'Unavailable' : `${area.burdenRank} of 142`],
        ]} />
        <p>Rank identifies the model’s annual burden order. It is not a case count or a confirmed outbreak.</p>
      </details>
      <section className="qs-inspector-section"><h4>Nearest registered hospital</h4>
        <p className="qs-inspector-name">{nearestHospital?.name ?? 'Unavailable'}</p>
        <InspectorFacts rows={[
          ['Straight-line distance', nearest[0] ? `${nearest[0].distanceKm.toFixed(2)} km` : 'Unavailable'],
          ['Location evidence', 'Provisional point'],
        ]} />
        <div className="qs-inspector-actions"><button type="button" className="text-button" disabled={!nearestHospital} onClick={() => nearestHospital && inspectHospital(nearestHospital.id)}>Inspect hospital <ChevronRight size={14} /></button></div>
      </section>
      <details className="qs-inspector-disclosure"><summary>Hospitals mapped inside this barangay ({localHospitals.length})</summary>
        <div className="qs-location-list">{localHospitals.map(entry => {
          const h = context?.hospitals.find(h => h.id === entry.facilityId);
          return h && <div key={h.id}><div><span>{h.name}</span><small>{entry.distanceKm.toFixed(2)} km · straight-line</small></div><button type="button" className="text-button" onClick={() => inspectHospital(h.id)}>Inspect <ChevronRight size={13} /></button></div>;
        })}</div>
        <p>Provisional point-in-polygon matches; not verified entrances or referral guidance.</p>
      </details>
    </section>
  ) : null;
  const hospitalDetails = (
    <section className="qs-hospital-inspector" aria-label="Hospital scenario details">
      <details className="qs-inspector-disclosure qs-hospital-lookup"><summary>Inspect another registered hospital</summary>
        <WorkspaceSelect label="Inspect hospital" value={hospital} disabled={!context} onChange={value => {
          if (value) inspectHospital(value); else { setHospital(''); setShowHotspotDetails(true); }
        }} options={[{ value: '', label: 'Most likely first hospitals' }, ...(context?.hospitals.map(h => ({ value: h.id, label: h.name })) ?? [])]} />
      </details>
      {inspectedHospital && <section className="qs-inspector-block qs-hospital-context"><h4>Nearest ranked barangay</h4>
        <p className="qs-inspector-name">{hospitalHotspotArea?.name ?? (scenario ? 'No ranked candidate in this window' : 'Start playback to view')}</p>
        <InspectorFacts rows={[
          ['Straight-line distance', hospitalHotspot ? `${hospitalHotspot.distanceKm.toFixed(2)} km` : 'Unavailable'],
          ['Projected window cases', format(hospitalHotspotCases?.cumulativeCases)],
          ['Experimental range', range(hospitalHotspotCases?.caseRange)],
        ]} />
        <p className="qs-inspector-note">Closest annual candidate by representative point; not a verified hospital entrance or referral.</p>
        <div className="qs-inspector-actions"><button type="button" className="text-button" disabled={!hospitalHotspotArea} onClick={() => hospitalHotspotArea && inspectHotspot(hospitalHotspotArea.id)}>Inspect barangay <ChevronRight size={13} /></button><button type="button" className="text-button" onClick={() => { setHospital(''); setShowHotspotDetails(true); }}>Most likely first hospitals</button></div>
      </section>}
      <h3 className="qs-inspector-section-title">{inspectedHospital ? 'Hospital capacity & demand' : 'Most likely first hospitals'}</h3>
      {!inspectedHospital && <p className="qs-inspector-note">{displayedHospitals.length
        ? `Ranked by modeled probability of first admission within the QC network for a patient from ${area?.name}.`
        : 'Hospital-choice probabilities are unavailable for this barangay in the current scenario.'}</p>}
      {displayedHospitals.map(({ hospital: h, share, distanceKm }, index) => {
        const stat = snapshot?.facilities.find(item => item.facilityId === h.id);
        const peak = scenario?.bedProjection?.hospitalPeaks.find(item => item.facilityId === h.id);
        return <details key={h.id} className="qs-hospital-entry" open={!!inspectedHospital}>
          <summary><span className="qs-hospital-entry-name">{h.name}</span><span className="qs-hospital-entry-meta">{share == null ? 'Selected hospital' : `#${index + 1} · ${probabilityPercent(share)} probability`} · {distanceKm == null ? 'Distance unavailable' : `${distanceKm.toFixed(2)} km straight-line`}</span></summary>
          <div className="qs-hospital-entry-body">
            <section className="qs-inspector-section"><h4>Registered inventory</h4>
              <InspectorFacts rows={[
                ['Accredited beds', format(h.accreditedBeds)],
                ['Register date', h.sourceAsOf],
                ['Actual staffed / dengue beds', 'Unknown'],
                ['Location evidence', 'Provisional point'],
              ]} />
              <p className="qs-inspector-note">PhilHealth accredited beds are not staffed, free or dengue-usable beds. {h.id} is a local record ID.</p>
            </section>
            <BedUse forecast={stat?.bedForecast} day={day} occupancyPct={stat?.supportedOccupancyPct} />
            <section className="qs-inspector-section"><h4>Scenario capacity · day {day}</h4>
              <InspectorFacts rows={[
                [firstHospital ? 'Additional beds needed today' : 'Beds short before diversion', format(stat?.bedForecast?.additionalStaffedBedsNeeded)],
                ['First-choice arrivals still unplaced today', stat?.unplacedToday == null ? '—' : formatFractional(stat.unplacedToday)],
                ['Assumed normal capacity', format(stat?.normalCapacity)],
                ['Activated surge capacity', format(stat?.activatedSurgeCapacity)],
                ['Residual supported slots', format(stat?.remainingSupportedCapacity)],
                ['Expected dengue census', format(stat?.supportedCensus)],
                ['Normal-relative occupancy', percent(stat?.normalOccupancyPct)],
                ['Supported-relative occupancy', percent(stat?.supportedOccupancyPct)],
                ['Unstaffed holding', format(stat?.holdingCensus)],
              ]} />
              <p className="qs-inspector-note">Capacities and occupancy are scenario assumptions, not current vacancies.</p>
            </section>
            <details className="qs-inspector-disclosure"><summary>Daily & peak bed-demand breakdown</summary>
              <InspectorFacts rows={[
                ['Required staffed beds', format(stat?.bedForecast?.staffedBedsRequired)],
                ['No-added-surge bed need', format(stat?.bedForecast?.baselineStaffedBedsRequired)],
                ['Extra beds due to surge', format(stat?.bedForecast?.additionalStaffedBedsDueToSurge)],
                ['Low–high case sensitivity', `${format(stat?.bedForecast?.lowerStaffedBedsRequired)}–${format(stat?.bedForecast?.upperStaffedBedsRequired)}`],
                ['Window peak staffing need', format(peak?.peakStaffedBedsRequired)],
                ['Window peak extra from surge', format(peak?.additionalStaffedBedsDueToSurge)],
              ]} />
              <p>All modeled origin barangays contribute to hospital-wide demand. The arrival split is an assumption, not observed admissions.</p>
            </details>
            <div className="qs-inspector-actions">{!inspectedHospital && <button type="button" className="text-button" onClick={() => inspectHospital(h.id)}>Inspect this hospital <ChevronRight size={13} /></button>}<a href={h.primarySourceUrl} target="_blank" rel="noreferrer">Bed source</a><a href={h.coordinateSourceUrl} target="_blank" rel="noreferrer">Coordinate evidence</a></div>
          </div>
        </details>;
      })}
      {!inspectedHospital && selectedBedProjection && <details className="qs-inspector-disclosure"><summary>Bed demand attributed to this barangay</summary>
        <p className="qs-inspector-note">{surgeStatus} · day {day}. Arrival shares are assumptions and do not represent bed occupancy.</p>
        {selectedBedProjection.hospitals.map(row => {
          const stat = snapshot?.facilities.find(item => item.facilityId === row.facilityId);
          return <section key={row.facilityId} className="qs-inspector-section"><h4>{context?.hospitals.find(h => h.id === row.facilityId)?.name ?? row.facilityId}</h4>
            <InspectorFacts rows={[
              ['Assumed arrival share', `${formatFractional(row.share * 100)}%`],
              ['Expected admissions from this place', format(row.expectedAdmissions)],
              ['Peak staffed beds from this place', format(row.peakStaffedBedsRequired)],
              ['Extra beds from surge', format(row.additionalStaffedBedsDueToSurge)],
              [firstHospital ? 'Hospital-wide beds short today' : 'Hospital beds short before diversion', format(stat?.bedForecast?.additionalStaffedBedsNeeded)],
              ['Hospital-wide beds needed', format(stat?.bedForecast?.expectedBeds)],
              ['Assumed dengue slots', format(stat?.bedForecast?.assumedSupportedDengueCapacity)],
              ['Hospital-wide demand percentage', percent(stat?.bedForecast?.demandUtilizationPct)],
            ]} />
            <div className="qs-inspector-actions"><button type="button" className="text-button" onClick={() => inspectHospital(row.facilityId)}>Inspect hospital <ChevronRight size={13} /></button></div>
          </section>;
        })}
        <p>Local rows attribute demand to this barangay; hospital-wide totals include all modeled origins. Actual available beds remain unknown.</p>
      </details>}
    </section>
  );
  return (
    <main ref={workspace} className="qc-workspace qs-workspace" data-map-fullscreen data-reduced-motion={reduced} data-expanded={expanded} data-panel={panelView ?? 'none'} data-wide={wideResults}>
      <h1 className="qs-sr-only">Quezon City simulation</h1>
      <div className="qs-layout" inert={showGuide || undefined}>
        <section className="qs-map-column" aria-label="Simulation map and timeline">
          <div className="qs-map-stage">
            <OutbreakMap context={context} snapshot={snapshot ?? null} maximum={data?.mapScaleMaxDailyCases ?? 1}
              selected={selected} selectedHospital={hospital} hotspotIds={markerHotspotIds} rankedHotspotIds={rankedHotspotIds}
              probabilityPlace={probabilityPlace} distanceOnly={resultSplit === 'markov_proximity'} hospitalHotspot={hospitalHotspot} caseMetric={caseMetric} caseColorMaximum={caseColorMaximum}
              connectionFocus={hospital ? 'hospital' : showHotspotDetails ? 'barangay' : null} inspectionVersion={hospitalInspection}
              animationDurationMs={Math.min(650, 800 / speed)} onSelect={inspectHotspot} onHospital={inspectHospital}
              playing={playing} reducedMotion={reduced} connectionsEnabled={connectionsEnabled} showLinks={links} view={view} buildings3d={buildings3d}
              showHospitals={showHospitals} satellite={satellite} onReady={setMapController} onStatus={setMapStatus}
            showCityBoundaries={showCityBoundaries} onCityBoundaryStatus={setCityBoundaryStatus} />
            <div className="qs-topbar">
              <button ref={scenarioTrigger} type="button" className="text-button qs-scenario-trigger" data-map-overlay aria-label="Edit simulation scenario" aria-controls="qs-context-panel" aria-expanded={panelView === 'scenario'} onClick={() => panelView === 'scenario' ? closePanel() : openPanel('scenario')}>
                <SlidersHorizontal size={17} aria-hidden="true" /><span><strong>{tab === 'historical' ? 'Historical replay' : 'Future forecast'}</strong><small>Quezon City · {Number.isFinite(selectedDays) ? `${selectedDays} days` : 'Choose dates'}</small></span><ChevronDown size={13} aria-hidden="true" />
              </button>
              <button type="button" className="text-button qs-results-trigger" data-map-overlay aria-label="Open simulation results" aria-controls="qs-context-panel" aria-expanded={panelView === 'results'} onClick={() => panelView === 'results' ? closePanel() : openPanel('results')}><ChartNoAxesCombined size={16} aria-hidden="true" /><span>Results</span></button>
            </div>
            {(loading || error || stale) && <div className={`qs-engine-status${error ? ' qs-error' : ''}`} data-map-overlay role={error ? 'alert' : 'status'}>
              <Info size={15} aria-hidden="true" /><span>{error || (stale ? 'Settings changed. Run again to update results.' : connectionStatus === 'starting' ? ENGINE_STARTING_MESSAGE : connectionStatus === 'connecting' ? 'Connecting to the simulation engine…' : 'Loading forecast and simulation…')}</span>
              {!loading && <button type="button" className="text-button" onClick={() => stale ? runSimulation() : calculate(controls ?? undefined)}>{stale ? 'Run simulation' : 'Reload data-based forecast'}</button>}
              {stale && <button type="button" className="text-button" onClick={() => openPanel('scenario')}>Edit settings</button>}
            </div>}
            {(mapStatus === 'unavailable' || mapStatus === 'partial') && <div className="qs-map-fallback" role="status">{mapStatus === 'partial' ? 'Geography layer unavailable.' : 'Map unavailable.'} <button type="button" className="text-button" onClick={() => openDetail('barangays')}>Open result tables</button></div>}
            <div className="qs-map-tools" data-map-overlay role="group" aria-label="Map controls">
              <button type="button" className="text-button qs-map-button" aria-label="Map layers" aria-pressed={panelView === 'layers'} onClick={() => panelView === 'layers' ? closePanel() : openPanel('layers')}><Layers size={18} /><span className="qs-control-tooltip">Map layers</span></button>
              <button type="button" className="text-button qs-map-button" aria-label={buildings3d ? 'Switch to 2D map' : 'Switch to 3D map'} aria-pressed={buildings3d} disabled={mapControlsDisabled} onClick={() => setBuildings3d(v => !v)}><span className="qs-3d">3D</span><span className="qs-control-tooltip">{buildings3d ? '2D view' : '3D view'}</span></button>
              <button type="button" className="text-button qs-map-button" aria-label="Reset map view" disabled={mapControlsDisabled} onClick={() => mapController.current?.resetView()}><Compass size={18} /><span className="qs-control-tooltip">Reset map view</span></button>
              <button ref={fullscreenButton} type="button" className="text-button qs-map-button" aria-label={expanded ? 'Exit fullscreen' : 'Enter fullscreen'} onClick={toggleFullscreen}>{expanded ? <Shrink size={18} /> : <Expand size={18} />}<span className="qs-control-tooltip">{expanded ? 'Exit fullscreen' : 'Fullscreen'}</span></button>
              <span className="qs-control-divider" />
              <button type="button" className="text-button qs-map-button qs-zoom" aria-label="Zoom in" disabled={mapControlsDisabled} onClick={() => mapController.current?.zoomIn()}><Plus size={18} /><span className="qs-control-tooltip">Zoom in</span></button>
              <button type="button" className="text-button qs-map-button qs-zoom" aria-label="Zoom out" disabled={mapControlsDisabled} onClick={() => mapController.current?.zoomOut()}><Minus size={18} /><span className="qs-control-tooltip">Zoom out</span></button>
            </div>
            <button type="button" className="text-button qs-timeline-toggle" data-map-overlay aria-controls="qs-timeline" aria-expanded={!timelineHidden} aria-label={timelineHidden ? 'Show timeline and playback' : 'Hide timeline and playback'} onClick={() => setTimelineHidden(v => !v)}>
              {timelineHidden ? <><ChevronUp size={15} aria-hidden="true" /><span>Show timeline</span><small>Day {day} / {data?.durationDays ?? '—'}{playing ? ' · Playing' : ''}</small></> : <ChevronDown size={15} aria-hidden="true" />}
              {!timelineHidden && <span className="qs-control-tooltip">Hide timeline</span>}
            </button>
            <details className="qs-map-key" data-map-overlay><summary><span className="qs-rank-swatch">1</span> Map key <ChevronDown size={12} aria-hidden="true" /></summary><div className="qc-map-legend qs-map-key-content">
                <strong>
                  {scenario
                    ? caseMetric === 'daily'
                      ? `Expected cases during day ${day} · each place’s dated allocation`
                      : `Expected cases accumulated to day ${day}`
                    : 'Forecast locations preview · case values hidden'}
                </strong>
                <div className="qc-case-color-ramp" aria-hidden="true" />
                <div>
                  {CASE_BANDS.map((b) => (
                    <span key={b.min}>
                      <i style={{ background: b.color }} />
                      {scenario
                        ? format((b.min / 50) * caseColorMaximum)
                        : b.min === 0
                          ? 'Low'
                          : b.min === 50
                            ? 'High'
                            : '·'}
                    </span>
                  ))}
                </div>
                <div className="qc-marker-key">
                  <span>
                    <b className="qc-marker-hotspot" aria-hidden="true">
                      1
                    </b>
                    Annual predicted burden · number = rank
                  </span>
                  <span>
                    <b className="qc-marker-hospital" aria-hidden="true">
                      ✚
                    </b>
                    Hospital · provisional point, location not verified
                  </span>
                  <span><b className="qc-marker-linked" aria-hidden="true">•</b>Other linked or selected barangay · unranked</span>
                  <span>
                    <i className="qc-other-barangay" />
                    Other barangay · may still have cases
                  </span>
                  <span><i className="qc-selected-barangay" aria-hidden="true" />Selected barangay boundary</span>
                  {showCityBoundaries && cityBoundaryStatus === 'ready' && <span><i className="qc-city-boundary" aria-hidden="true" />City boundaries · Quezon City highlighted</span>}
                </div>
                {connectionsEnabled && <div className="qc-line-key">
                  {[...(probabilityPlace ? [SIMULATION_LINES.probability] : [SIMULATION_LINES.proximity,
                    ...(scenario ? [context?.firstAdmissionOriginShares ? { ...SIMULATION_LINES.placement, label: 'Up to three largest placement flows per selection' } : SIMULATION_LINES.placement, SIMULATION_LINES.holding] : []),
                    SIMULATION_LINES['hospital-context']]),
                    ...(snapshot?.expansionRing?.length ? [SIMULATION_LINES.front] : []),
                  ].map(line => <span key={line.kind} data-line-kind={line.kind}><i aria-hidden="true" style={{ borderTop: `${line.width}px ${line.dash.length ? 'dashed' : 'solid'} ${line.color}` }} />{line.label}</span>)}
                  <small>Click a marker to reveal its links. Chevrons point from barangays toward hospitals.</small>
                  {!scenario && <small>Modeled placement lines appear only after advancing to a day with saved placements.</small>}
                </div>}
                <details className="qc-legend-more">
                  <summary>
                    More about the map colors, markers and lines
                  </summary>
                  <p className="qc-progression-note">
                    {hotspotRanking
                    ? `XGBoost ranks predicted annual barangay burden for ${hotspotRanking.forecastYear}, trained only through ${hotspotRanking.trainingCutoffYear}. Only the ten highest-burden candidates receive numbered markers. Their modeled annual shares allocate the dated QC forecast; this is not validated weekly hotspot detection.`
                      : 'Places follow dated modeled allocations; local weekly hotspot forecasts are unavailable.'}{' '}
                    All places update together, without a neighbor-triggered
                    outbreak sequence.
                  </p>
                  <small>
                    Smooth shades between these reference values; scale is fixed
                    for the selected window. Accumulated cases show daily
                    growth; daily forecasts may stay flat within a source week.{' '}
                    {reduced
                      ? 'Reduced motion is on: color animation is disabled.'
                      : 'Colors animate from each place’s forecast values; no geographic infection chain is implied.'}
                  </small>
                  <small>
                    Only the {markerHotspotIds?.length ?? '—'} highest predicted
                    annual-burden candidates have numbered markers and case-band
                    coloring; other barangays remain neutral. Small unnumbered dots identify other barangays linked to an inspected hospital. Positive demand
                    alone does not make a hotspot. Click a marker to inspect its
                    hospital connections. {hotspotRanking?.model}; no
                    confirmed weekly-outbreak claim.
                  </small>
                  <small>
                    Selected links reveal from barangay to hospital, including hospital inspection. Dashed teal links show proximity; dashed ochre links identify a hospital’s nearest ranked barangay. Solid links show saved modeled placements; ochre indicates that some placements use temporary holding. A placement replaces the proximity decoration on the same pair. Markers stay on their locations at every zoom: hospital pins point with their tip and barangay markers are centred. Close markers can overlap (higher ranks on top); zoom in to separate them. Connections end at the markers. Straight-line links are not travel routes or observed patient movement. The raised boundary is decorative. Hospital pins do not report vacancies; all entrance locations remain unverified. Polygon colors show modeled case counts, not hospital pressure or official outbreak thresholds.
                  </small>
                </details>
              </div></details>
          </div>
          <section id="qs-timeline" className="qs-timeline" role="group" aria-label="Simulation timeline and playback" hidden={timelineHidden}>
            <div className="qs-timeline-heading"><span className="qs-research-status">Research scenario · Assumed capacity</span><button ref={guideTrigger} type="button" className="text-button qs-help" aria-label="How to use this page" aria-expanded={showGuide} onClick={openGuide}><CircleHelp size={15} />Help</button></div>
            <div className="qs-transport">
              <button type="button" className="text-button qs-play" aria-label={playing ? 'Pause simulation' : 'Play simulation'} disabled={!data} onClick={() => { if (data && day === data.durationDays) setDay(0); setPlaying(v => !v); }}>{playing ? <Pause size={17} /> : <Play size={17} />}{playing ? 'Pause' : 'Play'}</button>
              <div className="qs-timeline-date"><strong>{snapshot ? formatScenarioDate(snapshot.date) : controls?.startDate ? formatScenarioDate(controls.startDate) : 'Choose a scenario'}</strong><span>Day {day} / {data?.durationDays ?? '—'} · {playing ? 'Playing' : scenario ? 'Paused' : data ? 'Ready' : 'Awaiting update'}</span></div>
              <div className="qs-day-track"><label className="qs-sr-only" htmlFor="qs-simulation-day">Simulation day</label><input id="qs-simulation-day" aria-label="Simulation day" type="range" min={0} max={data?.durationDays ?? 28} step={1} value={day} disabled={!data} onChange={event => { setDay(Number(event.target.value)); setPlaying(false); }} />
                {canJumpToPeak && <button type="button" className="text-button qs-peak" aria-label={`Jump to peak bed demand on day ${peakDay}`} style={{ left: `clamp(0px, calc(${(peakDay! / data!.durationDays) * 100}% - 37px), calc(100% - 74px))` }} onClick={() => { setPlaying(false); setDay(peakDay!); }}><Flag size={11} aria-hidden="true" />Peak · {peakDay}</button>}
              </div>
              <div className="qs-playback-actions">
                <button type="button" className="text-button qs-icon-action" aria-label="Restart simulation" disabled={!data} onClick={() => { setDay(0); setPlaying(false); }}><RotateCcw size={16} /><span className="qs-control-tooltip">Restart</span></button>
                <button type="button" className="text-button qs-final-day" aria-label="Jump to final day" disabled={!data || day >= (data?.durationDays ?? 0)} onClick={() => { setPlaying(false); if (data) setDay(data.durationDays); }}><SkipForward size={16} /><span>Final day</span></button>
                <details ref={playbackMenu} className="qs-playback-more"><summary aria-label="More playback options"><SlidersHorizontal size={15} /><span className="qs-control-tooltip">Playback options</span></summary><div className="qs-playback-menu">
                  <div className="qs-step-controls"><button type="button" className="text-button" aria-label="Previous day" disabled={!data || day === 0} onClick={() => { setPlaying(false); setDay(d => Math.max(0, d - 1)); }}><ChevronLeft size={15} />Previous</button><button type="button" className="text-button" aria-label="Next day" disabled={!data || day >= (data?.durationDays ?? 0)} onClick={() => { setPlaying(false); setDay(d => data ? Math.min(data.durationDays, d + 1) : d); }}>Next<ChevronRight size={15} /></button></div>
                  <label className="qs-field-label">Playback speed<WorkspaceSelect label="Playback speed" value={String(speed)} options={[0.5,1,2,4].map(value => ({ value: String(value), label: `${value} days/s` }))} onChange={value => setSpeed(Number(value))} /></label>
                </div></details>
              </div>
            </div>
            <div className="qs-live-totals" aria-label="Selected-day summary">
              <div><span>Projected cases so far</span><strong>{format(snapshot?.cumulativeCases)}</strong><small>{snapshot?.caseRange ? `Experimental range ${range(snapshot.caseRange)}` : `Cases · accumulated to day ${day}`}</small></div>
              <div><span>Total beds needed</span><strong>{format(staffedBeds)}</strong><small>{firstHospital ? 'Dengue demand, rounded up at each hospital' : 'Staffed beds required · assumed admissions'}</small></div>
              {firstHospital
                ? <div><span>Additional beds needed</span><strong>{format(snapshot?.bedForecast?.hospitalBedsShort)}</strong><small>{snapshot?.bedForecast?.hospitalBedsShort === 0 ? 'Assumed capacity covers demand at every hospital' : 'Shortfall after counting each hospital’s assumed capacity'}</small></div>
                : <div><span>Unplaced demand to date</span><strong>{format(snapshot?.cumulativeUnresolved)}</strong><small>Expected patients · cumulative</small></div>}
              <button type="button" className="text-button qs-more-results" onClick={() => openDetail('overview')}>View results <ChevronRight size={14} /></button>
            </div>
            {introToast && data && !scenario && <p className="qs-first-hint">Press Play or choose a day. Numbered markers show annual burden rank; H pins are hospitals.</p>}
          </section>
        </section>
        <aside id="qs-context-panel" className="qs-context-panel" hidden={!panelView} aria-labelledby="qs-panel-title" data-reduced-motion={reduced}>
          <div className="qs-panel-header"><div>{panelView !== 'scenario' && <span>SurgeWise / Simulation</span>}<h2 ref={panelHeading} tabIndex={-1} id="qs-panel-title">{panelView ? panelTitles[panelView] : 'Simulation'}</h2></div><div>
            {panelView === 'results' && <button type="button" className="text-button qs-panel-icon" aria-label={wideResults ? 'Narrow results panel' : 'Expand results panel'} aria-pressed={wideResults} onClick={() => setWideResults(v => !v)}>{wideResults ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>}
            <button type="button" className="text-button qs-panel-icon" aria-label="Close simulation panel" onClick={closePanel}><X size={18} /></button></div></div>
          <div className="qs-panel-body" hidden={panelView !== 'scenario'} aria-label="Simulation controls">{settings}</div>
          <div className="qs-panel-body qs-results-body" hidden={panelView !== 'results'} aria-label="Simulation results">
            <div className="qs-result-tools"><WorkspaceSelect label="Result view" value={activeDetail} options={detailTabs.map(item => ({ value: item.id, label: item.label }))} onChange={value => setDetailTab(value as DetailTab)} /><button type="button" className="text-button qs-export" disabled={!scenario} onClick={download} aria-label="Export simulation results"><Download size={15} />Export</button></div>
            <div className="qs-analysis-scroll">{overview}
              {activeDetail === 'overview' && <div className="qs-result-actions">
                {activeRun && <a className="qs-report-link" href={`/outbreak-response/report/${activeRun.scenarioId}`} target="_blank" rel="noopener noreferrer">
                  <FileText size={17} />View LGU report<ExternalLink size={14} />
                  <span className="qs-sr-only"> (opens in a new tab)</span>
                </a>}
                <button type="button" className="text-button" disabled={!controls || loading} onClick={compareAllocations}>Compare hospital-choice assumptions <ArrowLeft size={13} /></button>
                <button type="button" className="text-button" onClick={() => openDetail('city-beds')}>Explore daily bed demand <ChevronRight size={13} /></button>
              </div>}
              {activeDetail === 'overview' && <div className="qc-playback-panel">
              <div className="qc-chart-heading">
                <strong>
                  Daily expected cases
                  {scenario ? ' · click a bar to jump to that day' : ''}
                </strong>
                <span>
                  <i className="qc-swatch-baseline" aria-hidden="true" />
                  Reference forecast{' '}
                  <i className="qc-swatch-shock" aria-hidden="true" />
                  Separately assumed shock
                </span>
              </div>
              <svg
                viewBox="0 0 900 80"
                role="img"
                aria-label="QC daily case forecast trajectory, including a separately colored hypothetical shock"
              >
                {scenario?.days.slice(1).map((d, i) => {
                  const x = 10 + (i * 880) / scenario.durationDays,
                    width = 880 / scenario.durationDays - 4;
                  return (
                    <g
                      key={d.dayIndex}
                      className="qc-chart-day"
                      onClick={() => {
                        setPlaying(false);
                        setDay(d.dayIndex);
                      }}
                    >
                      <title>{`Day ${d.dayIndex} · ${d.date}: ${format(d.expectedCases)} expected cases`}</title>
                      <rect
                        x={x - 2}
                        y={0}
                        width={width + 4}
                        height={80}
                        fill={d.dayIndex === day ? '#225d6114' : 'transparent'}
                      />
                      <rect
                        x={x}
                        y={75 - (d.expectedCases / maxCases) * 65}
                        width={width}
                        height={(d.expectedCases / maxCases) * 65}
                        rx={2}
                        fill="#cc873e"
                      />
                      <rect
                        x={x}
                        y={75 - (d.baselineCases / maxCases) * 65}
                        width={width}
                        height={(d.baselineCases / maxCases) * 65}
                        rx={2}
                        fill="#347d77"
                      />
                    </g>
                  );
                })}
              </svg>
              <p className="qc-interval-note">
                Day {day} · cases during [
                {snapshot?.intervalStart.slice(0, 10) ?? '—'},{' '}
                {snapshot?.intervalEnd.slice(0, 10) ?? '—'})
              </p>
            </div>}{analysis}
              {activeDetail === 'methods' && <details className="qc-environment">
                <summary>
                  {tab === 'future'
                    ? 'Seasonal forecasting engine'
                    : 'Environmental basis'}
                </summary>
                {source ? (
                  <>
                    <p>
                      {tab === 'future'
                        ? 'Training observations through'
                        : 'Source origin'}{' '}
                      <strong>
                        {source.issueBlock.YR} / WN {source.issueBlock.WN}
                      </strong>
                    </p>
                    {data?.futureForecast && (
                      <p>
                        <strong>
                          {data.futureForecast.selectedModel ===
                          'seasonal_xgboost'
                            ? 'XGBoost seasonal case forecast'
                            : data.futureForecast.selectedModel ===
                                'seasonal_boosted_trees'
                              ? 'Seasonal gradient-boosted trees'
                              : 'Seasonal baseline'}
                        </strong>
                        <br />
                        Issued for planning: {data.futureForecast.asOfDate}
                      </p>
                    )}
                    {data?.futureForecast?.accuracyAssessment && (
                      <p className="qc-range-caution">
                        Experimental accuracy:{' '}
                        {data.futureForecast.accuracyAssessment.comparison
                          .map(
                            (row) =>
                              `${row.year}: ${format(row.maeSkillVsSeasonalBaseline * 100)}% MAE improvement versus seasonal baseline`
                          )
                          .join('; ')}
                        . Negative means worse. Current-year, barangay-weekly
                        and bed-occupancy accuracy remain unverified.
                      </p>
                    )}
                    {tab === 'historical' && <>
                      {source.environmentalInputs.map((f) => (
                        <div key={f.sourceColumn}>
                          <span>
                            {factorName[f.sourceColumn] || f.sourceColumn}
                          </span>
                          <strong>
                            {format(f.valueAtOrigin)} <small>{f.unit}</small>
                          </strong>
                        </div>
                      ))}
                      <p>Observed inputs at origin, lagged 1, 2 and 4 source blocks in the city model. No measured barangay microclimate.</p>
                    </>}
                  </>
                ) : (
                  <p>
                    {tab === 'future' ? 'Model details load with the case forecast.' : 'Environmental evidence loads with the approved forecast.'}
                  </p>
                )}
              </details>}
            </div>
          </div>
          <div className="qs-panel-body qs-inspector-body" hidden={panelView !== 'hospitals'}>{selectedPlace}{hospitalDetails}<button type="button" className="text-button qs-inspector-results" onClick={() => openDetail(inspectedHospital ? 'city-beds' : 'place-beds')}>{inspectedHospital ? 'View city-wide bed demand' : 'View barangay bed-demand results'} <ChevronRight size={14} /></button></div>
          <div className="qs-panel-body qs-layers-body" hidden={panelView !== 'layers'}>
            <p className="qs-panel-intro">Choose the context and information on your map.</p>
            <label className="qs-field-label">Map area<WorkspaceSelect label="Map extent" value={view} onChange={value => setView(value as 'qc' | 'philippines')} options={[{value:'qc',label:'Quezon City'},{value:'philippines',label:'Philippines context'}]} /></label>
            <label className="qs-field-label">Color barangays by<WorkspaceSelect label="Map case measure" value={caseMetric} onChange={value => setCaseMetric(value as 'daily' | 'cumulative')} options={[{value:'cumulative',label:'Accumulated projected cases'},{value:'daily',label:'Daily projected cases'}]} /></label>
            <label className="qs-layer"><span><MapPin size={17} /><span>Hospital pins<small>PhilHealth inventory · provisional points</small></span></span><input type="checkbox" checked={showHospitals} onChange={event => setShowHospitals(event.target.checked)} /></label>
            <label className="qs-layer"><span><MapIcon size={17} /><span>City boundaries<small>{cityBoundaryStatus === 'unavailable' ? 'Unavailable · NCR boundary file could not load' : 'NCR city outlines · Quezon City highlighted'}</small></span></span><input type="checkbox" checked={showCityBoundaries && cityBoundaryStatus !== 'unavailable'} disabled={cityBoundaryStatus === 'unavailable'} onChange={event => setShowCityBoundaries(event.target.checked)} /></label>
            <label className="qs-layer"><span><Layers size={17} /><span>3D view<small>Generalized buildings where mapped</small></span></span><input type="checkbox" checked={buildings3d} onChange={event => setBuildings3d(event.target.checked)} /></label>
            <label className="qs-layer"><span><Satellite size={17} /><span>Satellite imagery<small>Esri World Imagery · capture dates vary</small></span></span><input type="checkbox" checked={satellite} onChange={event => setSatellite(event.target.checked)} /></label>
            <label className="qs-layer"><span><Activity size={17} /><span>Overview connections<small>Nearby hospitals and daily placements across ranked barangays</small></span></span><input type="checkbox" checked={links} onChange={event => setLinks(event.target.checked)} /></label>
            <label className="qs-layer"><span><Pause size={17} /><span>Reduced motion<small>Static colors and manual playback</small></span></span><input type="checkbox" checked={reduced} onChange={event => { setReduced(event.target.checked); if(event.target.checked) setPlaying(false); }} /></label>
            <p className="qs-layer-note">Colors show projected case counts, not official outbreak thresholds. Uncolored barangays may still have cases. Building geometry and hospital entrances are unverified context. Satellite imagery is dated background, not current conditions.</p>
            <details className="qs-national-context" onToggle={event => setLocatorOpen(event.currentTarget.open)}><summary>Philippines locator</summary>{locatorOpen && <PhilippinesOverview />}</details>
            <button type="button" className="text-button qs-source-link" onClick={() => openDetail('methods')}>Run assumptions & sources <ChevronRight size={14} /></button>
          </div>
          <footer className="qs-panel-footer"><span>Research estimates · No live vacancies</span><a href="/research">Research <ChevronRight size={12} /></a></footer>
        </aside>
      </div>
      {showGuide && <div className="qs-guide-backdrop" onClick={event => { if(event.target === event.currentTarget) closeGuide(); }} onKeyDown={event => {
        if(event.key === 'Escape') { event.stopPropagation(); closeGuide(); }
        if(event.key === 'Tab') {
          const focusable = event.currentTarget.querySelectorAll<HTMLElement>('button, a[href], input, select, summary');
          const first = focusable[0], last = focusable[focusable.length - 1];
          if(event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if(!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      }}><section className="qs-guide" role="dialog" aria-modal="true" aria-labelledby="qs-guide-title"><div className="qs-guide-heading"><h2 id="qs-guide-title">Explore a preparedness scenario</h2><button type="button" ref={guideClose} className="text-button qs-panel-icon" aria-label="Close guide" onClick={closeGuide}><X size={18} /></button></div>
        <ol><li><strong>Play the scenario.</strong> Use the timeline, jump to the final day, or explore the marked peak in bed demand.</li><li><strong>Inspect the map.</strong> Numbered markers are annual projected-burden ranks, not case counts or confirmed outbreaks. H pins are hospitals.</li><li><strong>Try an assumption.</strong> Open Scenario to edit dates, surge and hospital assumptions. Run again to update every result together.</li><li><strong>Explore Results.</strong> Read the case ranges, bed-demand charts and hospital-choice comparisons, then export the saved scenario.</li></ol>
        <details><summary>Terms used in this simulation</summary><dl>{Object.values(GLOSSARY).map(([term, meaning]) => <div key={term}><dt>{term}</dt><dd>{meaning}</dd></div>)}</dl></details>
        <p>Historical source evidence and configured assumptions support this research scenario. Current hospital vacancies, dengue capacity and entrances are not verified. This is not live surveillance or clinical referral guidance.</p><button type="button" className="text-button qs-primary" onClick={closeGuide}>Explore the map</button>
      </section></div>}
    </main>
  );
}
