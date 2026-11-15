import Image from 'next/image';

/**
 * SurgeWise logo mark: a navy "S" and teal "W" ribbon joined by a red line that
 * runs from a hotspot dot up to a medical cross — a surge reaching care.
 * Artwork: /public/brand/surgewise-mark.png (mark) and surgewise-logo.png (mark +
 * wordmark), both with transparent backgrounds.
 *
 * - `on-light`: the original colours, for light surfaces.
 * - `on-dark` / `badge`: /public/brand/surgewise-mark-on-dark.png, where the navy
 *   "S" is recoloured to a light ribbon so it stays visible on navy header bars;
 *   the teal "W" and the red line and cross are unchanged. Both are transparent.
 * `size` is the rendered height in px. The mark is decorative: every place it is
 * used already shows the "SurgeWise" name beside it.
 */
type Variant = 'on-dark' | 'on-light' | 'badge';

const SRC = { light: '/brand/surgewise-mark.png', dark: '/brand/surgewise-mark-on-dark.png' };
const RATIO = 433 / 256; // width / height of the mark artwork

export default function SurgeWiseMark({ size = 28, variant = 'on-light', className }: { size?: number; variant?: Variant; className?: string }) {
  const src = variant === 'on-light' ? SRC.light : SRC.dark;
  return <Image src={src} alt="" aria-hidden width={Math.round(size * RATIO)} height={size} className={className} unoptimized priority />;
}
