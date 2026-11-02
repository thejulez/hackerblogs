import * as L from "lucide";

type Node = [string, Record<string, string | number>][];

/** Icons used on the site, keyed by sprite id; served once as /icons.svg (pages/icons.svg.ts). */
export const ICONS: Record<string, Node> = {
  // topics
  programming: L.Code,
  systems: L.Cpu,
  web: L.Globe,
  security: L.Shield,
  ai: L.Brain,
  data: L.Database,
  math: L.Sigma,
  science: L.FlaskConical,
  startups: L.Rocket,
  business: L.Briefcase,
  economics: L.TrendingUp,
  design: L.Palette,
  writing: L.PenLine,
  career: L.GraduationCap,
  culture: L.Users,
  politics: L.Landmark,
  history: L.Scroll,
  philosophy: L.BookOpen,
  hardware: L.Wrench,
  games: L.Gamepad2,
  productivity: L.Timer,
  health: L.HeartPulse,
  other: L.Hash,
  // navigation and actions
  shuffle: L.Shuffle,
  company: L.Building,
  search: L.Search,
  plus: L.Plus,
  check: L.Check,
  x: L.X,
  rss: L.Rss,
  download: L.Download,
  trash: L.Trash2,
  external: L.ExternalLink,
  chevron: L.ChevronDown,
} as unknown as Record<string, Node>;

const attrs = (o: Record<string, string | number>) =>
  Object.entries(o)
    .map(([k, v]) => `${k}="${String(v).replace(/"/g, "&quot;")}"`)
    .join(" ");

export const symbol = (id: string) =>
  `<symbol id="i-${id}" viewBox="0 0 24 24">${ICONS[id].map(([tag, a]) => `<${tag} ${attrs(a)}/>`).join("")}</symbol>`;

/** Reference to a sprite icon; size in px. */
export const icon = (id: string, size = 16, cls = "") =>
  `<svg class="icon ${cls}" width="${size}" height="${size}" aria-hidden="true"><use href="/icons.svg#i-${id}"/></svg>`;

export const topicIcon = (t: string) => (t in ICONS ? t : "other");
