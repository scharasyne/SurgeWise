import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire, Module } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { SIMULATION_LINES } from './simulation-connections.ts';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

// Constructed display fixture, not source observations. Distinct sentinel counts
// detect projections leaking into the loaded-but-not-started workspace.
const dayFixture = (dayIndex) => ({
  dayIndex,
  date: '2027-01-01',
  intervalStart: '2027-01-01',
  intervalEnd: '2027-01-02',
  expectedCases: 987654,
  cumulativeCases: 987654,
  baselineCases: 987654,
  barangays: [],
  facilities: [
    {
      facilityId: 'fixture-hospital',
      supportedOccupancyPct: 87.5,
      bedForecast: {
        expectedBeds: 12,
        assumedSupportedDengueCapacity: 10,
        demandUtilizationPct: 120,
      },
    },
  ],
  hotspotIds: ['fixture-hotspot'],
  expansionRing: [],
  bedForecast: { staffedBedsRequired: 765432 },
  supportedCensus: 0,
  holdingCensus: 0,
  cumulativeUnresolved: 0,
});
const fixture = {
  progressionMethod: 'production_weekly_barangay_forecast',
  durationDays: 1,
  days: [dayFixture(0), dayFixture(1)],
  periodSummary: {
    expectedCases: 987654,
    caseRange: { lowerCases: 876543, upperCases: 1098765 },
    barangays: [
      { barangayId: 'fixture-hotspot', cumulativeCases: 987654 },
      { barangayId: 'outside-top-ten', cumulativeCases: 23 },
    ],
  },
  bedProjection: {
    staffedBedsRequired: 765432,
    hospitalPeaks: [],
    placePeaks: [
      {
        barangayId: 'fixture-hotspot',
        hospitals: [
          {
            facilityId: 'fixture-hospital',
            share: 1,
            expectedAdmissions: 543210,
            peakStaffedBedsRequired: 765432,
            baselinePeakStaffedBedsRequired: 65432,
            additionalStaffedBedsDueToSurge: 12345,
          },
        ],
      },
    ],
  },
  forecastEvidence: {
    issueBlock: { YR: 2025, WN: 52 },
    environmentalInputs: [],
    observedSourceYearToDateCases: 654321,
  },
  forecastBacktest: [],
};
const filename = fileURLToPath(
  new URL('../components/qc-simulation-workspace.tsx', import.meta.url)
);
const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;
const require = createRequire(import.meta.url);

function renderWorkspace(day, stateOverrides = {}) {
  let state = 0;
  const loaded = new Module(filename);
  loaded.filename = filename;
  loaded.paths = require.resolve.paths('react');
  const nativeRequire = loaded.require.bind(loaded);
  loaded.require = (name) => {
    if (name === 'react')
      return {
        ...React,
        useState(initial) {
          const index = state++;
          const overrides = {
            2: fixture,
            4: {
              barangays: ['fixture-hotspot', 'outside-top-ten'].map((id) => ({
                id,
                name: id,
                nearestHospitals: [],
              })),
              hospitals: [],
            },
            5: day,
            8: 'fixture-hotspot',
            16: false,
            ...stateOverrides,
          };
          return [index in overrides ? overrides[index] : initial, () => {}];
        },
        useRef: (value) => ({ current: value }),
        useEffect: () => {},
        useCallback: (callback) => callback,
      };
    if (name === 'next/dynamic')
      return {
        default: () => (props) =>
          React.createElement('output', {
            'data-hotspot-markers': props.hotspotIds?.join(',') ?? '',
          }),
      };
    if (name === '@/components/workspace-select') return { default: props => React.createElement('button', { type: 'button', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }, props.options.find(option => option.value === props.value)?.label ?? props.value) };
    if (name === '@/components/hospital-search') return { default: props => React.createElement('input', { type: 'text', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }) };
    if (name === '@/components/qc-workspace-sidebar')
      return { default: ({ children }) => children };
    if (name === '@/components/workspace-loader') return { default: () => null };
    if (name === '@/components/surgewise-mark') return { default: () => null };
    if (name.startsWith('@/lib/'))
      return require(`./${name.slice('@/lib/'.length)}.ts`);
    if (name.endsWith('qc-archive-forecast-validation.json')) return { default: nativeRequire(name) };
    return nativeRequire(name);
  };
  loaded._compile(compiled, filename);
  return loaded.exports.default();
}

function renderDay(day, stateOverrides = {}) {
  return renderToStaticMarkup(renderWorkspace(day, stateOverrides));
}

