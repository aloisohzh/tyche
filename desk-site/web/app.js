/* Tyche desk dashboard - renders journal-derived state + live Forward automation + cloud cadence. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[—–]/g, "-").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hy = (s) => String(s ?? "").replace(/[—–]/g, "-");

const VERSION = "0.7.1";
const CHANGELOG = [
  {
    version: "0.7.1", date: "2026-11-21", title: "Open the desk on one panel",
    items: [
      "#controls, #strategy, #risk, #automation and #overview deep-link to that view, so a bookmark or a screenshot of one card stays reproducible; without a hash the desk still reopens on the last view you used.",
    ],
  },
  {
    version: "0.7.0", date: "2026-11-21", title: "Scheduled daily checks: see the cadence, switch it, fire it now",
    items: [
      "Controls gained a Scheduled daily checks card: the automation card that owns today, its fire times and timezone, its next runs, and what each recent run did or failed to do.",
      "The desk can switch the cadence off and back on and fire one run immediately; every action is journaled and the pause is re-read from the platform before it is reported as done.",
      "Fire times and timezone are shown read-only, with the reason: they live in the card's cron and again in its prompt, so retuning them is a card rebuild, not a setting.",
      "Run Scout starts the researcher on its own with today's live playbook ids in the brief - ideas only, nothing that sizes, approves or submits an order.",
    ],
  },
  {
    version: "0.6.0", date: "2026-11-21", title: "Strategy switches: turn a playbook on or off from the desk",
    items: [
      "Controls now lists every playbook the config claims with its lane, its frozen rules hash and its roster status, and each one can be switched without editing a config file.",
      "A switch is an operator override in data/strategies.json, journaled as strategy.enabled / strategy.disabled and pushed to the cloud mount like the kill-switch flag, so a toggle never re-freezes a strategy (L-037).",
      "Turning a lane off stops new entries; exits, stops and targets keep running. A lane with no registered thesis file says so before you switch it on.",
      "A corrupt switch file falls back to the lane configs and the desk reports the problem instead of guessing what is live.",
    ],
  },
  {
    version: "0.5.0", date: "2026-11-20", title: "Per-trade thesis on every card; exits retry until the broker takes them",
    items: [
      "Every trade card now carries the scout's thesis: hypothesis, synthesis, edge, bear case, invalidation, horizon and a pass/fail/unknown factor checklist with the axes it does not cover.",
      "Outlook reads the per-trade regime, direction, conviction and bull/bear factor alignment instead of a generic playbook line.",
      "The contract fields (playbook, outlook, expected edge, invalidation) are journaled with each plan, so none of them are guessed from prices.",
      "A PB-004 exit that never reaches the broker is now an incident: it is journaled as a protection gap and re-armed with fresh quotes instead of expiring after 90 seconds.",
      "Protection gaps appear on the risk timeline, and scalp fills are counted in their own intraday sleeve for expectancy.",
      "Re-arming is idempotent: an active request is retried as-is, and a live broker order blocks a duplicate exit.",
    ],
  },
  {
    version: "0.4.0", date: "2026-11-20", title: "Plain-English desk: live broker feed, real orderbook, expandable trades",
    items: [
      "Overview leads with the Moomoo account value (total assets including cash held for resting orders) and the last broker reading; the next-run countdown and feed line are gone.",
      "Jargon retired: 'marks' are now readings, regime checks are labelled rows (pass/fail), and chart points name their source and time.",
      "Strategy is one expandable table - symbol, playbook, intent, stop, target, max loss and a check count per idea; expand for the five checks and the journal evidence.",
      "Order history rebuilt around the trade: playbook, entry/exit intent, stop, max loss and notes, with the broker order id on hover.",
      "New risk-limits panel maps every docs/risk-card.md guard to its cap and current reading, with explicit gaps where the desk cannot measure a limit.",
      "'CLEAR' renamed to 'Released'; the allocation donut is larger and square; type scale raised across the desk.",
      "Controls groups operator-only settings behind an unlock zone; Data sources and Known limitations read as rows, and Telegram status uses the site's status pill.",
      "Account selector shows the real account title and masked id, so the challenge account is recognisable at a glance.",
      "Automation renamed Orchestration; schedules render as a table with live countdowns.",
    ],
  },
  {
    version: "0.3.0", date: "2026-11-19", title: "Trader-first overview + hosted operator console",
    items: [
      "Overview now leads with a trader scorecard: total paper P&L, open and realized P&L, win rate, expectancy, Sharpe and max drawdown - with honest small-sample labels.",
      "Automation evidence (schedules, sessions, credits, journal chain) moved off Overview onto the Automation page, where it belongs.",
      "Hosted operator console: unlock the Controls page with your passphrase to select trading mode and operate the kill-switch from the published site; everyone else stays view-only (refresh always works).",
      "Kill-switch now reaches the cloud desk: a shared data/halt.json flag rides the git mount, so buys are blocked everywhere while de-risking sells still pass.",
      "'Updated' stamp is now relative Singapore time (just now, 5 mins ago, yesterday) and ticks live.",
      "Descriptions use the full container width; the empty decorative banner is gone; Controls rebuilt as icon rows with tighter card spacing.",
      "Plain-English copy across every page - the market calendar gate, schedule note and risk labels read like a trader wrote them.",
    ],
  },
  {
    version: "0.2.2", date: "2026-11-19", title: "ANT IPO event capture",
    items: [
      "Market calendar pins the Anthropic (ANT) Nasdaq debut on Nov 19 ($83 offer, ~$1.5T valuation) and the Dec 4 Hang Seng HK-US Tech Index inclusion; new ipo/index event kinds.",
      "Today is an event day: opening/closing drives run with event caution - halved order counts and per-trade risk.",
      "US.ANT added to the tactical research universe (proposals only); calendar chips render ipo (violet) and index (green) events.",
    ],
  },
  {
    version: "0.2.1", date: "2026-11-19", title: "Per-trade risk budget + fee-net expectancy (ADR 0016)",
    items: [
      "Expectancy scorecard computes from journaled fills: per-sleeve n, win%, average win/loss in R, E[R] and E[%NAV], net of modeled fees.",
      "New contract field 'Initial risk': planned stop distance and R budget (1% NAV) per order, journaled at plan time.",
      "Open initial risk across lots shown under the sleeve table; the provisional chip carries the closed-trade count until n>=30.",
      "Honesty rules: unattributed fills are counted, never guessed; E[R] stays blank until both wins and losses exist.",
    ],
  },
  {
    version: "0.2.0", date: "2026-11-19", title: "Desk polish + operator controls",
    items: [
      "NAV hero now reconciles to the broker app: total assets including cash held for resting orders.",
      "Account selector in the top bar - the whole desk (NAV, positions, orders, equity, gauges) follows the selected account.",
      "All timestamps localized to Singapore (SGT) and US Eastern (ET); UTC retired from the desk.",
      "Selectable trading mode - Manual, Auto (re-arm last approved bounds), Pre-approve (define a fresh bounded envelope) - plus a kill-switch control, on the local desk.",
      "Plain-language labels for contract fields and risk rules; raw codes kept as secondary detail.",
      "Version log replaces the challenge-window footer; the desk contract lives inside this window.",
      "Top bar decluttered: regime, kill-switch and journal chips removed (state lives in Overview, Risk and Controls).",
      "Tyche branding, sentence-case labels, justified paragraphs and tighter card alignment.",
    ],
  },
  {
    version: "0.1.0", date: "2026-11-18", title: "First desk release",
    items: [
      "Fortuna-aligned redesign: five views (Overview, Strategy, Risk & Execution, Automation, Controls).",
      "Journal-derived state with hash-chain verification; cloud run bundles as the challenge-account feed.",
      "Live Qoder Sites Function: state from the repo feed, automation from the Forward API (PAT server-side).",
      "Order-approval panel wired to the bounded envelope system with disarm control.",
      "Kill-switch drill evidence, market-calendar phase routing, instrumentation completeness.",
    ],
  },
];
const DESK_CONTRACT = "Tyche v" + VERSION + " - read-only desk - order entry lives in the executor behind per-order operator confirmation or a bounded envelope - account ids redacted to ***NNN - no live trading - journal is the only truth.";

let STATE = null;
let AUTO = null;
let SCHEDULE = null;
let SCOUT = null;
let CLOUD_VIEW_ACTIVE = false;
const SNAPSHOT = window.TYCHE_SNAPSHOT || null;
const LIVE = window.TYCHE_LIVE || null;
let posSort = { key: "market_value", dir: -1 };
let posQuery = "";
let rejKind = "all";
let rejQuery = "";
let deskAcct = null;
let autoErrorShown = false;
let insView = "all";
let operatorKey = null;
let operatorConfigured = null;
const controlsEnabled = () => (!LIVE && !SNAPSHOT) || (!!LIVE && !!operatorKey);
// A card is cloud state, not a repo file. The hosted function publishes the cadence for reading but
// has no verified write path to the automation API, so the switch stays on the local desk: one control
// surface for cadence, rather than a button that might half-work from the browser.
const scheduleControllable = () => !LIVE && !SNAPSHOT;
const CONTROL_URL = LIVE ? (LIVE.control_url || "/functions/v1/app/control") : null;
const CONTROL_STATUS_URL = LIVE ? (LIVE.control_status_url || "/functions/v1/app/control/status") : null;

const THEMES = ["light", "dark"];
function currentTheme() { return document.documentElement.getAttribute("data-theme") || "light"; }
function setTheme(t) {
  if (!THEMES.includes(t)) t = "light";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("tyche-theme", t); } catch (e) {}
  document.querySelectorAll(".theme-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeSet === t)));
}

/* ---------------- view routing ---------------- */
const VIEWS = ["overview", "strategy", "risk", "automation", "controls"];
const VIEW_LABEL = { overview: "Overview", strategy: "Strategy", risk: "Risk & Execution", automation: "Orchestration", controls: "Controls" };
function showView(name) {
  if (!VIEWS.includes(name)) name = "overview";
  CLOUD_VIEW_ACTIVE = name === "controls";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  document.querySelectorAll(".nav-item").forEach((n) => {
    const on = n.dataset.view === name;
    n.classList.toggle("is-active", on);
    n.setAttribute("aria-current", on ? "page" : "false");
  });
  const crumb = $("#crumb-view");
  if (crumb) crumb.textContent = VIEW_LABEL[name];
  try { localStorage.setItem("tyche-view", name); } catch (e) {}
  if (CLOUD_VIEW_ACTIVE && STATE) fetchCloud();
  try { if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name); } catch (e) {}
  window.scrollTo({ top: 0, behavior: "smooth" });
}
const setText = (sel, v) => { const el = $(sel); if (el) el.textContent = v; };

const CONTRACT_FIELDS = ["thesis_ref", "inputs_ref", "outlook", "vehicle", "expected_edge", "invalidation", "protection_type", "roll_plan", "sizing", "initial_risk", "realized"];
const FIELD_LABELS = {
  thesis_ref: "Playbook", inputs_ref: "Price inputs", outlook: "Market outlook", vehicle: "Instrument type",
  expected_edge: "Expected edge", invalidation: "Exit trigger", protection_type: "Downside protection",
  roll_plan: "Roll plan", sizing: "Position sizing", initial_risk: "Initial risk", realized: "Realized P&L",
  "outlook + conviction": "Outlook + conviction", "macro / sentiment / seasonality": "Macro / sentiment / seasonality",
  "protection heartbeat": "Protection heartbeat", "thesis_ref / inputs_ref": "Playbook + price inputs",
};
const RULE_LABELS = {
  "account.paper_only": "Paper-only account", "account.sim_verified": "Verified sim account",
  "account.nav": "Positive NAV", "account.reconcile": "NAV reconciliation",
  "market.allowed": "Allowed market", "universe.membership": "Universe membership",
  "price.available": "Price available", "price.minimum": "Minimum price", "price.limit_deviation": "Limit near market",
  "order.max_notional": "Per-order budget", "order.pending": "No resting duplicate", "order.min_notional": "Minimum order size",
  "instrument.contract": "Contract match", "position.no_short": "No naked shorts", "position.count": "Position count",
  "position.max_weight": "Position weight cap", "option.underlying_price": "Fresh underlying price",
  "option.premium_cap": "Option premium cap", "trade.risk_budget": "Per-trade risk budget", "trade.stop": "Stop below entry",
  "halt.active": "Kill-switch active", "drawdown.hard": "Hard drawdown limit", "loss.daily_limit": "Daily loss limit",
  "portfolio.gross": "Gross exposure cap", "portfolio.min_cash": "Cash reserve", "sleeve.max_weight": "Sleeve allocation",
  "orders.competition_count": "Competition order ceiling", "orders.daily_count": "Daily order budget", "turnover.daily": "Daily turnover budget",
};
const humanize = (code) => {
  const s = String(code || "").replace(/[._]/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "-";
};
const fieldLabel = (f) => FIELD_LABELS[f] || humanize(f);
const ruleLabel = (r) => RULE_LABELS[r] || humanize(r);

const STAGES = [
  { key: "thesis", name: "Thesis", sub: "hypothesis & theme", empty: "No per-trade thesis cards yet - the playbook reference is still being built. The market view lives in the plan notes." },
  { key: "multifactor", name: "Multi-factor", sub: "macro · technical · flow", empty: "Technicals are in the plan signals. Macro, sentiment, flow and seasonality briefs arrive with the researcher." },
  { key: "outlook", name: "Outlook", sub: "bullish / bearish / range", empty: "Market-level view only today; the per-trade outlook and act/wait check are still being built." },
  { key: "vehicle", name: "Vehicle & Edge", sub: "ETFs · stocks · options", empty: "" },
  { key: "edge", name: "Edge / Expectancy", sub: "expected vs realized", empty: "Pre-trade expected edge is not built yet; realized edge shows here as trades close." },
];
const STATUS_LABEL = {
  closed: "Closed", filled: "Filled", "halt-skipped": "Halt-skipped", blocked: "Blocked",
  approved: "Approved", cancelled: "Cancelled", "broker-rejected": "Broker rejected",
  requested: "Requested", submitted: "Submitted", pending: "Pending", "part-filled": "Part-filled",
};
const STATUS_ORDER = { closed: 0, filled: 1, submitted: 2, "halt-skipped": 3, blocked: 4, "broker-rejected": 5, cancelled: 6, approved: 7, requested: 8 };
const DONUT_HUES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)", "var(--chart-7)", "var(--chart-8)"];

/* completeness ring - theme-aware via CSS vars */
function ring(frac, size = 30, stroke = 3.5) {
  const r = (size - stroke) / 2, C = 2 * Math.PI * r;
  const col = frac >= 0.8 ? "var(--green)" : frac >= 0.5 ? "var(--amber)" : "var(--red)";
  return `<svg class="cring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="contract completeness ${Math.round(frac * 100)}%">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" style="stroke:var(--line)" stroke-width="${stroke}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" style="stroke:${col}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(frac * C).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="53%" dominant-baseline="middle" text-anchor="middle" font-size="${(size * 0.3).toFixed(1)}" font-family="IBM Plex Mono, monospace" font-weight="600" style="fill:var(--ink)">${Math.round(frac * 100)}</text>
  </svg>`;
}

