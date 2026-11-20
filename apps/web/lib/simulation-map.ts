export type SimulationMapController = { resetView: () => void; zoomIn: () => void; zoomOut: () => void };
export type SimulationMapStatus = 'loading' | 'ready' | 'partial' | 'unavailable';
/** Optional NCR city-outline layer (same source and style as Dashboard). */
export type CityBoundaryStatus = 'loading' | 'ready' | 'unavailable';
/** Simulation city-outline style. The layer literals in outbreak-map.tsx repeat these
 *  values (the style test validates layers as plain literals); keep them in sync. */
export const CITY_BOUNDARY_STYLE = {
  highlightedArea: 'QUEZON_CITY',
  fill: { highlighted: '#32a69a', other: '#8ea5b0', highlightedOpacity: 0.12, otherOpacity: 0.035 },
  // Over imagery a bright teal, distinct from the white barangay lines and yellow roads.
  line: { color: '#248e86', satelliteColor: '#7fe8d6', highlightedWidth: 2.2, otherWidth: 0.8 },
} as const;
export type SimulationBounds = [[number, number], [number, number]];

/**
 * Opening (and reset) Simulation view, chosen by the user on 2026-11-21 from a 1917×912
 * window: centre ≈ 121.051°E, 14.676°N at zoom ≈ 11.45 on a 716-px-tall map. Its
 * north–south range fills the map height; its east–west range keeps all of Quezon City
 * (121.000–121.153°E) in view, so narrow screens zoom out instead of cropping QC.
 * The latitude range is 3% taller than the screenshot's visible range because the
 * camera is fitted before the bottom timeline finishes loading and shortens the map.
 * Use `defaultSimulationCamera` to fit it.
 */
export const DEFAULT_QC_VIEW: SimulationBounds = [[120.949, 14.586], [121.153, 14.765]];
/** Quezon City's east–west extent over the same latitude range (narrow-screen fallback). */
export const QC_EXTENT_VIEW: SimulationBounds = [[121.0, 14.586], [121.153, 14.765]];

type Padding = { top: number; bottom: number; left: number; right: number };
type Overlay = { left: number; top: number; width: number; height: number };

/** Web Mercator zoom (512-px tiles) at which `bounds` fit inside the padded viewport. */
export function fitZoom([[west, south], [east, north]]: SimulationBounds, width: number, height: number, padding: Padding) {
  const x = (lng: number) => (lng + 180) / 360;
  const y = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / Math.PI) / 2;
  const spanX = (x(east) - x(west)) * 512, spanY = (y(south) - y(north)) * 512;
  const availableX = Math.max(1, width - padding.left - padding.right), availableY = Math.max(1, height - padding.top - padding.bottom);
  return Math.log2(Math.min(availableX / spanX, availableY / spanY));
}

/**
 * Opening/reset camera. Wide screens: DEFAULT_QC_VIEW with equal side margins (so it
 * stays centred on the chosen point) and no top/bottom padding (the latitude range fills
 * the height). Narrow screens, where width would force that view further out than QC
 * needs, fit Quezon City's own extent instead so the city is not shown needlessly small.
 */
export function defaultSimulationCamera(width: number, height: number, overlays: Overlay[]): { bounds: SimulationBounds; padding: Padding } {
  const { left, right } = simulationMapPadding(width, height, overlays);
  const side = Math.max(left, right);
  const chosen = { bounds: DEFAULT_QC_VIEW, padding: { top: 0, bottom: 0, left: side, right: side } };
  const city = { bounds: QC_EXTENT_VIEW, padding: { top: 0, bottom: 0, left, right } };
  return fitZoom(city.bounds, width, height, city.padding) > fitZoom(chosen.bounds, width, height, chosen.padding) + 0.01 ? city : chosen;
}

/** Camera extent only; include the whole selected boundary, not just its point. */
export function selectionMapBounds(points: [number, number][], polygonBounds?: SimulationBounds): SimulationBounds | null {
  const coordinates = polygonBounds ? [...points, ...polygonBounds] : points;
  if (!coordinates.length || coordinates.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90)) return null;
  return [[Math.min(...coordinates.map(p => p[0])), Math.min(...coordinates.map(p => p[1]))],
    [Math.max(...coordinates.map(p => p[0])), Math.max(...coordinates.map(p => p[1]))]];
}

/** Camera padding only: wide top/bottom overlays must not consume the left edge. */
export function simulationMapPadding(width: number, height: number, overlays: Array<{left: number; top: number; width: number; height: number}>) {
  let top = 65, bottom = 55, left = 35, right = 65;
  for (const rect of overlays) {
    if (rect.width > width * 0.55) {
      if (rect.top < height / 2) top = Math.max(top, rect.top + rect.height + 12);
      else bottom = Math.max(bottom, height - rect.top + 12);
    } else if (rect.left < width * 0.3 && rect.top < height * 0.6) {
      top = Math.max(top, rect.top + rect.height + 12);
    } else if (rect.left + rect.width > width * 0.75) right = Math.max(right, width - rect.left + 12);
  }
  top = Math.min(top, Math.max(12, height * 0.3)); bottom = Math.min(bottom, Math.max(12, height * 0.25));
  left = Math.min(left, width * 0.2); right = Math.min(right, width * 0.25);
  return { top, bottom, left, right };
}