test('legend uses renderer line definitions, preserves day-zero gating and covers actual marker meanings', () => {
  const lines = tree => findElements(tree, node => node.props?.['data-line-kind']);
  const preview = renderWorkspace(0);
  assert.equal(lines(preview).length, 0);
  const started = renderWorkspace(1);
  for (const { node } of lines(started)) {
    const definition = SIMULATION_LINES[node.props['data-line-kind']];
    const swatch = findElements(node, child=>child.type==='i')[0].node;
    assert.equal(swatch.props.style.borderTop, `${definition.width}px ${definition.dash.length ? 'dashed' : 'solid'} ${definition.color}`);
    assert.ok(renderToStaticMarkup(node).includes(definition.label));
  }
  assert.ok(lines(started).some(({node})=>node.props['data-line-kind']==='holding'));
  const html=renderToStaticMarkup(started);
  for(const label of ['provisional point, location not verified','Selected or linked barangay','Selected barangay boundary','Click a barangay or hospital to reveal its links','barangays are shaded by their modeled cases']) assert.ok(html.includes(label),label);
  assert.ok(!html.includes('Hover or inspect a separated'));
  // Numbered rank markers were removed: every barangay is shaded instead.
  for(const removed of ['number = rank','Numbered markers','numbered markers','remain neutral','may still have cases']) assert.ok(!html.includes(removed),removed);
});

function findElements(node, predicate, ancestors = []) {
  if (!node || typeof node !== 'object') return [];
  const matches = predicate(node) ? [{ node, ancestors }] : [];
  const children = node.props?.children;
  for (const child of Array.isArray(children)
    ? children.flat(Infinity)
    : [children]) {
    matches.push(...findElements(child, predicate, [...ancestors, node]));
  }
  return matches;
}

const controlFixture = {
  startDate: '2012-07-01',
  endDate: '2012-07-15',
  mode: 'forecast',
  normalCapacity: 20,
  surgeCapacity: 10,
  holdingCapacity: 5,
  hospitalizationRate: 0.15,
  baselineOccupancy: 0.75,
  lengthOfStayDays: 4,
  admissionDelayDays: 0,
  surgeActivationDay: 0,
  allocationPolicy: 'first_hospital',
  arrivalSplitPolicy: 'markov_preference',
};

test('the initial view reserves the map, with one hidden contextual panel and an independent timeline', () => {
  const tree = renderWorkspace(0, { 3: controlFixture });
  const panel = findElements(tree, node => node.props?.id === 'qs-context-panel')[0].node;
  assert.equal(panel.props.hidden, true);
  const timeline = findElements(tree, node => node.props?.['aria-label'] === 'Simulation timeline and playback');
  assert.equal(timeline.length, 1);
  assert.ok(!timeline[0].ancestors.some(node => node.props?.id === 'qs-context-panel'));
  assert.equal(findElements(tree, node => node.type === 'header').length, 0);
  assert.equal(findElements(tree, node => node.type === 'aside').length, 1);
});

test('future setup offers a case surge and hospital planning without a weather scenario', () => {
  for (const surgeEnabled of [true, false]) {
    const controls = { ...controlFixture, surgeEnabled, surgeMultiplier: 2, growthDays: 7, surgeOnsetDay: 0, weatherProfile: 'wetter' };
    const tree = renderWorkspace(0, { 0: 'future', 3: controls, 23: 'scenario' });
    const form = findElements(tree, node => node.props?.id === 'qc-settings-form')[0].node;
    const html = renderToStaticMarkup(form);
    assert.match(html, /Projected dengue cases/);
    assert.match(html, /Add a hypothetical surge/);
    assert.match(html, /Hospital planning/);
    assert.doesNotMatch(html, /weather|wetter|drier|hotter/i);
    for (const label of ['Peak case multiplier', 'Days before surge starts', 'Time to peak']) {
      assert.equal(findElements(form, node => node.props?.['aria-label'] === label).length, Number(surgeEnabled));
    }
    assert.doesNotMatch(renderToStaticMarkup(tree), /wetter weather/i);
  }
});

