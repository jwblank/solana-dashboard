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
  document.getElementById("source-cards").replaceChildren(...sourceCards(cards));
}

function sourceCards(cards) {
  return cards.map((item) => {
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
  });
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

function renderEvidencePage(dashboard, backtest, ledger) {
  setText("evidence-summary", evidenceSummaryText(dashboard, backtest));
  renderEvidenceScorecard(dashboard);
  renderEvidenceKpis(dashboard, backtest);
  renderEvidenceBlocks(dashboard);
  renderBacktest(backtest);
  renderLedger(ledger);
  renderMethodSteps();
  renderTermExplainers();
}

function renderInterpretationPage(interpretation) {
  setText("llm-title", interpretation.title || "Duiding niet beschikbaar");
  setText("llm-intro", interpretation.intro || "");
  renderInterpretationAudit(interpretation);
  renderInterpretationSections(interpretation.sections || []);
  renderInterpretationInputs(interpretation.input_snapshot || {});
  setText("llm-note", interpretation.footer_note || "");
}

function renderInterpretationAudit(interpretation) {
  const statusText = interpretation.status === "llm_success"
    ? "LLM-call geslaagd"
    : "Fallback gebruikt";
  const items = [
    ["Status", statusText],
    ["Model", interpretation.model || "n.v.t."],
    ["Provider", interpretation.provider || "n.v.t."],
    ["LLM-call", interpretation.llm_called_at_utc || "Niet aangeroepen"],
    ["Update", interpretation.generated_at_utc || "n.v.t."],
    ["Datacutoff", interpretation.data_cutoff_utc || "n.v.t."]
  ];
  const target = document.getElementById("llm-audit");
  target.replaceChildren(...items.map(([label, value]) => {
    const row = document.createElement("div");
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    row.append(span, strong);
    return row;
  }));
  (interpretation.warnings || []).forEach((warning) => {
    const small = document.createElement("small");
    small.textContent = warning;
    target.append(small);
  });
}

function renderInterpretationSections(sections) {
  document.getElementById("llm-sections").replaceChildren(...sections.map((item) => {
    const card = document.createElement("article");
    card.className = "interpretation-card";
    const h3 = document.createElement("h3");
    h3.textContent = item.heading;
    const p = document.createElement("p");
    p.textContent = item.text;
    card.append(h3, p);
    return card;
  }));
}

function renderInterpretationInputs(facts) {
  const items = [
    ["Marktsignaal", facts.market_signal],
    ["Bewijskwaliteit", facts.evidence_quality],
    ["Prijssterkte", facts.price_strength],
    ["Netwerkgebruik", facts.network_usage],
    ["Kapitaal", facts.capital],
    ["Ecosysteembreedte", facts.ecosystem_breadth],
    ["SOL", facts.sol_price],
    ["Analoge dagen", facts.analog_count],
    ["Historisch positief", facts.analog_positive_frequency],
    ["7d backtest", `${facts.backtest_7d?.prediction_count || 0} runs`]
  ];
  document.getElementById("llm-inputs").replaceChildren(...items.map(([label, value]) => {
    const div = document.createElement("div");
    div.className = "stat";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value || "n.v.t.";
    div.append(span, strong);
    return div;
  }));
}

function renderEvidenceScorecard(dashboard) {
  const target = document.getElementById("evidence-scorecard");
  target.replaceChildren(
    labeledValue("Bewijskwaliteit", fmtScore100(dashboard.scores.evidence_quality)),
    labeledValue("Marktsignaal", fmtScore100(dashboard.scores.market_signal)),
    labeledValue("Duiding", dashboard.summary.evidence_label)
  );
}

function renderEvidenceKpis(dashboard, backtest) {
  const components = dashboard.scores.evidence_components || {};
  const horizon7 = backtest.horizons?.["7d"] || {};
  const cards = [
    {
      label: "Datakwaliteit",
      value: fmtScore100(components.data_quality),
      text: "Meet of de gebruikte databronnen beschikbaar, actueel en compleet zijn.",
      interpretation: highIsBetter(components.data_quality)
    },
    {
      label: "Steekproefomvang",
      value: fmtScore100(components.sample_adequacy),
      text: "Beoordeelt of er genoeg vergelijkbare historische situaties zijn.",
      interpretation: highIsBetter(components.sample_adequacy)
    },
    {
      label: "Out-of-sample kwaliteit",
      value: fmtScore100(components.out_of_sample_quality),
      text: "Meet prestaties op latere data die niet gebruikt is om het signaal te vormen.",
      interpretation: highIsBetter(components.out_of_sample_quality)
    },
    {
      label: "Backtest 7d",
      value: formatDecimal(horizon7.brier_skill),
      text: "Brier skill vergelijkt de methode met een simpele basislijn.",
      interpretation: brierSkillText(horizon7.brier_skill)
    },
    {
      label: "Stabiliteit",
      value: fmtScore100(components.stability),
      text: "Meet of de uitkomst niet te afhankelijk is van kleine dataverschillen.",
      interpretation: highIsBetter(components.stability)
    },
    {
      label: "Analogie-overeenkomst",
      value: fmtScore100(components.analog_similarity),
      text: "Meet hoe sterk vandaag lijkt op de gekozen historische vergelijkingsdagen.",
      interpretation: highIsBetter(components.analog_similarity)
    }
  ];
  document.getElementById("evidence-kpis").replaceChildren(...cards.map(explainerCard));
}

function renderEvidenceBlocks(dashboard) {
  const cards = (dashboard.scores.block_details || []).map((item) => {
    const card = document.createElement("article");
    card.className = "evidence-block";
    const head = document.createElement("div");
    head.className = "evidence-block-head";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const score = document.createElement("span");
    score.textContent = fmtScore100(item.score);
    head.append(title, score);
    const meta = document.createElement("div");
    meta.className = "metric-row";
    [
      ["Weging", fmtWeight(item.weight)],
      ["Status", item.status],
      ["Schaal", item.score_label]
    ].forEach(([label, value]) => {
      const chip = document.createElement("span");
      chip.className = "metric";
      chip.textContent = `${label}: ${value}`;
      meta.append(chip);
    });
    const summary = document.createElement("p");
    summary.textContent = item.summary;
    const list = document.createElement("ul");
    list.className = "clean compact";
    (item.drivers || []).slice(0, 3).forEach((driver) => {
      const li = document.createElement("li");
      li.textContent = driver;
      list.append(li);
    });
    card.append(head, meta, summary, list);
    return card;
  });
  document.getElementById("evidence-blocks").replaceChildren(...cards);
}

function renderBacktest(backtest) {
  const entries = Object.entries(backtest.horizons || {});
  const cards = entries.map(([horizon, row]) => explainerCard({
    label: `${horizon} horizon`,
    value: `${row.prediction_count || 0} runs`,
    text: `Richting: ${formatPctLike(row.directional_accuracy)}. Brier skill: ${formatDecimal(row.brier_skill)}.`,
    interpretation: backtestInterpretation(row)
  }));
  document.getElementById("backtest-cards").replaceChildren(...cards);
  const bRows = entries.map(([h, row]) => [
    h,
    row.prediction_count || 0,
    formatPctLike(row.directional_accuracy),
    formatDecimal(row.brier_score),
    formatDecimal(row.brier_skill),
    formatDecimal(row.calibration_error)
  ]);
  document.getElementById("backtest-table").replaceChildren(table([
    "Horizon",
    "Voorspellingen",
    "Richting",
    "Brier",
    "Brier skill",
    "Kalibratiefout"
  ], bRows));
  const skill7 = backtest.horizons?.["7d"]?.brier_skill;
  document.getElementById("edge-warning").textContent = skill7 > 0
    ? "De 7-daagse backtest laat lichte meerwaarde zien, maar de steekproef blijft beperkt."
    : "De 7-daagse backtest toont nog geen overtuigende meerwaarde boven een simpele basislijn.";
}

function renderLedger(ledger) {
  const target = document.getElementById("ledger-summary");
  const predictions = ledger.predictions?.length || 0;
  const outcomes = ledger.outcomes?.length || 0;
  target.replaceChildren(
    explainerCard({
      label: "Voorspellingen",
      value: String(predictions),
      text: "Aantal officiële signalen dat in het append-only logboek is vastgelegd.",
      interpretation: predictions ? "Er is een controleerbaar spoor." : "Nog geen signalen vastgelegd."
    }),
    explainerCard({
      label: "Uitkomsten",
      value: String(outcomes),
      text: "Aantal voorspellingen waarvan de latere uitkomst al gemeten is.",
      interpretation: outcomes ? "Er is al feedback op eerdere signalen." : "Nog te vroeg voor outcome-meting."
    })
  );
}

function renderMethodSteps() {
  const steps = [
    ["1. Data ophalen", "Dagprijzen, DeFi-data, kapitaalstromen en actuele netwerkcontext worden opgehaald."],
    ["2. Normaliseren", "Elke indicator wordt omgerekend naar een score van 0 tot 100 ten opzichte van de eigen historie."],
    ["3. Vergelijken", "Vandaag wordt vergeleken met eerdere dagen die statistisch vergelijkbaar waren."],
    ["4. Controleren", "De methode wordt walk-forward getest, zodat toekomstige informatie buiten beeld blijft."]
  ];
  document.getElementById("method-steps").replaceChildren(...steps.map(([title, text]) => {
    const item = document.createElement("article");
    item.className = "method-step";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const p = document.createElement("p");
    p.textContent = text;
    item.append(strong, p);
    return item;
  }));
}

function renderTermExplainers() {
  const terms = [
    {
      label: "Out-of-sample kwaliteit",
      value: "Controle buiten trainingsdata",
      text: "De methode wordt beoordeeld op latere data die niet gebruikt is om het signaal te bepalen.",
      interpretation: "Hoger is beter; laag betekent dat het signaal historisch nog kwetsbaar is."
    },
    {
      label: "Brier skill",
      value: "Meerwaarde t.o.v. basislijn",
      text: "Vergelijkt de fout van dit model met een simpele referentie zoals historische frequentie.",
      interpretation: "Boven 0 is beter dan de basislijn; onder 0 is slechter."
    },
    {
      label: "Kalibratiefout",
      value: "Betrouwbaarheid van kansen",
      text: "Meet of uitspraken over waarschijnlijkheid passen bij wat later werkelijk gebeurde.",
      interpretation: "Lager is beter; hoog betekent dat kansen te zeker of te voorzichtig kunnen zijn."
    },
    {
      label: "Caps",
      value: "Voorzichtigheidsregels",
      text: "Beperkingen die voorkomen dat een score te stellig wordt bij weinig bewijs.",
      interpretation: "Caps maken de conclusie conservatiever en transparanter."
    }
  ];
  document.getElementById("term-explainer").replaceChildren(...terms.map(explainerCard));
}

function renderIndicatorTab(targetId, tab) {
  const target = document.getElementById(targetId);
  if (!target || !tab) return;
  const hero = document.createElement("section");
  hero.className = "indicator-hero";
  const text = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Indicator";
  const title = document.createElement("h2");
  title.textContent = tab.title;
  const subtitle = document.createElement("p");
  subtitle.className = "plain";
  subtitle.textContent = tab.subtitle;
  const summary = document.createElement("p");
  summary.textContent = tab.summary;
  const note = document.createElement("p");
  note.className = "plain";
  note.textContent = tab.note;
  text.append(eyebrow, title, subtitle, summary, note);

  const score = document.createElement("div");
  score.className = "indicator-score";
  const scoreLabel = document.createElement("span");
  scoreLabel.textContent = "Score";
  const scoreValue = document.createElement("strong");
  scoreValue.textContent = fmtScore100(tab.score);
  const weight = document.createElement("small");
  weight.textContent = fmtWeight(tab.weight);
  const status = document.createElement("small");
  status.textContent = tab.status;
  score.append(scoreLabel, scoreValue, weight, status);
  hero.append(text, score);

  const components = document.createElement("section");
  components.className = "wide";
  const componentTitle = document.createElement("h3");
  componentTitle.textContent = "Onderliggende metingen";
  const componentGrid = document.createElement("div");
  componentGrid.className = "component-grid";
  componentGrid.replaceChildren(...(tab.components || []).map(componentCard));
  components.append(componentTitle, componentGrid);

  const trend = document.createElement("section");
  trend.className = "wide";
  const trendTitle = document.createElement("h3");
  trendTitle.textContent = "Trend";
  const trendGrid = document.createElement("div");
  trendGrid.className = "spark-grid";
  trendGrid.replaceChildren(...(tab.trend?.series || []).map((series) => {
    return sparklineCard(tab.trend?.rows || [], series);
  }));
  trend.append(trendTitle, trendGrid);

  const sources = document.createElement("section");
  sources.className = "wide";
  const sourceTitle = document.createElement("h3");
  sourceTitle.textContent = "Bronnen voor dit blok";
  const sourceGrid = document.createElement("div");
  sourceGrid.className = "source-grid";
  sourceGrid.replaceChildren(...sourceCards(tab.sources || []));
  sources.append(sourceTitle, sourceGrid);

  target.replaceChildren(hero, components, trend, sources);
}

function componentCard(item) {
  const card = document.createElement("article");
  card.className = "component-card";
  const label = document.createElement("span");
  label.textContent = item.label;
  const value = document.createElement("strong");
  value.textContent = item.value;
  const score = document.createElement("small");
  score.className = "weight";
  score.textContent = `Score: ${fmtScore100(item.score)}`;
  const weight = document.createElement("small");
  weight.textContent = item.weight;
  const description = document.createElement("p");
  description.textContent = item.description;
  card.append(label, value, score, weight, description);
  return card;
}

function sparklineCard(rows, series) {
  const card = document.createElement("article");
  card.className = "mini-chart";
  const label = document.createElement("span");
  label.textContent = series.label;
  const values = rows
    .map((row, index) => ({index, value: Number(row[series.key])}))
    .filter((point) => Number.isFinite(point.value));
  const latest = values.length ? values[values.length - 1].value : null;
  const strong = document.createElement("strong");
  strong.textContent = formatTrendValue(latest, series.unit);
  card.append(label, strong, sparklineSvg(values));
  if (values.length) {
    const range = document.createElement("small");
    const min = Math.min(...values.map((point) => point.value));
    const max = Math.max(...values.map((point) => point.value));
    range.textContent = `Bereik: ${formatTrendValue(min, series.unit)} tot ${formatTrendValue(max, series.unit)}`;
    card.append(range);
  }
  return card;
}

function sparklineSvg(values) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 320 90");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-hidden", "true");
  const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axis.setAttribute("x1", "0");
  axis.setAttribute("y1", "70");
  axis.setAttribute("x2", "320");
  axis.setAttribute("y2", "70");
  axis.setAttribute("class", "spark-axis");
  svg.append(axis);
  if (values.length < 2) return svg;
  const min = Math.min(...values.map((point) => point.value));
  const max = Math.max(...values.map((point) => point.value));
  const span = max - min || 1;
  const lastIndex = values[values.length - 1].index || 1;
  const points = values.map((point) => {
    const x = (point.index / lastIndex) * 320;
    const y = 78 - ((point.value - min) / span) * 66;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", points);
  line.setAttribute("class", "spark-line");
  svg.append(line);
  return svg;
}

function formatTrendValue(value, unit) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  const number = Number(value);
  if (unit === "%") return `${(number * 100).toFixed(1)}%`;
  if (unit === "$") return `$${number.toFixed(2)}`;
  if (unit === "/100") return `${Math.round(number)}/100`;
  if (unit === "x") return `${number.toFixed(2)}x`;
  return Math.abs(number) >= 10 ? number.toFixed(1) : number.toFixed(2);
}