/* ---------------- formatting ---------------- */
const money = (n, d = 2) => n == null ? "-" : "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n, d = 1) => n == null ? "-" : (n * 100).toFixed(d) + "%";
const signedMoney = (n) => n == null ? "-" : (n >= 0 ? "+" : "−") + money(Math.abs(n));
const signedPct = (n, d = 2) => n == null ? "-" : (n >= 0 ? "+" : "−") + (Math.abs(n) * 100).toFixed(d) + "%";
const TZ_SGT = "Asia/Singapore", TZ_ET = "America/New_York";
const tzTime = (ts, tz, withSec = true) => ts ? new Date(ts).toLocaleTimeString("en-GB", { timeZone: tz, hourCycle: "h23", hour: "2-digit", minute: "2-digit", ...(withSec ? { second: "2-digit" } : {}) }) : "-";
const etTime = (ts) => tzTime(ts, TZ_ET);
const sgtTime = (ts) => tzTime(ts, TZ_SGT);
const etHHMM = (ts) => tzTime(ts, TZ_ET, false);
const sgtHHMM = (ts) => tzTime(ts, TZ_SGT, false);
const dualTime = (ts) => ts ? `${etHHMM(ts)} ET · ${sgtHHMM(ts)} SGT` : "-";
const dualCell = (ts) => ts ? `<div>${etTime(ts)} ET</div><div class="dim">${sgtTime(ts)} SGT</div>` : "-";
const dateLabel = (ts) => ts ? new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: TZ_ET }) : "-";
const etDateStr = (ts) => ts ? new Date(ts).toLocaleDateString("en-CA", { timeZone: TZ_ET }) : "";
const sgtDateStr = (ts) => ts ? new Date(ts).toLocaleDateString("en-CA", { timeZone: TZ_SGT }) : "";
function relativeTime(ts) {
  if (!ts) return "";
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, (Date.now() - t) / 1000);
  if (sec < 45) return "just now";
  if (sec < 90) return "1 min ago";
  if (sec < 3600) return Math.floor(sec / 60) + " mins ago";
  if (sec < 5400) return "1 hour ago";
  if (sec < 86400) return Math.floor(sec / 3600) + " hours ago";
  const days = Math.round((Date.parse(sgtDateStr(new Date().toISOString()) + "T00:00:00Z") - Date.parse(sgtDateStr(ts) + "T00:00:00Z")) / 86400000);
  if (days <= 1) return "yesterday";
  if (days < 7) return days + " days ago";
  return new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: TZ_SGT });
}
function stampText() {
  if (!STATE) return "Loading…";
  const ts = STATE.generated_at;
  const rel = relativeTime(ts);
  const prefix = SNAPSHOT ? "Built " : "Updated ";
  return rel ? `${prefix}${rel} · SGT ${sgtHHMM(ts)}` : prefix + dualTime(ts);
}
const sym = (s) => String(s || "").replace(/^US\./, "");
function fmtDur(sec) {
  if (sec == null) return "-";
  sec = Math.round(sec);
  if (sec < 60) return sec + "s";
  if (sec < 3600) return Math.floor(sec / 60) + "m " + (sec % 60) + "s";
  return Math.floor(sec / 3600) + "h " + Math.floor((sec % 3600) / 60) + "m";
}
function fmtCountdown(ms) {
  if (ms <= 0) return "now";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (d > 0) return `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
  return `${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m ${String(ss).padStart(2, "0")}s`;
}
const plClass = (n) => n > 0 ? "pos" : n < 0 ? "neg" : "";

/* ---------------- account selection ---------------- */
function accountList() {
  if (STATE.accounts && STATE.accounts.length) return STATE.accounts.map((a) => a.account);
  const snaps = STATE.snapshots && Object.keys(STATE.snapshots).length ? STATE.snapshots : null;
  if (snaps) return Object.keys(snaps);
  if (STATE.snapshot) return [STATE.snapshot.account];
  return Object.keys(STATE.nav_marks || {});
}
function currentSnap() {
  if (STATE.snapshots && deskAcct && STATE.snapshots[deskAcct]) return STATE.snapshots[deskAcct];
  return STATE.snapshot;
}
function accountMeta(a) {
  return (STATE.accounts || []).find((x) => x.account === a) || null;
}
function acctTitle(a) {
  const meta = accountMeta(a);
  return meta?.title || (a === STATE.feed?.primary_account ? "Moomoo x Qoder challenge" : "Paper account");
}
function acctLabel(a) {
  const title = acctTitle(a);
  return title ? `${title} · ${a}` : a;
}
function acctShort(a) {
  const meta = accountMeta(a);
  if (!meta) return a;
  if (meta.primary) return "challenge account";
  const kind = meta.account_type === 1 ? "cash" : meta.account_type === 2 ? "margin" : "paper";
  return `${kind} account`;
}
function renderAccountBar() {
  const sel = $("#account-select");
  const accts = accountList();
  if (!accts.includes(deskAcct)) deskAcct = accts[0] || null;
  sel.innerHTML = accts.map((a) => `<option value="${esc(a)}"${a === deskAcct ? " selected" : ""}>${esc(acctLabel(a))}</option>`).join("");
  sel.title = deskAcct ? acctLabel(deskAcct) : "";
  setText("#equity-acct-tag", deskAcct ? acctLabel(deskAcct) : "-");
}

/* ---------------- data fetch ---------------- */
async function fetchJson(url, fallback) {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    if (j && j.error) throw new Error(j.error);
    return j;
  } catch (err) {
    if (fallback) {
      const r2 = await fetch(fallback, { cache: "no-store" });
      if (r2.ok) { const j2 = await r2.json(); if (!j2.error) return j2; }
    }
    throw err;
  }
}

async function fetchCloud() {
  // Each feed degrades on its own: a dead Scout lane must not blank the cadence card, and neither
  // may blank the desk.
  const schedUrl = SNAPSHOT ? SNAPSHOT.schedule_url : (LIVE ? LIVE.schedule_url : "/api/schedule");
  const scoutUrl = SNAPSHOT ? SNAPSHOT.scout_url : (LIVE ? LIVE.scout_url : "/api/scout");
  if (schedUrl) {
    try {
      SCHEDULE = await fetchJson(schedUrl, LIVE ? LIVE.schedule_fallback : null);
    } catch (err) {
      SCHEDULE = { ok: false, card: null, cards: [], runs: [], problem: err.message };
    }
  }
  if (scoutUrl && scheduleControllable()) {
    try {
      SCOUT = await fetchJson(scoutUrl, LIVE ? LIVE.scout_fallback : null);
    } catch (err) {
      SCOUT = { ok: false, running: null, history: [], problem: err.message };
    }
  }
  renderSchedule();
  renderScout();
}

async function fetchAll(manual = false) {
  const btn = $("#refresh-btn");
  if (btn) btn.classList.add("spinning");
  const stateUrl = SNAPSHOT ? SNAPSHOT.state_url : (LIVE ? LIVE.state_url : "/api/state");
  const autoUrl = SNAPSHOT ? SNAPSHOT.automation_url : (LIVE ? LIVE.automation_url : "/api/automation");
  let stateErr = null;
  // State and automation are fetched independently: an automation outage (or a single
  // render exception) must never blank the figures. Last good STATE is always kept.
  try {
    STATE = await fetchJson(stateUrl, LIVE ? LIVE.state_fallback : null);
    if (!deskAcct) deskAcct = STATE.feed?.primary_account || accountList()[0] || null;
  } catch (err) { stateErr = err.message; }
  try {
    AUTO = await fetchJson(autoUrl, LIVE ? LIVE.automation_fallback : null);
  } catch (err) {
    if (!AUTO) AUTO = { ok: false, live: false, schedules: [], sessions: [], calendar: null, source: "unreachable", error: err.message };
  }
  // The two cloud feeds belong to the Controls page. Each /sessions read carries the agent definition
  // with every row, so they are pulled when that page is in view (and once at startup) rather than
  // polled with the desk figures.
  if (CLOUD_VIEW_ACTIVE || !SCHEDULE) await fetchCloud();
  if (STATE) {
    renderAll();
    setText("#updated-stamp", stampText());
  }
  if (stateErr) {
    showToast(STATE ? "State refresh failed: " + stateErr + " - keeping last good data" : "Could not load desk state: " + stateErr, true);
  } else if (manual && STATE) {
    showToast(SNAPSHOT ? "Snapshot re-read - data frozen at build time" : "Desk state refreshed - journal chain " + (STATE.chain.ok ? "verified" : "BROKEN"));
  }
  if (!SNAPSHOT && AUTO && !AUTO.ok && !autoErrorShown) {
    autoErrorShown = true;
    showToast("Forward API unreachable - showing cached local schedule export", true);
  }
  if (btn) setTimeout(() => btn.classList.remove("spinning"), 450);
}

function showToast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 4200);
}

/* ---------------- desk strip ---------------- */
function srcLabel(src) {
  const s = String(src || "");
  const cap = s.match(/^broker capture\s+(\S+)/i);
  if (cap) return `broker capture ${cap[1]}`;
  if (/^live moomoo/i.test(s)) return "live moomoo";
  return s;
}
function renderDesk() {
  const snap = currentSnap();
  const marks = STATE.nav_marks[deskAcct] || [];
  setText("#nav-acct", deskAcct ? `· ${acctShort(deskAcct)}` : "");
  setText("#nav-value", snap ? money(snap.nav) : "-");
  const deltaEl = $("#nav-delta");
  if (marks.length >= 2) {
    const d = marks[marks.length - 1].nav - marks[0].nav;
    deltaEl.textContent = `${signedMoney(d)} (${signedPct(d / marks[0].nav, 3)}) since the first reading`;
    deltaEl.className = "desk-delta mono " + (d >= 0 ? "up" : "down");
  } else { deltaEl.textContent = ""; }
  const last = marks[marks.length - 1];
  $("#nav-src").textContent = last
    ? `Last reading: ${srcLabel(last.source)} · ${dateLabel(last.ts)} ${etHHMM(last.ts)} ET`
    : "No reading saved yet";
  $("#nav-src").title = last ? hy(last.source) : "";

  const brokerVal = $("#broker-value");
  if (brokerVal) {
    const total = snap && snap.broker_total_asset != null ? Number(snap.broker_total_asset) : snap?.nav;
    brokerVal.textContent = total != null ? money(total) : "-";
  }
  const brokerSrc = $("#broker-src");
  if (brokerSrc) {
    if (!snap) {
      brokerSrc.textContent = "No broker reading yet";
    } else {
      const hold = Number(snap.order_hold || 0);
      const when = snap.as_of ? `${dateLabel(snap.as_of)} ${etHHMM(snap.as_of)} ET` : "time unknown";
      const head = snap.live ? "Live from moomoo" : `Broker reading · ${when}`;
      const tail = snap.live && snap.as_of ? ` · ${when}` : "";
      brokerSrc.textContent = head + tail + (hold > 0 ? ` · ${money(hold)} held for resting orders` : "");
      brokerSrc.title = hy(snap.source || "");
    }
  }

  $("#cash-value").textContent = snap ? money(snap.cash) : "-";
  $("#cash-weight").textContent = snap ? pct(snap.cash_weight) + " of NAV · min " + pct(STATE.risk.min_cash_weight, 0) : "-";
  $("#gross-value").textContent = snap ? pct(snap.gross_weight) : "-";
  $("#gross-cap").textContent = "Cap " + pct(STATE.risk.max_gross_exposure, 0);

  const checks = STATE.latest_plan?.regime_checks || {};
  const labels = { equity_trend: "Equity trend up", credit_trend: "Credit trend calm", golden_cross: "Golden cross", vol_calm: "Volatility calm" };
  const entries = Object.entries(checks);
  $("#regime-checks").innerHTML = entries.length
    ? entries.map(([k, v]) =>
      `<div class="check-row"><span class="check-mark ${v ? "on" : "off"}">${v ? "✓" : "✕"}</span><span class="check-name">${esc(labels[k] || humanize(k))}</span><span class="check-state">${v ? "pass" : "fail"}</span></div>`).join("")
    : '<p class="check-gap">No regime check journaled yet - the next planner run records it.</p>';
  const passed = entries.filter(([, v]) => v).length;
  setText("#regime-score", entries.length ? `${passed} of ${entries.length} pass` : "-");

  const plan = STATE.latest_plan;
  $("#vol-note").textContent = plan
    ? `Portfolio vol ${plan.portfolio_vol != null ? pct(plan.portfolio_vol) : "-"} · size scale ${plan.vol_scale != null ? Number(plan.vol_scale).toFixed(2) : "-"}`
    : "-";

  const start = Date.UTC(2026, 10, 17), end = Date.UTC(2026, 10, 28);
  const now = Date.now();
  const frac = Math.min(1, Math.max(0, (now - start) / (end - start)));
  $("#window-fill").style.width = (frac * 100).toFixed(1) + "%";
  const day = Math.min(12, Math.max(1, Math.floor((now - start) / 86400000) + 1));
  $("#window-days").textContent = `Day ${day} of 12 · ${dateLabel(new Date(now).toISOString())} · closes Nov 28`;
}

/* ---------------- trader scorecard ---------------- */
function markStats(marks) {
  let peak = -Infinity, dd = 0;
  for (const m of marks) { peak = Math.max(peak, m.nav); dd = Math.max(dd, (peak - m.nav) / peak); }
  const rets = [];
  for (let i = 1; i < marks.length; i++) rets.push(marks[i].nav / marks[i - 1].nav - 1);
  let sharpe = null;
  if (rets.length >= 3) {
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const varr = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1);
    const sd = Math.sqrt(varr);
    if (sd > 1e-12) sharpe = mean / sd;
  }
  return { dd, sharpe, rets };
}
function scoreTile(label, value, sub, cls = "") {
  return `<div class="score-tile"><span class="score-label">${esc(label)}</span><b class="score-value mono ${cls}">${value}</b><span class="score-sub">${sub}</span></div>`;
}
function renderScorecard() {
  const grid = $("#score-grid");
  if (!grid) return;
  const snap = currentSnap();
  const marks = STATE.nav_marks[deskAcct] || [];
  const e = STATE.expectancy || {};
  const { dd, sharpe } = markStats(marks);
  setText("#score-acct-tag", deskAcct ? acctLabel(deskAcct) : "-");

  const base = marks.length ? marks[0].nav : null;
  const cur = snap ? snap.nav : (marks.length ? marks[marks.length - 1].nav : null);
  const total = base != null && cur != null ? cur - base : null;
  const totalPct = total != null && base ? total / base : null;
  const open = (snap?.positions || []).reduce((a, p) => a + (p.pl || 0), 0);
  const hasPos = (snap?.positions || []).length > 0;

  const tiles = [
    scoreTile("Total P&L", total != null ? signedMoney(total) : "-",
      total != null ? `${signedPct(totalPct, 2)} since the first reading` : "needs a starting reading", plClass(total)),
    scoreTile("Open P&L", hasPos ? signedMoney(open) : "-",
      hasPos ? `unrealized · ${snap.positions.length} position${snap.positions.length === 1 ? "" : "s"}` : "no open positions", plClass(open)),
    scoreTile("Realized (net)", e.pnl_net != null ? signedMoney(e.pnl_net) : "-",
      e.closed_n ? `${e.closed_n} closed · net of fees` : "no closed trades yet", plClass(e.pnl_net)),
    scoreTile("Win rate", e.win_rate != null ? pct(e.win_rate, 0) : "-",
      e.closed_n ? `${e.closed_n} closed trade${e.closed_n === 1 ? "" : "s"}` : "small sample", ""),
    scoreTile("Expectancy", e.expectancy_r != null ? e.expectancy_r.toFixed(2) + " R" : "-",
      e.expectancy_r != null ? "average edge per trade" : "needs wins and losses", plClass(e.expectancy_r)),
    scoreTile("Sharpe", sharpe != null ? sharpe.toFixed(2) : "-",
      sharpe != null ? "per reading · provisional" : "needs 3+ readings", ""),
    scoreTile("Max drawdown", marks.length ? pct(dd, 2) : "-",
      marks.length ? `from ${marks.length} saved reading${marks.length === 1 ? "" : "s"}` : "no readings yet", dd > 0 ? "neg" : ""),
  ];
  grid.innerHTML = tiles.join("");
  setText("#score-note", "Sharpe is measured between saved readings (not annualized) and stays blank until there are at least three. Realized P&L is net of modeled fees from closed trades. Every figure is provisional while the sample is small - the journal is the only truth.");
}

/* ---------------- strategy - expandable trade table ---------------- */
let tradeFilter = "all";

function tradeKind(status) {
  if (["filled", "submitted", "part-filled", "requested", "approved"].includes(status)) return "active";
  if (["halt-skipped", "blocked", "broker-rejected", "cancelled"].includes(status)) return "skipped";
  return "planned";
}

function stageText(key, st) {
  if (!st) return "";
  if (key === "thesis") return st.text || (st.synthesis || "");
  if (key === "multifactor") {
    if (Array.isArray(st.factors) && st.factors.length) {
      const tally = (s) => st.factors.filter((f) => f.state === s).length;
      const axes = (st.covered || []).join(", ");
      return `${tally("pass")} pass · ${tally("fail")} fail · ${tally("unknown")} unknown${axes ? ` · axes: ${axes}` : ""}`;
    }
    const bits = [];
    if (st.score != null) bits.push(`score ${st.score}`);
    if (typeof st.momentum === "number" || typeof st.momentum === "string") bits.push(`momentum ${st.momentum}`);
    if (typeof st.volatility === "number" || typeof st.volatility === "string") bits.push(`volatility ${st.volatility}`);
    if (st.selected != null) bits.push(st.selected ? "selected by the scan" : "not selected by the scan");
    return bits.length ? bits.join(" · ") : (st.note || "");
  }
  if (key === "outlook") {
    const align = Object.entries(st.alignment || {}).map(([axis, view]) => `${axis} ${view}`).join(", ");
    if (st.conviction || align) {
      return [st.mapped || st.regime, st.conviction ? `conviction ${st.conviction}` : null, align || null]
        .filter(Boolean).join(" · ");
    }
    return st.mapped ? `${st.mapped}${st.regime ? ` (regime: ${st.regime})` : ""}` : (st.gap || "");
  }
  if (key === "vehicle") return [st.type, st.rationale].filter(Boolean).join(" · ");
  if (key === "edge") return [st.expected, st.realized != null ? `realized ${signedMoney(st.realized)}` : null].filter(Boolean).join(" · ") || (st.gap || "");
  return "";
}

function renderPipeline() {
  const rows = $("#trade-rows");
  if (!rows) return;
  const cards = (STATE.cards || []).slice().sort((a, b) => String(b.as_of || "").localeCompare(String(a.as_of || "")));
  const filt = $("#trade-filters");
  if (filt) {
    const kinds = [["all", "All"], ["planned", "Planned"], ["active", "Active"], ["skipped", "Skipped"]];
    filt.innerHTML = kinds.map(([k, label]) => {
      const n = k === "all" ? cards.length : cards.filter((c) => tradeKind(c.status) === k).length;
      return `<button class="fchip${tradeFilter === k ? " on" : ""}" data-trade-kind="${k}">${label} ${n}</button>`;
    }).join("");
    filt.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => { tradeFilter = b.dataset.tradeKind; renderPipeline(); }));
  }
  setText("#strategy-count", `· ${cards.length}`);
  const shown = cards.filter((c) => tradeFilter === "all" || tradeKind(c.status) === tradeFilter);
  rows.innerHTML = shown.length ? shown.map((c) => {
    const st = c.stages || {};
    const done = STAGES.filter((s) => (st[s.key]?.state || "gap") === "ok").length;
    const label = STATUS_LABEL[c.status] || c.status;
    const fill = c.status === "filled" && c.order?.fill_price != null ? money(c.order.fill_price) : null;
    return `<tr class="trade-row" data-card="${esc(c.id)}" tabindex="0" aria-expanded="false" title="Click to expand the five checks">
      <td class="exp-col"><span class="expander">▸</span></td>
      <td><strong>${esc(sym(c.symbol))}</strong><div class="dim mono">${esc(c.as_of || "")}</div></td>
      <td>${esc(c.strategy || "Desk playbook")}</td>
      <td>${esc(c.intent || "-")}</td>
      <td><span class="side ${c.side}">${esc((c.side || "").toUpperCase())}</span></td>
      <td class="num">${c.quantity}</td>
      <td class="num">${c.limit_price != null ? money(c.limit_price) : "market"}</td>
      <td class="num">${c.stop_price != null ? money(c.stop_price) : "-"}</td>
      <td class="num">${c.target != null ? money(c.target) : "-"}</td>
      <td class="num">${c.max_loss != null ? money(c.max_loss) : "-"}</td>
      <td><span class="chip status-${c.status}">${esc(label)}</span>${fill ? `<div class="dim mono">fill ${fill}</div>` : ""}</td>
      <td class="num"><span class="check-count ${done === 5 ? "full" : done >= 3 ? "part" : "low"}">${done}/5</span></td>
    </tr>
    <tr class="trade-detail" hidden><td colspan="12">
      <div class="trade-detail-grid">
        ${STAGES.map((s) => {
          const stt = st[s.key] || { state: "gap" };
          return `<div class="td-stage ${stt.state || "gap"}">
            <div class="td-stage-head"><i class="sw ${stt.state || "gap"}"></i><strong>${esc(s.name)}</strong><span class="td-state">${esc(stt.state || "gap")}</span></div>
            <p>${esc(stageText(s.key, stt) || "not instrumented")}</p>
          </div>`;
        }).join("")}
      </div>
      <div class="trade-detail-foot">
        <span class="td-meta">${esc(c.account || "-")} · ${esc(c.strategy || "Desk playbook")}${c.dry_run ? " · dry run" : ""}${c.contract ? ` · contract ${Math.round(c.contract.completeness * 100)}%` : ""}</span>
        <button class="btn btn-sm" type="button" data-open="${esc(c.id)}">Open full detail</button>
      </div>
    </td></tr>`;
  }).join("") : '<tr><td colspan="12" class="empty-row">No trade ideas in this filter yet.</td></tr>';

  rows.querySelectorAll(".trade-row").forEach((tr) => {
    const detail = tr.nextElementSibling;
    if (!detail || !detail.classList.contains("trade-detail")) return;
    const toggle = () => {
      const open = detail.hidden;
      detail.hidden = !open;
      tr.classList.toggle("open", open);
      tr.setAttribute("aria-expanded", String(open));
    };
    tr.addEventListener("click", toggle);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
  });
  rows.querySelectorAll("[data-open]").forEach((b) =>
    b.addEventListener("click", (e) => { e.stopPropagation(); openDrawer(b.dataset.open); }));
}

/* ---------------- drawer ---------------- */
function crow(key, value, gap = false, chip = "") {
  return `<div class="crow${gap ? " is-gap" : ""}"><span class="k">${esc(key)}</span><span class="v">${value}${chip}</span></div>`;
}

function openDrawer(cardId) {
  const card = (STATE.cards || []).find((c) => c.id === cardId);
  if (!card) return;
  const pos = (currentSnap()?.positions || []).find((p) => p.symbol === card.symbol);
  const status = card.status;
  $("#drawer-title").innerHTML = `
    <div>
      <div class="d-title"><span class="sym">${esc(sym(card.symbol))}</span>
        <span class="side ${card.side}">${card.side.toUpperCase()}</span>
        <span class="chip status-${status}">${esc(STATUS_LABEL[status] || status)}</span></div>
      <div class="d-sub">${esc(pos?.name || "")} · ${esc(card.account)} · ${esc(card.as_of)}${card.dry_run ? " · dry run" : ""}</div>
    </div>`;
  const o = card.order;
  const cf = card.contract?.fields || {};
  const comp = card.contract?.completeness ?? 0;
  const provTag = (p) => `<span class="prov ${p}">${p}</span>`;
  let html = `<div class="d-completeness">${ring(comp, 46, 4.5)}<div class="dc-text"><strong>Contract completeness ${Math.round(comp * 100)}%</strong><span>${card.contract?.filled ?? 0} of ${card.contract?.total ?? 10} fields carried - journaled + honestly derived</span></div></div>`;
  html += `<div class="d-section"><h5>Pipeline contract</h5><div class="contract">` +
    CONTRACT_FIELDS.map((f) => {
      const fld = cf[f] || { value: null, provenance: "gap", note: "" };
      const val = fld.value == null ? '<span class="gap-text">not instrumented</span>' : esc(fld.value);
      return `<div class="crow${fld.provenance === "gap" ? " is-gap" : ""}"><span class="k"><span class="k-label">${esc(fieldLabel(f))}</span><span class="k-raw mono">${esc(f)}</span>${provTag(fld.provenance)}</span><span class="v">${val}<span class="crow-note">${esc(fld.note)}</span></span></div>`;
    }).join("") +
    `</div></div>`;
  html += `<div class="d-section"><h5>Risk kernel verdict</h5>
    <span class="chip ${card.verdict.allowed ? "ok-chip" : "status-blocked"}">${card.verdict.allowed ? "Allowed" : "Blocked"}</span>
    <div style="height:8px"></div>`;
  for (const b of card.verdict.breaches || []) {
    html += `<div class="breach"><span class="rule-code" title="${esc(b.rule)}">${esc(ruleLabel(b.rule))}</span> - ${esc(b.detail)}</div>`;
  }
  for (const n of card.verdict.notes || []) html += `<p class="table-note" style="padding:0">${esc(n)}</p>`;
  if (!(card.verdict.breaches || []).length && !(card.verdict.notes || []).length) {
    html += `<p class="table-note" style="padding:0">No breaches - order passed every hard cap.</p>`;
  }
  html += `</div>`;
  if (o) {
    html += `<div class="d-section"><h5>Order lifecycle</h5><div class="contract">
      ${crow("Remark", `<span class="mono">${esc(o.remark || "-")}</span>`)}
      ${crow("Order id", `<span class="mono">${esc(o.order_id || "not created")}</span>`)}
      ${crow("Requested", o.requested_ts ? `${etTime(o.requested_ts)} ET · ${sgtTime(o.requested_ts)} SGT` : "-")}
      ${crow("Submitted", o.submitted_ts ? `${etTime(o.submitted_ts)} ET · ${sgtTime(o.submitted_ts)} SGT` : "-", !o.submitted_ts)}
      ${crow("Fill", o.fill_price != null ? `${o.fill_qty ?? o.quantity} @ ${money(o.fill_price)}` : STATUS_LABEL[o.status] || o.status)}
      ${o.supersedes ? crow("Supersedes", `<span class="mono">${esc(o.supersedes)}</span>`) : ""}
      ${o.note ? crow("Note", esc(o.note)) : ""}
    </div></div>`;
    html += `<div class="d-section"><h5>Journal evidence · hash-chained</h5><ul class="ev-list">` +
      o.events.map((e) => `<li><span class="ev-type">${esc(e.type)}</span><span class="ev-ts">${etHHMM(e.ts)} ET · ${sgtHHMM(e.ts)} SGT</span><span class="ev-hash">${esc(e.hash.slice(0, 12))}…</span></li>`).join("") +
      `</ul></div>`;
  }
  html += `<p class="table-note" style="padding:0">Provenance: <b>journaled</b> = written down at plan time · <b>derived</b> = computed from the record · <b>gap</b> = not captured yet. Nothing is made up - the journal is the only truth.</p>`;
  $("#drawer-body").innerHTML = html;
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#drawer-backdrop").classList.add("open");
  $("#drawer-close").focus();
}

function openChangelog() {
  $("#drawer-title").innerHTML = `<div><div class="d-title"><span class="sym">Version log</span></div><div class="d-sub">Every desk update bumps the version - click any release to see what changed.</div></div>`;
  let html = CHANGELOG.map((rel) => `
    <div class="d-section changelog-rel">
      <h5><span class="version-tag mono">v${esc(rel.version)}</span> ${esc(rel.title)} <span class="changelog-date">${esc(rel.date)}</span></h5>
      <ul class="changelog-list">${rel.items.map((it) => `<li>${esc(it)}</li>`).join("")}</ul>
    </div>`).join("");
  html += `<div class="d-section"><h5>Desk contract</h5><p class="table-note" style="padding:0">${esc(DESK_CONTRACT)}</p></div>`;
  $("#drawer-body").innerHTML = html;
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#drawer-backdrop").classList.add("open");
  $("#drawer-close").focus();
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#drawer-backdrop").classList.remove("open");
}

/* ---------------- expectancy ---------------- */
function renderExpectancy() {
  const e = STATE.expectancy;
  const r2 = (v) => (v == null ? "-" : v.toFixed(2));
  const pc = (v) => (v == null ? "-" : (100 * v).toFixed(0) + "%");
  const rows = e.sleeves.length ? e.sleeves : [{ name: "no closed trades yet", closed_n: 0 }];
  $("#sleeve-rows").innerHTML = rows.map((s) =>
    `<tr><td>${esc(s.name)}</td><td class="num">${s.closed_n}</td><td class="num">${pc(s.win_rate)}</td><td class="num">${r2(s.avg_win_r)}</td><td class="num">${r2(s.avg_loss_r)}</td><td class="num">${r2(s.expectancy_r)}</td><td class="num">${s.expectancy_pct == null ? "-" : (100 * s.expectancy_pct).toFixed(2) + "%"}</td></tr>`).join("");
  const openRisk = (e.open_lots || []).reduce((a, l) => a + (l.risk_pct_nav || 0), 0);
  $("#sleeve-note").textContent = e.closed_n
    ? `Overall E[R] ${r2(e.expectancy_r)} on ${e.r_n} closed with R · net ${signedMoney(e.pnl_net)} · open initial risk ${(100 * openRisk).toFixed(2)}% NAV across ${(e.open_lots || []).length} lot(s).`
    : `No strategy trades closed yet - the drill round-trip below is a kill-switch validation, not strategy edge. Open initial risk ${(100 * openRisk).toFixed(2)}% NAV across ${(e.open_lots || []).length} lot(s).`;
  const chip = $("#exp-chip");
  if (chip) chip.textContent = e.provisional ? `provisional · n=${e.closed_n} (<30)` : `n=${e.closed_n} closed`;
  const fills = STATE.drill.fills || {};
  const seed = fills["3115432"], sell = fills["3115472"];
  $("#realized-big").textContent = e.realized_gross != null ? signedMoney(e.realized_gross) : "-";
  $("#realized-big").className = "realized-big mono " + plClass(e.realized_gross);
  $("#realized-legs").textContent = seed && sell
    ? `10 SPY · in ${money(seed.price)} → out ${money(sell.price)} · gross, pre-fee`
    : "awaiting reconciled fills";
  $("#fees-note").textContent = hy(e.fees_note);
}

/* ---------------- execution & risk ---------------- */
function renderKill() {
  const halted = STATE.halt.halted;
  const drill = STATE.drill;
  const events = [...(STATE.halt_timeline || []), ...(STATE.protection_gaps || [])];
  const sell = (STATE.orders || []).find((o) => o.side === "sell" && o.order_id);
  if (sell) {
    events.push({ ts: sell.requested_ts, type: "order.requested", payload: { symbol: sell.symbol, quantity: sell.quantity } });
    if (sell.fill_price != null) events.push({ ts: sell.submitted_ts, type: "order.filled", payload: { symbol: sell.symbol, quantity: sell.quantity, price: sell.fill_price } });
  }
  events.sort((a, b) => a.ts.localeCompare(b.ts));
  const items = events.map((ev) => {
    const cls = ev.type === "halt.engaged" ? "ev-engaged" : ev.type === "halt.skip" || ev.type === "protection.gap" ? "ev-skip" : ev.type === "halt.released" ? "ev-released" : "";
    let text;
    if (ev.type === "halt.skip") text = `blocked ${sym(ev.payload.symbol)} ${ev.payload.quantity} - ${esc(ev.payload.reason)}`;
    else if (ev.type === "halt.engaged") text = `kill-switch engaged - ${esc(ev.payload.reason)}`;
    else if (ev.type === "halt.released") text = `kill-switch released - ${esc(ev.payload.reason)}`;
    else if (ev.type === "order.filled") text = `de-risk sell filled ${ev.payload.quantity} ${sym(ev.payload.symbol)} @ ${money(ev.payload.price)}`;
    else if (ev.type === "protection.gap") text = `protection gap - ${sym(ev.payload.symbol)} exit never reached the broker (${esc(ev.payload.resolution || "expired")}), re-armed`;
    else text = `de-risk sell requested ${sym(ev.payload.symbol)} ${ev.payload.quantity}`;
    return `<li class="${cls}"><span class="mono">${etHHMM(ev.ts)} ET</span> - ${text}</li>`;
  }).join("");
  $("#kill-card").innerHTML = `
    <span class="card-kicker">Kill-switch</span>
    <div class="kill-state ${halted ? "armed" : "clear"}"><span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "RELEASED"}</strong></div>
    <div class="kill-sub">${halted ? "New buys are blocked everywhere. De-risking sells still pass." : "Buys are allowed - no active halt."}</div>
    <div class="kill-meta">${esc(STATE.halt.reason || "")}${STATE.halt.ts ? ` · ${dualTime(STATE.halt.ts)}` : ""}</div>
    ${drill.pass ? `<span class="drill-badge">✓ kill-switch drill PASS · 2026-11-18</span>` : ""}
    <ul class="kill-timeline">${items}</ul>`;
}

function renderApproval() {
  const a = STATE.approvals;
  const pill = $("#approval-mode-pill");
  const body = $("#approval-body");
  if (!a) {
    body.innerHTML = '<p class="table-note">Approval state unavailable.</p>';
    return;
  }
  const armed = a.mode === "armed";
  const active = a.auto_active === true;
  pill.className = "pill " + (active ? "live-pill live" : armed ? "kill armed" : "live-pill cached");
  pill.querySelector("span").textContent = active ? "Pre-approved · envelope armed" : armed ? "Armed · kill-switch" : "Manual · per-order";
  pill.title = hy(a.reason || "");

  const env = a.envelope;
  const canControl = controlsEnabled();
  const modeState = !armed ? "manual" : String(env?.approved_by || "").includes("auto re-arm") ? "auto" : "pre";
  let envelopeHtml;
  if (env && Array.isArray(env.orders) && env.orders.length) {
    const rows = env.orders.map((o) => {
      const bound = o.side === "buy" ? "≤ " + money(o.limit_max) : "≥ " + money(o.limit_min);
      return `<tr><td><strong>${esc(o.symbol)}</strong></td><td>${esc(o.side)}</td><td class="num mono">${o.max_qty}</td><td class="num mono">${bound}</td></tr>`;
    }).join("");
    const used = a.used || 0;
    const max = a.max_orders || env.max_orders || 0;
    const pctUsed = max ? Math.min(100, Math.round((used / max) * 100)) : 0;
    envelopeHtml = `
      <div class="tbl-scroll"><table class="tbl approval-tbl">
        <thead><tr><th>Symbol</th><th>Side</th><th class="num">Max qty</th><th class="num">Limit bound</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      <div class="approval-budget">
        <span class="card-kicker">Envelope budget · ${used}/${max} used today</span>
        <div class="budget-track"><div class="budget-fill" style="width:${pctUsed}%"></div></div>
      </div>`;
  } else {
    envelopeHtml = '<p class="table-note">No pre-approved batch. Every order waits for your explicit confirmation at the desk console.</p>';
  }

  const validTag = env
    ? (env.valid_today ? '<span class="chip ok-chip">Valid today</span>' : '<span class="chip">Stale · not today</span>')
    : '<span class="chip">No envelope</span>';
  const haltTag = a.halted ? '<span class="chip halt-chip">Kill-switch armed</span>' : "";
  const haltNote = a.halted ? '<p class="table-note halt-note">Kill-switch engaged - no new entries regardless of mode.</p>' : "";

  const modeBtn = (mode, label, hint) =>
    `<button class="mode-opt${modeState === mode ? " on" : ""}" data-mode="${mode}"${canControl ? "" : " disabled"} title="${esc(hint)}">${esc(label)}</button>`;
  const modeSeg = `
    <div class="mode-seg" role="group" aria-label="Trading mode">
      ${modeBtn("manual", "Manual", "Every order needs your explicit confirmation at the desk.")}
      ${modeBtn("auto", "Auto", "Re-arm your last approved bounds for today - one click.")}
      ${modeBtn("pre", "Pre-approve", "Define a fresh bounded envelope for unattended runs.")}
    </div>
    <p class="mode-hint">${canControl
      ? "Manual confirms every order. Auto re-uses your last approved bounds for today. Pre-approve defines fresh bounds. The kill-switch overrides all modes."
      : (LIVE ? "View-only - unlock the operator console above to change the trading mode. Everyone can refresh." : "Read-only snapshot - trading mode is selectable on the live desk.")}</p>`;

  const envForm = canControl ? `
    <div class="env-form" id="env-form" hidden>
      <div class="env-form-head"><span class="card-kicker">New pre-approved envelope · today (ET)</span>
        <button class="text-button" id="env-add-line" type="button">+ Add line</button></div>
      <div id="env-lines"></div>
      <div class="env-form-grid">
        <label>Max orders<input type="number" id="env-max-orders" min="1" step="1" value="2" class="search"></label>
        <label>Max notional $ (optional)<input type="number" id="env-max-notional" min="1" step="any" placeholder="no cap" class="search"></label>
        <label class="env-note">Note<input type="text" id="env-note" maxlength="200" placeholder="why this batch is approved" class="search"></label>
      </div>
      <div class="env-form-actions">
        <button class="btn btn-primary" id="env-submit">Arm envelope</button>
        <button class="btn" id="env-cancel">Cancel</button>
      </div>
      <p class="table-note" style="padding:8px 0 0">Buys need a limit ceiling; sells need a limit floor. The executor only submits within these bounds, and the envelope expires at the end of today (ET).</p>
    </div>` : "";

  body.innerHTML = `
    <div class="approval-grid">
      <div class="approval-info">
        <p class="approval-reason">${esc(a.reason || "")}</p>
        <div class="approval-meta">${validTag}<span class="chip">ET today ${esc(a.today_et || "")}</span>${haltTag}</div>
        ${haltNote}
        <div class="approval-control">${modeSeg}</div>
        ${envForm}
      </div>
      <div class="approval-envelope">${envelopeHtml}</div>
    </div>`;

  if (canControl) {
    body.querySelectorAll(".mode-opt").forEach((b) => b.addEventListener("click", () => onModeClick(b.dataset.mode)));
    const add = $("#env-add-line");
    if (add) add.addEventListener("click", () => addEnvLine());
    const cancel = $("#env-cancel");
    if (cancel) cancel.addEventListener("click", () => { $("#env-form").hidden = true; });
    const submit = $("#env-submit");
    if (submit) submit.addEventListener("click", submitEnvelope);
  }
}

function onModeClick(mode) {
  const a = STATE.approvals;
  if (mode === "manual") {
    if (a.mode !== "armed") { showToast("Already manual - every order needs your confirmation"); return; }
    disarmAuto();
  } else if (mode === "auto") {
    armAuto();
  } else {
    const form = $("#env-form");
    form.hidden = !form.hidden;
    if (!form.hidden && !$("#env-lines").children.length) { addEnvLine(); addEnvLine(); }
  }
}

function addEnvLine() {
  const wrap = $("#env-lines");
  const row = document.createElement("div");
  row.className = "env-line";
  row.innerHTML = `
    <input type="text" class="search env-symbol" placeholder="SPY" maxlength="12" aria-label="Symbol">
    <select class="select env-side" aria-label="Side"><option value="buy">Buy</option><option value="sell">Sell</option></select>
    <input type="number" class="search env-qty" min="1" step="1" placeholder="Max qty" aria-label="Max quantity">
    <input type="number" class="search env-limit" min="0.01" step="any" placeholder="Limit bound $" aria-label="Limit bound">
    <button class="icon-button env-remove" type="button" title="Remove line" aria-label="Remove line">✕</button>`;
  row.querySelector(".env-remove").addEventListener("click", () => row.remove());
  wrap.appendChild(row);
}

async function postControl(url, payload) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload == null ? undefined : JSON.stringify(payload),
  });
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || "HTTP " + r.status);
  if (j.ok === false) throw new Error(j.error || "Control rejected");
  return j;
}

async function controlPost(localUrl, action, payload = {}) {
  if (!LIVE) return postControl(localUrl, payload);
  if (!operatorKey) throw new Error("Operator console locked - unlock it first");
  try {
    return await postControl(CONTROL_URL, { ...payload, passphrase: operatorKey, action });
  } catch (e) {
    if (/passphrase/i.test(e.message)) {
      operatorKey = null;
      renderOperator(); renderApproval(); renderKillControl();
    }
    throw e;
  }
}

/* ---------------- operator console (hosted) ---------------- */
async function fetchOperatorStatus() {
  if (!LIVE) return;
  try {
    const r = await fetch(CONTROL_STATUS_URL, { cache: "no-store" });
    const j = await r.json();
    operatorConfigured = !!j.operator_configured;
  } catch (e) {
    operatorConfigured = false;
  }
  renderOperator();
}

function renderAdminZone() {
  const zone = $("#admin-zone");
  if (!zone) return;
  const can = controlsEnabled();
  zone.dataset.locked = String(!can);
  const locked = $("#admin-locked");
  if (locked) locked.hidden = can;
  const state = $("#admin-state");
  if (state) {
    state.className = "pill " + (can ? "live-pill live" : "cached");
    const label = state.querySelector("span");
    if (label) label.textContent = can ? (LIVE ? "Unlocked" : "Unlocked - local desk") : "Locked";
  }
  const jump = $("#admin-jump");
  if (jump) jump.hidden = !LIVE || operatorConfigured === false;
}

function renderOperator() {
  const card = $("#operator-card");
  if (!card) return;
  renderAdminZone();
  if (!LIVE) { card.hidden = true; return; }
  card.hidden = false;
  const state = $("#operator-state");
  const row = $("#operator-row");
  const sub = $("#operator-sub");
  const icon = $("#operator-icon");
  if (operatorConfigured === false) {
    row.hidden = true;
    state.className = "pill cached";
    state.querySelector("span").textContent = "Not configured";
    sub.textContent = "Operator controls are disabled on this hosted desk until the owner adds TYCHE_OPERATOR_PASSPHRASE and TYCHE_GITHUB_PAT in Sites Settings. Everyone can still refresh and view every figure.";
    icon.classList.remove("ok");
    renderAdminZone();
    return;
  }
  if (operatorKey) {
    row.hidden = true;
    state.className = "pill live-pill live";
    state.querySelector("span").textContent = "Unlocked";
    sub.innerHTML = 'Operator unlocked - you can change the trading mode and kill-switch below. <button class="text-button" id="operator-lock" type="button">Lock again</button>';
    const lock = $("#operator-lock");
    if (lock) lock.addEventListener("click", lockOperator);
    icon.classList.add("ok");
  } else {
    row.hidden = false;
    state.className = "pill cached";
    state.querySelector("span").textContent = "Locked";
    sub.textContent = "This desk is shared read-only. Unlock with your operator passphrase to change the trading mode or the kill-switch. The passphrase is held in memory only and never stored.";
    icon.classList.remove("ok");
  }
  renderAdminZone();
}

function lockOperator() {
  operatorKey = null;
  renderOperator(); renderApproval(); renderKillControl();
  showToast("Operator console locked - controls are view-only again");
}

async function unlockOperator() {
  const inp = $("#operator-pass");
  const pass = (inp?.value || "").trim();
  if (!pass) { showToast("Enter your operator passphrase", true); return; }
  const btn = $("#operator-unlock");
  btn.disabled = true; btn.textContent = "Unlocking…";
  try {
    await postControl(CONTROL_URL, { passphrase: pass, action: "ping" });
    operatorKey = pass;
    inp.value = "";
    renderOperator(); renderApproval(); renderKillControl();
    showToast("Operator console unlocked - controls enabled");
  } catch (e) {
    showToast("Unlock failed: " + e.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Unlock";
  }
}

async function disarmAuto() {
  if (!confirm("Switch to Manual and propagate to the cloud desk?\n\nOrders revert to per-order confirmation. This commits + pushes the envelope removal. Reversible - re-arm any time with Auto or Pre-approve.")) return;
  try {
    const j = await controlPost("/api/approvals/disarm", "disarm");
    if (j.pushed) showToast("Manual mode - per-order confirmation (cloud synced)");
    else showToast("Disarmed locally; cloud push failed: " + (j.git_error || "unknown"), true);
    await fetchAll(true);
  } catch (e) {
    showToast("Disarm failed: " + e.message, true);
  }
}

async function armAuto() {
  if (!confirm("Auto mode: re-arm your LAST approved envelope for today?\n\nThe previous bounds (symbols, quantities, limit bounds, order budget) are re-approved as-is for today's ET date and pushed to the cloud desk. Choose Pre-approve instead to define fresh bounds.")) return;
  try {
    const j = await controlPost("/api/approvals/arm", "arm", { reuse_last: true });
    showToast(j.pushed ? "Auto armed - last approved bounds valid today (cloud synced)" : "Armed locally; cloud push failed: " + (j.git_error || "unknown"), !j.pushed);
    await fetchAll(true);
  } catch (e) {
    showToast("Auto arm failed: " + e.message, true);
  }
}

async function submitEnvelope() {
  const lines = [...document.querySelectorAll("#env-lines .env-line")].map((row) => {
    const symbol = row.querySelector(".env-symbol").value.trim().toUpperCase().replace(/^US\./, "");
    const side = row.querySelector(".env-side").value;
    const qty = Number(row.querySelector(".env-qty").value);
    const limit = Number(row.querySelector(".env-limit").value);
    const line = { symbol, side, max_qty: qty };
    if (side === "buy") line.limit_max = limit; else line.limit_min = limit;
    return line;
  }).filter((l) => l.symbol && l.max_qty > 0 && l.limit_max > 0 || l.symbol && l.max_qty > 0 && l.limit_min > 0);
  const maxOrders = Number($("#env-max-orders").value);
  const maxNotional = $("#env-max-notional").value ? Number($("#env-max-notional").value) : null;
  if (!lines.length) { showToast("Add at least one complete line (symbol, qty, limit bound)", true); return; }
  if (!(maxOrders >= 1)) { showToast("Max orders must be at least 1", true); return; }
  const summary = lines.map((l) => `${l.symbol} ${l.side} ≤ ${l.max_qty} @ ${l.side === "buy" ? "≤ " + money(l.limit_max) : "≥ " + money(l.limit_min)}`).join("\n");
  if (!confirm(`Arm this pre-approved envelope for today (ET)?\n\n${summary}\n\nMax orders: ${maxOrders}${maxNotional ? "\nMax notional: " + money(maxNotional) : ""}\n\nThe executor may submit within these bounds without a per-order popup. It expires at the end of today.`)) return;
  const btn = $("#env-submit");
  btn.disabled = true; btn.textContent = "Arming…";
  try {
    const j = await controlPost("/api/approvals/arm", "arm", { max_orders: maxOrders, max_notional: maxNotional, note: $("#env-note").value, orders: lines });
    showToast(j.pushed ? "Envelope armed - pre-approved auto within bounds (cloud synced)" : "Armed locally; cloud push failed: " + (j.git_error || "unknown"), !j.pushed);
    await fetchAll(true);
  } catch (e) {
    showToast("Arm failed: " + e.message, true);
    btn.disabled = false; btn.textContent = "Arm envelope";
  }
}

function renderKillControl() {
  const wrap = $("#kill-control-body");
  if (!wrap) return;
  const halted = STATE.halt.halted;
  const canControl = controlsEnabled();
  const srcTag = STATE.halt.source === "repo" ? " · shared cloud flag" : "";
  wrap.innerHTML = `
    <div class="kill-state ${halted ? "armed" : "clear"}"><span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "RELEASED"}</strong></div>
    <div class="kill-sub">${halted ? "New buys are blocked everywhere." : "Buys are allowed - no active halt."}</div>
    <div class="kill-meta">${esc(STATE.halt.reason || "")}${STATE.halt.ts ? ` · ${dualTime(STATE.halt.ts)}` : ""}${srcTag}</div>
    ${canControl ? `
      ${halted ? "" : '<input type="text" id="halt-reason" class="search halt-reason" maxlength="200" placeholder="Reason for halting (journaled)" aria-label="Halt reason">'}
      <button class="btn ${halted ? "btn-primary" : "disarm-btn"} kill-btn" id="kill-toggle">${halted ? "Release kill-switch" : "Engage kill-switch"}</button>
      <p class="table-note" style="padding:10px 0 0">${halted ? "Releasing lets buys through again after your review. The change is journaled and reaches the cloud desk." : "Engaging blocks new buys everywhere immediately; de-risking sells still pass. The change is journaled and reaches the cloud desk."}</p>
    ` : `<p class="table-note" style="padding:10px 0 0">${LIVE ? "View-only - unlock the operator console above to operate the kill-switch." : "Read-only snapshot - the kill-switch is operated from the live desk."}</p>`}`;
  const btn = $("#kill-toggle");
  if (btn) btn.addEventListener("click", () => toggleHalt(!halted));
}

async function toggleHalt(halted) {
  const reason = halted ? ($("#halt-reason")?.value || "").trim() : "";
  const msg = halted
    ? `Engage the kill-switch?\n\nNew buys are blocked immediately; de-risking sells still pass.${reason ? "\n\nReason: " + reason : ""}`
    : "Release the kill-switch?\n\nBuys are permitted again after your review.";
  if (!confirm(msg)) return;
  const btn = $("#kill-toggle");
  if (btn) { btn.disabled = true; btn.textContent = halted ? "Engaging…" : "Releasing…"; }
  try {
    await controlPost("/api/halt", "halt", { halted, reason });
    showToast(halted ? "Kill-switch ARMED - buys blocked everywhere, transition journaled" : "Kill-switch released - buys permitted, transition journaled");
    await fetchAll(true);
  } catch (e) {
    showToast("Kill-switch change failed: " + e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = halted ? "Engage kill-switch" : "Release kill-switch"; }
  }
}

function strategyRow(row, canControl) {
  const meta = [row.strategy_id, row.lane, row.rules_hash ? "frozen " + row.rules_hash : "no rules file"].join(" · ");
  const decided = row.source === "data/strategies.json"
    ? "set by the switch file"
    : "lane config default";
  const unrostered = row.roster_status !== "live"
    ? `<span class="pill cached strat-warn">no registered thesis</span>`
    : "";
  const control = canControl
    ? `<button class="btn ${row.enabled ? "strat-off" : "btn-primary"}" type="button" data-strat="${esc(row.strategy_id)}" data-enabled="${row.enabled ? "0" : "1"}">${row.enabled ? "Turn off" : "Turn on"}</button>`
    : `<span class="pill kill ${row.enabled ? "clear" : "armed"}"><i class="dot"></i><span>${row.enabled ? "on" : "off"}</span></span>`;
  return `<div class="strategy-row" data-live="${row.enabled ? "1" : "0"}">
    <div class="strat-name"><strong>${esc(row.name)}</strong>${unrostered}</div>
    <div class="strat-meta">${esc(meta)}</div>
    <div class="strat-note">${esc(decided)}${row.rules_file_problem ? " · " + esc(row.rules_file_problem) : ""}</div>
    <div class="strat-ctl">${control}</div>
  </div>`;
}

function renderStrategies() {
  const wrap = $("#strategy-list");
  if (!wrap) return;
  const view = STATE.strategies;
  if (!view || view.error) {
    wrap.innerHTML = `<p class="table-note">${view ? esc(view.error) : "Strategy switches unavailable."}</p>`;
    setText("#strategy-side", "");
    return;
  }
  const canControl = controlsEnabled();
  wrap.innerHTML = view.strategies.map((row) => strategyRow(row, canControl)).join("");
  wrap.querySelectorAll("[data-strat]").forEach((btn) => btn.addEventListener("click", () => {
    toggleStrategy(btn.dataset.strat, btn.dataset.enabled === "1");
  }));
  const file = view.switch_file || {};
  const problem = view.problem ? `<div class="strat-problem">${esc(view.problem)}</div>` : "";
  setText("#strategy-side", "");
  $("#strategy-side").innerHTML = `${problem}
    <div class="strat-live">${view.live.length ? "Live now: " + esc(view.live.join(", ")) : "No strategy is live."}</div>
    <div class="strat-meta">${file.present
      ? `Switch file updated ${esc(dualTime(file.updated_at))} by ${esc(file.updated_by || "operator")}`
      : "No operator override yet - each lane's own config decides."}</div>
    <div class="strat-meta">Turned off at the lane config:${view.strategies.filter((r) => !r.lane_config_enabled).map((r) => " " + r.strategy_id).join(",") || " none"}</div>`;
}

async function toggleStrategy(strategyId, enabled) {
  const row = (STATE.strategies.strategies || []).find((s) => s.strategy_id === strategyId);
  const unrostered = row && row.roster_status !== "live";
  const msg = enabled
    ? `Turn ${strategyId} on?

