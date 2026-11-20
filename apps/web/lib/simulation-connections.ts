import type { Map as MapLibreMap } from 'maplibre-gl';
import type { MovieContext, MovieDay } from './outbreak-types';

/** One visual contract for the SVG, map layers and legend. */
export const SIMULATION_LINES = {
  proximity: { kind: 'proximity', color: '#287c75', dash: [4, 5], label: 'Three nearest + hospitals inside barangay', width: 1.5 },
  probability: { kind: 'probability', color: '#665495', dash: [2, 3], label: 'First-hospital probability · selected barangay', width: 2 },
  placement: { kind: 'placement', color: '#287c75', dash: [], label: 'Modeled placements · selected day', width: 2 },
  holding: { kind: 'holding', color: '#a56434', dash: [], label: 'Placement includes temporary holding', width: 2 },
  'hospital-context': { kind: 'hospital-context', color: '#a77638', dash: [4, 5], label: 'Hospital’s nearest ranked barangay', width: 1.5 },
  front: { kind: 'front', color: '#deb65d', dash: [3, 3], label: 'Assumed expansion boundary', width: 2 },
} as const;

export type ConnectionFocus = 'barangay' | 'hospital' | null;
export type SimulationConnection = {
  id: string; kind: 'proximity' | 'placement' | 'hospital-context' | 'probability';
  barangayId: string; facilityId: string; from: [number, number]; to: [number, number];
  patients: number; holding: number; label?: string;
};
type Options = {
  selected: string; selectedHospital: string; focus: ConnectionFocus;
  hotspotIds?: string[]; showOverview: boolean; hospitalHotspot?: { barangayId: string } | null;
};

/** Display relationships only. Coordinates, nearest-site rankings and placements
 * come from the approved context/saved day; this does not calculate referrals. */
export function simulationConnections(context: MovieContext, snapshot: MovieDay | null, options: Options): SimulationConnection[] {
  if (!options.focus && !options.showOverview) return [];
  const barangays = new Map(context.barangays.map(b => [b.id, b]));
  const hospitals = new Map(context.hospitals.map(h => [h.id, h]));
  if (options.focus === 'hospital' && !hospitals.has(options.selectedHospital)) return [];
  if (options.focus === 'barangay' && !barangays.has(options.selected)) return [];
  const candidates = new Set(options.hotspotIds ?? snapshot?.hotspotIds ?? []);
  if (options.focus === 'barangay') { candidates.clear(); candidates.add(options.selected); }
  const result = new Map<string, SimulationConnection>();
  const add = (kind: SimulationConnection['kind'], barangayId: string, facilityId: string, patients = 0, holding = 0) => {
    const barangay = barangays.get(barangayId), hospital = hospitals.get(facilityId);
    if (!barangay || !hospital) return;
    const id = `${kind}:${barangayId}:${facilityId}`;
    result.set(id, { id, kind, barangayId, facilityId, from: barangay.coordinates, to: hospital.coordinates, patients, holding });
  };
  for (const id of candidates) {
    const barangay = barangays.get(id);
    if (!barangay) continue;
    const nearby = [...barangay.nearestHospitals.slice(0, 3), ...(barangay.hospitalsWithinBarangay ?? [])];
    for (const link of nearby) if (options.focus !== 'hospital' || link.facilityId === options.selectedHospital) add('proximity', id, link.facilityId);
  }
  if (options.focus === 'hospital' && options.hospitalHotspot) {
    const id = options.hospitalHotspot.barangayId, facilityId = options.selectedHospital;
    if (!result.has(`proximity:${id}:${facilityId}`)) add('hospital-context', id, facilityId);
  }
  // A diversion carries the origin mix of the first hospital to the receiving site.
  const arrivalShares = context.weeklyOriginShares?.[snapshot?.arrivalWeekIndex ?? 0] ?? context.firstAdmissionOriginShares;
  if (arrivalShares && snapshot) {
    const routes = snapshot.firstHospitalRoutes ?? snapshot.facilities.map(site => ({
      firstFacilityId: site.facilityId, facilityId: site.facilityId,
      supportedPlacements: site.supportedPlacementsToday ?? 0, holdingPlacements: site.holdingPlacementsToday ?? 0,
    }));
    type Flow = { b: string; h: string; patients: number; held: number };
    const flows = new Map<string, Map<string, Flow>>();
    for (const route of routes) {
      const h = route.facilityId, total = route.supportedPlacements + route.holdingPlacements;
      if (total <= 0 || (options.focus === 'hospital' && h !== options.selectedHospital)) continue;
      const actual = snapshot.placementsByOrigin?.[h];
      const counts = actual
        ? context.barangays.map(({ id }, i) => ({ b: id, patients: (actual.supported[i] ?? 0) + (actual.holding[i] ?? 0), held: actual.holding[i] ?? 0 }))
        : Object.entries(arrivalShares[route.firstFacilityId] ?? {}).map(([b, fraction]) =>
            ({ b, patients: total * fraction, held: route.holdingPlacements * fraction }));
      for (const { b, patients, held } of counts) {
        if (patients <= 0) continue;
        if (options.focus !== 'hospital' && !candidates.has(b)) continue;
        const key = options.focus === 'hospital' ? h : b;
        const peer = options.focus === 'hospital' ? b : h;
        const group = flows.get(key) ?? new Map<string, Flow>();
        const flow = group.get(peer) ?? { b, h, patients: 0, held: 0 };
        flow.patients += patients;
        flow.held += held;
        group.set(peer, flow);
        flows.set(key, group);
      }
    }
    for (const group of flows.values()) {
      const largest = [...group.values()].sort((a, b) => b.patients - a.patients).slice(0, 3);
      for (const row of largest) add('placement', row.b, row.h, row.patients, row.held);
    }
  }
  for (const row of snapshot?.assignments ?? []) {
    const matches = options.focus === 'hospital' ? row.facilityId === options.selectedHospital : candidates.has(row.barangayId);
    const patients = row.supportedPlacements + row.holdingPlacements;
    if (matches && Number.isFinite(patients) && patients > 0 && row.supportedPlacements >= 0 && row.holdingPlacements >= 0) add('placement', row.barangayId, row.facilityId, patients, row.holdingPlacements);
  }
  return [...result.values()];
}