function labeledValue(label, value) {
  const div = document.createElement("div");
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  div.append(span, strong);
  return div;
}

function explainerCard(item) {
  const card = document.createElement("article");
  card.className = "explainer-card";
  const span = document.createElement("span");
  span.textContent = item.label;
  const strong = document.createElement("strong");
  strong.textContent = item.value;
  const p = document.createElement("p");
  p.textContent = item.text;
  const small = document.createElement("small");
  small.textContent = item.interpretation;
  card.append(span, strong, p, small);
  return card;
}

function evidenceSummaryText(dashboard, backtest) {
  const count = dashboard.analog_summary?.count || 0;
  const skill7 = backtest.horizons?.["7d"]?.brier_skill;
  const skillText = skill7 > 0 ? "lichte historische meerwaarde" : "nog beperkte meerwaarde";
  return `De bewijskwaliteit is ${fmtScore100(dashboard.scores.evidence_quality)}. De huidige conclusie steunt op ${count} vergelijkbare historische dagen en een backtest met ${skillText}.`;
}

function highIsBetter(value) {
  if (value === null || value === undefined) return "Nog niet berekend.";
  if (value >= 75) return "Sterk: deze controle ondersteunt het signaal.";
  if (value >= 55) return "Redelijk: bruikbaar, maar niet doorslaggevend.";
  return "Beperkt: interpreteer het signaal voorzichtig.";
}

