import { test } from 'node:test';
import assert from 'node:assert/strict';
import { probabilityConnections, probabilityPercent, probabilityFacts, probabilityNote } from './hospital-probabilities.ts';
import { simulationConnections, connectionFrame, drawSimulationFlow, SIMULATION_LINES } from './simulation-connections.ts';

const hospitals = ['H1', 'H2', 'H3', 'H4'].map((id, index) => ({ id, coordinates: [121 + index / 100, 14.6] }));
const link = (facilityId, distanceKm = 1) => ({ facilityId, distanceKm });
const context = { hospitals, barangays: [
  { id: 'B1', coordinates: [121, 14.7], nearestHospitals: [link('H1'), link('H2'), link('H3'), link('H4')], hospitalsWithinBarangay: [link('H4')] },
  { id: 'B2', coordinates: [121.1, 14.7], nearestHospitals: [link('H2'), link('H3'), link('H4')] },
  { id: 'B3', coordinates: [121.2, 14.7], nearestHospitals: [link('H3')] },
] };
const snapshot = { assignments: [
  { barangayId: 'B1', facilityId: 'H2', supportedPlacements: 3, holdingPlacements: 0 },
  { barangayId: 'B2', facilityId: 'H2', supportedPlacements: 0, holdingPlacements: 2 },
  { barangayId: 'B3', facilityId: 'H3', supportedPlacements: 0, holdingPlacements: 0 },
  { barangayId: 'missing', facilityId: 'H2', supportedPlacements: 3, holdingPlacements: 0 },
] };
const options = { selected: 'B1', selectedHospital: '', focus: null, hotspotIds: ['B1', 'B2'], showOverview: false };

test('initial map has no connections until inspection or the overview toggle', () => {
  assert.deepEqual(simulationConnections(context, snapshot, options), []);
  assert.ok(simulationConnections(context, snapshot, { ...options, showOverview: true }).length);
});
test('barangay inspection connects its three nearest and contained hospitals using supplied coordinates', () => {
  const source = structuredClone(context);
  const connections = simulationConnections(context, null, { ...options, focus: 'barangay' });
  assert.deepEqual(connections.map(c => c.facilityId), ['H1', 'H2', 'H3', 'H4']);
  for (const connection of connections) {
    assert.equal(connection.barangayId, 'B1');
    assert.equal(connection.kind, 'proximity');
    assert.deepEqual(connection.from, context.barangays[0].coordinates);
    assert.deepEqual(connection.to, hospitals.find(h => h.id === connection.facilityId).coordinates);
  }
  assert.deepEqual(context, source);
});
test('hospital inspection shows incoming saved placements and never reverses their origin', () => {
  const connections = simulationConnections(context, snapshot, { ...options, selectedHospital: 'H2', focus: 'hospital' });
  assert.ok(connections.length);
  assert.ok(connections.every(c => c.facilityId === 'H2'));
  assert.deepEqual(connections.filter(c => c.kind === 'placement').map(c => [c.barangayId, c.patients, c.holding]), [['B1', 3, 0], ['B2', 2, 2]]);
  assert.ok(connections.every(c => c.from[1] === 14.7 && c.to[1] === 14.6));
});
test('unknown IDs and zero placements do not create orphan or fictional connections', () => {
  assert.deepEqual(simulationConnections(context, snapshot, { ...options, focus: 'barangay', selected: 'missing' }), []);
  assert.deepEqual(simulationConnections(context, snapshot, { ...options, focus: 'hospital', selectedHospital: 'missing' }), []);
  const connections = simulationConnections(context, snapshot, { ...options, focus: 'barangay', selected: 'B3' });
  assert.ok(connections.every(c => c.kind !== 'placement'));
});
test('hospital nearest-ranked context is directed from barangay to hospital before playback', () => {
  const connections = simulationConnections(context, null, { ...options, focus: 'hospital', selectedHospital: 'H1', hospitalHotspot: { barangayId: 'B3' } });
  assert.ok(connections.some(c => c.kind === 'hospital-context' && c.barangayId === 'B3' && c.facilityId === 'H1'));
  assert.ok(connections.every(c => c.kind !== 'placement'));
});
test('reveal and moving chevrons travel from the origin to destination; reduced motion is static', () => {
  const from = { x: 100, y: 200 }, to = { x: 400, y: 100 };
  const first = connectionFrame(from, to, 0, false);
  const later = connectionFrame(from, to, 400, false);
  assert.deepEqual(first.end, from);
  assert.ok(later.end.x > from.x && later.end.x < to.x);
  assert.ok(later.arrow.x > from.x && later.arrow.x < to.x);
  assert.ok(later.arrow.y < from.y && later.arrow.y > to.y);
  assert.equal(first.angle, later.angle);
  assert.deepEqual(connectionFrame(from, to, 900, false).end, to);
  assert.deepEqual(connectionFrame(from, to, 0, true), connectionFrame(from, to, 5000, true));
  assert.deepEqual(connectionFrame(from, to, 0, true).end, to);
});

