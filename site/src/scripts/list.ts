import { card, type Row } from "../lib/card";
import { ACTIVITY, FEED, order, SINCE, TYPE, type Sort, type View } from "../lib/views";
import { bindPickButtons } from "./picks";

const PAGE = 30;
type Test = (b: Row) => boolean;

export function initList() {
  const controls = document.getElementById("controls")!;
  const view = controls.dataset.view as View;
  const topic = controls.dataset.topic || "";
  const list = document.getElementById("list")!;
  const more = document.getElementById("more") as HTMLButtonElement;
  const empty = document.getElementById("empty")!;
  const state: Record<string, string> = { activity: "", feed: "", since: "", type: "", sort: "" };
  const chosen = new Set<string>();
  let all: Row[] = [];
  let rows: Row[] = [];
  let limit = PAGE;

  // one test per filter dimension, so each dimension's counts can ignore its own choice
  const now = Date.now();
  const pick =
    (opts: [string, string, (b: Row, now: number) => boolean][]) =>
    (v: string): Test => {
      const f = opts.find(([k]) => k === v)?.[2] ?? (() => true);
      return (b) => f(b, now);
    };
  const option: Record<string, (v: string) => Test> = {
    activity: pick(ACTIVITY),
    feed: pick(FEED),
    type: pick(TYPE),
    since: pick(SINCE),
  };
  // search: every word must appear in the blog's name, author, site, topics, summary or description
  const q = document.getElementById("q") as HTMLInputElement;
  if (innerWidth < 480) q.placeholder = q.placeholder.replace(", authors, topics", ""); // fits a phone
  const clear = document.getElementById("q-clear") as HTMLButtonElement;
  let words: string[] = [];
  const hay = new WeakMap<Row, string>();
  const text = (b: Row) => {
    let h = hay.get(b);
    if (!h) hay.set(b, (h = [b.name, b.author, b.site, b.topics.join(" "), b.why, b.description].join(" ").toLowerCase()));
    return h;
  };
  let timer = 0;
  q.addEventListener("input", () => {
    clear.hidden = !q.value;
    clearTimeout(timer);
    timer = window.setTimeout(() => {
      words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
      apply();
    }, 120);
  });
  clear.addEventListener("click", () => {
    q.value = "";
    clear.hidden = true;
    words = [];
    apply();
    q.focus();
  });

  const tests = (): Record<string, Test> => ({
    search: (b) => !words.length || words.every((w) => text(b).includes(w)),
    topics: (b) => !chosen.size || b.topics.some((t) => chosen.has(t)),
    activity: option.activity(state.activity),
    feed: option.feed(state.feed),
    type: option.type(state.type),
    since: option.since(state.since),
  });
  const except =
    (t: Record<string, Test>, skip: string): Test =>
    (b) =>
      Object.entries(t).every(([k, f]) => k === skip || f(b));

  controls.querySelectorAll<HTMLButtonElement>(".pill").forEach((p) =>
    p.addEventListener("click", () => {
      const t = p.dataset.topic!;
      chosen.has(t) ? chosen.delete(t) : chosen.add(t);
      p.setAttribute("aria-pressed", String(chosen.has(t)));
      apply();
    }),
  );

  // <details> menus: pick an option, close, show it as the summary
  controls.querySelectorAll<HTMLDetailsElement>(".menu").forEach((m) => {
    m.querySelectorAll<HTMLButtonElement>("[data-value]").forEach((o) =>
      o.addEventListener("click", () => {
        state[m.dataset.name!] = o.dataset.value!;
        m.querySelectorAll("[data-value]").forEach((x) => x.setAttribute("aria-selected", String(x === o)));
        m.querySelector(".current")!.textContent = o.dataset.short!;
        m.classList.toggle("set", !!o.dataset.value);
        m.open = false;
        apply();
      }),
    );
  });
  document.addEventListener("click", (e) => {
    controls.querySelectorAll<HTMLDetailsElement>(".menu[open]").forEach((m) => {
      if (!m.contains(e.target as Node)) m.open = false;
    });
  });

  function counts(base: Row[], t: Record<string, Test>) {
    const fmt = (n: number) => n.toLocaleString("en");
    const forTopics = base.filter(except(t, "topics"));
    controls.querySelectorAll<HTMLButtonElement>(".pill").forEach((p) => {
      const n = forTopics.filter((b) => b.topics.includes(p.dataset.topic!)).length;
      p.querySelector(".c")!.textContent = fmt(n);
      p.classList.toggle("zero", n === 0 && p.getAttribute("aria-pressed") !== "true");
    });
    controls.querySelectorAll<HTMLDetailsElement>(".menu").forEach((m) => {
      const dim = m.dataset.name!;
      if (!option[dim]) return;
      const pool = base.filter(except(t, dim));
      m.querySelectorAll<HTMLButtonElement>("[data-value]").forEach((o) => {
        const c = o.querySelector(".c");
        if (c) c.textContent = fmt(pool.filter(option[dim](o.dataset.value!)).length);
      });
    });
  }

  function apply() {
    const base = order(all, view, { topic, sort: (state.sort || undefined) as Sort | undefined });
    const t = tests();
    rows = base.filter(except(t, ""));
    counts(base, t);
    limit = PAGE;
    render();
  }

  function render() {
    list.innerHTML = rows
      .slice(0, limit)
      .map((b) => card(b))
      .join("");
    bindPickButtons(list);
    more.hidden = rows.length <= limit;
    empty.hidden = rows.length > 0;
  }

  more.addEventListener("click", () => {
    limit += PAGE;
    render();
  });

  // autoscroll: load the next page as "Show more" nears the viewport, up to AUTO rows, so the footer stays reachable;
  // past that, and without IntersectionObserver, the button does it
  const AUTO = 150;
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting) || more.hidden || limit >= AUTO) return;
        limit += PAGE;
        render();
        io.unobserve(more);
        requestAnimationFrame(() => io.observe(more)); // re-check: a short page can leave the button in view
      },
      { rootMargin: "0px 0px 600px 0px" },
    );
    io.observe(more);
  }

  fetch("/data/blogs.json")
    .then((r) => r.json())
    .then((data: Row[]) => {
      all = data;
      apply();
    });
}