export type FlowPoint = { x: number; y: number };
/** Cosmetic screen-space timing; arrow direction always follows from -> to. */
export function connectionFrame(from: FlowPoint, to: FlowPoint, elapsedMs: number, reducedMotion: boolean) {
  const elapsed = Math.max(0, elapsedMs);
  const mix = (progress: number) => ({ x: from.x + (to.x - from.x) * progress, y: from.y + (to.y - from.y) * progress });
  const progress = reducedMotion ? 1 : 1 - (1 - Math.min(1, elapsed / 650)) ** 3;
  const arrowProgress = reducedMotion ? .62 : (elapsed % 2400) / 2400;
  return { end: mix(progress), arrow: mix(arrowProgress), angle: Math.atan2(to.y - from.y, to.x - from.x) * 180 / Math.PI,
    opacity: reducedMotion ? .9 : Math.min(1, arrowProgress * 10, (1 - arrowProgress) * 10) };
}


/** SVG over the canvas lets connections end at the displayed pin, including its
 * overlap offset. Source coordinates remain unchanged. All arrows point b -> h. */
export function drawSimulationFlow(map: Pick<MapLibreMap, 'getCanvasContainer'>, connections: SimulationConnection[], project: (id: string, coordinates: [number, number]) => FlowPoint,
  reducedMotion: boolean, startedAt: number) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('class', 'qs-flow-overlay');
  if (connections.some(connection => connection.kind === 'probability')) {
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', 'First-hospital probability arrows');
  } else {
    svg.setAttribute('aria-hidden', 'true');
  }
  // MapLibre listens for wheel and touch gestures on the canvas container.
  map.getCanvasContainer().append(svg);
  const placements = new Set(connections.filter(c => c.kind === 'placement').map(c => `${c.barangayId}:${c.facilityId}`));
  // A saved placement supersedes the proximity decoration on the same pair.
  const shown = connections.filter(c => c.kind === 'placement' || !placements.has(`${c.barangayId}:${c.facilityId}`));
  const entries = shown.map((connection, index) => {
    const group = document.createElementNS(ns, 'g');
    group.dataset.kind = connection.kind;
    group.dataset.from = connection.barangayId; group.dataset.to = connection.facilityId;
    const style = SIMULATION_LINES[connection.kind === 'placement' && connection.holding > 0 ? 'holding' : connection.kind];
    const color = style.color;
    const width = connection.kind === 'placement' ? Math.min(4, 1.8 + Math.sqrt(connection.patients) * .25) : style.width;
    const casing = document.createElementNS(ns, 'line');
    casing.setAttribute('stroke', '#fbfdf9'); casing.setAttribute('stroke-width', String(width + 2)); casing.setAttribute('opacity', '.8');
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('stroke', color); line.setAttribute('stroke-width', String(width)); line.setAttribute('stroke-linecap', 'round');
    if (style.dash.length) line.setAttribute('stroke-dasharray', style.dash.join(' '));
    const arrow = document.createElementNS(ns, 'path');
    arrow.setAttribute('d', 'M -5 -3.5 L 0 0 L -5 3.5'); arrow.setAttribute('fill', 'none');
    arrow.setAttribute('stroke', color); arrow.setAttribute('stroke-width', '2.2');
    arrow.setAttribute('stroke-linecap', 'round'); arrow.setAttribute('stroke-linejoin', 'round');
    group.append(casing, line, arrow);
    const segments = [casing, line];
    if (connection.kind === 'probability') {
      const hit = document.createElementNS(ns, 'line');
      hit.setAttribute('class', 'qs-choice-hit');
      hit.setAttribute('stroke', 'transparent');
      hit.setAttribute('stroke-width', '12');
      hit.setAttribute('tabindex', '0');
      hit.setAttribute('role', 'button');
      hit.setAttribute('aria-label', connection.label ?? connection.facilityId);
      group.append(hit);
      segments.push(hit);
    }
    svg.append(group);
    return { connection, segments, arrow, delay: index * 35 };
  });
  let frame = 0;
  const render = (now: number) => {
    for (const { connection, segments, arrow, delay } of entries) {
      const from = project(`b-${connection.barangayId}`, connection.from), to = project(`h-${connection.facilityId}`, connection.to);
      const current = connectionFrame(from, to, now - startedAt - delay, reducedMotion);
      for (const path of segments) {
        path.setAttribute('x1', String(from.x)); path.setAttribute('y1', String(from.y));
        path.setAttribute('x2', String(current.end.x)); path.setAttribute('y2', String(current.end.y));
      }
      arrow.setAttribute('transform', `translate(${current.arrow.x},${current.arrow.y}) rotate(${current.angle})`);
      arrow.setAttribute('opacity', String(current.opacity));
    }
  };
  const animate = (now: number) => { render(now); frame = requestAnimationFrame(animate); };
  render(performance.now());
  if (!reducedMotion && entries.length) frame = requestAnimationFrame(animate);
  return { svg, update: () => render(performance.now()), destroy: () => { cancelAnimationFrame(frame); svg.remove(); } };
}
