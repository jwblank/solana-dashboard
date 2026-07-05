const fmtPct = (x) => x === null || x === undefined ? "n.v.t." : `${(x * 100).toFixed(1)}%`;
const fmtScore = (x) => x === null || x === undefined ? "..." : Math.round(x);

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
  const blocks = data.scores.blocks;
  const cards = [
    ["Prijssterkte", blocks.price_strength, "Koerskracht van SOL, ook vergeleken met BTC."],
    ["Activiteit", blocks.activity, "DEX-volume en fees als bevestiging van gebruik."],
    ["Kapitaal", blocks.capital, "TVL en stablecoinvoorraad in het ecosysteem."],
    ["Ecosysteembreedte", null, "Experimentele indicator; nog niet gevalideerd."],
    ["Risico", data.current.risk.volatility_30d, `Drawdown: ${fmtPct(data.current.risk.drawdown_90d)}`],
    ["Netwerkcontext", null, "Actueel, nog niet historisch gevalideerd."]
  ];
  document.getElementById("cards").replaceChildren(...cards.map(([title, value, text]) => {
    const card = document.createElement("article");
    card.className = "card";
    const span = document.createElement("span");
    span.textContent = title;
    const strong = document.createElement("strong");
    strong.textContent = value === null ? "Apart" : fmtScore(value);
    const p = document.createElement("p");
    p.textContent = text;
    card.append(span, strong, p);
    return card;
  }));
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
  const [dashboard, analogs, backtest, ledger, glossary] = await Promise.all([
    loadJson("./data/dashboard.json"),
    loadJson("./data/current_analogs.json"),
    loadJson("./data/backtest_summary.json"),
    loadJson("./data/ledger.json"),
    loadJson("./data/glossary.json")
  ]);
  if (dashboard.demo_notice) {
    const notice = document.getElementById("demo-notice");
    notice.hidden = false;
    notice.textContent = dashboard.demo_notice;
  }
  setText("sol-price", `$${dashboard.current.sol_price.toFixed(2)}`);
  setText("updated-at", dashboard.generated_at_utc);
  setText("data-cutoff", dashboard.data_cutoff_utc);
  setText("method-version", dashboard.method_version);
  setText("regime", dashboard.summary.regime.replaceAll("_", " "));
  setText("conclusion-text", dashboard.summary.conclusion);
  setText("market-score", fmtScore(dashboard.scores.market_signal));
  setText("market-label", dashboard.summary.market_signal_label);
  setText("evidence-score", fmtScore(dashboard.scores.evidence_quality));
  setText("evidence-label", dashboard.summary.evidence_label);
  renderCards(dashboard);
  const a = dashboard.analog_summary;
  setText("analog-summary", `${dashboard.summary.language_label}: ${fmtPct(a.positive_frequency)} positief na ${a.horizon_days} dagen (${a.count} vergelijkbare situaties). Mediaan: ${fmtPct(a.median_return)}. Midden 80%: ${fmtPct(a.p10)} tot ${fmtPct(a.p90)}.`);
  document.getElementById("change-list").replaceChildren(...dashboard.summary.what_would_change.map((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    return li;
  }));
  window.renderAnalogChart(analogs.rows || []);
  window.setupPosition(dashboard, analogs.rows || []);
  window.renderGlossary(glossary);
  document.getElementById("evidence-route").append(table(["Onderdeel", "Waarde"], [
    ["Datakwaliteit", dashboard.scores.evidence_components.data_quality],
    ["Steekproefomvang", dashboard.scores.evidence_components.sample_adequacy],
    ["Out-of-sample kwaliteit", dashboard.scores.evidence_components.out_of_sample_quality],
    ["Stabiliteit", dashboard.scores.evidence_components.stability],
    ["Analogie-overeenkomst", dashboard.scores.evidence_components.analog_similarity],
    ["Toegepaste caps", dashboard.scores.quality_caps.join("; ") || "Geen"]
  ]));
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