New entries in this lane become tradeable again${unrostered ? ", and it has NO registered thesis file (pre-registration discipline says write one first)" : ""}.`
    : `Turn ${strategyId} off?

New entries stop; exits, stops and targets keep running. Scout will stop proposing for it.`;
  if (!confirm(msg)) return;
  const btn = document.querySelector(`[data-strat="${strategyId}"]`);
  if (btn) { btn.disabled = true; btn.textContent = enabled ? "Turning on…" : "Turning off…"; }
  try {
    const j = await controlPost("/api/strategies/toggle", "strategy", { strategy_id: strategyId, enabled });
    showToast(`${strategyId} ${enabled ? "enabled" : "disabled"} - journaled${j.pushed ? " and pushed to the cloud mount" : ""}`);
    if (j.git_error) showToast("Switch saved locally but the push failed: " + j.git_error, true);
    await fetchAll(true);
  } catch (e) {
    showToast("Strategy switch failed: " + e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = enabled ? "Turn on" : "Turn off"; }
  }
}

/* ---------------- scheduled daily checks ---------------- */
function scheduleRunRow(run) {
  const trigger = run.trigger === "schedule" ? "scheduled fire" : (hy(run.trigger || "run"));
  const outcome = run.error
    ? `<span class="sched-err">${esc(String(run.error).slice(0, 140))}</span>`
    : "no error reported";
  return `<tr><td class="mono">${esc(dualTime(run.at))}</td><td>${esc(trigger)}</td><td>${outcome}</td></tr>`;
}

function renderSchedule() {
  const body = $("#schedule-body");
  const side = $("#schedule-side");
  if (!body) return;
  const view = SCHEDULE;
  const card = view && view.ok ? view.card : null;
  if (!view) {
    body.innerHTML = '<p class="table-note">Cadence not loaded yet.</p>';
    if (side) side.innerHTML = "";
    return;
  }
  if (!view.ok) {
    body.innerHTML = `<p class="table-note">The automation API could not be read just now: ${esc(view.problem || "unknown error")}. This says nothing about the card itself - only that the desk is blind at this moment.</p>`;
    if (side) side.innerHTML = `<span class="pill cached"><i class="dot"></i><span>unavailable</span></span>`;
    return;
  }
  if (!card) {
    body.innerHTML = `<p class="table-note">${view.orphan_date
      ? `No automation card owns ${esc(view.today_et)}, so nothing fires on this date. The desk waits for the next card to be built.`
      : "No automation card was returned."}</p>`;
    if (side) side.innerHTML = `<span class="pill cached"><i class="dot"></i><span>no card</span></span>`;
    return;
  }
  const on = !card.paused;
  const times = (view.fire_times || []).join(" · ") || "not stated";
  const next = (view.next_runs || []).filter((iso) => Date.parse(iso) > Date.now()).slice(0, 4)
    .map((iso) => `<li>${esc(dualTime(iso))}</li>`).join("") || '<li class="sched-none">none listed</li>';
  const runs = (view.runs || []).slice(0, 4).map(scheduleRunRow).join("")
    || '<tr><td colspan="3" class="sched-none">This card has not run yet.</td></tr>';
  body.innerHTML = `
    <div class="sched-line">
      <span class="pill live-pill ${on ? "live" : "cached"}"><i class="dot"></i><span>${on ? "running on schedule" : "paused"}</span></span>
      <span class="sched-times mono">${esc(times)}</span>
      <span class="sched-tz">${esc(view.timezone || "")}</span>
    </div>
    <ul class="kill-facts">
      <li><span>Card</span>${esc(card.name)} - window ${esc(card.window || "?")}</li>
      <li><span>Runs</span>the desk agent (v${esc(card.agent && card.agent.version)}) at each fire; the card's own prompt says what a fire may do - pre-market plans, midday watches and shouts only, close reconciles</li>
      <li><span>Last fire</span>${esc(dualTime(card.last_run))}${card.paused && card.paused_reason ? " · " + esc(card.paused_reason) : ""}</li>
    </ul>
    <div class="sched-cols">
      <div><h4>Next runs</h4><ul class="sched-next">${next}</ul></div>
      <div><h4>Recent runs</h4><table class="tbl sched-runs"><tbody>${runs}</tbody></table></div>
    </div>`;
  const can = scheduleControllable() && controlsEnabled();
  const note = `<div class="strat-meta sched-edit-note">${esc(view.edit_note || "")}</div>`;
  if (side) {
    side.innerHTML = (can
      ? `<button class="btn ${on ? "strat-off" : "btn-primary"}" type="button" id="schedule-pause">${on ? "Pause cadence" : "Resume cadence"}</button>
         <button class="btn" type="button" id="schedule-run">Run a check now</button>`
      : `<span class="pill cached"><i class="dot"></i><span>${LIVE ? "read-only here" : "local desk only"}</span></span>`) + note;
    const pauseBtn = $("#schedule-pause");
    const runBtn = $("#schedule-run");
    if (pauseBtn) pauseBtn.addEventListener("click", () => scheduleControl(on ? "pause" : "resume", card));
    if (runBtn) runBtn.addEventListener("click", () => scheduleControl("run_now", card));
  }
}

async function scheduleControl(action, card) {
  const pauseMsg = `Pause the scheduled checks?

