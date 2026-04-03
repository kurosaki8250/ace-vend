// frontend/static/script.js — ACE-Vend UI

const MAX_FEED_CARDS = 50;
const MAX_INVENTORY = 10; // assumed max for bar scaling

let autoRunTimer = null;
let totalHallucinations = 0;

// ── SSE ─────────────────────────────────────────────────────────────────────

const es = new EventSource("/stream");
es.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "step") handleStepEvent(msg);
  else if (msg.type === "reset") handleReset();
};
es.onerror = () => console.warn("SSE connection dropped; will reconnect.");

// ── Initial state load ───────────────────────────────────────────────────────

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  renderEnvState(data.env);
  renderPlaybook(data.playbook);
  document.getElementById("bullet-count").textContent = data.playbook_count;
  totalHallucinations = data.total_hallucinations;
  document.getElementById("hallucination-count").textContent = totalHallucinations;
}
loadState();

// ── Event handlers ───────────────────────────────────────────────────────────

function handleStepEvent(event) {
  renderEnvState(event.state);
  document.getElementById("step-counter").textContent = event.step;
  document.getElementById("bullet-count").textContent = event.playbook_count;
  if (event.hallucination) {
    totalHallucinations++;
    document.getElementById("hallucination-count").textContent = totalHallucinations;
  }
  appendActivityCard(event);
  if (event.curator) refreshPlaybook();
  if (event.owner_report) showReportToast(event.owner_report);
}

function handleReset() {
  totalHallucinations = 0;
  document.getElementById("hallucination-count").textContent = 0;
  document.getElementById("step-counter").textContent = 0;
  document.getElementById("cash").textContent = "$0.00";
  document.getElementById("activity-feed").innerHTML = "";
  loadState();
}

// ── Render helpers ───────────────────────────────────────────────────────────

function renderEnvState(env) {
  document.getElementById("cash").textContent = `$${env.cash.toFixed(2)}`;

  const badge = document.getElementById("status-badge");
  badge.textContent = env.status;
  badge.className = `badge ${env.status}`;

  const invEl = document.getElementById("inventory");
  invEl.innerHTML = "";
  for (const [item, qty] of Object.entries(env.inventory)) {
    const price = env.prices ? env.prices[item] : "?";
    const pct = Math.min(100, (qty / MAX_INVENTORY) * 100);
    const cls = qty === 0 ? "empty" : qty <= 1 ? "low" : "";
    invEl.innerHTML += `
      <div class="inv-item">
        <div class="inv-label"><span>${item} <span style="color:var(--muted)">$${price}</span></span><span>${qty}</span></div>
        <div class="inv-bar-bg"><div class="inv-bar-fill ${cls}" style="width:${pct}%"></div></div>
      </div>`;
  }
}

function appendActivityCard(event) {
  const feed = document.getElementById("activity-feed");
  const card = document.createElement("div");
  card.className = "activity-card";

  const outcome = event.outcome || {};
  const reflection = event.reflection || {};
  const action = event.action || {};

  card.innerHTML = `
    <div class="card-step">Step ${event.step}</div>
    ${event.reasoning ? `<div class="reasoning">💭 ${escHtml(event.reasoning)}</div>` : ""}
    <span class="action-tag">${escHtml(action.type || "?")}${action.item ? ` · ${action.item}` : ""}</span>
    <div class="outcome ${outcome.success ? "" : "fail"}">${escHtml(outcome.message || "")}</div>
    ${event.hallucination ? `<span class="hallucination-flag">⚠ HALLUCINATION BLOCKED</span>` : ""}
    ${reflection.insight ? `<div class="reflection">💡 ${escHtml(reflection.insight)}</div>` : ""}
  `;

  feed.prepend(card);
  // Trim old cards
  while (feed.children.length > MAX_FEED_CARDS) feed.removeChild(feed.lastChild);
}

function renderPlaybook(bullets) {
  const list = document.getElementById("playbook-list");
  list.innerHTML = "";
  if (!bullets || bullets.length === 0) {
    list.innerHTML = `<p style="color:var(--muted);font-size:0.8rem">No bullets yet — run a few steps.</p>`;
    return;
  }
  for (const b of bullets) {
    list.innerHTML += `
      <div class="bullet-card">
        <div class="bullet-section">${escHtml(b.section)}</div>
        <div class="bullet-text">${escHtml(b.text)}</div>
        <div class="bullet-score">
          <span class="helpful">✓ ${b.helpful}</span>
          <span class="harmful">✗ ${b.harmful}</span>
          <span style="color:var(--muted)">score ${b.score}</span>
        </div>
      </div>`;
  }
  document.getElementById("bullet-count").textContent = bullets.length;
}

async function refreshPlaybook() {
  const res = await fetch("/api/playbook");
  const bullets = await res.json();
  renderPlaybook(bullets);
}

function showReportToast(msg) {
  const feed = document.getElementById("reports-feed");
  const toast = document.createElement("div");
  toast.className = "report-toast";
  toast.textContent = msg;
  feed.prepend(toast);
  setTimeout(() => toast.remove(), 8000);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Button controls ──────────────────────────────────────────────────────────

document.getElementById("btn-step").addEventListener("click", runStep);
document.getElementById("btn-send").addEventListener("click", sendCustomer);
document.getElementById("btn-reset").addEventListener("click", doReset);
document.getElementById("btn-refresh-playbook").addEventListener("click", refreshPlaybook);
document.getElementById("customer-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendCustomer();
});

document.getElementById("btn-auto").addEventListener("click", () => {
  const btn = document.getElementById("btn-auto");
  if (autoRunTimer) {
    clearInterval(autoRunTimer);
    autoRunTimer = null;
    btn.textContent = "⏵ Auto-run";
    btn.classList.remove("active");
  } else {
    const interval = parseInt(document.getElementById("speed-slider").value, 10);
    autoRunTimer = setInterval(runStep, interval);
    btn.textContent = "⏹ Stop";
    btn.classList.add("active");
  }
});

document.getElementById("speed-slider").addEventListener("input", (e) => {
  const val = parseInt(e.target.value, 10);
  document.getElementById("speed-label").textContent = `${(val / 1000).toFixed(1)} s`;
  if (autoRunTimer) {
    clearInterval(autoRunTimer);
    autoRunTimer = setInterval(runStep, val);
  }
});

async function runStep() {
  const customer = document.getElementById("customer-input").value.trim();
  document.getElementById("customer-input").value = "";
  await fetch("/api/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer }),
  });
}

async function sendCustomer() {
  await runStep();
}

async function doReset() {
  if (autoRunTimer) {
    clearInterval(autoRunTimer);
    autoRunTimer = null;
    document.getElementById("btn-auto").textContent = "⏵ Auto-run";
    document.getElementById("btn-auto").classList.remove("active");
  }
  await fetch("/api/reset", { method: "POST" });
}