function svgNode() {
  return {
    dataset: {}, attributes: {}, children: [],
    setAttribute(key, value) { this.attributes[key] = value; },
    append(...children) {
      for (const child of children) child.parentElement = this;
      this.children.push(...children);
    },
    remove() {
      this.parentElement.children = this.parentElement.children.filter(child => child !== this);
      this.parentElement = null;
    },
  };
}

test('actual SVG renderer uses displayed endpoints, preserves direction, cancels frames and suppresses duplicate pair decorations', async t => {
  const previous = { document: globalThis.document, raf: globalThis.requestAnimationFrame, cancel: globalThis.cancelAnimationFrame };
  const frames = [], cancelled = [];
  globalThis.document = { createElementNS: svgNode };
  globalThis.requestAnimationFrame = callback => { frames.push(callback); return frames.length; };
  globalThis.cancelAnimationFrame = id => cancelled.push(id);
  try {
    const canvasContainer = svgNode();
    const map = { getCanvasContainer: () => canvasContainer };
    const connections = simulationConnections(context, snapshot, { ...options, focus: 'barangay' });
    const project = id => id.startsWith('b-') ? { x: 50, y: 150 } : { x: 350, y: 50 };
    const started = performance.now();
    const flow = drawSimulationFlow(map, connections, project, false, started);
    const { svg } = flow;
    assert.equal(svg.attributes['aria-hidden'], 'true');
    assert.equal(svg.children.length, 4, 'one visible relationship per endpoint pair');
    const placement = svg.children.find(group => group.dataset.kind === 'placement');
    assert.equal(placement.dataset.from, 'B1');
    assert.equal(placement.dataset.to, 'H2');
    frames.shift()(started + 1000);
    assert.equal(placement.children[1].attributes.x1, '50');
    assert.equal(placement.children[1].attributes.y1, '150');
    assert.equal(placement.children[1].attributes.x2, '350');
    assert.equal(placement.children[1].attributes.y2, '50');
    assert.match(placement.children[2].attributes.transform, /rotate\(-18\.43/);
    assert.equal(placement.children[1].attributes['stroke-dasharray'], undefined);
    flow.destroy();
    assert.equal(canvasContainer.children.length, 0);
    assert.ok(cancelled.length);
    frames.length = 0;
    const still = drawSimulationFlow(map, connections, project, true, started);
    assert.equal(frames.length, 0, 'reduced motion must never schedule animation frames');
    assert.equal(still.svg.children[0].children[1].attributes.x2, '350');
    assert.equal(still.svg.children[0].children[1].attributes['stroke-dasharray'], '4 5');
    still.destroy();
    const incoming=simulationConnections(context,snapshot,{...options,focus:'hospital',selectedHospital:'H2'});
    const holding=drawSimulationFlow(map,incoming,project,true,started);
    const held=holding.svg.children.find(group=>group.dataset.from==='B2' && group.dataset.kind==='placement');
    assert.equal(held.children[1].attributes.stroke,SIMULATION_LINES.holding.color);
    assert.equal(held.children[2].attributes.stroke,SIMULATION_LINES.holding.color);
    holding.destroy();

    await t.test('probability hit targets belong to the map gesture container until cleanup', () => {
      const choices = [{ facilityId: 'H1', share: 1 }];
      const interactive = drawSimulationFlow(map, probabilityConnections(context, 'B1', choices), project, true, started);
      assert.deepEqual(canvasContainer.children, [interactive.svg]);
      assert.equal(interactive.svg.attributes.role, 'group');
      const line = interactive.svg.children[0].children.find(child => child.attributes.class === 'qs-choice-hit');
      assert.equal(line.attributes.tabindex, '0');
      assert.equal(line.attributes.role, 'button');
      interactive.destroy();
      assert.equal(canvasContainer.children.length, 0);
    });
  } finally {
    if (previous.document === undefined) delete globalThis.document; else globalThis.document = previous.document;
    if (previous.raf === undefined) delete globalThis.requestAnimationFrame; else globalThis.requestAnimationFrame = previous.raf;
    if (previous.cancel === undefined) delete globalThis.cancelAnimationFrame; else globalThis.cancelAnimationFrame = previous.cancel;
  }
});

test('first-hospital map shows largest actual placements and excludes unplaced demand', () => {
  const firstAdmissionOriginShares = Object.fromEntries(hospitals.map(h => [h.id, { B1: .75, B2: .25 }]));
  const local = { ...context, firstAdmissionOriginShares };
  const day = { assignments: [], facilities: hospitals.map((h, i) => ({ facilityId: h.id,
    supportedPlacementsToday: i, holdingPlacementsToday: i === 3 ? 1 : 0, unplacedToday: 10 })) };
  const options = { selected: 'B1', selectedHospital: '', focus: 'barangay', showOverview: false };
  const drawn = simulationConnections(local, day, options).filter(c => c.kind === 'placement');
  assert.deepEqual(drawn.map(c => c.facilityId), ['H4', 'H3', 'H2']);
  assert.equal(drawn[0].patients, 3);
  assert.equal(drawn[0].holding, .75);
  const hospital = simulationConnections(local, day, { ...options, focus: 'hospital', selectedHospital: 'H4' })
    .filter(c => c.kind === 'placement');
  assert.equal(hospital.reduce((sum, c) => sum + c.patients, 0), 4);
});

test('choice arrows cover the entire selected origin row independently of daily placements', () => {
  const source = { ...context, hospitals: Array.from({length:46}, (_,i) => ({
    id: `H${i}`, name: `Hospital ${i}`, coordinates: [121 + i/100, 14.6],
  })) };
  const choices = source.hospitals.map((h,i) => ({facilityId:h.id, share:i ? 0.5/45 : 0.5}));
  const arrows = probabilityConnections(source, 'B2', choices);
  assert.equal(arrows.length, 46);
  assert.deepEqual(arrows.map(a => a.facilityId), choices.map(h => h.facilityId));
  assert.ok(arrows.every(a => a.barangayId === 'B2' && a.kind === 'probability'));
  assert.deepEqual(arrows.at(-1).from, context.barangays[1].coordinates);
  assert.deepEqual(arrows.at(-1).to, source.hospitals.at(-1).coordinates);
  assert.match(arrows.at(-1).label, /1.11%/);
  assert.deepEqual(probabilityConnections(source, 'missing', choices), []);
  assert.equal(probabilityPercent(0.000001), '<0.01%');
});

test('probability details distinguish an unknown preference, distance-only mode and archived rows', () => {
  const choice = { facilityId:'H1', share:.0517, breakdown:{distanceKm:2.3346, proximityShare:.03504, preferenceMultiplier:1.5} };
  assert.deepEqual(probabilityFacts(choice), [['Straight-line distance','2.33 km'], ['Distance-only probability','3.50%'],
    ['Preference weight','1.5×'], ['Modeled probability','5.17%']]);
  assert.match(probabilityNote(choice,{mappedFavoriteHospitalId:'H1'},false), /Mapped preferred hospital/);
  assert.match(probabilityNote(choice,{mappedFavoriteHospitalId:null},false), /Preference unknown/);
  assert.match(probabilityNote(choice,{mappedFavoriteHospitalId:'H1'},true), /uses distance alone/);
  const old = { facilityId:'H1', share:.04 };
  assert.deepEqual(probabilityFacts(old), [['Modeled probability','4.00%']]);
  assert.match(probabilityNote(old,{},false), /Only the final probability/);
});

test('overflow placement arrows carry each first hospital’s origin shares to the actual destination', () => {
  const source = { ...context, firstAdmissionOriginShares: { H1: { B1: .75, B2: .25 }, H2: { B2: 1 } } };
  const day = { assignments: [], firstHospitalRoutes: [
    { firstFacilityId: 'H1', facilityId: 'H2', supportedPlacements: 2, holdingPlacements: 2 },
    { firstFacilityId: 'H2', facilityId: 'H2', supportedPlacements: 3, holdingPlacements: 0 },
  ] };
  const placed = focus => simulationConnections(source, day, { ...options, focus, selectedHospital: 'H2' })
    .filter(c => c.kind === 'placement').map(c => [c.barangayId, c.facilityId, c.patients, c.holding]);
  assert.deepEqual(placed('hospital'), [['B2', 'H2', 4, .5], ['B1', 'H2', 3, 1.5]]);
  assert.deepEqual(placed('barangay'), [['B1', 'H2', 3, 1.5]]);
});

test('ranked overflow arrows show the actual origin mix of a receiving hospital', () => {
  const source = { ...context, firstAdmissionOriginShares: { H1: { B1: 1 }, H2: { B1: 1 } } };
  const day = { assignments: [], placementsByOrigin: { H2: { supported: [2, 3, 0], holding: [0, 1, 0] } },
    facilities: [{ facilityId: 'H1', supportedPlacementsToday: 1 }, { facilityId: 'H2', supportedPlacementsToday: 5, holdingPlacementsToday: 1 }] };
  const placed = focus => simulationConnections(source, day, { ...options, focus, selectedHospital: 'H2' })
    .filter(c => c.kind === 'placement').map(c => [c.barangayId, c.facilityId, c.patients, c.holding]);
  assert.deepEqual(placed('hospital'), [['B2', 'H2', 4, 1], ['B1', 'H2', 2, 0]]);
  assert.deepEqual(placed('barangay'), [['B1', 'H2', 2, 0], ['B1', 'H1', 1, 0]]);
});

test('production placement arrows use the origin shares of the week that generated admissions', () => {
  const source = { ...context, firstAdmissionOriginShares: { H1: { B1: 1 } },
    weeklyOriginShares: [{ H1: { B1: 1 } }, { H1: { B1: .25, B2: .75 } }] };
  const snapshot = { arrivalWeekIndex: 1, facilities: [{ facilityId: 'H1', supportedPlacementsToday: 4 }], assignments: [] };
  const flows = simulationConnections(source, snapshot, { ...options, focus: 'hospital', selectedHospital: 'H1' })
    .filter(row => row.kind === 'placement').map(row => [row.barangayId, row.patients]);
  assert.deepEqual(flows, [['B2', 3], ['B1', 1]]);
});