test('imported allotments replace the default split only for the hospitals they list', () => {
  // Constructed planning assumptions, not source records.
  const hospitals = [{ id: 'HOSP-614', name: 'Alpha Hospital', accreditedBeds: 40 }, { id: 'HOSP-615', name: 'Beta Hospital', accreditedBeds: 20 }];
  const bedAllotments = [{ facilityId: 'HOSP-614', dengueBeds: 30, nonDengueBeds: 10, holdingSpaces: 7 }];
  const html = renderToStaticMarkup(renderWorkspace(1, { 3: { ...controlFixture, bedAllotments }, 4: { barangays: ['fixture-hotspot', 'outside-top-ten'].map(id => ({ id, name: id, nearestHospitals: [] })), hospitals }, 23: 'scenario' }));
  assert.ok(html.includes('Import CSV or Excel') && html.includes('Download template'));
  assert.ok(html.includes('1 hospital has its own values · 1 use the defaults'));
  assert.ok(html.includes('Bed totals') && html.includes('Hospital to adjust') && !html.includes('Default beds per hospital'));
  // Network totals: HOSP-614 imported (30/10/7, default extra 10+0) + HOSP-615 default (5/15/5, extra 10+0).
  for (const [label, value] of [['All 2 hospitals', '60 beds'], ['Reserved for dengue', '35'], ['Reserved for other care', '25'], ['Holding spaces', '12'], ['Extra staffed beds', '20']])
    assert.ok(html.includes(`<dt>${label}</dt><dd>${value}</dd>`), label);
  assert.match(html.replace(/<!-- -->/g, ''), /<th scope="row">Alpha Hospital<\/th><td>40<\/td><td>30<\/td><td>10<\/td>/);
  const plain = renderToStaticMarkup(renderWorkspace(1, { 3: controlFixture, 4: { barangays: ['fixture-hotspot', 'outside-top-ten'].map(id => ({ id, name: id, nearestHospitals: [] })), hospitals }, 23: 'scenario' }));
  assert.ok(plain.includes('Import CSV or Excel') && !plain.includes('Clear all hospital-specific values'));
  assert.ok(plain.includes('<dt>Reserved for dengue</dt><dd>15</dd>'));
});

test('capacity table shows whole starting reservations for totals-only and unlisted hospitals', () => {
  const hospitals = [{ id: 'HOSP-614', name: 'Alpha', accreditedBeds: 85 }, { id: 'HOSP-615', name: 'Beta', accreditedBeds: 20 }];
  const controls = { ...controlFixture, baselineOccupancy: .9, bedAllotments: [{ facilityId: 'HOSP-614', staffedBeds: 85 }] };
  const html = renderToStaticMarkup(renderWorkspace(1, { 3: controls, 4: { barangays: ['fixture-hotspot', 'outside-top-ten'].map(id => ({ id, name: id, nearestHospitals: [] })), hospitals }, 23: 'scenario' })).replace(/<!-- -->/g, '');
  assert.ok(html.includes('<th scope="row">Alpha</th><td>85</td><td>9</td><td>76</td>'));
  assert.ok(html.includes('<th scope="row">Beta</th><td>20</td><td>2</td><td>18</td>'));
  assert.ok(html.includes('<dt>Reserved for dengue</dt><dd>11</dd>'));
});

test('both modes and scenario assumptions remain accessible in Scenario while export has one Results entry point', () => {
  const tree = renderWorkspace(1, { 3: controlFixture, 23: 'scenario' });
  const settings = findElements(tree, node => node.props?.['aria-label'] === 'Simulation controls')[0];
  assert.equal(settings.node.props.hidden, false);
  const tabs = findElements(settings.node, node => node.props?.role === 'tab' && node.props?.id?.startsWith('qc-tab-'));
  assert.equal(tabs.length, 2); assert.equal(tabs.filter(item => item.node.props['aria-selected']).length, 1);
  assert.equal(findElements(settings.node, node => node.props?.label === 'Hospital to adjust').length, 1);
  for (const label of ['Start date', 'Duration', 'Cases admitted', 'Hospital stay', 'Delay before admission']) {
    assert.equal(findElements(settings.node, node => node.props?.['aria-label'] === label).length, 1, label);
  }
  // Bed capacity is a second tab row; its panel stays mounted (hidden) so no input is lost.
  const sections = findElements(settings.node, node => node.props?.role === 'tab' && node.props?.id?.startsWith('qc-section-'));
  assert.deepEqual(sections.map(item => [item.node.props.id, item.node.props['aria-selected']]), [['qc-section-scenario', true], ['qc-section-capacity', false]]);
  const sectionPanel = id => findElements(settings.node, node => node.props?.id === id)[0].node.props;
  assert.equal(sectionPanel('qc-section-panel-scenario').hidden, false);
  assert.equal(sectionPanel('qc-section-panel-capacity').hidden, true);
  // The default split is no longer edited here; totals still come from the engine inputs (20 beds at 75% non-dengue).
  for (const label of ['Staffed beds per hospital', 'Beds for dengue', 'Beds for non-dengue', 'Extra staffed beds', 'Days until extra beds open', 'Temporary holding spaces'])
    assert.equal(findElements(settings.node, node => node.props?.['aria-label'] === label).length, 0, label);
  assert.equal(findElements(settings.node, node => node.props?.label === 'How patients choose a hospital').length, 1);
  assert.equal(findElements(settings.node, node => node.props?.label === 'When a hospital is full').length, 1);
  const presets = findElements(settings.node, node => node.props?.['aria-pressed'] !== undefined);
  assert.equal(presets.length, 4);
  assert.deepEqual(presets.filter(({node}) => node.props['aria-pressed']).map(({node}) => node.key), ['14']);
  assert.ok(presets.every(({node}) => node.props.type === 'button'));
  const snapshot = findElements(settings.node, node => node.props?.className === 'qs-window-note')[0].node;
  assert.match(renderToStaticMarkup(snapshot), /Jul 15, 2012/);
  const exports = findElements(tree, node => node.type === 'button' && node.props.onClick?.name === 'download');
  assert.equal(exports.length, 1);
  assert.ok(exports[0].ancestors.some(node => node.props?.['aria-label'] === 'Simulation results'));
});