function brierSkillText(value) {
  if (value === null || value === undefined) return "Nog niet berekend.";
  if (value > 0.05) return "Positief: duidelijk beter dan de basislijn.";
  if (value > 0) return "Licht positief: iets beter dan de basislijn.";
  return "Zwak: niet beter dan de basislijn.";
}

function backtestInterpretation(row) {
  const skill = row.brier_skill;
  const accuracy = row.directional_accuracy;
  if ((skill || 0) > 0 && (accuracy || 0) > 0.5) {
    return "Deze horizon draagt voorzichtig positief bewijs bij.";
  }
  if ((skill || 0) > 0) return "De foutscore is licht positief, maar richting blijft gemengd.";
  return "Deze horizon bewijst nog weinig voorspellende meerwaarde.";
}

function formatDecimal(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  return Number(value).toFixed(3);
}

function formatPctLike(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  return `${(Number(value) * 100).toFixed(1)}%`;
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
  const [dashboard, backtest, ledger, glossary, interpretation] = await Promise.all([
    loadJson("./data/dashboard.json"),
    loadJson("./data/backtest_summary.json"),
    loadJson("./data/ledger.json"),
    loadJson("./data/glossary.json"),
    loadJson("./data/interpretation.json")
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
  renderIndicatorTab("price-tab", dashboard.indicator_tabs?.price);
  renderIndicatorTab("network-tab", dashboard.indicator_tabs?.network);
  renderIndicatorTab("capital-tab", dashboard.indicator_tabs?.capital);
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
  renderEvidencePage(dashboard, backtest, ledger);
  renderInterpretationPage(interpretation);
}

main().catch((error) => {
  document.body.prepend(Object.assign(document.createElement("p"), {className: "notice", textContent: error.message}));
});
