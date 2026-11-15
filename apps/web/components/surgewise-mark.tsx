import Image from 'next/image';

/**
 * SurgeWise logo mark: a navy "S" and teal "W" ribbon joined by a red line that
 * runs from a hotspot dot up to a medical cross — a surge reaching care.
 * Artwork: /public/brand/surgewise-mark.png (mark) and surgewise-logo.png (mark +
 * wordmark), both with transparent backgrounds.
 *
 * - `on-light`: the mark on its own, for light surfaces.
 * - `on-dark` / `badge`: the mark on a small honeydew tile, because the navy "S"
 *   would disappear against the navy header bars.
 * `size` is the rendered height in px. The mark is decorative: every place it is
 * used already shows the "SurgeWise" name beside it.
 */
type Variant = 'on-dark' | 'on-light' | 'badge';

const SRC = '/brand/surgewise-mark.png';
const RATIO = 433 / 256; // width / height of the mark artwork

export default function SurgeWiseMark({ size = 28, variant = 'on-dark', className }: { size?: number; variant?: Variant; className?: string }) {
  if (variant === 'on-light') {
    return <Image src={SRC} alt="" aria-hidden width={Math.round(size * RATIO)} height={size} className={className} unoptimized priority />;
  }
  const inner = Math.round(size * 0.68);
  return <span
    className={['sw-mark-tile', className].filter(Boolean).join(' ')}
    style={{ height: size, padding: `0 ${Math.round(size * 0.18)}px`, borderRadius: Math.round(size * 0.26) }}
    aria-hidden
  >
    <Image src={SRC} alt="" width={Math.round(inner * RATIO)} height={inner} unoptimized priority />
  </span>;
}