test('fullscreen contains the timeline and contextual controls, and loading/errors stay visible outside closed panels', () => {
  const tree = renderWorkspace(0, { 3: controlFixture });
  const fullscreen = findElements(tree, node => node.props?.['data-map-fullscreen'] !== undefined);
  assert.equal(fullscreen.length, 1);
  assert.equal(findElements(fullscreen[0].node, node => node.props?.['aria-label'] === 'Simulation timeline and playback').length, 1);
  assert.equal(findElements(fullscreen[0].node, node => node.props?.id === 'qs-context-panel').length, 1);
  for (const overrides of [{ 2: null, 4: null, 16: true }, { 17: 'Forecast unavailable' }]) {
    const current = renderWorkspace(0, overrides);
    const messages = findElements(current, node => node.props?.className?.startsWith('qs-engine-status'));
    assert.equal(messages.length, 1);
    assert.ok(!messages[0].ancestors.some(node => node.props?.id === 'qs-context-panel'));
  }
});

test('hospital inspection keeps actions outside explanatory paragraphs and retains separate capacity and occupancy facts', () => {
  const context = {
    barangays: ['fixture-hotspot','outside-top-ten'].map(id => ({ id,name:'Constructed barangay fixture',nearestHospitals:[{facilityId:'fixture-hospital',distanceKm:1}],hospitalsWithinBarangay:[] })),
    hospitals: [{ id:'fixture-hospital',name:'Constructed hospital fixture',accreditedBeds:100,sourceAsOf:'2026-09-30',primarySourceUrl:'https://example.invalid/register',coordinateSourceUrl:'https://example.invalid/point' }],
  };
  const tree = renderWorkspace(1,{4:context,9:'fixture-hospital',23:'hospitals'});
  const inspector = findElements(tree,node=>node.props?.className==='qs-panel-body qs-inspector-body')[0].node;
  assert.equal(inspector.props.hidden,false);
  for(const paragraph of findElements(inspector,node=>node.type==='p')) {
    assert.equal(findElements(paragraph.node,node=>node.type==='button').length,0);
  }
  const html=renderToStaticMarkup(tree);
  for(const label of ['Actual staffed / dengue beds','Unknown','Normal-relative occupancy','Supported-relative occupancy','Unstaffed holding','Activated surge capacity','Residual supported slots','Expected dengue census','Window peak staffing need','Coordinate evidence']) assert.ok(html.includes(label),label);
  assert.match(html,/120% of modeled dengue slots/);
});