Nothing fires until you resume - not the pre-market plan, not the midday protection watch, not the close reconciliation. Positions keep their existing stops, but no run reviews them while this is off.`;
  const resumeMsg = `Resume the scheduled checks?

The desk fires again at each scheduled time in the card window (${hy(card.window || "")}) and trades paper orders through the normal gates.`;
  const runMsg = `Fire one desk run now?

This starts the same session a scheduled fire would: calendar check, reconciliation, planning and paper orders through the existing approval path. It arms no gate and lifts no halt.${card.paused ? "\n\nThe card is PAUSED - you are asking for one manual run anyway." : ""}`;
  const msg = action === "pause" ? pauseMsg : action === "resume" ? resumeMsg : runMsg;
  if (!confirm(msg)) return;
  const btn = $(action === "run_now" ? "#schedule-run" : "#schedule-pause");
  const label = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = action === "run_now" ? "Firing…" : "Working…"; }
  try {
    const j = await controlPost("/api/schedule/control", "schedule", { action });
    if (action === "run_now") {
      showToast("Desk run requested - it appears in Recent runs when the platform starts it");
    } else if (j.verified) {
      showToast(action === "pause" ? "Cadence paused - journaled and confirmed on the platform" : "Cadence resumed - journaled and confirmed on the platform");
    } else {
      showToast("The platform did not confirm the change - re-read the card before trusting it", true);
    }
    await fetchAll(true);
  } catch (e) {
    showToast("Schedule control failed: " + e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = label; }
    await fetchAll(true);
  }
}

/* ---------------- Run Scout ---------------- */
function renderScout() {
  const body = $("#scout-body");
  const side = $("#scout-side");
  if (!body) return;
  if (!scheduleControllable()) {
    body.innerHTML = '<p class="table-note">Scout is started from the local desk, which holds the cloud token. The scheduled fires still run the researcher as their first phase.</p>';
    if (side) side.innerHTML = '<span class="pill cached"><i class="dot"></i><span>local desk only</span></span>';
    return;
  }
  const view = SCOUT;
  if (!view) {
    body.innerHTML = '<p class="table-note">Scout status not loaded yet.</p>';
    if (side) side.innerHTML = "";
    return;
  }
  if (!view.ok) {
    body.innerHTML = `<p class="table-note">The automation API could not be read: ${esc(view.problem || "unknown error")}.</p>`;
    if (side) side.innerHTML = '<span class="pill cached"><i class="dot"></i><span>unavailable</span></span>';
    return;
  }
  const running = view.running;
  const brief = view.brief || {};
  const history = (view.history || []).slice(0, 4).map((row) => `<li>${esc(dualTime(row.created_at))} - ${esc(row.status || "?")} <span class="mono">${esc(row.id || "")}</span></li>`).join("");
  body.innerHTML = `
    <div class="sched-line">
      <span class="pill live-pill ${running ? "cached" : "live"}"><i class="dot"></i><span>${running ? "a run is in flight" : "idle - ready"}</span></span>
      <span class="sched-tz">${running ? esc(running.id || "") : (brief.live || []).length + " playbook(s) live"}</span>
    </div>
    ${view.stale ? `<p class="table-note sched-warn">A Scout session older than two hours never finished (${esc(view.stale.id)}). It is reported, not treated as a block.</p>` : ""}
    <details class="scout-brief">
      <summary>The brief it would send now</summary>
      <pre>${esc(brief.brief || "unavailable")}</pre>
    </details>
    ${history ? `<ul class="sched-next scout-history">${history}</ul>` : '<p class="table-note">No Scout run started from the desk yet.</p>'}`;
  if (side) {
    side.innerHTML = running
      ? '<span class="pill cached"><i class="dot"></i><span>wait for the current run</span></span>'
      : '<button class="btn btn-primary" type="button" id="scout-run">Run Scout</button>';
    const btn = $("#scout-run");
    if (btn) btn.addEventListener("click", runScout);
  }
}

async function runScout() {
  const brief = (SCOUT && SCOUT.brief) || {};
  if (!brief.brief) { showToast("No brief composed - refresh Controls before starting Scout", true); return; }
  const msg = `Start a Scout run now?

