/** Blogs the visitor picked to follow, kept in localStorage, shown in the tray at the bottom of every page. */

type Pick = { slug: string; name: string; feed: string; site: string };

const KEY = "hackerblogs:picks";
const BATCH = 10; // any-feeds takes up to 10 feeds per link
const listeners = new Set<() => void>();

function read(): Pick[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function write(list: Pick[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* private mode: picks last for this page view only */
  }
  memory = list;
  listeners.forEach((f) => f());
}

let memory: Pick[] = typeof localStorage === "undefined" ? [] : read();

const picks = () => memory;
const isPicked = (slug: string) => memory.some((p) => p.slug === slug);
const onPicks = (f: () => void) => listeners.add(f);

function toggle(p: Pick) {
  write(isPicked(p.slug) ? memory.filter((x) => x.slug !== p.slug) : [...memory, p]);
}

function followUrl(list: Pick[]): string {
  const q = new URLSearchParams();
  for (const p of list) q.append("url", p.feed);
  q.set("ref", "hackerblogs");
  return `https://www.any-feeds.com/subscribe?${q}`;
}

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");

function downloadOpml(list: Pick[]) {
  const items = list
    .map(
      (p) =>
        `    <outline type="rss" text="${esc(p.name)}" title="${esc(p.name)}" xmlUrl="${esc(p.feed)}" htmlUrl="${esc("https://" + p.site)}"/>`,
    )
    .join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n  <head><title>Hacker Blogs selection</title></head>\n  <body>\n${items}\n  </body>\n</opml>\n`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([xml], { type: "text/x-opml" }));
  a.download = "hackerblogs.opml";
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Wire every [data-pick] button on the page and the tray. Safe to call again after re-rendering a list. */
export function bindPickButtons(root: ParentNode = document) {
  root.querySelectorAll<HTMLButtonElement>("button[data-pick]").forEach((b) => {
    if (b.dataset.bound) return;
    b.dataset.bound = "1";
    b.addEventListener("click", (e) => {
      e.preventDefault();
      toggle(JSON.parse(b.dataset.pick!));
    });
  });
  paintButtons(root);
}

function paintButtons(root: ParentNode = document) {
  root.querySelectorAll<HTMLButtonElement>("button[data-pick]").forEach((b) => {
    const on = isPicked(JSON.parse(b.dataset.pick!).slug);
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
    const label = b.querySelector(".label");
    if (label) label.textContent = on ? "Added" : "Follow";
    b.querySelector("use")?.setAttribute("href", on ? "/icons.svg#i-check" : "/icons.svg#i-plus");
  });
}

export function initTray() {
  const tray = document.getElementById("tray")!;
  const count = document.getElementById("tray-count")!;
  const follow = document.getElementById("tray-follow")!;
  const render = () => {
    const list = picks();
    tray.hidden = list.length === 0;
    document.body.classList.toggle("tray-on", list.length > 0);
    count.textContent = `${list.length} blog${list.length === 1 ? "" : "s"} picked`;
    const links = [];
    for (let i = 0; i < list.length; i += BATCH) {
      const a = document.createElement("a");
      a.className = "btn primary";
      a.href = followUrl(list.slice(i, i + BATCH));
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = list.length <= BATCH ? "Follow on any-feeds" : `Follow ${i + 1}–${Math.min(i + BATCH, list.length)}`;
      links.push(a);
    }
    follow.replaceChildren(...links);
    paintButtons();
  };
  document.getElementById("tray-opml")!.addEventListener("click", () => downloadOpml(picks()));
  document.getElementById("tray-clear")!.addEventListener("click", () => write([]));
  onPicks(render);
  bindPickButtons();
  render();
}
