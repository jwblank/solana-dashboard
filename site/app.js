const fmtPct = (x) => x === null || x === undefined ? "n.v.t." : `${(x * 100).toFixed(1)}%`;
const fmtScore = (x) => x === null || x === undefined ? "..." : Math.round(x);
const fmtScore100 = (x) => x === null || x === undefined ? ".../100" : `${Math.round(x)}/100`;
const fmtWeight = (x) => `${Math.round(x * 100)}% van score`;

async function loadJson(path) {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${separator}v=${Date.now()}`, {cache: "no-store"});
  if (!response.ok) throw new Error(`Kon ${path} niet laden`);
  return response.json();
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function activateTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.tab).classList.add("active");
    });
  });
}

function renderCards(data) {
  const cards = data.scores.block_details || [];
  document.getElementById("cards").replaceChildren(...cards.map((item) => {
    const card = document.createElement("article");
    card.className = "card";
    const span = document.createElement("span");
    span.textContent = item.title;
    const strong = document.createElement("strong");
    strong.textContent = fmtScore100(item.score);
    const weight = document.createElement("small");
    weight.className = "weight";
    weight.textContent = fmtWeight(item.weight);
    const status = document.createElement("em");
    status.textContent = item.status;
    const p = document.createElement("p");
    p.textContent = item.summary;
    const note = document.createElement("small");
    note.textContent = item.score_note;
    const metrics = document.createElement("div");
    metrics.className = "metric-row";
    (item.metrics || []).forEach((m) => {
      const chip = document.createElement("span");
      chip.className = "metric";
      chip.textContent = `${m.label}: ${m.value}`;
      metrics.append(chip);
    });
    card.append(span, strong, weight, status, p, metrics, note);
    return card;
  }));
}

function renderSources(audit) {
  const cards = audit?.sources || [];
  document.getElementById("source-cards").replaceChildren(...cards.map((item) => {
    const card = document.createElement("article");
    card.className = "source-card";
    const top = document.createElement("div");
    top.className = "source-top";
    const title = document.createElement("strong");
    title.textContent = item.name;
    const status = document.createElement("span");
    status.className = item.status === "Succesvol" ? "status-ok" : "status-warn";
    status.textContent = item.status;
    top.append(title, status);
    const role = document.createElement("p");
    role.textContent = item.role;
    const meta = document.createElement("div");
    meta.className = "metric-row";
    [
      ["Validatie", item.validation],
      ["Dekking", item.coverage],
      ["Laatste succes", item.last_success_at_utc]
    ].forEach(([label, value]) => {
      const chip = document.createElement("span");
      chip.className = "metric";
      chip.textContent = `${label}: ${value || "n.v.t."}`;
      meta.append(chip);
    });
    if (item.warning) {
      const warning = document.createElement("small");
      warning.textContent = item.warning;
      card.append(top, role, meta, warning);
    } else {
      card.append(top, role, meta);
    }
    return card;
  }));
}

function renderStats(targetId, stats) {
  const target = document.getElementById(targetId);
  target.replaceChildren(...(stats || []).map((item) => {
    const div = document.createElement("div");
    div.className = "stat";
    const span = document.createElement("span");
    span.textContent = item.label;
    const strong = document.createElement("strong");
    strong.textContent = item.value;
    div.append(span, strong);
    return div;
  }));
}

function renderBlockEvidence(data) {
  const rows = (data.scores.block_details || []).map((item) => [
    item.title,
    fmtWeight(item.weight),
    fmtScore100(item.score),
    item.status,
    `${item.summary} ${item.drivers.join(" ")}`
  ]);
  return table(["Blok", "Weging", "Score", "Status", "Kern en drijvers"], rows);
}

function table(headers, rows) {
  const t = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    trh.append(th);
  });
  thead.append(trh);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((cell) => {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.append(td);
    });
    tbody.append(tr);
  });
  t.append(thead, tbody);
  return t;
}

async function main() {
  activateTabs();
  const [dashboard, backtest, ledger, glossary] = await Promise.all([
    loadJson("./data/dashboard.json"),
    loadJson("./data/backtest_summary.json"),
    loadJson("./data/ledger.json"),
    loadJson("./data/glossary.json")
  ]);
  if (dashboard.demo_notice) {
    const notice = document.getElementById("demo-notice");
    notice.hidden = false;
    notice.textContent = dashboard.demo_notice;
  }
  const solPrice = dashboard.current.live_sol_price ?? dashboard.current.sol_price;
  setText("sol-price", `$${solPrice.toFixed(2)}`);
  setText("updated-at", dashboard.generated_at_utc);
  setText("data-cutoff", dashboard.data_cutoff_utc);
  setText("method-version", dashboard.method_version);
  setText("regime", dashboard.summary.regime_title || dashboard.summary.regime.replaceAll("_", " "));
  setText("conclusion-text", dashboard.summary.conclusion);
  setText("interpretation-note", dashboard.summary.interpretation_note || "");
  setText("market-score", fmtScore100(dashboard.scores.market_signal));
  setText("market-label", dashboard.summary.market_signal_label);
  setText("evidence-score", fmtScore100(dashboard.scores.evidence_quality));
  setText("evidence-label", dashboard.summary.evidence_label);
  renderCards(dashboard);
  setText("analog-summary", dashboard.historical_context?.summary || "");
  renderStats("analog-stats", dashboard.historical_context?.stats || []);
  setText("audit-summary", dashboard.data_audit?.summary || "");
  renderStats("audit-stats", dashboard.data_audit?.freshness || []);
  renderSources(dashboard.data_audit);
  setText("audit-warnings", (dashboard.data_audit?.warnings || []).join(" ") || "Geen waarschuwingen bij deze update.");
  document.getElementById("change-list").replaceChildren(...dashboard.summary.what_would_change.map((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    return li;
  }));
  window.renderGlossary(glossary);
  document.getElementById("evidence-route").append(table(["Onderdeel", "Waarde"], [
    ["Eindscore", fmtScore100(dashboard.scores.market_signal)],
    ["Scoreduiding", dashboard.scores.method_note],
    ["Datakwaliteit", dashboard.scores.evidence_components.data_quality],
    ["Steekproefomvang", dashboard.scores.evidence_components.sample_adequacy],
    ["Out-of-sample kwaliteit", dashboard.scores.evidence_components.out_of_sample_quality],
    ["Stabiliteit", dashboard.scores.evidence_components.stability],
    ["Analogie-overeenkomst", dashboard.scores.evidence_components.analog_similarity],
    ["Toegepaste caps", dashboard.scores.quality_caps.join("; ") || "Geen"]
  ]));
  const blockHeading = document.createElement("h3");
  blockHeading.textContent = "Scoreblokken";
  document.getElementById("evidence-route").append(blockHeading, renderBlockEvidence(dashboard));
  const bRows = Object.entries(backtest.horizons).map(([h, row]) => [
    h, row.prediction_count || 0, row.directional_accuracy ?? "n.v.t.", row.brier_score ?? "n.v.t.", row.brier_skill ?? "n.v.t.", row.calibration_error ?? "n.v.t."
  ]);
  document.getElementById("backtest-table").append(table(["Horizon", "Voorspellingen", "Richting", "Brier", "Brier skill", "Kalibratiefout"], bRows));
  const skill7 = backtest.horizons["7d"]?.brier_skill;
  document.getElementById("edge-warning").textContent = skill7 > 0 ? "De huidige backtest laat enige voorspellende meerwaarde zien." : "In de huidige backtest is nog geen overtuigende voorspellende meerwaarde aangetoond.";
  document.getElementById("ledger-table").append(table(["Voorspellingen", "Outcomes"], [[ledger.predictions.length, ledger.outcomes.length]]));
}

main().catch((error) => {
  document.body.prepend(Object.assign(document.createElement("p"), {className: "notice", textContent: error.message}));
});