It starts one researcher session in the cloud - research and ideas only, no sizing, no approval, no order.
It cannot see the repository, so the brief below is everything it gets.

${brief.brief}`;
  if (!confirm(msg)) return;
  const btn = $("#scout-run");
  if (btn) { btn.disabled = true; btn.textContent = "Starting…"; }
  try {
    await controlPost("/api/scout/run", "scout", { confirmed: true });
    showToast("Scout started - the session answers in Qoder; its run appears in the history");
  } catch (e) {
    showToast("Scout could not start: " + e.message, true);
  }
  await fetchCloud();
}

function gauge(label, value, cap, capLabel, mode, valueLabel) {
  const frac = Math.min(1, value / cap);
  const cls = mode === "min" ? (value >= cap ? "g-ok" : "g-hot") : frac < 0.6 ? "g-ok" : frac < 0.85 ? "g-warn" : "g-hot";
  const mark = `<span class="cap-mark" style="left:${Math.min(100, cap * 100)}%"></span>`;
  return `<div class="gauge">
    <div class="gauge-top"><span>${esc(label)}</span><span class="g-val">${esc(valueLabel || pct(value))} <span class="g-cap">/ ${esc(capLabel)}</span></span></div>
    <div class="gauge-bar"><i class="${cls}" style="width:${(Math.min(1, value) * 100).toFixed(1)}%"></i>${mark}</div>
  </div>`;
}

function renderGauges() {
  const snap = currentSnap(), risk = STATE.risk;
  const maxPos = Math.max(...(snap?.positions || [{ weight: 0 }]).map((p) => p.weight));
  const maxPosSym = sym((snap?.positions || [{}])[0]?.symbol);
  const marks = STATE.nav_marks[deskAcct] || [];
  let peak = -Infinity, dd = 0;
  for (const m of marks) { peak = Math.max(peak, m.nav); dd = Math.max(dd, (peak - m.nav) / peak); }
  const today = etDateStr(new Date().toISOString());
  const ordersToday = (STATE.orders || []).filter((o) => etDateStr(o.requested_ts) === today && (!snap?.account || o.account === snap.account)).length;
  const ddRung = (label, threshold) => `<div class="rung${dd >= threshold ? " hit" : ""}"><b>${pct(threshold, 0)}</b>${esc(label)}</div>`;
  $("#gauges-card").innerHTML = `
    <span class="card-kicker">Exposure vs hard caps</span>
    ${gauge("Gross exposure", snap?.gross_weight || 0, risk.max_gross_exposure, pct(risk.max_gross_exposure, 0) + " cap")}
    ${gauge("Cash weight", snap?.cash_weight || 0, risk.min_cash_weight, pct(risk.min_cash_weight, 0) + " min", "min")}
    ${gauge(`Largest position · ${maxPosSym}`, maxPos, risk.max_position_weight, pct(risk.max_position_weight, 0) + " cap")}
    ${gauge("Order attempts today", ordersToday / risk.max_orders_per_day, 1, "daily cap", null, `${ordersToday}/${risk.max_orders_per_day}`)}
    <span class="card-kicker" style="margin-top:6px">Drawdown ladder · current DD ${pct(dd, 2)} <em>(${marks.length} saved reading${marks.length === 1 ? "" : "s"})</em></span>
    <div class="ladder">
      ${ddRung("alert", risk.soft_drawdown_pct)}
      ${ddRung("auto-halt", risk.hard_drawdown_pct)}
      ${ddRung("daily stop", risk.daily_loss_limit_pct)}
    </div>`;
}

function renderRiskGuards() {
  const wrap = $("#guard-rows");
  if (!wrap) return;
  const snap = currentSnap();
  const risk = STATE.risk || {};
  const orders = (STATE.orders || []).filter((o) => !deskAcct || o.account === deskAcct);
  const nav = snap?.nav || 0;
  const positions = snap?.positions || [];
  const today = etDateStr(new Date().toISOString());
  const todays = orders.filter((o) => etDateStr(o.requested_ts) === today);
  const notional = (o) => (o.limit_price != null ? o.limit_price : (o.fill_price || 0)) * (o.quantity || 0);
  const maxOrder = todays.length ? Math.max(...todays.map(notional)) : null;
  const minOrder = todays.length ? Math.min(...todays.map(notional)) : null;
  const maxCardLoss = Math.max(...(STATE.cards || []).map((c) => c.max_loss || 0), 0);
  const minPrice = positions.length ? Math.min(...positions.map((p) => p.last_price)) : null;
  const shorts = positions.filter((p) => p.quantity < 0).length;
  const maxPos = positions.length ? Math.max(...positions.map((p) => p.weight)) : null;
  const maxPosSym = positions.length ? positions.slice().sort((a, b) => b.weight - a.weight)[0].symbol : null;
  const turnover = nav ? todays.reduce((a, o) => a + notional(o), 0) / nav : null;
  const marks = STATE.nav_marks[deskAcct] || [];
  let peak = -Infinity, dd = 0;
  for (const m of marks) { peak = Math.max(peak, m.nav); dd = Math.max(dd, (peak - m.nav) / peak); }
  const meta = accountMeta(deskAcct) || {};
  const acctType = snap?.account_type ?? meta.account_type;
  const marketId = snap?.market_id ?? meta.market_id;
  const simTypes = risk.sim_account_types || [1, 2];
  const simMarket = risk.sim_market_id ?? 100;
  const priced = todays.filter((o) => o.limit_price != null && positions.some((p) => p.symbol === o.symbol && p.last_price));
  const limitDev = priced.length
    ? Math.max(...priced.map((o) => {
      const last = positions.find((p) => p.symbol === o.symbol).last_price;
      return Math.abs(o.limit_price / last - 1);
    }))
    : null;
  const maxState = (v, cap) => v == null ? "gap" : v > cap ? "breach" : v > cap * 0.85 ? "warn" : "ok";
  const minState = (v, floor) => v == null ? "gap" : v < floor ? "breach" : v < floor * 1.15 ? "warn" : "ok";

  const tiles = [];
  const T = (name, value, cap, state, note) => tiles.push({ name, value, cap, state, note });
  T("Account type", acctType != null ? `type ${acctType}` : "-", `types ${simTypes.join(" / ")}`,
    acctType != null && simTypes.includes(acctType) ? "ok" : "gap", "paper simulator only - no live or crypto tools mounted");
  T("Market", marketId != null ? `market ${marketId}` : "-", `US = ${simMarket}`,
    marketId === simMarket ? "ok" : "gap", "US equities only");
  T("Minimum price", minPrice != null ? money(minPrice) : "-", money(risk.min_price ?? 1),
    minState(minPrice, risk.min_price ?? 1), "cheapest holding must clear the price floor");
  T("Limit near market", limitDev != null ? pct(limitDev, 2) : "not measured", `max ${pct(risk.max_limit_deviation_pct, 0)}`,
    maxState(limitDev, risk.max_limit_deviation_pct), limitDev != null
      ? "largest limit-vs-last gap among today's priced orders"
      : "checked at submit - no priced orders in this session");
  T("Per-order budget", maxOrder != null && nav ? pct(maxOrder / nav, 1) : "-", `${pct(risk.max_order_notional_pct, 0)} NAV`,
    maxState(maxOrder != null && nav ? maxOrder / nav : null, risk.max_order_notional_pct), "largest single order notional today");
  T("Per-trade risk", maxCardLoss && nav ? pct(maxCardLoss / nav, 2) : "-", `${pct(risk.risk_per_trade_pct, 1)} NAV`,
    maxState(maxCardLoss && nav ? maxCardLoss / nav : null, risk.risk_per_trade_pct), "max loss (qty x stop distance) on a journaled idea");
  T("Minimum order size", minOrder != null ? money(minOrder, 0) : "-", money(risk.min_order_notional ?? 500, 0),
    minState(minOrder, risk.min_order_notional ?? 500), "smallest order today - fee drag guard");
  T("No naked shorts", shorts ? `${shorts} short` : "none", "0 allowed", shorts ? "breach" : "ok", "inventory-first only; no new shorting");
  T("Position count", positions.length, `max ${risk.max_positions ?? 100}`,
    maxState(positions.length, risk.max_positions ?? 100), "held names");
  T("Largest position", maxPos != null ? `${sym(maxPosSym)} ${pct(maxPos)}` : "-", `max ${pct(risk.max_position_weight, 0)}`,
    maxState(maxPos, risk.max_position_weight), "single-name concentration");
  T("Gross exposure", snap?.gross_weight != null ? pct(snap.gross_weight) : "-", `max ${pct(risk.max_gross_exposure, 0)}`,
    maxState(snap?.gross_weight, risk.max_gross_exposure), "sum of positions over NAV");
  T("Cash reserve", snap?.cash_weight != null ? pct(snap.cash_weight) : "-", `min ${pct(risk.min_cash_weight, 0)}`,
    minState(snap?.cash_weight, risk.min_cash_weight), "cash weight floor");
  T("Orders today", todays.length, `max ${risk.max_orders_per_day ?? 120}`,
    maxState(todays.length, risk.max_orders_per_day ?? 120), "buys and sells both count");
  T("Turnover today", turnover != null ? pct(turnover) : "-", `max ${pct(risk.max_daily_turnover_pct, 0)}`,
    maxState(turnover, risk.max_daily_turnover_pct), "notional traded over NAV");
  T("Drawdown alert", marks.length ? pct(dd, 2) : "-", `alert ${pct(risk.soft_drawdown_pct, 0)}`,
    marks.length ? (dd >= risk.hard_drawdown_pct ? "breach" : dd >= risk.soft_drawdown_pct ? "warn" : "ok") : "gap",
    "from the saved readings, high-water reading basis");
  T("Hard drawdown stop", marks.length ? pct(dd, 2) : "-", `stop ${pct(risk.hard_drawdown_pct, 0)}`,
    marks.length ? (dd >= risk.hard_drawdown_pct ? "breach" : "ok") : "gap", "the desk halts new buys at this level");
  T("Kill-switch", STATE.halt.halted ? "armed" : "released", "blocks buys", STATE.halt.halted ? "warn" : "ok",
    STATE.halt.halted ? "new buys are blocked everywhere" : "buys pass; de-risking sells always pass");
  T("Fee model", "modeled", "per fill", "ok", "fees estimated from the journal; reconciliation in the daily report");

  const counts = tiles.reduce((a, t) => { a[t.state] = (a[t.state] || 0) + 1; return a; }, {});
  const summary = $("#guard-summary");
  if (summary) {
    summary.innerHTML =
      `<span class="chip ok-chip">${counts.ok || 0} passing</span>` +
      (counts.warn ? `<span class="chip provisional">${counts.warn} near</span>` : "") +
      (counts.breach ? `<span class="chip halt-chip">${counts.breach} over</span>` : "") +
      (counts.gap ? `<span class="chip">${counts.gap} not measurable</span>` : "");
  }
  wrap.innerHTML = tiles.map((t) => `<div class="guard-tile ${t.state}">
    <div class="guard-top"><span class="guard-name">${esc(t.name)}</span><span class="guard-flag">${t.state === "gap" ? "n/a" : t.state === "ok" ? "ok" : t.state === "warn" ? "near" : "over"}</span></div>
    <div class="guard-val mono">${esc(t.value)}${t.cap ? `<span class="guard-cap"> / ${esc(t.cap)}</span>` : ""}</div>
    <div class="guard-note">${esc(t.note)}</div>
  </div>`).join("");
}

function renderDonut() {
  const wrap = $("#donut-wrap");
  const snap = currentSnap();
  if (!snap) { wrap.innerHTML = '<p class="table-note">No snapshot</p>'; return; }
  const total = snap.nav || 0;
  const frac = (v) => (total ? v / total : 0);
  const ranked = snap.positions
    .map((p, i) => ({ label: sym(p.symbol), value: p.market_value, hue: DONUT_HUES[i % DONUT_HUES.length] }))
    .sort((a, b) => b.value - a.value);
  const rest = ranked.slice(4);
  const all = ranked.slice(0, 4);
  if (rest.length) all.push({ label: `other ${rest.length}`, value: rest.reduce((a, s) => a + s.value, 0), hue: "var(--chart-other)" });
  if (snap.cash > 0) all.push({ label: "cash", value: snap.cash, hue: "var(--chart-cash)" });
  const segs = all.filter((s) => s.value > 0).sort((a, b) => b.value - a.value);
  const r = 54, C = 2 * Math.PI * r;
  let offset = 0;
  const arcs = [], chips = [];
  segs.forEach((s) => {
    const f = frac(s.value);
    arcs.push(`<circle r="${r}" cx="70" cy="70" fill="none" style="stroke:${s.hue}" stroke-width="17"
      stroke-dasharray="${(f * C).toFixed(2)} ${C.toFixed(2)}" stroke-dashoffset="${(-offset * C).toFixed(2)}"
      transform="rotate(-90 70 70)"><title>${esc(s.label)} ${pct(f)}</title></circle>`);
    if (f >= 0.1) {
      const mid = (offset + f / 2) * 2 * Math.PI - Math.PI / 2;
      const lx = 70 + r * Math.cos(mid), ly = 70 + r * Math.sin(mid);
      const txt = pct(f), w = txt.length * 4.6 + 6;
      chips.push(`<g><rect x="${(lx - w / 2).toFixed(1)}" y="${(ly - 5.5).toFixed(1)}" width="${w.toFixed(1)}" height="11" rx="3" style="fill:var(--surface)"/>` +
        `<text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="middle" style="fill:var(--ink)" font-size="7.5" font-weight="600" font-family="IBM Plex Mono, monospace">${txt}</text></g>`);
    }
    offset += f;
  });
  const legend = segs.map((s) => `<li><i style="background:${s.hue}"></i>${esc(s.label)}<span class="mono">${pct(frac(s.value))}</span></li>`).join("");
  const summary = segs.map((s) => `${s.label} ${pct(frac(s.value))}`).join(", ");
  wrap.innerHTML = `
    <svg viewBox="0 0 140 140" width="200" height="200" role="img" aria-label="Allocation by market value: ${esc(summary)}">
      <circle r="${r}" cx="70" cy="70" fill="none" style="stroke:var(--surface2)" stroke-width="17"/>
      ${arcs.join("")}
      ${chips.join("")}
      <text x="70" y="66" text-anchor="middle" style="fill:var(--ink)" font-size="15" font-weight="600" font-family="IBM Plex Mono, monospace">${snap.positions.length}</text>
      <text x="70" y="82" text-anchor="middle" style="fill:var(--muted)" font-size="8.5" letter-spacing="1">NAMES + CASH</text>
    </svg>
    <ul class="donut-legend">${legend}</ul>`;
}

function renderPositions() {
  const snap = currentSnap();
  const rows = (snap?.positions || [])
    .filter((p) => !posQuery || (p.symbol + " " + p.name).toLowerCase().includes(posQuery))
    .sort((a, b) => {
      const k = posSort.key;
      const va = a[k], vb = b[k];
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * posSort.dir;
    });
  $("#pos-count").textContent = `· ${rows.length}/${snap?.positions.length || 0} · broker sim_list`;
  $("#pos-rows").innerHTML = rows.map((p) => {
    const w = p.weight;
    const wcls = w < 0.2 ? "w-ok" : w < 0.3 ? "w-warn" : "w-hot";
    return `<tr>
      <td><strong>${esc(sym(p.symbol))}</strong></td>
      <td style="color:var(--muted)">${esc(p.name)}</td>
      <td class="num">${p.quantity.toLocaleString()}</td>
      <td class="num">${money(p.avg_cost)}</td>
      <td class="num">${money(p.last_price)}</td>
      <td class="num">${money(p.market_value)}</td>
      <td class="num weight-cell">${pct(w)}<div class="weight-bar"><i class="${wcls}" style="width:${Math.min(100, w / STATE.risk.max_position_weight * 100).toFixed(1)}%"></i></div></td>
      <td class="num ${plClass(p.pl)}">${signedMoney(p.pl)}</td>
      <td class="num ${plClass(p.pl_pct)}">${signedPct(p.pl_pct)}</td>
    </tr>`;
  }).join("");
  document.querySelectorAll(".pos-tbl th[data-sort]").forEach((th) => {
    th.classList.toggle("sorted-asc", th.dataset.sort === posSort.key && posSort.dir === 1);
    th.classList.toggle("sorted-desc", th.dataset.sort === posSort.key && posSort.dir === -1);
  });
}

function renderOrders() {
  const all = (STATE.orders || []).filter((o) => !deskAcct || o.account === deskAcct);
  const working = all.filter((o) => ["requested", "submitted"].includes(o.status)).length;
  const el = $("#working-orders");
  el.textContent = working === 0 ? "0 working orders - all terminal" : `${working} working`;
  el.className = "chip " + (working === 0 ? "ok-chip" : "provisional");
  const orders = all.slice().reverse();
  $("#order-rows").innerHTML = orders.map((o) => {
    const note = [o.reason, o.authorization && o.authorization !== "manual" ? `${o.authorization} authorization` : ""]
      .filter(Boolean).join(" · ");
    const hover = `Order ${o.order_id || "not created"} · ${o.account || "-"}${o.request_id ? ` · request ${o.request_id}` : ""}`;
    return `<tr title="${esc(hover)}">
      <td class="mono nowrap">${o.requested_ts ? dualCell(o.requested_ts) : "-"}</td>
      <td><strong>${esc(sym(o.symbol))}</strong></td>
      <td>${esc(o.strategy || "Desk playbook")}</td>
      <td>${o.intent ? `<span class="intent ${esc(String(o.intent).toLowerCase())}">${esc(o.intent)}</span>` : "-"}</td>
      <td><span class="side ${o.side}">${esc((o.side || "").toUpperCase())}</span></td>
      <td class="num">${o.quantity}</td>
      <td class="num">${o.limit_price != null ? money(o.limit_price) : "market"}</td>
      <td class="num">${o.fill_price != null ? money(o.fill_price) : "-"}</td>
      <td class="num">${o.max_loss != null ? money(o.max_loss) : "-"}</td>
      <td><span class="chip status-${o.status}">${esc(STATUS_LABEL[o.status] || o.status)}</span>${o.order_id ? "" : '<div class="dim mono">no broker id</div>'}</td>
      <td class="notes-cell" title="${esc(note)}">${esc(note || "-")}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="11" class="empty-row">No orders for this account yet.</td></tr>';
}

