/* Tyche desk dashboard - renders journal-derived state + live Forward automation. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[—–]/g, "-").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hy = (s) => String(s ?? "").replace(/[—–]/g, "-");

const VERSION = "0.2.1";
const CHANGELOG = [
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
const SNAPSHOT = window.TYCHE_SNAPSHOT || null;
const LIVE = window.TYCHE_LIVE || null;
let posSort = { key: "market_value", dir: -1 };
let posQuery = "";
let rejKind = "all";
let rejQuery = "";
let deskAcct = null;
let autoErrorShown = false;
let insView = "all";

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
const VIEW_LABEL = { overview: "Overview", strategy: "Strategy", risk: "Risk & Execution", automation: "Automation", controls: "Controls" };
function showView(name) {
  if (!VIEWS.includes(name)) name = "overview";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  document.querySelectorAll(".nav-item").forEach((n) => {
    const on = n.dataset.view === name;
    n.classList.toggle("is-active", on);
    n.setAttribute("aria-current", on ? "page" : "false");
  });
  const crumb = $("#crumb-view");
  if (crumb) crumb.textContent = VIEW_LABEL[name];
  try { localStorage.setItem("tyche-view", name); } catch (e) {}
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
  { key: "thesis", name: "Thesis", sub: "hypothesis & theme", empty: "No per-trade thesis cards yet - the playbook reference is a P1 instrumentation gap. The regime hypothesis lives in plan notes." },
  { key: "multifactor", name: "Multi-factor", sub: "macro · technical · flow", empty: "Technicals are in plan signals. Macro, sentiment & flow and seasonality briefs arrive with the researcher child." },
  { key: "outlook", name: "Outlook", sub: "bullish / bearish / range", empty: "Market-level regime only today; per-setup outlook + conviction and the act/wait gate are pending." },
  { key: "vehicle", name: "Vehicle & Edge", sub: "ETFs · stocks · options", empty: "" },
  { key: "edge", name: "Edge / Expectancy", sub: "expected vs realized", empty: "Pre-trade expected edge is not instrumented yet; realized edge renders here as trades close." },
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
  const snaps = STATE.snapshots && Object.keys(STATE.snapshots).length ? STATE.snapshots : null;
  if (snaps) return Object.keys(snaps);
  if (STATE.snapshot) return [STATE.snapshot.account];
  return Object.keys(STATE.nav_marks || {});
}
function currentSnap() {
  if (STATE.snapshots && deskAcct && STATE.snapshots[deskAcct]) return STATE.snapshots[deskAcct];
  return STATE.snapshot;
}
function acctLabel(a) {
  const primary = STATE.feed?.primary_account;
  const kind = a === primary ? "Challenge" : a.startsWith("SIM-") ? "Demo" : "Paper";
  return `${a} · ${kind}`;
}
function renderAccountBar() {
  const sel = $("#account-select");
  const accts = accountList();
  if (!accts.includes(deskAcct)) deskAcct = accts[0] || null;
  sel.innerHTML = accts.map((a) => `<option value="${esc(a)}"${a === deskAcct ? " selected" : ""}>${esc(acctLabel(a))}</option>`).join("");
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
  if (STATE) {
    renderAll();
    setText("#updated-stamp", (SNAPSHOT ? "Snapshot built " : "Updated ") + dualTime(STATE.generated_at));
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
function renderDesk() {
  const snap = currentSnap();
  const marks = STATE.nav_marks[deskAcct] || [];
  $("#nav-acct").textContent = snap ? `· ${snap.account} · ${snap.env}` : "";
  $("#nav-value").textContent = snap ? money(snap.nav) : "-";
  const deltaEl = $("#nav-delta");
  if (marks.length >= 2) {
    const d = marks[marks.length - 1].nav - marks[0].nav;
    deltaEl.textContent = `${signedMoney(d)} (${signedPct(d / marks[0].nav, 3)}) vs first mark`;
    deltaEl.className = "desk-delta mono " + (d >= 0 ? "up" : "down");
  } else { deltaEl.textContent = ""; }
  const last = marks[marks.length - 1];
  $("#nav-src").textContent = last ? `Latest mark: ${last.source} · ${dualTime(last.ts)} · n=${marks.length}` : "";
  const broker = $("#nav-broker");
  if (broker) {
    broker.textContent = snap && snap.broker_total_asset != null
      ? `Broker total assets ${money(snap.broker_total_asset)} - includes ${money(snap.order_hold)} held for resting orders (what the Moomoo app shows)`
      : "";
  }
  $("#cash-value").textContent = snap ? money(snap.cash) : "-";
  $("#cash-weight").textContent = snap ? pct(snap.cash_weight) + " of NAV · min " + pct(STATE.risk.min_cash_weight, 0) : "-";
  $("#gross-value").textContent = snap ? pct(snap.gross_weight) : "-";
  $("#gross-cap").textContent = "Cap " + pct(STATE.risk.max_gross_exposure, 0);
  const checks = STATE.latest_plan?.regime_checks || {};
  const labels = { equity_trend: "Equity trend", credit_trend: "Credit trend", golden_cross: "Golden cross", vol_calm: "Vol calm" };
  $("#regime-checks").innerHTML = Object.entries(checks).map(([k, v]) =>
    `<span class="check-dot ${v ? "on" : "off"}" data-label="${esc(labels[k] || k)}: ${v ? "pass" : "fail"}"></span>`).join("");
  const plan = STATE.latest_plan;
  $("#vol-note").textContent = plan ? `Portfolio vol ${pct(plan.portfolio_vol)} · scale ${plan.vol_scale.toFixed(2)}` : "-";
  const start = Date.UTC(2026, 10, 17), end = Date.UTC(2026, 10, 28);
  const now = Date.now();
  const frac = Math.min(1, Math.max(0, (now - start) / (end - start)));
  $("#window-fill").style.width = (frac * 100).toFixed(1) + "%";
  const day = Math.min(12, Math.max(1, Math.floor((now - start) / 86400000) + 1));
  $("#window-days").textContent = `Day ${day} of 12 · ${dateLabel(new Date(now).toISOString())} · closes Nov 28`;
}

/* ---------------- pipeline ---------------- */
function trackHtml(card, nowIdx = -1) {
  return `<div class="track">` + STAGES.map((s, i) => {
    const st = card.stages[s.key]?.state || "gap";
    return `<i class="${st}${i === nowIdx ? " now" : ""}" title="${esc(s.name)}: ${st}"></i>`;
  }).join("") + `</div>`;
}

