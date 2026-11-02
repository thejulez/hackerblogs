/**
 * How much the stance data can say, following the summary audit (data/audit/summaries.md):
 * - shares are shown only from 30 sampled comments, and as bands, not exact percentages;
 * - criticism is shown only with at least 3 critical comments;
 * - rankings use a lower confidence bound, so a few lucky comments do not lift a blog.
 */
type Stance = { recommend: number; neutral: number; critical: number } | null | undefined;

const MIN_SAMPLE = 30;
export const MIN_CRITICAL = 3;

const sampleSize = (s: Stance) => (s ? s.recommend + s.neutral + s.critical : 0);

export function band(s: Stance): { label: string; key: "often" | "sometimes" | "rarely" } | null {
  const n = sampleSize(s);
  if (!s || n < MIN_SAMPLE) return null;
  const share = s.recommend / n;
  return share >= 0.4
    ? { label: "Often recommended", key: "often" }
    : share >= 0.15
      ? { label: "Sometimes recommended", key: "sometimes" }
      : { label: "Rarely recommended", key: "rarely" };
}

export const showCritical = (s: Stance) => !!s && sampleSize(s) >= MIN_SAMPLE && s.critical >= MIN_CRITICAL;

/** Wilson score lower bound (95%) of the recommend share; 0 below the minimum sample. */
export function recommendScore(s: Stance): number {
  const n = sampleSize(s);
  if (!s || n < MIN_SAMPLE) return 0;
  const p = s.recommend / n,
    z = 1.96;
  return (p + (z * z) / (2 * n) - z * Math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)) / (1 + (z * z) / n);
}