function renderRejections() {
  const all = STATE.rejections || [];
  const kinds = ["all", "risk-kernel", "halt", "broker"];
  $("#rej-filters").innerHTML = kinds.map((k) => {
    const n = k === "all" ? all.length : all.filter((r) => r.kind === k).length;
    const label = k === "all" ? "All" : k === "risk-kernel" ? "Risk rules" : k === "halt" ? "Halt" : "Broker";
    return `<button class="fchip${rejKind === k ? " on" : ""}" data-kind="${k}">${label} ${n}</button>`;
  }).join("");
  $("#rej-filters").querySelectorAll(".fchip").forEach((b) =>
    b.addEventListener("click", () => { rejKind = b.dataset.kind; renderRejections(); }));
  const rows = all.filter((r) =>
    (rejKind === "all" || r.kind === rejKind) &&
    (!rejQuery || (r.rule + " " + ruleLabel(r.rule) + " " + r.symbol + " " + r.detail).toLowerCase().includes(rejQuery)));
  $("#rej-count").textContent = `· ${rows.length}/${all.length} events`;
  $("#rej-rows").innerHTML = rows.map((r) => `<tr>
    <td class="mono" style="font-size:10.5px">${dualCell(r.ts)}</td>
    <td><span class="kind ${r.kind}">${r.kind === "risk-kernel" ? "Risk rules" : r.kind === "halt" ? "Halt" : "Broker"}</span></td>
    <td><span class="rule-code" title="${esc(r.rule)}">${esc(ruleLabel(r.rule))}</span></td>
    <td><strong>${esc(sym(r.symbol))}</strong></td>
    <td><span class="side ${r.side}">${r.side.toUpperCase()}</span></td>
    <td class="num">${r.quantity.toLocaleString()}</td>
    <td style="color:var(--muted)">${esc(r.detail)}</td>
  </tr>`).join("");
}