function cardHtml(card, nowIdx = -1) {
  const status = card.status;
  const label = STATUS_LABEL[status] || status;
  const trip = card.round_trip != null ? `<span class="round-trip">${signedMoney(card.round_trip)} round-trip</span>` : "";
  const dry = card.dry_run ? `<span class="chip dry">Dry run</span>` : "";
  return `<article class="tcard side-${card.side}" tabindex="0" role="button" data-card="${esc(card.id)}" aria-label="Open ${esc(sym(card.symbol))} trade detail">
    <div class="tcard-top">
      <span class="sym">${esc(sym(card.symbol))}</span>
      <span class="side ${card.side}">${card.side.toUpperCase()}</span>
      ${dry}
      ${card.contract ? ring(card.contract.completeness, 26, 3) : ""}
      <span class="acct-tag">${esc(card.account)}</span>
    </div>
    <div class="tcard-qty">${card.quantity} @ ${money(card.limit_price)} · ${money(card.notional, 0)}</div>
    ${trackHtml(card, nowIdx)}
    <div class="tcard-foot">
      <span class="chip status-${status}">${esc(label)}</span>
      ${trip || `<span class="stage-now">${card.band === "execution" ? "execution band" : "stage 4 · vehicle & edge"}</span>`}
    </div>
  </article>`;
}

