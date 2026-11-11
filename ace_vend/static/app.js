/* ACE-Vend dashboard — vanilla JS, no build step, no CDN. */

const $ = (id) => document.getElementById(id);

const EMOJI = {
  coke: "🥤",
  water: "💧",
  chips: "🍟",
  candy: "🍫",
  coffee: "☕",
};

let autoTimer = null;
let latest = null;

/* ------------------------------------------------------------- utilities */

function money(value) {
  const n = Number(value) || 0;
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

function pct(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`);
  return response.json();
}

/* ---------------------------------------------------------------- render */

function render(state) {
  latest = state;
  const env = state.environment;
  const metrics = state.metrics;

  $("step-badge").textContent = `step ${env.step}`;
  $("backend-badge").textContent = metrics.backend || "offline";
  $("mode-select").value = state.mode;

  $("stat-profit").textContent = money(env.profit);
  $("stat-revenue").textContent = `revenue ${money(env.revenue)} · spend ${money(env.spend)}`;
  $("stat-cash").textContent = money(env.cash);
  $("stat-units").textContent = `${env.units_sold} units sold · ${env.stockouts} stockouts`;
  $("stat-service").textContent = pct(env.service_rate);
  $("stat-service-sub").textContent = `${env.fulfilled} / ${env.requests} requests`;
  $("stat-guard").textContent = state.guard.blocked;
  $("stat-guard-sub").textContent = `${state.guard.checked} actions checked`;

  renderSlots(env.products);
  renderChart(env.history);
  renderDecision(state.records[state.records.length - 1]);
  renderLog(state.records);
  renderPlaybook(state.playbook);
  renderBreakdown(state.guard.by_category);

  $("stock-pill").textContent = `${env.products.reduce((sum, p) => sum + p.stock, 0)} units`;
}

function renderSlots(products) {
  const root = $("slots");
  root.replaceChildren();

  for (const product of products) {
    const fill = product.capacity ? product.stock / product.capacity : 0;
    const row = el("div", "slot");
    if (product.stock === 0) row.classList.add("empty");
    else if (fill <= 0.34) row.classList.add("low");

    row.append(el("div", "slot-emoji", EMOJI[product.sku] || "📦"));

    const info = el("div");
    info.append(el("div", "slot-name", product.name));
    info.append(
      el(
        "div",
        "slot-meta",
        `${money(product.price)} · cost ${money(product.cost)}`
      )
    );
    row.append(info);
    row.append(el("div", "slot-meta", `${product.stock}/${product.capacity}`));

    const bar = el("div", "bar");
    const inner = el("span");
    inner.style.width = `${Math.max(2, Math.round(fill * 100))}%`;
    bar.append(inner);
    row.append(bar);

    root.append(row);
  }
}

function renderChart(history) {
  const line = $("chart-line");
  if (!history || history.length < 2) {
    line.setAttribute("points", "");
    return;
  }

  const profits = history.map((h) => h.profit);
  const min = Math.min(0, ...profits);
  const max = Math.max(1, ...profits);
  const span = max - min || 1;

  const points = profits.map((profit, index) => {
    const x = (index / (profits.length - 1)) * 300;
    const y = 88 - ((profit - min) / span) * 84;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  line.setAttribute("points", points.join(" "));
}

function renderDecision(record) {
  if (!record) {
    $("dec-request").textContent = "waiting for the first step…";
    $("dec-action").textContent = "—";
    $("dec-reasoning").textContent = "";
    $("dec-guard").textContent = "—";
    $("dec-guard").className = "mono";
    $("dec-violations").replaceChildren();
    return;
  }

  const decision = record.decision || record.proposed;
  const args = decision && decision.args ? decision.args : {};
  const argText = Object.entries(args)
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");

  $("dec-request").textContent = record.request.text;
  $("dec-action").textContent = decision
    ? `${decision.action}(${argText})`
    : "blocked";
  $("dec-reasoning").textContent = decision ? decision.reasoning || "" : "";

  const guard = $("dec-guard");
  guard.textContent = record.guard.allowed
    ? "allowed"
    : `blocked (${record.guard.layer})`;
  guard.className = `mono ${record.guard.allowed ? "allowed" : "blocked"}`;

  const list = $("dec-violations");
  list.replaceChildren();
  for (const violation of record.guard.violations || []) {
    list.append(el("li", null, violation));
  }

  const reward = $("reward-pill");
  reward.textContent = `${record.reward >= 0 ? "+" : ""}${money(record.reward)}`;
  reward.style.color = record.reward < 0 ? "var(--bad)" : "var(--ok)";
}

function renderLog(records) {
  const list = $("log");
  list.replaceChildren();

  const recent = (records || []).slice(-14).reverse();
  for (const record of recent) {
    const item = el("li", record.outcome.event);
    item.append(el("span", "log-step", `#${record.step}`));
    item.append(el("span", null, record.outcome.message));
    const reward = el(
      "span",
      `log-reward ${record.reward < 0 ? "neg" : ""}`,
      money(record.reward)
    );
    item.append(reward);
    list.append(item);
  }
}

