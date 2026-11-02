/** Which blogs a list view shows and in what order; shared by the server render and the browser. */
import type { Row } from "./card";
import { recommendScore } from "./stance";

export type View = "all" | "top" | "recommended" | "rising" | "topic";
export type Sort = "top" | "recommended" | "rising" | "recent";

const KEYS: Record<Sort, (b: Row) => number> = {
  top: (b) => b.n_people,
  recommended: (b) => recommendScore(b.stance) * 1000 + b.n_people / 1e6, // confidence bound, not raw count
  rising: (b) => b.people_2y,
  recent: (b) => (b.last_seen ? Date.parse(b.last_seen) : 0),
};

const defaultSort = (view: View): Sort => (view === "recommended" ? "recommended" : view === "rising" ? "rising" : "top");

export function order(all: Row[], view: View, o: { topic?: string; sort?: Sort } = {}): Row[] {
  let list = all;
  if (view === "topic" && o.topic) list = list.filter((b) => b.topics.includes(o.topic!));
  if (view === "rising") list = list.filter((b) => b.people_2y > 0);
  const key = KEYS[o.sort ?? defaultSort(view)];
  return [...list].sort((a, b) => key(b) - key(a) || a.rank - b.rank);
}

const DAY = 86_400_000;
/** "Activity" filter: by the date of the newest post in the feed. */
export const ACTIVITY: [string, string, (b: Row, now: number) => boolean][] = [
  ["", "Any activity", () => true],
  ["30d", "Posted in the last 30 days", (b, now) => !!b.last_post_at && now - Date.parse(b.last_post_at) <= 30 * DAY],
  ["6m", "Posted in the last 6 months", (b, now) => !!b.last_post_at && now - Date.parse(b.last_post_at) <= 183 * DAY],
  ["1y", "Posted in the last year", (b, now) => !!b.last_post_at && now - Date.parse(b.last_post_at) <= 365 * DAY],
  ["2y", "Posted in the last 2 years", (b) => b.status === "ok"],
  ["inactive", "No posts in 2 years", (b) => b.status === "stale"],
];
export const FEED: [string, string, (b: Row) => boolean][] = [
  ["", "With or without feed", () => true],
  ["with", "With feed", (b) => b.status !== "none"],
  ["without", "Without feed", (b) => b.status === "none"],
];
export const TYPE: [string, string, (b: Row) => boolean][] = [
  ["", "Personal and company", () => true],
  ["personal", "Personal", (b) => b.type === "personal"],
  ["company", "Company", (b) => b.type === "company"],
];
export const SINCE: [string, string, (b: Row) => boolean][] = [
  ["", "First linked: any time", () => true],
  ["2015", "First linked since 2015", (b) => (b.first_seen ?? "") >= "2015"],
  ["2020", "First linked since 2020", (b) => (b.first_seen ?? "") >= "2020"],
  ["2025", "First linked since 2025", (b) => (b.first_seen ?? "") >= "2025"],
];