function renderPipeline() {
  const cards = STATE.cards || [];
  const grid = $("#stage-grid");
  grid.innerHTML = STAGES.map((stage, i) => {
    const inStage = cards.filter((c) => c.band === "stage" + (i + 1));
    const body = inStage.length
      ? inStage.map((c) => cardHtml(c, i)).join("")
      : `<div class="stage-empty">${esc(stage.empty)}<br><span class="chip gap-chip">Instrumentation pending</span></div>`;
    return `<div class="stage-col">
      <div class="stage-col-head"><span class="stage-num">${i + 1}</span><div><strong>${esc(stage.name)}</strong><span>${esc(stage.sub)}</span></div></div>
      ${body}
    </div>`;
  }).join("");
  const band = cards.filter((c) => c.band === "execution")
    .sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9));
  $("#band-cards").innerHTML = band.map((c) => cardHtml(c)).join("");
  grid.querySelectorAll(".tcard").forEach(bindCard);
  $("#band-cards").querySelectorAll(".tcard").forEach(bindCard);
}

function bindCard(el) {
  el.addEventListener("click", () => openDrawer(el.dataset.card));
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDrawer(el.dataset.card); } });
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
  html += `<p class="table-note" style="padding:0">Provenance: <b>journaled</b> = carried by the plan/journal · <b>derived</b> = computed deterministically from journaled inputs + pinned config · <b>gap</b> = not instrumented yet. Nothing is fabricated - the journal is the only truth.</p>`;
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
  const events = [...(STATE.halt_timeline || [])];
  const sell = (STATE.orders || []).find((o) => o.side === "sell" && o.order_id);
  if (sell) {
    events.push({ ts: sell.requested_ts, type: "order.requested", payload: { symbol: sell.symbol, quantity: sell.quantity } });
    if (sell.fill_price != null) events.push({ ts: sell.submitted_ts, type: "order.filled", payload: { symbol: sell.symbol, quantity: sell.quantity, price: sell.fill_price } });
  }
  events.sort((a, b) => a.ts.localeCompare(b.ts));
  const items = events.map((ev) => {
    const cls = ev.type === "halt.engaged" ? "ev-engaged" : ev.type === "halt.skip" ? "ev-skip" : ev.type === "halt.released" ? "ev-released" : "";
    let text;
    if (ev.type === "halt.skip") text = `withheld ${sym(ev.payload.symbol)} ${ev.payload.quantity} - ${esc(ev.payload.reason)}`;
    else if (ev.type === "halt.engaged") text = `halt engaged - ${esc(ev.payload.reason)}`;
    else if (ev.type === "halt.released") text = `halt released - ${esc(ev.payload.reason)}`;
    else if (ev.type === "order.filled") text = `de-risk sell filled ${ev.payload.quantity} ${sym(ev.payload.symbol)} @ ${money(ev.payload.price)}`;
    else text = `de-risk sell requested ${sym(ev.payload.symbol)} ${ev.payload.quantity}`;
    return `<li class="${cls}"><span class="mono">${etHHMM(ev.ts)} ET</span> - ${text}</li>`;
  }).join("");
  $("#kill-card").innerHTML = `
    <span class="card-kicker">Kill-switch</span>
    <div class="kill-state ${halted ? "armed" : "clear"}"><span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "CLEAR"}</strong></div>
    <div class="kill-meta">${esc(STATE.halt.reason || "")} · ${dualTime(STATE.halt.ts)}</div>
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
  const canControl = !LIVE && !SNAPSHOT;
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
      : "Read-only feed - trading mode is selectable on the local desk console."}</p>`;

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

