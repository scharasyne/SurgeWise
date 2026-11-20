/** Display bins only: these are not public-health outbreak thresholds. */
export const CASE_BANDS = [
  { min: 0, max: 5, label: '0–<5', color: '#edf1c7' },
  { min: 5, max: 10, label: '5–<10', color: '#b9cd87' },
  { min: 10, max: 25, label: '10–<25', color: '#deb65d' },
  { min: 25, max: 50, label: '25–<50', color: '#cc873e' },
  { min: 50, max: Infinity, label: '50+', color: '#9c522e' },
];
export function caseBand(value: number) {
  if (!Number.isFinite(value) || value < 0) throw Error('Case burden must be finite and nonnegative.');
  return CASE_BANDS.find(b => value >= b.min && value < b.max)!;
}
/**
 * Smooth display color, scaled to a fixed full-window maximum; never a risk threshold.
 * Square-root scale: every barangay is shaded, and most hold a small fraction of the
 * busiest one's cases, so a linear scale would paint nearly all of them the palest shade.
 */
export function caseColor(value: number, maximum = 50) {
  if (!Number.isFinite(value) || value < 0 || !Number.isFinite(maximum) || maximum <= 0) throw Error('Invalid case color scale.');
  const scaled = Math.sqrt(Math.min(1, value / maximum)) * 50;
  const lower = [...CASE_BANDS].reverse().find(band => scaled >= band.min)!;
  const upper = CASE_BANDS[CASE_BANDS.indexOf(lower) + 1];
  if (!upper) return lower.color;
  const fraction = (scaled - lower.min) / (upper.min - lower.min);
  const rgb = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const a = rgb(lower.color), b = rgb(upper.color);
  return `rgb(${a.map((channel, i) => Math.round(channel + (b[i] - channel) * fraction)).join(', ')})`;
}

/** Case count drawn in a band's reference color (`position` is a CASE_BANDS `min`, 0–50). */
export function caseScaleValue(position: number, maximum: number) {
  return (Math.max(0, Math.min(50, position)) / 50) ** 2 * maximum;
}

export function interpolateCaseValues(previous: Map<string, number>, target: Map<string, number>, fraction: number) {
  const t = Math.max(0, Math.min(1, fraction));
  return new Map([...target].map(([id, value]) => [id, (previous.get(id) ?? 0) + (value - (previous.get(id) ?? 0)) * t]));
}
export function addDateDays(date: string, days: number) {
  const result = new Date(`${date}T00:00:00Z`);
  result.setUTCDate(result.getUTCDate() + days);
  return result.toISOString().slice(0, 10);
}