/* ---------------- equity ---------------- */
function shortSrc(src) {
  const s = String(src || "");
  if (/^broker capture/i.test(s)) return "Broker capture";
  if (/^live moomoo/i.test(s)) return "Live moomoo";
  const cloud = s.match(/^cloud:(\d{4}-\d{2}-\d{2})-([a-z0-9_]+)$/i) || s.match(/^cloud run\s+(\d{4}-\d{2}-\d{2})-([a-z0-9_]+)/i);
  if (cloud) {
    const phase = cloud[2].replace(/_/g, " ").replace(/(\d+)$/, " $1").trim();
    return "Cloud " + phase;
  }
  if (/^plan\.created/i.test(s)) return "Journal plan";
  if (/^snapshot/i.test(s)) return "Broker snapshot";
  return s.length > 24 ? s.slice(0, 23) + "..." : s;
}
function renderEquity() {
  const marks = STATE.nav_marks[deskAcct] || [];
  const stats = $("#equity-stats");
  if (!marks.length) {
    stats.innerHTML = "";
    $("#equity-chart").innerHTML = '<p class="table-note">No saved readings for this account yet.</p>';
    $("#returns-bars").innerHTML = "";
    return;
  }
  const first = marks[0], last = marks[marks.length - 1];
  const delta = last.nav - first.nav;
  let peak = -Infinity, dd = 0;
  for (const m of marks) { peak = Math.max(peak, m.nav); dd = Math.max(dd, (peak - m.nav) / peak); }
  const nReadings = marks.reduce((a, m) => a + (m.count || 1), 0);
  const nextFriday = (() => {
    const d = new Date();
    const add = (5 - d.getUTCDay() + 7) % 7 || 7;
    return new Date(d.getTime() + add * 86400000);
  })();
  stats.innerHTML = `
    <div class="estat"><span class="desk-label">Latest value</span><b>${money(last.nav)}</b></div>
    <div class="estat"><span class="desk-label">Change since first reading</span><b class="${plClass(delta)}">${signedMoney(delta)} · ${signedPct(delta / first.nav, 3)}</b></div>
    <div class="estat"><span class="desk-label">Max drawdown</span><b>${pct(dd, 2)}</b></div>
    <div class="estat"><span class="desk-label">Saved readings</span><b>${nReadings}</b> <span class="chip provisional">provisional</span></div>
    <div class="estat"><span class="desk-label">Next weekly reading</span><b>${dateLabel(nextFriday.toISOString())}</b></div>`;

  const W = 1000, H = 270, L = 92, R = 34, T = 30, B = 44;
  const navs = marks.map((m) => m.nav);
  const lo = Math.min(...navs), hi = Math.max(...navs);
  const pad = Math.max((hi - lo) * 0.35, hi * 0.00025);
  const yMin = lo - pad, yMax = hi + pad;
  const x = (i) => marks.length === 1 ? (L + (W - L - R) / 2) : L + (i / (marks.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
  let grid = "";
  for (let g = 0; g <= 3; g++) {
    const v = yMin + (g / 3) * (yMax - yMin);
    const yy = y(v);
    grid += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" style="stroke:var(--line-soft)" stroke-width="1"/>
      <text x="${L - 10}" y="${yy + 4}" text-anchor="end" style="fill:var(--faint)" font-size="11.5" font-family="IBM Plex Mono, monospace">$${Math.round(v).toLocaleString()}</text>`;
  }
  const pts = marks.map((m, i) => [x(i), y(m.nav)]);
  const linePath = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const areaPath = linePath + ` L ${pts[pts.length - 1][0].toFixed(1)} ${H - B} L ${pts[0][0].toFixed(1)} ${H - B} Z`;
  const dots = marks.map((m, i) => {
    const [cx, cy] = pts[i];
    const above = i % 2 === 0 || marks.length === 1;
    return `<circle cx="${cx}" cy="${cy}" r="6" style="fill:var(--bg1);stroke:var(--green)" stroke-width="2.5">
        <title>${esc(m.source)} · ${dualTime(m.ts)} · ${money(m.nav)}</title></circle>
      <text x="${cx}" y="${above ? cy - 16 : cy + 26}" text-anchor="middle" style="fill:var(--ink)" font-size="13" font-weight="600" font-family="IBM Plex Mono, monospace">${money(m.nav, 0)}</text>
      <text x="${cx}" y="${H - B + 18}" text-anchor="middle" style="fill:var(--label-2)" font-size="11">${esc(shortSrc(m.source))}${m.count > 1 ? " x" + m.count : ""}</text>
      <text x="${cx}" y="${H - B + 33}" text-anchor="middle" style="fill:var(--label-4)" font-size="10" font-family="IBM Plex Mono, monospace">${dateLabel(m.ts)} ${etHHMM(m.ts)} ET</text>`;
  }).join("");
  $("#equity-chart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Saved account value readings over time">
      <defs>
        <linearGradient id="eqArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style="stop-color:var(--green)" stop-opacity=".22"/><stop offset="1" style="stop-color:var(--green)" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="eqLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" style="stop-color:var(--blue)"/><stop offset="1" style="stop-color:var(--green)"/>
        </linearGradient>
      </defs>
      ${grid}
      ${marks.length > 1 ? `<path d="${areaPath}" fill="url(#eqArea)"/><path class="equity-line" d="${linePath}" fill="none" stroke="url(#eqLine)" stroke-width="2.5" stroke-linecap="round"/>` : ""}
      ${dots}
    </svg>`;
  const rets = [];
  for (let i = 1; i < marks.length; i++) rets.push({ r: marks[i].nav / marks[i - 1].nav - 1, label: etHHMM(marks[i].ts) });
  const maxAbs = Math.max(...rets.map((d) => Math.abs(d.r)), 1e-9);
  $("#returns-bars").innerHTML = rets.length
    ? rets.map((d) => `<div class="rbar ${d.r >= 0 ? "up" : "down"}"><b class="${plClass(d.r)}">${signedPct(d.r, 3)}</b><i style="height:${Math.max(4, Math.abs(d.r) / maxAbs * 40)}px"></i><span>${d.label} ET</span></div>`).join("")
    : '<p class="table-note" style="padding:0">Only one reading so far - no change to show yet. The fee-net daily series arrives with the EOD performance generator.</p>';
}

/* ---------------- automation ---------------- */
function tickCountdowns() {
  document.querySelectorAll("[data-countdown]").forEach((b) => {
    b.textContent = fmtCountdown(Number(b.dataset.countdown) - Date.now());
  });
}

/* ---------------- market calendar / session-phase routing ---------------- */
const PHASE_META = {
  pre_market: { name: "Pre-market", hue: "var(--amber)" },
  opening_drive: { name: "Opening drive", hue: "var(--green)" },
  midday: { name: "Midday", hue: "var(--slate)" },
  closing_drive: { name: "Closing drive", hue: "var(--cyan)" },
  after_hours: { name: "After-hours", hue: "var(--magenta)" },
  closed: { name: "Closed", hue: "var(--faint)" },
};
const ACTIVITY_LABEL = { plan: "plans", active: "trades", monitor: "monitors", reconcile: "reconciles", noop: "rests" };
const EVENT_HUE = { fomc: "var(--red)", macro: "var(--amber)", earnings: "var(--cyan)", ipo: "var(--violet)", index: "var(--green)" };
const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
function plainCalReason(cal) {
  const r = String(cal.reason || "");
  const pm = PHASE_META[cal.phase] || PHASE_META.closed;
  if (r.startsWith("market closed:")) return "Market closed - " + r.slice(14).trim() + ". Scheduled runs skip until the next session.";
  if (r.startsWith("outside trading session")) return "Outside trading hours (04:00-20:00 ET). Scheduled runs skip.";
  const m = r.match(/phase mismatch: schedule wants (\w+), now (\w+)/);
  if (m) return `This schedule trades in the ${(PHASE_META[m[1]] || {}).name || m[1]} window; right now it is ${(PHASE_META[m[2]] || {}).name || m[2]}.`;
  if (r.endsWith("active")) return `${pm.name} window is open - this schedule trades now.`;
  return hy(r);
}

function renderCalendar() {
  const cal = AUTO?.calendar;
  const card = $("#cal-card");
  if (!cal) { card.style.display = "none"; return; }
  card.style.display = "";

  const etHHMMNow = cal.now_et.slice(11, 16);
  const etDate = new Date(cal.now_et);
  const dayName = etDate.toLocaleDateString("en-US", { weekday: "short", timeZone: TZ_ET });
  const monDay = etDate.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: TZ_ET });
  $("#cal-now").textContent = `${dayName} ${monDay} · ${etHHMMNow} ${cal.et_label} · ${sgtHHMM(cal.now_utc)} SGT`;

  const gate = $("#cal-gate");
  gate.className = "cal-gate " + (cal.run ? "run" : "skip");
  gate.querySelector("span").textContent = cal.run ? "Trading now" : "Skipping now";
  gate.title = "Whether a scheduled run firing right now would place orders";
  const pm = PHASE_META[cal.phase] || PHASE_META.closed;
  const phasePill = $("#cal-phase");
  phasePill.textContent = pm.name;
  phasePill.style.setProperty("--seg-hue", pm.hue);
  $("#cal-reason").textContent = plainCalReason(cal) + (cal.strategy?.event_caution ? " Event day - order count and per-trade risk are halved." : "");

  const tl = cal.timeline || [];
  const rail = $("#cal-rail");
  const ticks = $("#cal-rail-ticks");
  if (!tl.length) {
    rail.innerHTML = `<div class="cal-seg closed" style="width:100%;--seg-hue:var(--faint)"><span>market closed${cal.holiday ? " · " + esc(cal.holiday) : ""}</span></div>`;
    ticks.innerHTML = "";
    $("#cal-rail-overlay").innerHTML = "";
    rail.setAttribute("aria-label", "Market closed" + (cal.holiday ? " - " + cal.holiday : ""));
  } else {
    const startMin = toMin(tl[0].start), endMin = toMin(tl[tl.length - 1].end), span = endMin - startMin;
    const boundaries = [{ t: tl[0].start, min: startMin }];
    let segs = "";
    tl.forEach((s) => {
      const a = toMin(s.start), b = toMin(s.end), meta = PHASE_META[s.phase];
      const w = ((b - a) / span * 100).toFixed(3);
      segs += `<div class="cal-seg${s.phase === cal.phase ? " active" : ""}" style="width:${w}%;--seg-hue:${meta.hue}" title="${meta.name} · ${s.start}-${s.end} ET"></div>`;
      boundaries.push({ t: s.end, min: b });
    });
    let marker = "";
    if (cal.trading_day) {
      const nowMin = toMin(etHHMMNow);
      if (nowMin >= startMin && nowMin <= endMin) {
        const f = Math.min(98.5, Math.max(1.5, (nowMin - startMin) / span * 100)).toFixed(3);
        marker = `<div class="cal-now-marker" style="left:${f}%"><span class="mono">${etHHMMNow}</span><i></i></div>`;
      }
    }
    rail.innerHTML = segs;
    $("#cal-rail-overlay").innerHTML = marker;
    const seen = new Set();
    ticks.innerHTML = boundaries.filter((b) => !seen.has(b.min) && seen.add(b.min)).map((b) => {
      const f = ((b.min - startMin) / span * 100).toFixed(3);
      return `<span style="left:${f}%">${b.t}</span>`;
    }).join("");
    rail.setAttribute("aria-label", "Session phases: " + tl.map((s) => `${PHASE_META[s.phase].name} ${s.start} to ${s.end} ET`).join(", ") + `. Current phase: ${pm.name}.`);
  }

  $("#cal-phases").innerHTML = (cal.phase_strategies || []).map((p) => {
    const meta = PHASE_META[p.phase];
    const seg = tl.find((s) => s.phase === p.phase);
    const range = seg ? `${seg.start}-${seg.end}` : "-";
    const sleeves = (p.sleeves || []).map((s) => `<span class="cal-sleeve">${esc(s)}</span>`).join("") || '<span class="cal-sleeve none">none</span>';
    return `<div class="cal-phase${p.phase === cal.phase ? " active" : ""}" style="--seg-hue:${meta.hue}">
      <div class="cal-phase-head"><span class="cal-swatch"></span><span class="cal-phase-name">${meta.name}</span></div>
      <span class="cal-phase-time mono">${range} ET</span>
      <span class="cal-activity ${p.activity}">${ACTIVITY_LABEL[p.activity] || p.activity}</span>
      <div class="cal-phase-meta"><span>max <b>${p.max_orders}</b> order${p.max_orders === 1 ? "" : "s"}</span><span>${p.new_entries ? "new entries" : "no new entries"}</span></div>
      <div class="cal-sleeves">${sleeves}</div>
    </div>`;
  }).join("");

  const evChips = (cal.events || []).map((e) => `<span class="cal-event" style="--ev-hue:${EVENT_HUE[e.kind] || "var(--slate)"}"><i></i>${esc(e.name)}${e.time_et ? ` <b class="mono">${esc(e.time_et)}</b>` : ""}</span>`).join("");
  const earn = cal.earnings_season ? `<span class="cal-event" style="--ev-hue:var(--cyan)"><i></i>${esc(cal.earnings_season)}</span>` : "";
  const half = cal.half_day ? '<span class="cal-flag half">half day · 13:00 ET close</span>' : "";
  const hol = cal.holiday ? `<span class="cal-flag closed">closed · ${esc(cal.holiday)}</span>` : "";
  const today = (evChips || earn || half || hol) ? `${evChips}${earn}${half}${hol}` : '<span class="cal-none">no scheduled events</span>';
  const ahead = (cal.upcoming || []).map((u) => {
    const dd = new Date(u.date + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
    if (u.closed) return `<span class="cal-day closed"><b>${dd}</b><span>${esc(u.closed)}</span></span>`;
    const n = (u.events || []).length;
    const sub = u.half_day ? "half day" : n ? `${n} event${n > 1 ? "s" : ""}` : "clear";
    return `<span class="cal-day${u.half_day ? " half" : ""}${n ? " has-event" : ""}"><b>${dd}</b><span>${sub}</span></span>`;
  }).join("");
  $("#cal-aware").innerHTML =
    `<div class="cal-aware-row"><span class="cal-aware-label">Today</span><div class="cal-aware-items">${today}</div></div>` +
    `<div class="cal-aware-row"><span class="cal-aware-label">Ahead</span><div class="cal-aware-items cal-days">${ahead}</div></div>`;

  $("#cal-window").textContent = `${cal.window.start} → ${cal.window.end}`;
  $("#cal-cron-rows").innerHTML = (cal.schedules || []).map((s) => {
    const meta = PHASE_META[s.phase] || { name: "gate-routed", hue: "var(--cyan)" };
    return `<tr>
      <td><strong style="font-size:12px">${esc(s.name)}</strong></td>
      <td><span class="cal-cron mono">${esc(s.cron)}</span></td>
      <td><span class="cal-phase-tag" style="--seg-hue:${meta.hue}">${meta.name}</span></td>
      <td><span class="cal-activity ${s.activity}">${ACTIVITY_LABEL[s.activity] || s.activity}</span></td>
      <td class="mono" style="font-size:11px">${esc(s.et_time)}</td>
      <td class="mono" style="font-size:11px">${esc(s.sgt_time || "-")}</td>
      <td class="num">${s.days}</td>
    </tr>`;
  }).join("");
  $("#cal-cron-note").textContent = "One hourly schedule fires at :05 past each hour from 08:05 to 17:05 ET (21:05 to 06:05 SGT, landing after midnight in Singapore). It only trades on NYSE open days - weekends and holidays are skipped automatically. Each run checks the session phase first, so a run outside its window does nothing, and half-days and clock changes are handled.";

  const wl = cal.watchlist;
  const wlWrap = $("#cal-watchlist-wrap");
  if (wlWrap) {
    wlWrap.hidden = !wl;
    if (wl) {
      $("#cal-watchlist-state").textContent = `${wl.stale ? "Stale" : "Fresh"} · as of ${wl.as_of} · ${wl.active_count} active`;
      $("#cal-watchlist-rows").innerHTML = (wl.entries || []).map((e) => `<tr>
        <td><strong style="font-size:12px">${esc(e.symbol)}</strong></td>
        <td>${esc(e.sleeve)}</td>
        <td style="font-size:11px">${esc(e.strategy)}</td>
        <td class="mono num">${e.entry_low.toFixed(2)}-${e.entry_high.toFixed(2)}</td>
        <td class="mono num">${e.stop.toFixed(2)}</td>
        <td class="mono num">${e.target.toFixed(2)}</td>
        <td class="mono">${esc(e.expiry)}</td>
        <td>${esc(e.status)}</td>
      </tr>`).join("") || '<tr><td colspan="8" style="color:var(--faint)">No entries.</td></tr>';
    }
  }
}

function renderAutomation() {
  const pill = $("#automation-source");
  if (SNAPSHOT) {
    pill.className = "pill live-pill cached";
    pill.querySelector("span").textContent = "Static snapshot · " + dateLabel(SNAPSHOT.built_at);
    pill.title = "Baked read-only snapshot - " + (AUTO.source || "");
  } else {
    const isLive = LIVE ? AUTO.live === true : AUTO.ok;
    pill.className = "pill live-pill " + (isLive ? "live" : "cached");
    pill.querySelector("span").textContent = isLive ? "Live · Forward API" : (LIVE ? "Cached export" : "Cached local export");
    pill.title = hy(AUTO.source) + (AUTO.error ? " - " + AUTO.error : "");
  }
  const allScheds = AUTO.schedules || [];
  const activeScheds = allScheds.filter((s) => s.status === "active").length;
  const allSessions = AUTO.sessions || [];
  const totalCredits = allSessions.reduce((x, s) => x + (s.usage?.total_credits || 0), 0);
  setText("#ov-sched-count", allScheds.length ? `${activeScheds}/${allScheds.length}` : "-");
  setText("#ov-sessions", allSessions.length ? String(allSessions.length) : "-");
  setText("#ov-credits", allSessions.length ? totalCredits.toFixed(1) : "-");
  setText("#ov-chain", STATE.chain.ok ? `${STATE.chain.count} ✓` : "BROKEN");
  const scheds = [...(AUTO.schedules || [])].sort((a, b) => {
    const na = (a.trigger_policy?.upcoming_runs_at || ["9999"])[0];
    const nb = (b.trigger_policy?.upcoming_runs_at || ["9999"])[0];
    return na.localeCompare(nb);
  });
  setText("#sched-count", allScheds.length ? `${activeScheds} active / ${allScheds.length}` : "-");
  $("#sched-rows").innerHTML = scheds.map((s) => {
    const next = (s.trigger_policy?.upcoming_runs_at || [])[0];
    const nextT = next ? Date.parse(next) : null;
    return `<tr class="${s.status === "active" ? "" : "is-paused"}">
      <td><strong>${esc(s.name)}</strong><div class="dim">${esc(s.description || "")}</div></td>
      <td><span class="cal-cron mono">${esc(s.trigger_policy?.expression || "-")}</span><div class="dim mono">${esc(s.trigger_policy?.timezone || "UTC")}</div></td>
      <td><span class="sched-pill ${s.status === "active" ? "active" : "paused"}"><i></i>${esc(s.status || "unknown")}</span></td>
      <td>${nextT && nextT > Date.now()
        ? `<b class="mono" data-countdown="${nextT}">${fmtCountdown(nextT - Date.now())}</b><div class="dim mono">${dateLabel(next)} ${etHHMM(next)} ET · ${sgtHHMM(next)} SGT</div>`
        : '<span class="dim">No upcoming run in this window</span>'}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="4" class="empty-row">No schedules returned - Forward may be unreachable; the cached export carries the last known set.</td></tr>';
  const sessions = AUTO.sessions || [];
  const credits = sessions.reduce((a, s) => a + (s.usage?.total_credits || 0), 0);
  $("#credits-total").textContent = `Σ ${credits.toFixed(1)} credits`;
  $("#session-rows").innerHTML = sessions.map((s) => {
    const st = s.status || "unknown";
    return `<tr>
      <td><strong style="font-size:12px">${esc(s.title || s.id)}</strong><div class="mono" style="font-size:9.5px;color:var(--faint)">${esc(s.id)}</div></td>
      <td style="color:var(--muted)">${esc(s.template?.name || "-")}</td>
      <td><span class="sess-status ${esc(st)}"><i></i>${esc(st)}</span></td>
      <td><span class="chip ${s.source_type === "schedule" ? "dry" : ""}" style="font-size:9.5px">${esc(s.source_type || "-")}</span></td>
      <td class="num">${(s.usage?.total_credits ?? 0).toFixed(1)}</td>
      <td class="num">${fmtDur(s.stats?.active_seconds)}</td>
      <td class="mono" style="font-size:10.5px">${dualCell(s.created_at)}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="7" style="color:var(--faint)">No sessions - Forward API unreachable; cached export carries schedules only.</td></tr>';
}

/* ---------------- instrumentation ---------------- */
function insRowHtml(r) {
  const gap = r.status === "gap";
  return `<div class="ins-row${gap ? " is-gap" : ""}"><span class="ins-field"><span class="k-label">${esc(fieldLabel(r.field))}</span><span class="k-raw mono">${esc(r.field)}</span></span><span><span class="prov ${r.status}">${r.status}</span></span><span class="ins-note">${esc(r.note)}</span></div>`;
}

function renderInstrumentation() {
  const ins = STATE.instrumentation;
  if (!ins) return;
  $("#ins-ring").innerHTML = ring(ins.completeness_avg, 64, 6);
  $("#ins-avg").textContent = Math.round(ins.completeness_avg * 100) + "%";
  $("#ins-cards-n").textContent = ins.cards_n;
  const c = ins.field_counts;
  $("#ins-counts").innerHTML =
    `<div class="ins-count journaled"><b>${c.journaled}</b><span>journaled</span></div>` +
    `<div class="ins-count derived"><b>${c.derived}</b><span>derived</span></div>` +
    `<div class="ins-count gap"><b>${c.gap}</b><span>gap</span></div>`;
  const fields = insView === "gaps" ? ins.fields.filter((r) => r.status === "gap") : ins.fields;
  $("#ins-rows").innerHTML = fields.map(insRowHtml).join("") ||
    '<p class="table-note" style="padding:6px 4px">No gap fields in the per-trade contract - every field is journaled or honestly derived.</p>';
  $("#ins-cross").innerHTML = ins.cross_cutting.map(insRowHtml).join("");
  document.querySelectorAll("#ins-toggle button").forEach((b) => b.classList.toggle("on", b.dataset.ins === insView));
}

/* ---------------- controls footer ---------------- */
function renderFooter() {
  const list = $("#divergence-list");
  if (list) {
    list.innerHTML = (STATE.divergences || []).map((d, i) =>
      `<div class="info-row"><span class="info-k">Gap ${i + 1}</span><span class="info-v">${esc(d)}</span></div>`).join("")
      || '<div class="info-row"><span class="info-v">No open gaps recorded.</span></div>';
  }
  const chain = $("#chain-row");
  if (chain) {
    chain.innerHTML = STATE.chain.ok
      ? `<span class="info-k">Journal integrity</span><span class="info-v">Chain verified - ${STATE.chain.count} events (plans, orders, halts, rejections - every journaled event, not just fills).</span>`
      : `<span class="info-k">Journal integrity</span><span class="info-v halt-note">CHAIN BROKEN - ${esc(STATE.chain.error || "verification failed")}</span>`;
  }
}

/* ---------------- overview extras ---------------- */
function renderOverview() {
  const a = STATE.approvals;
  const ov = $("#ov-approval");
  if (ov && a) {
    const active = a.auto_active === true, armed = a.mode === "armed";
    ov.className = "pill " + (active ? "live-pill live" : armed ? "kill armed" : "live-pill cached");
    ov.querySelector("span").textContent = active ? "Pre-approved · envelope armed" : armed ? "Armed · kill-switch" : "Manual · per-order";
    ov.title = hy(a.reason || "");
  }
  const kill = $("#ov-kill");
  if (kill) {
    const halted = STATE.halt.halted;
    kill.className = "brief-kill " + (halted ? "armed" : "clear");
    kill.innerHTML = `<span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "RELEASED"}</strong><span>${esc(STATE.halt.reason || (halted ? "" : "buys are allowed"))}</span>`;
  }
}

/* ---------------- render all ---------------- */
function safeRender(name, fn) {
  try { fn(); } catch (err) { console.error("[tyche] render " + name + " failed:", err); }
}
function renderAll() {
  if (!STATE) return;
  safeRender("accountBar", renderAccountBar);
  safeRender("desk", renderDesk);
  safeRender("scorecard", renderScorecard);
  safeRender("overview", renderOverview);
  safeRender("pipeline", renderPipeline);
  safeRender("expectancy", renderExpectancy);
  safeRender("kill", renderKill);
  safeRender("approval", renderApproval);
  safeRender("killControl", renderKillControl);
  safeRender("strategies", renderStrategies);
  safeRender("schedule", renderSchedule);
  safeRender("scout", renderScout);
  safeRender("gauges", renderGauges);
  safeRender("riskGuards", renderRiskGuards);
  safeRender("donut", renderDonut);
  safeRender("positions", renderPositions);
  safeRender("orders", renderOrders);
  safeRender("rejections", renderRejections);
  safeRender("equity", renderEquity);
  safeRender("instrumentation", renderInstrumentation);
  safeRender("footer", renderFooter);
  safeRender("operator", renderOperator);
  if (AUTO) {
    safeRender("calendar", renderCalendar);
    safeRender("automation", renderAutomation);
  }
  safeRender("countdowns", tickCountdowns);
}

/* ---------------- interactions ---------------- */
function setup() {
  setTheme(currentTheme());
  setText("#version-tag", "v" + VERSION);
  if (SNAPSHOT) {
    const banner = $("#snapshot-banner");
    banner.innerHTML = `<span class="snap-tag">read-only snapshot</span>` +
      `<span class="snap-built">built ${esc(dualTime(SNAPSHOT.built_at))}</span>` +
      `<span>Data is frozen at build time - the live desk refreshes from the journal and Forward API. Theme, filters, sorting and the drawer still work.</span>`;
    banner.hidden = false;
  }
  document.querySelectorAll(".theme-btn").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.themeSet)));
  document.querySelectorAll("#ins-toggle button").forEach((b) => b.addEventListener("click", () => { insView = b.dataset.ins; renderInstrumentation(); }));
  $("#refresh-btn").addEventListener("click", () => fetchAll(true));
  const adminJump = $("#admin-jump");
  if (adminJump) adminJump.addEventListener("click", () => {
    const pass = $("#operator-pass");
    if (pass && !pass.closest("[hidden]")) pass.focus();
    else showToast("Operator login is not configured on this desk", true);
  });
  const unlockBtn = $("#operator-unlock");
  if (unlockBtn) unlockBtn.addEventListener("click", unlockOperator);
  const passInput = $("#operator-pass");
  if (passInput) passInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); unlockOperator(); } });
  $("#version-btn").addEventListener("click", openChangelog);
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeDrawer(); return; }
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "t" || e.key === "T") { setTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]); }
    else if (e.key === "r" || e.key === "R") { fetchAll(true); }
    else if (e.key >= "1" && e.key <= "5") { showView(VIEWS[Number(e.key) - 1]); }
  });
  $("#pos-search").addEventListener("input", (e) => { posQuery = e.target.value.toLowerCase(); renderPositions(); });
  $("#rej-search").addEventListener("input", (e) => { rejQuery = e.target.value.toLowerCase(); renderRejections(); });
  $("#account-select").addEventListener("change", (e) => { deskAcct = e.target.value; renderAll(); });
  document.querySelectorAll(".pos-tbl th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      posSort = posSort.key === k ? { key: k, dir: -posSort.dir } : { key: k, dir: k === "symbol" ? 1 : -1 };
      renderPositions();
    }));

  setInterval(() => {
    const now = new Date().toISOString();
    $("#clock").textContent = `SGT ${sgtTime(now)} · ET ${etTime(now)}`;
  }, 1000);
  setInterval(tickCountdowns, 1000);
  setInterval(() => { if (STATE) setText("#updated-stamp", stampText()); }, 30000);

  document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", () => showView(n.dataset.view)));
  let savedView = "overview";
  try { savedView = localStorage.getItem("tyche-view") || "overview"; } catch (e) {}
  // A #view link wins over the last-used view, so a bookmark or a screenshot of one panel stays reproducible.
  const fromHash = (location.hash || "").replace(/^#\/?/, "");
  showView(VIEWS.includes(fromHash) ? fromHash : savedView);
  renderOperator();
  fetchOperatorStatus();
}

setup();
fetchAll();