async function disarmAuto() {
  if (!confirm("Switch to Manual and propagate to the cloud desk?\n\nOrders revert to per-order confirmation. This commits + pushes the envelope removal. Reversible - re-arm any time with Auto or Pre-approve.")) return;
  try {
    const j = await postControl("/api/approvals/disarm");
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
    const j = await postControl("/api/approvals/arm", { reuse_last: true });
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
    const j = await postControl("/api/approvals/arm", { max_orders: maxOrders, max_notional: maxNotional, note: $("#env-note").value, orders: lines });
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
  const canControl = !LIVE && !SNAPSHOT;
  wrap.innerHTML = `
    <div class="kill-state ${halted ? "armed" : "clear"}"><span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "CLEAR"}</strong></div>
    <div class="kill-meta">${esc(STATE.halt.reason || "")} · ${dualTime(STATE.halt.ts)}</div>
    ${canControl ? `
      ${halted ? "" : '<input type="text" id="halt-reason" class="search halt-reason" maxlength="200" placeholder="Reason for halting (journaled)" aria-label="Halt reason">'}
      <button class="btn ${halted ? "btn-primary" : "disarm-btn"} kill-btn" id="kill-toggle">${halted ? "Release kill-switch" : "Engage kill-switch"}</button>
      <p class="table-note" style="padding:10px 0 0">${halted ? "Release resumes buys after your review. The transition is journaled." : "Engaging blocks new buys immediately; de-risking sells still pass. The transition is journaled."}</p>
    ` : '<p class="table-note" style="padding:10px 0 0">Read-only feed - the kill-switch is operated from the local desk console or <code>tyche halt</code> / <code>tyche resume</code>.</p>'}`;
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
    await postControl("/api/halt", { halted, reason });
    showToast(halted ? "Kill-switch ARMED - buys blocked, transition journaled" : "Kill-switch released - buys permitted, transition journaled");
    await fetchAll(true);
  } catch (e) {
    showToast("Kill-switch change failed: " + e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = halted ? "Engage kill-switch" : "Release kill-switch"; }
  }
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
    <span class="card-kicker" style="margin-top:6px">Drawdown ladder · current DD ${pct(dd, 2)} <em>(n=${marks.length} marks)</em></span>
    <div class="ladder">
      ${ddRung("soft alert", risk.soft_drawdown_pct)}
      ${ddRung("hard halt", risk.hard_drawdown_pct)}
      ${ddRung("daily loss block", risk.daily_loss_limit_pct)}
    </div>`;
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
    <svg viewBox="0 0 140 140" width="150" height="150" role="img" aria-label="Allocation by market value: ${esc(summary)}">
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
  const orders = (STATE.orders || []).filter((o) => !deskAcct || o.account === deskAcct);
  const working = orders.filter((o) => ["requested", "submitted"].includes(o.status)).length;
  const el = $("#working-orders");
  el.textContent = working === 0 ? "0 working orders - all terminal" : `${working} working`;
  el.className = "chip " + (working === 0 ? "ok-chip" : "provisional");
  $("#order-rows").innerHTML = orders.map((o) => `<tr>
    <td class="mono">${esc(o.order_id || "-")}</td>
    <td class="mono" style="font-size:10.5px;color:var(--muted)">${esc(o.remark || "-")}</td>
    <td class="mono acct-cell">${esc(o.account || "-")}</td>
    <td><span class="side ${o.side}">${o.side.toUpperCase()}</span></td>
    <td class="num">${o.quantity}</td>
    <td class="num">${o.limit_price != null ? money(o.limit_price) : "market"}</td>
    <td><span class="chip status-${o.status}">${esc(STATUS_LABEL[o.status] || o.status)}</span></td>
    <td class="num">${o.fill_price != null ? money(o.fill_price) : "-"}</td>
    <td class="mono" style="font-size:10.5px"><div>${etHHMM(o.requested_ts)} → ${o.submitted_ts ? etHHMM(o.submitted_ts) : "-"} ET</div><div class="dim">${sgtHHMM(o.requested_ts)} → ${o.submitted_ts ? sgtHHMM(o.submitted_ts) : "-"} SGT</div></td>
  </tr>`).join("");
}

function renderRejections() {
  const all = STATE.rejections || [];
  const kinds = ["all", "risk-kernel", "halt", "broker"];
  $("#rej-filters").innerHTML = kinds.map((k) => {
    const n = k === "all" ? all.length : all.filter((r) => r.kind === k).length;
    const label = k === "all" ? "All" : k === "risk-kernel" ? "Risk kernel" : k === "halt" ? "Halt" : "Broker";
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
    <td><span class="kind ${r.kind}">${r.kind === "risk-kernel" ? "Risk kernel" : r.kind === "halt" ? "Halt" : "Broker"}</span></td>
    <td><span class="rule-code" title="${esc(r.rule)}">${esc(ruleLabel(r.rule))}</span></td>
    <td><strong>${esc(sym(r.symbol))}</strong></td>
    <td><span class="side ${r.side}">${r.side.toUpperCase()}</span></td>
    <td class="num">${r.quantity.toLocaleString()}</td>
    <td style="color:var(--muted)">${esc(r.detail)}</td>
  </tr>`).join("");
}