function renderPlaybook(playbook) {
  const list = $("pb-list");
  list.replaceChildren();

  const bullets = playbook.bullets || [];
  const stats = playbook.stats || {};

  $("pb-pill").textContent = `${bullets.length} bullets`;
  $("pb-meta").textContent = bullets.length
    ? `${stats.tokens} tokens · ${stats.merges} merges · ${stats.evictions} evictions`
    : "no lessons learned yet — run a few steps";

  if (!bullets.length) {
    list.append(el("div", "pb-empty", "The Reflector has not written anything yet."));
    return;
  }

  const ordered = [...bullets].sort((a, b) => b.score - a.score);
  for (const bullet of ordered) {
    const item = el("div", "pb-item");

    const top = el("div", "pb-top");
    top.append(el("span", "pb-id", bullet.id));
    top.append(el("span", "pb-section", bullet.section));

    const scores = el("div", "pb-scores");
    scores.append(el("span", "score pos", `+${bullet.helpful}`));
    scores.append(el("span", "score neg", `-${bullet.harmful}`));
    top.append(scores);

    item.append(top);
    item.append(el("div", "pb-text", bullet.text));
    list.append(item);
  }
}

function renderBreakdown(categories) {
  const list = $("guard-breakdown");
  list.replaceChildren();

  const entries = Object.entries(categories || {});
  if (!entries.length) {
    list.append(el("li", null, "nothing blocked yet"));
    return;
  }

  entries.sort((a, b) => b[1] - a[1]);
  for (const [key, value] of entries) {
    const item = el("li");
    item.append(el("span", null, key));
    item.append(el("span", "count", value));
    list.append(item);
  }
}

/* -------------------------------------------------------------- controls */

async function step() {
  try {
    const result = await post("/api/step", {});
    render(result.state);
  } catch (error) {
    setStatus(`step failed: ${error.message}`, "offline");
  }
}

function toggleAuto() {
  const button = $("btn-auto");
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
    button.textContent = "Auto-run";
    button.classList.remove("primary");
    return;
  }
  button.textContent = "Stop";
  button.classList.add("primary");
  autoTimer = setInterval(step, 850);
}

async function reset() {
  const seed = latest ? latest.seed : 42;
  const state = await post("/api/reset", { seed });
  render(state);
}

async function changeMode(event) {
  const mode = event.target.value;
  const state = await post("/api/mode", { mode });
  render(state);
}

async function sendCustomer() {
  const input = $("customer-input");
  const text = input.value.trim();
  if (!text) return;
  const result = await post("/api/step", { customer: text });
  render(result.state);
  input.value = "";
}

async function runExperiment() {
  const output = $("experiment-output");
  const button = $("btn-experiment");
  output.classList.remove("hidden");
  output.textContent = "running 3 conditions…";
  button.disabled = true;

  try {
    const result = await post("/api/experiment", {
      steps: 60,
      seed: latest ? latest.seed : 42,
    });
    output.textContent = result.table;
  } catch (error) {
    output.textContent = `experiment failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function setStatus(text, kind) {
  const node = $("footer-status");
  node.textContent = text;
  node.className = kind || "";
}

/* ------------------------------------------------------------- live feed */

function connect() {
  if (!window.EventSource) {
    startPolling();
    return;
  }

  const source = new EventSource("/api/stream");

  source.addEventListener("state", (event) => {
    try {
      render(JSON.parse(event.data));
      setStatus("live", "live");
    } catch (error) {
      setStatus(`parse error: ${error.message}`, "offline");
    }
  });

  source.addEventListener("open", () => setStatus("live", "live"));

  source.addEventListener("error", () => {
    setStatus("reconnecting…", "offline");
    // EventSource retries on its own; polling is the fallback for proxies
    // that strip text/event-stream.
    startPolling();
  });
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch("/api/state");
      render(await response.json());
    } catch (error) {
      setStatus("disconnected", "offline");
    }
  }, 2000);
}

/* ------------------------------------------------------------------ init */

$("btn-step").addEventListener("click", step);
$("btn-auto").addEventListener("click", toggleAuto);
$("btn-reset").addEventListener("click", reset);
$("btn-send").addEventListener("click", sendCustomer);
$("btn-experiment").addEventListener("click", runExperiment);
$("mode-select").addEventListener("change", changeMode);

$("customer-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") sendCustomer();
});

fetch("/api/state")
  .then((response) => response.json())
  .then(render)
  .catch(() => setStatus("cannot reach server", "offline"));

connect();
