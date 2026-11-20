import type maplibregl from 'maplibre-gl';
import type { HospitalChoice, MovieBarangay, MovieContext, MovieHospital } from './outbreak-types';
import type { SimulationConnection } from './simulation-connections';

export function probabilityPercent(share: number) {
  return share > 0 && share < .0001 ? '<0.01%' : (share * 100).toFixed(2) + '%';
}

/** Draw every first destination in the saved origin row, regardless of capacity or placements. */
export function probabilityConnections(context: MovieContext, originId: string, choices: HospitalChoice[]): SimulationConnection[] {
  const origin = context.barangays.find(b => b.id === originId);
  if (!origin) return [];
  const hospitals = new Map(context.hospitals.map(h => [h.id, h]));
  return choices.flatMap(choice => {
    const hospital = hospitals.get(choice.facilityId);
    if (!hospital) return [];
    return [{ id: `probability:${originId}:${hospital.id}`, kind: 'probability' as const,
      barangayId: originId, facilityId: hospital.id, from: origin.coordinates, to: hospital.coordinates,
      patients: 0, holding: 0, label: `${origin.name} to ${hospital.name}, ${probabilityPercent(choice.share)} modeled first-admission probability` }];
  });
}

export function probabilityFacts(choice: HospitalChoice): [string, string][] {
  const facts: [string, string][] = [];
  if (choice.breakdown) {
    const { distanceKm, proximityShare, preferenceMultiplier } = choice.breakdown;
    facts.push(['Straight-line distance', `${distanceKm.toFixed(2)} km`],
      ['Distance-only probability', probabilityPercent(proximityShare)], ['Preference weight', `${preferenceMultiplier}×`]);
  }
  facts.push(['Modeled probability', probabilityPercent(choice.share)]);
  return facts;
}

export function probabilityNote(choice: HospitalChoice, origin: MovieBarangay, distanceOnly: boolean) {
  if (!choice.breakdown) return 'Only the final probability is available in this saved run.';
  if (distanceOnly) return 'This scenario uses distance alone.';
  if (!origin.mappedFavoriteHospitalId) return 'Preference unknown. This barangay uses distance alone.';
  return origin.mappedFavoriteHospitalId === choice.facilityId
    ? 'Mapped preferred hospital. Weights are normalized across all destinations.'
    : 'Another hospital has the preference boost. The final probabilities sum to 100%.';
}

/** Inspect the static choice layer without intercepting the rest of the map. */
export function bindProbabilityPopup(svg: SVGSVGElement, map: maplibregl.Map, popup: maplibregl.Popup, origin: MovieBarangay,
  hospitals: MovieHospital[], choices: HospitalChoice[], distanceOnly: boolean) {
  const byId = new Map(choices.map(row => [row.facilityId, row]));
  const names = new Map(hospitals.map(h => [h.id, h.name]));
  const tooltipId = `hospital-probability-${origin.id}`;
  let active: SVGLineElement | null = null;
  let pinned = false;
  const close = () => {
    active?.removeAttribute('aria-describedby');
    active?.parentElement?.classList.remove('qs-choice-active');
    active = null; pinned = false; popup.remove();
  };
  function show(hit: SVGLineElement, pointer?: MouseEvent) {
    const id = hit.parentElement?.dataset.to ?? '';
    const choice = byId.get(id);
    if (!choice) return;
    const bounds = svg.getBoundingClientRect();
    const point: [number, number] = pointer
      ? [pointer.clientX - bounds.left, pointer.clientY - bounds.top]
      : [(hit.x1.baseVal.value + hit.x2.baseVal.value) / 2, (hit.y1.baseVal.value + hit.y2.baseVal.value) / 2];
    // Keep keyboard-triggered details visible even after the user pans the map.
    point[0] = Math.max(0, Math.min(bounds.width, point[0]));
    point[1] = Math.max(0, Math.min(bounds.height, point[1]));
    if (active !== hit) {
      active?.removeAttribute('aria-describedby');
      active?.parentElement?.classList.remove('qs-choice-active');
      hit.parentElement?.classList.add('qs-choice-active');
      active = hit;
      const content = document.createElement('div');
      content.id = tooltipId;
      content.setAttribute('role', 'tooltip');
      hit.setAttribute('aria-describedby', tooltipId);
      const heading = document.createElement('strong');
      heading.textContent = names.get(id) ?? id;
      const context = document.createElement('p');
      context.textContent = `First admission from ${origin.name}`;
      const facts = document.createElement('dl');
      for (const [label, value] of probabilityFacts(choice)) {
        const dt = document.createElement('dt'), dd = document.createElement('dd');
        dt.textContent = label; dd.textContent = value; facts.append(dt, dd);
      }
      const note = document.createElement('small');
      note.textContent = probabilityNote(choice, origin, distanceOnly);
      content.append(heading, context, facts, note);
      popup.setDOMContent(content);
    }
    popup.setLngLat(map.unproject(point));
    if (!popup.isOpen()) popup.addTo(map);
  }
  const hitFor = (event: Event) => event.target instanceof SVGLineElement && event.target.classList.contains('qs-choice-hit') ? event.target : null;
  const controller = new AbortController();
  const events = { signal: controller.signal };
  svg.addEventListener('pointerover', event => {
    const hit = hitFor(event);
    if (hit && event.pointerType !== 'touch' && !pinned) show(hit, event);
  }, events);
  svg.addEventListener('pointerout', event => {
    if (hitFor(event) && !pinned && event.pointerType !== 'touch' && active !== document.activeElement) close();
  }, events);
  svg.addEventListener('focusin', event => {
    const hit = hitFor(event);
    if (hit) { pinned = false; show(hit); }
  }, events);
  svg.addEventListener('focusout', event => { if (hitFor(event) && !pinned) close(); }, events);
  svg.addEventListener('click', event => {
    const hit = hitFor(event);
    if (!hit) return;
    event.stopPropagation();
    if (pinned && active === hit) close();
    else { show(hit, event); pinned = true; }
  }, events);
  svg.addEventListener('keydown', event => {
    const hit = hitFor(event);
    if (hit && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      if (pinned && active === hit) close();
      else { show(hit); pinned = true; }
    }
  }, events);
  document.addEventListener('keydown', event => {
    if (active && event.key === 'Escape') { event.stopPropagation(); close(); }
  }, { ...events, capture: true });
  document.addEventListener('pointerdown', event => { if (active && !hitFor(event)) close(); }, { ...events, capture: true });
  map.on('movestart', close);
  return () => { controller.abort(); map.off('movestart', close); close(); };
}