/* ---------------- equity ---------------- */
function renderEquity() {
  const marks = STATE.nav_marks[deskAcct] || [];
  const stats = $("#equity-stats");
  if (!marks.length) {
    stats.innerHTML = "";
    $("#equity-chart").innerHTML = '<p class="table-note">No NAV marks for this account yet.</p>';
    $("#returns-bars").innerHTML = "";
    return;
  }
  const first = marks[0], last = marks[marks.length - 1];
  const delta = last.nav - first.nav;
  let peak = -Infinity, dd = 0;
  for (const m of marks) { peak = Math.max(peak, m.nav); dd = Math.max(dd, (peak - m.nav) / peak); }
  const nMarks = marks.reduce((a, m) => a + (m.count || 1), 0);
  const nextFriday = (() => {
    const d = new Date();
    const add = (5 - d.getUTCDay() + 7) % 7 || 7;
    return new Date(d.getTime() + add * 86400000);
  })();
  stats.innerHTML = `
    <div class="estat"><span class="desk-label">Latest NAV</span><b>${money(last.nav)}</b></div>
    <div class="estat"><span class="desk-label">Δ vs first mark</span><b class="${plClass(delta)}">${signedMoney(delta)} · ${signedPct(delta / first.nav, 3)}</b></div>
    <div class="estat"><span class="desk-label">Max drawdown</span><b>${pct(dd, 2)}</b></div>
    <div class="estat"><span class="desk-label">Marks</span><b>${nMarks}</b> <span class="chip provisional">provisional</span></div>
    <div class="estat"><span class="desk-label">Next Friday mark</span><b>${dateLabel(nextFriday.toISOString())}</b></div>`;

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
      <text x="${L - 10}" y="${yy + 4}" text-anchor="end" style="fill:var(--faint)" font-size="11" font-family="IBM Plex Mono, monospace">$${Math.round(v).toLocaleString()}</text>`;
  }
  const pts = marks.map((m, i) => [x(i), y(m.nav)]);
  const linePath = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const areaPath = linePath + ` L ${pts[pts.length - 1][0].toFixed(1)} ${H - B} L ${pts[0][0].toFixed(1)} ${H - B} Z`;
  const dots = marks.map((m, i) => {
    const [cx, cy] = pts[i];
    const above = i % 2 === 0 || marks.length === 1;
    return `<circle cx="${cx}" cy="${cy}" r="6" style="fill:var(--bg1);stroke:var(--green)" stroke-width="2.5">
        <title>${esc(m.source)} · ${dualTime(m.ts)} · ${money(m.nav)}</title></circle>
      <text x="${cx}" y="${above ? cy - 16 : cy + 26}" text-anchor="middle" style="fill:var(--ink)" font-size="12.5" font-weight="600" font-family="IBM Plex Mono, monospace">${money(m.nav, 0)}</text>
      <text x="${cx}" y="${H - B + 18}" text-anchor="middle" style="fill:var(--muted)" font-size="10.5">${esc(m.source)}${m.count > 1 ? " ×" + m.count : ""}</text>
      <text x="${cx}" y="${H - B + 32}" text-anchor="middle" style="fill:var(--faint)" font-size="9.5" font-family="IBM Plex Mono, monospace">${dateLabel(m.ts)} ${etHHMM(m.ts)} ET</text>`;
  }).join("");
  $("#equity-chart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="NAV marks chart">
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
    : '<p class="table-note" style="padding:0">Single mark - no inter-mark return yet. The fee-net daily series arrives with the EOD performance generator.</p>';
}

/* ---------------- automation ---------------- */
function nextRunInfo() {
  const now = Date.now();
  let best = null;
  for (const s of AUTO?.schedules || []) {
    for (const ts of s.trigger_policy?.upcoming_runs_at || []) {
      const t = Date.parse(ts);
      if (t > now && (!best || t < best.t)) best = { t, name: s.name };
    }
  }
  if (!best && AUTO?.calendar?.next_run) {
    const t = Date.parse(AUTO.calendar.next_run.utc);
    if (t > now) best = { t, name: AUTO.calendar.next_run.name };
  }
  return best;
}

function tickCountdowns() {
  const info = nextRunInfo();
  const el = $("#next-run");
  if (info) {
    el.textContent = fmtCountdown(info.t - Date.now());
    const iso = new Date(info.t).toISOString();
    $("#next-run-name").textContent = `${info.name} · ${etHHMM(iso)} ET · ${sgtHHMM(iso)} SGT`;
  } else {
    el.textContent = "-";
    $("#next-run-name").textContent = "No upcoming runs";
  }
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
const ACTIVITY_LABEL = { plan: "plan", active: "active", monitor: "monitor", reconcile: "reconcile", noop: "no-op" };
const EVENT_HUE = { fomc: "var(--red)", macro: "var(--amber)", earnings: "var(--cyan)" };
const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };

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
  gate.querySelector("span").textContent = cal.run ? "RUN" : "SKIP";
  const pm = PHASE_META[cal.phase] || PHASE_META.closed;
  const phasePill = $("#cal-phase");
  phasePill.textContent = pm.name;
  phasePill.style.setProperty("--seg-hue", pm.hue);
  $("#cal-reason").textContent = hy(cal.reason) + (cal.strategy?.event_caution ? " · event caution - order count halved" : "");

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
  $("#cal-cron-note").textContent = "One hourly cron (08:05-17:05 ET at :05 = 21:05-06:05 SGT) fires only on computed NYSE trading days - weekends and holidays excluded by construction. The evaluate() gate routes every run by live session phase (plan / active / monitor / reconcile), half-day aware and DST-safe; a misfired cron still skips. SGT (+1d) means the run lands after midnight in Singapore.";

  const wl = cal.watchlist;
  const wlWrap = $("#cal-watchlist-wrap");
  if (wlWrap) {
    wlWrap.hidden = !wl;
    if (wl) {
      $("#cal-watchlist-state").textContent = `${wl.stale ? "STALE" : "FRESH"} · as of ${wl.as_of} · ${wl.active_count} active`;
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
  const scheds = [...(AUTO.schedules || [])].sort((a, b) => {
    const na = (a.trigger_policy?.upcoming_runs_at || ["9999"])[0];
    const nb = (b.trigger_policy?.upcoming_runs_at || ["9999"])[0];
    return na.localeCompare(nb);
  });
  $("#sched-grid").innerHTML = scheds.map((s) => {
    const next = (s.trigger_policy?.upcoming_runs_at || [])[0];
    const nextT = next ? Date.parse(next) : null;
    return `<div class="card sched-card">
      <div class="sched-name"><span class="sched-status${s.status === "active" ? "" : " paused"}"></span>${esc(s.name)}</div>
      <p class="sched-desc">${esc(s.description || "")}</p>
      <span class="sched-cron mono">${esc(s.trigger_policy?.expression || "-")} · ${esc(s.trigger_policy?.timezone || "UTC")}</span>
      <div class="sched-next">${nextT && nextT > Date.now() ? `Next run <b data-countdown="${nextT}">${fmtCountdown(nextT - Date.now())}</b> · ${dateLabel(next)} ${etHHMM(next)} ET · ${sgtHHMM(next)} SGT` : "No upcoming runs in the cached window - refresh for live Forward data"}</div>
      <div class="sched-pin">initial_events v${esc(s.initial_events_version ?? "?")} pinned · ${esc(s.status)} · ${esc((s.template_id || "").slice(0, 13))}…</div>
    </div>`;
  }).join("");
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
  $("#divergence-list").innerHTML = STATE.divergences.map((d) => `<li>${esc(d)}</li>`).join("");
  const chain = $("#chain-row");
  if (chain) {
    chain.innerHTML = STATE.chain.ok
      ? `<strong>Journal integrity:</strong> chain verified - ${STATE.chain.count} events (plans, orders, halts, rejections - every journaled event, not just fills)`
      : `<strong>Journal integrity:</strong> <span class="halt-note">CHAIN BROKEN - ${esc(STATE.chain.error || "verification failed")}</span>`;
  }
}

/* ---------------- overview extras ---------------- */
function renderOverview() {
  const feed = STATE.feed;
  const fn = $("#feed-note");
  if (fn) {
    fn.innerHTML = feed && feed.primary_account
      ? `Primary feed: <strong>${esc(feed.primary_account)}</strong> · ${esc(feed.source)}${feed.run ? ` · run ${esc(feed.run)}` : ""} · ${feed.cloud_runs || 0} cloud run${feed.cloud_runs === 1 ? "" : "s"} synced`
      : "";
  }
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
    kill.innerHTML = `<span class="kill-lamp ${halted ? "armed" : "clear"}"></span><strong>${halted ? "ARMED" : "CLEAR"}</strong><span>${esc(STATE.halt.reason || (halted ? "" : "no active halt"))}</span>`;
  }
  const scheds = (AUTO && AUTO.schedules) || [];
  const activeScheds = scheds.filter((s) => s.status === "active").length;
  const sessions = (AUTO && AUTO.sessions) || [];
  const credits = sessions.reduce((x, s) => x + (s.usage?.total_credits || 0), 0);
  setText("#ov-sched-count", scheds.length ? `${activeScheds}/${scheds.length}` : "-");
  setText("#ov-sessions", sessions.length ? String(sessions.length) : "-");
  setText("#ov-credits", sessions.length ? credits.toFixed(1) : "-");
  setText("#ov-chain", STATE.chain.ok ? `${STATE.chain.count} ✓` : "BROKEN");
}

/* ---------------- render all ---------------- */
function safeRender(name, fn) {
  try { fn(); } catch (err) { console.error("[tyche] render " + name + " failed:", err); }
}
function renderAll() {
  if (!STATE) return;
  safeRender("accountBar", renderAccountBar);
  safeRender("desk", renderDesk);
  safeRender("overview", renderOverview);
  safeRender("pipeline", renderPipeline);
  safeRender("expectancy", renderExpectancy);
  safeRender("kill", renderKill);
  safeRender("approval", renderApproval);
  safeRender("killControl", renderKillControl);
  safeRender("gauges", renderGauges);
  safeRender("donut", renderDonut);
  safeRender("positions", renderPositions);
  safeRender("orders", renderOrders);
  safeRender("rejections", renderRejections);
  safeRender("equity", renderEquity);
  safeRender("instrumentation", renderInstrumentation);
  safeRender("footer", renderFooter);
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
  $("#controls-refresh").addEventListener("click", () => fetchAll(true));
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

  document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", () => showView(n.dataset.view)));
  let savedView = "overview";
  try { savedView = localStorage.getItem("tyche-view") || "overview"; } catch (e) {}
  showView(savedView);
}

setup();
fetchAll();