test('preview keeps hospital rankings and search available, with arrows waiting for a run or playback', () => {
  const hospitals = ['Farther preferred', 'Closest', 'Third', 'Fourth'].map((name, i) => ({ id: 'H' + i, name }));
  const origin = { id: 'fixture-hotspot', name: 'Constructed barangay', nearestHospitals: [{ facilityId: 'H1', distanceKm: 1 }] };
  const choices = hospitals.map((h, i) => ({ ...fixture.bedProjection.placePeaks[0].hospitals[0],
    facilityId: h.id, share: [.4, .35, .15, .1][i], breakdown: { distanceKm: [2, 1, 3, 4][i] } }));
  const place = { barangayId: origin.id, hospitals: choices };
  const otherOrigin = { id: 'outside-top-ten', name: 'Other constructed barangay', nearestHospitals: [] };
  const selected = { 4: { barangays: [origin, otherOrigin], hospitals }, 10: true, 23: 'hospitals' };
  for (const policy of ['markov_preference', 'markov_proximity']) {
    const row = policy === 'markov_preference' ? place : { ...place, hospitals: [
      { ...choices[1], share: .4 }, { ...choices[0], share: .35 }, ...choices.slice(2),
    ] };
    const loaded = { ...fixture, bedProjection: { ...fixture.bedProjection, arrivalSplitPolicy: policy, placePeaks: [row] } };
    const tree = renderWorkspace(0, { ...selected, 2: loaded });
    const mapFor = workspace => findElements(workspace, node => 'probabilityPlace' in (node.props ?? {}))[0].node;
    const map = mapFor(tree);
    assert.equal(map.props.probabilityPlace, row);
    assert.equal(map.props.connectionsEnabled, false);
    assert.equal(mapFor(renderWorkspace(0, { ...selected, 2: loaded, 6: true })).props.connectionsEnabled, true);
    assert.equal(mapFor(renderWorkspace(1, { ...selected, 2: loaded })).props.connectionsEnabled, true);
    assert.equal(map.props.distanceOnly, policy === 'markov_proximity');
    const control = findElements(tree, node => node.props?.className === 'qs-choice-control')[0].node;
    const toggle = findElements(control, node => node.type === 'input')[0].node;
    assert.equal(toggle.props.checked, true);
    assert.equal(toggle.props.disabled, false);
    const cards = findElements(tree, node => node.props?.className === 'qs-hospital-entry');
    assert.deepEqual(cards.map(item => item.node.key), row.hospitals.slice(0, 3).map(h => h.facilityId));
    assert.match(renderToStaticMarkup(cards[0].node), /#1 · 40.00% probability/);
    assert.match(renderToStaticMarkup(control), /role="combobox"/);
    assert.doesNotMatch(renderToStaticMarkup(tree), /543,210|765,432/);
  }
  const draft = renderWorkspace(0, { ...selected, 2: null });
  assert.equal(findElements(draft, n => n.props?.className === 'qs-hospital-entry').length, 0);
  assert.match(renderToStaticMarkup(draft), /Hospital-choice probabilities are unavailable/);
});

test('loaded day zero hides projection counts, bed forecasts and historic totals; advancing reveals them', () => {
  const before = renderDay(0);
  assert.match(before, /Simulation not started/);
  assert.match(before, /Base cases for selected date/);
  assert.match(before, /data-hotspot-markers="fixture-hotspot"/);
  assert.ok(
    !before.includes('data-hotspot-markers="fixture-hotspot,outside-top-ten"')
  );
  assert.match(before, /Forecast locations preview · case values hidden/);
  for (const count of [
    '987,654',
    '876,543',
    '1,098,765',
    '765,432',
    '654,321',
    '543,210',
    '12,345',
  ])
    assert.ok(!before.includes(count), count);
  assert.ok(!before.includes('120% of modeled dengue slots'));
  const after = renderDay(1);
  assert.ok(!after.includes('Simulation not started'));
  for (const count of ['987,654', '765,432', '654,321', '543,210', '12,345'])
    assert.ok(after.includes(count), count);
  assert.match(after, /120% of modeled dengue slots/);
  assert.match(after, /87.5%/);
  assert.match(after, /This is not bed utilization/);
  const restarted = renderDay(0);
  assert.ok(!restarted.includes('987,654'));
});

test('Simulation owns observation inputs and shows dated weekly results only after playback starts', () => {
  const evidence = { ...fixture.forecastEvidence, weeklyCases: [
    { year: 2023, week: 1, cityCases: 87.12, barangayCases: { 'fixture-hotspot': 2 },
      scenarioCityCases: 174.24, scenarioBarangayCases: { 'fixture-hotspot': 4 } },
  ] };
  const settings = { 0: 'future', 2: { ...fixture, forecastEvidence: evidence },
    3: { ...controlFixture, weeklyInput: { weeks: 6, multiplier: '2' } } };
  const before = renderDay(0, settings);
  assert.match(before, /aria-label="Case source"/);
  assert.match(before, /aria-label="Forecast horizon"/);
  assert.doesNotMatch(before, /Weekly observations|uploaded observations/i);
  assert.doesNotMatch(before, /Weekly forecast cases|174\.24/);
  const after = renderDay(1, settings);
  for (const label of ['Weekly forecast cases', 'Weekly case area', '2023 · week 1', '87.12', '174.24']) assert.ok(after.includes(label), label);
  const historical = renderDay(1, { 2: { ...fixture, forecastEvidence: { ...evidence, caseSourceKind: 'gp_reconstruction' } } });
  assert.match(historical, /Imputed weekly cases/);
  assert.doesNotMatch(historical, /Weekly forecast cases/);
});

test('the QC timeline distinguishes weekly demand change, staffed totals and extra beds', () => {
  const days = Array.from({length: 15}, (_, i) => ({...dayFixture(i), weeklyCasesChangePct: -5,
    bedForecast: {expectedBeds: 10.5, weeklyDemandChangePct: 25, hospitalBedsRequired: 46, hospitalBedsShort: 0} }));
  const html = renderDay(14, { 2: {...fixture, durationDays: 14, days}, 3: controlFixture });
  for (const label of ['QC expected bed demand', '↑ 25% vs last week', '↓ 5% vs last week', 'QC staffed beds required', 'QC additional beds needed', 'Hospital bed details']) assert.ok(html.includes(label), label);
  assert.match(html, /aria-label="Simulation day"[^>]*step="7"/);
});

test('workspace shows automatic engine startup status and a reload action on failure', () => {
  const starting = renderDay(0, { 2: null, 4: null, 16: true, 20: 'starting' });
  assert.match(
    starting,
    /Engine starting or temporarily unavailable/
  );
  assert.match(
    starting,
    /Connecting automatically; this can take up to two minutes/
  );
  const failed = renderDay(0, {
    2: null,
    4: null,
    17: 'Engine did not respond within two minutes.',
  });
  assert.match(failed, /role="alert"/);
  assert.match(failed, /Engine did not respond within two minutes/);
  assert.match(failed, /Reload data-based forecast/);
  assert.ok(!failed.includes('Engine starting or temporarily unavailable'));
});

test('switching tabs and leaving the workspace cancel requests; late old results stay hidden', async () => {
  const effects = [],
    requests = [],
    updates = [];
  let state = 0;
  const loaded = new Module(filename);
  loaded.filename = filename;
  loaded.paths = require.resolve.paths('react');
  const nativeRequire = loaded.require.bind(loaded);
  loaded.require = (name) => {
    if (name === 'react')
      return {
        ...React,
        useState(initial) {
          const index = state++;
          return [initial, (value) => updates.push([index, value])];
        },
        useRef: (value) => ({ current: value }),
        useEffect: (effect) => effects.push(effect),
        useCallback: (callback) => callback,
      };
    if (name === 'next/dynamic') return { default: () => () => null };
    if (name === '@/components/workspace-select') return { default: props => React.createElement('button', { type: 'button', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }, props.options.find(option => option.value === props.value)?.label ?? props.value) };
    if (name === '@/components/hospital-search') return { default: props => React.createElement('input', { type: 'text', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }) };
    if (name === '@/components/qc-workspace-sidebar')
      return { default: ({ children }) => children };
    if (name === '@/components/workspace-loader') return { default: () => null };
    if (name === '@/components/surgewise-mark') return { default: () => null };
    if (name === '@/lib/engine-connection')
      return {
        ENGINE_STARTING_MESSAGE: 'Test startup status',
        // Deliberately permit late responses after abort to exercise the UI guard.
        fetchResearch: (url, init) =>
          new Promise((resolve) =>
            requests.push({ url, signal: init.signal, resolve })
          ),
      };
    if (name.startsWith('@/lib/'))
      return require(`./${name.slice('@/lib/'.length)}.ts`);
    if (name.endsWith('qc-archive-forecast-validation.json')) return { default: nativeRequire(name) };
    return nativeRequire(name);
  };
  loaded._compile(compiled, filename);
  const tree = loaded.exports.default();
  const cleanup = effects[0]();
  assert.equal(requests[0].url, '/api/research/qc-simulation');
  function find(node, id) {
    if (!node || typeof node !== 'object') return undefined;
    if (node.props?.id === id) return node;
    const children = node.props?.children;
    for (const child of Array.isArray(children)
      ? children.flat(Infinity)
      : [children]) {
      const found = find(child, id);
      if (found) return found;
    }
  }
  find(tree, 'qc-tab-future').props.onClick();
  assert.equal(requests[0].signal.aborted, true);
  assert.equal(requests[1].url, '/api/research/future-simulation');
  requests[0].resolve(Response.json(fixture));
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(!updates.some(([index, value]) => index === 2 && value !== null));
  cleanup();
  assert.equal(requests[1].signal.aborted, true);
  requests[1].resolve(Response.json(fixture));
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(!updates.some(([index, value]) => index === 2 && value !== null));
});

test('each mode restores its edited dates and input edits invalidate playback results', async () => {
  const context = {
    barangays: ['fixture-hotspot', 'outside-top-ten'].map((id) => ({
      id,
      name: id,
      nearestHospitals: [],
    })),
    hospitals: [],
  };
  const futureControls = {
    ...controlFixture,
    startDate: '2026-11-16',
    endDate: '2026-11-30',
    horizonDays: 14,
    weatherProfile: 'wetter', // A legacy profile echoed by the engine must not carry into the next request.
  };
  const states = new Map([
    [2, fixture],
    [3, controlFixture],
    [4, context],
    [5, 1],
    [6, true],
    [16, false],
  ]);
  const refs = [];
  const requests = [];
  let stateIndex = 0;
  let refIndex = 0;
  const loaded = new Module(filename);
  loaded.filename = filename;
  loaded.paths = require.resolve.paths('react');
  const nativeRequire = loaded.require.bind(loaded);
  loaded.require = (name) => {
    if (name === 'react') {
      return {
        ...React,
        useState(initial) {
          const index = stateIndex++;
          if (!states.has(index)) states.set(index, initial);
          return [
            states.get(index),
            (value) =>
              states.set(
                index,
                typeof value === 'function' ? value(states.get(index)) : value
              ),
          ];
        },
        useRef(initial) {
          const index = refIndex++;
          refs[index] ??= { current: initial };
          return refs[index];
        },
        useEffect: () => {},
        useCallback: (callback) => callback,
      };
    }
    if (name === 'next/dynamic') return { default: () => () => null };
    if (name === '@/components/workspace-select') return { default: props => React.createElement('button', { type: 'button', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }, props.options.find(option => option.value === props.value)?.label ?? props.value) };
    if (name === '@/components/hospital-search') return { default: props => React.createElement('input', { type: 'text', role: 'combobox', 'aria-label': props.label, disabled: props.disabled }) };
    if (name === '@/components/qc-workspace-sidebar')
      return { default: ({ children }) => children };
    if (name === '@/components/workspace-loader') return { default: () => null };
    if (name === '@/components/surgewise-mark') return { default: () => null };
    if (name === '@/lib/engine-connection') {
      return {
        ENGINE_STARTING_MESSAGE: 'Test startup status',
        async fetchResearch(url, init) {
          const controls = init.body ? JSON.parse(init.body) : futureControls;
          requests.push({ url, controls });
          return Response.json({
            ...fixture,
            context,
            controlValues: controls,
          });
        },
      };
    }
    if (name.startsWith('@/lib/'))
      return require(`./${name.slice('@/lib/'.length)}.ts`);
    if (name.endsWith('qc-archive-forecast-validation.json')) return { default: nativeRequire(name) };
    return nativeRequire(name);
  };
  loaded._compile(compiled, filename);
  function render() {
    stateIndex = 0;
    refIndex = 0;
    return loaded.exports.default();
  }
  function element(tree, predicate) {
    const matches = findElements(tree, predicate);
    assert.equal(matches.length, 1);
    return matches[0].node;
  }
  function changeStart(date) {
    element(
      render(),
      (node) => node.props?.['aria-label'] === 'Start date'
    ).props.onChange({ target: { value: date } });
  }
  async function switchMode(mode) {
    element(
      render(),
      (node) => node.props?.id === `qc-tab-${mode}`
    ).props.onClick();
    await new Promise((resolve) => setImmediate(resolve));
  }

  element(render(), node => node.props?.['aria-label'] === 'Edit simulation scenario').props.onClick();
  assert.equal(states.get(23), 'scenario');
  assert.equal(states.get(3), controlFixture);
  assert.equal(states.get(2), fixture);
  element(render(), node => node.props?.['aria-label'] === 'Close simulation panel').props.onClick();
  assert.equal(states.get(23), null);
  const capacity = () => element(render(), node => node.props?.['aria-label'] === 'Hospital stay');
  capacity().props.onChange({ currentTarget: { value: '', validity: { valid: false } } });
  assert.equal(capacity().props.value, '');
  const input = { value: '02', validity: { valid: true } };
  capacity().props.onChange({ currentTarget: input });
  assert.equal(input.value, '2');
  assert.equal(states.get(3).lengthOfStayDays, 2);
  element(render(), node => node.key === '7' && node.props?.['aria-pressed'] === false).props.onClick();
  assert.equal(states.get(3).endDate, '2012-07-08');
  assert.equal(element(render(), node => node.key === '7' && node.type === 'button').props['aria-pressed'], true);
  assert.deepEqual(requests, []);
  function checkRankedChoice() {
    const choice = () => element(render(), node => node.props?.label === 'How patients choose a hospital');
    const overflow = () => element(render(), node => node.props?.label === 'When a hospital is full');
    choice().props.onChange('markov_proximity');
    assert.deepEqual(overflow().props.options.map(o => o.value), ['first_hospital', 'next_probability']);
    overflow().props.onChange('next_probability');
    assert.equal(choice().props.value, 'markov_proximity');
    assert.deepEqual(choice().props.options.map(o => o.label), ['Distance and preferred hospital', 'Distance only']);
    choice().props.onChange('markov_preference');
    assert.equal(overflow().props.value, 'next_probability');
  }
  checkRankedChoice();
  changeStart('');
  assert.equal(element(render(), node => node.props?.type === 'submit').props.disabled, true);
  assert.equal(element(render(), node => node.props?.['aria-label'] === 'Duration').props.value, 7);
  changeStart('2012-08-01');
  assert.equal(states.get(3).endDate, '2012-08-08');
  assert.equal(states.get(2), null, 'outdated results are cleared');
  assert.equal(states.get(5), 0, 'playback resets to day zero');
  assert.equal(states.get(6), false, 'playback pauses');
  const scrolls = [];
  const scrollRegion = element(
    render(),
    (node) => node.props?.className === 'qs-settings-scroll qc-controls'
  );
  assert.ok(
    scrollRegion.props.ref,
    'the form scroll region is available during mode changes'
  );
  scrollRegion.props.ref.current = {
    scrollTo: (options) => scrolls.push(options),
  };
  await switchMode('future');
  checkRankedChoice();
  assert.equal(states.get(3).startDate, '2026-11-16');
  changeStart('2026-12-01');
  await switchMode('historical');
  assert.equal(states.get(3).startDate, '2012-08-01');
  await switchMode('future');
  assert.equal(states.get(3).startDate, '2026-12-01');
  assert.equal(Object.hasOwn(requests.at(-1).controls, 'weatherProfile'), false);
  assert.deepEqual(scrolls, [{ top: 0 }, { top: 0 }, { top: 0 }]);
  assert.deepEqual(
    requests.map((request) => request.url),
    [
      '/api/research/future-simulation',
      '/api/research/qc-simulation',
      '/api/research/future-simulation',
    ]
  );

  // A new run opens Overview immediately, even if the last result view was a table.
  scrollRegion.props.ref.current.checkValidity = () => true;
  element(render(), node => node.props?.label === 'Result view').props.onChange('city-beds');
  element(render(), node => node.props?.['aria-label'] === 'Edit simulation scenario').props.onClick();
  element(render(), node => node.props?.id === 'qc-settings-form').props.onSubmit({ preventDefault() {} });
  const connectionsEnabled = () => element(render(), node => 'connectionsEnabled' in (node.props ?? {})).props.connectionsEnabled;
  const reportLink = () => findElements(render(), node => node.props?.className === 'qs-report-link');
  assert.equal(reportLink().length, 0, 'no report while the result is pending');
  assert.equal(connectionsEnabled(), false, 'a pending request cannot show old arrows');
  assert.equal(element(render(), node => node.props?.['aria-label'] === 'Simulation results').props.hidden, false);
  assert.equal(element(render(), node => node.props?.label === 'Result view').props.value, 'overview');
  // Closing the panel while the request is in flight must be respected.
  element(render(), node => node.props?.['aria-label'] === 'Close simulation panel').props.onClick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(element(render(), node => node.props?.id === 'qs-context-panel').props.hidden, true);
  element(render(), node => node.props?.['aria-label'] === 'Pause simulation').props.onClick();
  assert.equal(connectionsEnabled(), true, 'a submitted run keeps connections available while paused at day zero');
  assert.equal(reportLink().length, 1, 'the full report is available even if playback is paused on day zero');
  await switchMode('historical');
  assert.equal(reportLink().length, 0, 'a new preview cannot expose the previous report');
  assert.equal(connectionsEnabled(), false, 'automatic loading in another mode returns to preview');
});

test('the loaded mode form enters after asynchronous loading and manual reduced motion is exposed', () => {
  const pending = renderWorkspace(0, {
    0: 'future',
    2: null,
    3: null,
    4: null,
  });
  const loaded = renderWorkspace(0, {
    0: 'future',
    3: controlFixture,
    13: true,
  });
  const pendingForm = findElements(
    pending,
    (node) => node.props?.id === 'qc-tab-panel'
  )[0].node;
  const loadedForm = findElements(
    loaded,
    (node) => node.props?.id === 'qc-tab-panel'
  )[0].node;
  assert.notEqual(
    pendingForm.key,
    loadedForm.key,
    'ready fields receive their own entry after loading'
  );
  const left = findElements(
    loaded,
    (node) => node.props?.['aria-label'] === 'Simulation controls'
  )[0].node;
  const dock = findElements(loaded, node => node.props?.id === 'qs-context-panel')[0].node;
  assert.ok(left); assert.equal(dock.props['data-reduced-motion'], true);
});

test('historical reconstruction labels the source week without a forecast origin', () => {
  const result = { ...fixture, forecastEvidence: { ...fixture.forecastEvidence,
    model: 'GP reconstruction', caseSourceKind: 'gp_reconstruction', issueBlock: null,
    observedReferenceBlock: { YR: 2012, WN: 1 }, unassignedWindowCases: 0.5,
    spatialCaveat: 'Retrospective weekly estimates from reported annual totals.',
  }};
  const html = renderDay(1, { 2: result });
  assert.match(html, /2012\/WN 1/);
  assert.match(html, /Reported QC cases through source week/);
  assert.match(html, /Unassigned expected cases in this window: 0.5/);
});
