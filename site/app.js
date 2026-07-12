const fmtPct = (x) => x === null || x === undefined ? "n.v.t." : `${(x * 100).toFixed(1)}%`;
const fmtScore = (x) => x === null || x === undefined ? "..." : Math.round(x);
const fmtScore100 = (x) => x === null || x === undefined ? ".../100" : `${Math.round(x)}/100`;
const fmtWeight = (x) => `${Math.round(x * 100)}% van score`;
let scoreHistoryChart = null;

async function loadJson(path) {
  const separator = path.includes("?") ? "&" : "?";
  const buildVersion = window.SOL_REALITY_CHECK_BUILD || "dev";
  const response = await fetch(`${path}${separator}v=${encodeURIComponent(buildVersion)}`, {cache: "no-cache"});
  if (!response.ok) throw new Error(`Kon ${path} niet laden`);
  return response.json();
}

function setText(id, value) {
  const target = document.getElementById(id);
  if (!target) return;
  target.textContent = value;
}

const routes = {
  "#actueel": {tab: "actueel"},
  "#prijs": {tab: "prijs"},
  "#netwerk": {tab: "netwerk"},
  "#kapitaal": {tab: "kapitaal"},
  "#voorspellingskracht": {tab: "voorspellingskracht"},
  "#bewijs": {tab: "bewijs"},
  "#bewijs-kwaliteit": {tab: "bewijs", anchor: "bewijs-kwaliteit"},
  "#bewijs-backtest": {tab: "bewijs", anchor: "bewijs-backtest"},
  "#bewijs-trackrecord": {tab: "bewijs", anchor: "bewijs-trackrecord"},
  "#bewijs-historie": {tab: "bewijs", anchor: "bewijs-historie"},
  "#bewijs-methode": {tab: "bewijs", anchor: "bewijs-methode"},
  "#bewijs-data": {tab: "bewijs", anchor: "bewijs-data"},
  "#analyse": {tab: "actueel"},
  "#analyse-totaal": {tab: "actueel"},
  "#analyse-prijs": {tab: "prijs"},
  "#analyse-netwerk": {tab: "netwerk"},
  "#analyse-kapitaal": {tab: "kapitaal"},
  "#analyse-ecosysteem": {tab: "netwerk"},
  "#analyse-historie": {tab: "bewijs", anchor: "bewijs-historie"}
};

function activateNavigation() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => navigateTo(`#${button.dataset.tab}`));
  });
  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => navigateTo(button.dataset.jump));
  });
  window.addEventListener("hashchange", applyRouteFromHash);
  applyRouteFromHash();
}

function navigateTo(hash) {
  if (window.location.hash === hash) {
    applyRouteFromHash();
    scrollToTop();
    return;
  }
  window.location.hash = hash;
}

function applyRouteFromHash() {
  const route = routes[window.location.hash] || routes["#actueel"];
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === route.tab);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === route.tab);
  });
  if (route.anchor) {
    const anchor = document.getElementById(route.anchor);
    if (anchor) {
      requestAnimationFrame(() => anchor.scrollIntoView({block: "start"}));
    }
  }
}

function scrollToTop() {
  window.scrollTo({top: 0, behavior: "smooth"});
}

function renderCards(data, targetId = "analysis-total-cards") {
  const cards = data.scores.block_details || [];
  const target = document.getElementById(targetId);
  if (!target) return;
  target.replaceChildren(...cards.map((item) => {
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
  const target = document.getElementById("source-cards");
  if (!target) return;
  target.replaceChildren(...sourceCards(cards));
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
    const priceDetails = priceBreakdown(item.price_breakdown || []);
    if (item.warning) {
      const warning = document.createElement("small");
      warning.textContent = item.warning;
      card.append(top, role, meta, priceDetails, warning);
    } else {
      card.append(top, role, meta, priceDetails);
    }
    return card;
  });
}

function priceBreakdown(rows) {
  const wrap = document.createElement("div");
  wrap.className = "price-breakdown";
  if (!rows.length) return wrap;
  rows.forEach((row) => {
    const block = document.createElement("div");
    block.className = "price-breakdown-block";
    const title = document.createElement("strong");
    title.textContent = `${row.asset}: ${formatSourcePrice(row.used_close)}`;
    const meta = document.createElement("div");
    meta.className = "metric-row";
    [
      ["Methode", row.method || row.provider],
      ["Datum", row.date],
      ["Bronnen", row.source_count ? String(row.source_count) : "n.v.t."],
      ["Genegeerd", row.outlier_count !== undefined ? String(row.outlier_count) : "0"],
      ["Spreiding", row.max_deviation_pct !== null && row.max_deviation_pct !== undefined ? `${row.max_deviation_pct}%` : "n.v.t."],
      ["Gat vanaf", row.gap_fill_start],
      ["CCXT laatst", row.ccxt_last_date ? `${row.ccxt_last_date} (${formatSourcePrice(row.ccxt_last_close)})` : ""]
    ].filter(([, value]) => value).forEach(([label, value]) => {
      const chip = document.createElement("span");
      chip.className = "metric";
      chip.textContent = `${label}: ${value}`;
      meta.append(chip);
    });
    block.append(title, meta);
    const exchanges = (row.exchange_prices || []).slice(0, 5);
    if (exchanges.length) {
      const list = document.createElement("div");
      list.className = "source-price-list";
      exchanges.forEach((source) => {
        const line = document.createElement("div");
        line.className = "source-price-line";
        const status = source.status || (source.used ? "succesvol gebruikt" : "succesvol geladen; genegeerd");
        line.textContent = `${formatExchangeName(source.exchange)}: ${formatSourcePrice(source.close)} ${status}`;
        list.append(line);
      });
      block.append(list);
    }
    wrap.append(block);
  });
  return wrap;
}

function formatExchangeName(value) {
  const text = String(value || "").toLowerCase();
  const names = { coinbase: "Coinbase", kraken: "Kraken", okx: "OKX", kucoin: "KuCoin" };
  if (!text) return "Bron";
  return names[text] || text.charAt(0).toUpperCase() + text.slice(1);
}

function formatSourcePrice(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  return `$${Number(value).toFixed(2)}`;
}

function renderStats(targetId, stats) {
  const target = document.getElementById(targetId);
  if (!target) return;
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

function renderOverview(overview, overviewHistory) {
  const current = overview.current_run || {};
  const previous = overview.previous_run;
  const changes = overview.changes || {};
  const title = current.regime_title || current.regime || "Actueel beeld";
  setText("overview-title", overviewTitle(title, current, changes));
  setText("overview-subtitle", previous
    ? "Vergelijking met de vorige officiële productierun."
    : "Nog onvoldoende officiële runs voor een vergelijking; actuele scores worden wel getoond.");
  renderStats("overview-meta", [
    {label: "Huidige run", value: formatDateTime(current.run_at_utc)},
    {label: "Vergelijkingsrun", value: previous ? formatDateTime(previous.run_at_utc) : "n.v.t."},
    {label: "SOL-slotkoers", value: `${formatMoney(current.sol_price)}${formatMoneyDelta(changes.sol_price_absolute, changes.sol_price_pct)}`},
    {label: "Methode", value: current.method_version || "n.v.t."}
  ]);
  renderOverviewScores(current, changes);
  renderOverviewChanges(overview.largest_changes || {});
  renderActueelDomainCards(overview.dashboard || null, overview.drivers || []);
  renderCurrentQualitySummary(overview.dashboard || null, overview.track_record || {});
  renderCurrentTrackSummary(overview.track_record || {});
  const methodTransitions = overview.method_transitions || overviewHistory?.method_transitions || [];
  renderScoreHistory(overviewHistory?.rows || [], methodTransitions, 90);
  renderHistoryRangeControls(overviewHistory?.rows || [], methodTransitions);
  renderMethodVersionNote(overviewHistory?.rows || [], methodTransitions);
  renderWaterfall(overview.waterfall || {}, overview.drivers || []);
  renderTrackRecord(overview.track_record || {});
  document.getElementById("overview-watchlist").replaceChildren(...(overview.what_would_change || []).map((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    return li;
  }));
}

function renderActueelDomainCards(dashboard, drivers) {
  const target = document.getElementById("actueel-domain-cards");
  if (!target) return;
  const details = dashboard?.scores?.block_details || [];
  const driverByKey = Object.fromEntries((drivers || []).map((driver) => [driver.key, driver]));
  const routeByKey = {
    price_strength: "#prijs",
    network_usage: "#netwerk",
    capital_flows: "#kapitaal",
    ecosystem_breadth: "#netwerk"
  };
  const cards = details.map((item) => {
    const driver = driverByKey[item.key] || {};
    const card = document.createElement("article");
    card.className = "change-card domain-card";
    const label = document.createElement("span");
    label.textContent = item.title;
    const score = document.createElement("strong");
    score.textContent = fmtScore100(item.score);
    const summary = document.createElement("p");
    summary.textContent = `${item.summary} ${driver.score_delta !== undefined ? formatBlockDelta(driver.score_delta) : ""}`.trim();
    const link = document.createElement("button");
    link.className = "button link-button compact-button";
    link.type = "button";
    link.textContent = "Open pagina";
    link.addEventListener("click", () => navigateTo(routeByKey[item.key] || "#actueel"));
    card.append(label, score, summary, link);
    return card;
  });
  target.replaceChildren(...cards);
}

function renderCurrentQualitySummary(dashboard, track) {
  setText(
    "actueel-quality-title",
    dashboard ? `${fmtScore100(dashboard.scores?.evidence_quality)} — ${dashboard.summary?.evidence_label || "onderbouwing"}` : "n.v.t."
  );
  const sources = dashboard?.data_audit?.sources || [];
  const warnings = dashboard?.data_audit?.warnings || [];
  const sourceStatus = sources.length
    ? `${sources.filter((source) => source.status === "Succesvol").length}/${sources.length} bronnen succesvol`
    : "geen bronstatus beschikbaar";
  const trackText = track?.maturity_status ? `Trackrecordfase: ${track.maturity_status}.` : "";
  setText("actueel-quality-text", `${sourceStatus}. ${warnings.length ? warnings[0] : "Geen datakwaliteitswaarschuwingen bij deze update."} ${trackText}`.trim());
}

function renderCurrentTrackSummary(track) {
  const official = track.official_signal_count || 0;
  const resolved = track.resolved_outcome_count || 0;
  setText("actueel-track-title", `${official} officiële signalen`);
  setText(
    "actueel-track-text",
    `${resolved} afgeronde forward-uitkomsten. ${track.forward_status || "Nog geen afgeronde publieke voorspellingen."}`
  );
}

function overviewTitle(title, current, changes) {
  if (!changes?.available) return `${title} — eerste officiële meting`;
  return `${title} — ${fmtScore100(current.current_strength_score)}, ${formatPointDelta(changes.market_score_points)}`;
}

function renderOverviewScores(current, changes) {
  const target = document.getElementById("overview-scorebox");
  target.replaceChildren(
    scoreDeltaCard("Huidige sterkte", current.current_strength_score, changes.market_score_points),
    scoreDeltaCard("Onderbouwing", current.support_score, changes.evidence_score_points)
  );
}

function scoreDeltaCard(label, value, delta) {
  const div = document.createElement("div");
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = fmtScore100(value);
  const small = document.createElement("small");
  small.textContent = formatPointDelta(delta);
  div.append(span, strong, small);
  return div;
}

function formatPointDelta(delta) {
  if (delta === null || delta === undefined || !Number.isFinite(Number(delta))) return "geen vergelijking beschikbaar";
  const value = Number(delta);
  if (Math.abs(value) < 0.05) return "onveranderd sinds vorige run";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} punten sinds vorige run`;
}

function formatBlockDelta(delta) {
  if (delta === null || delta === undefined || !Number.isFinite(Number(delta))) return "geen vergelijking beschikbaar";
  const value = Number(delta);
  if (Math.abs(value) < 0.05) return "onveranderd sinds vorige run";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} blokpunten sinds vorige run`;
}

function formatMoneyDelta(abs, pct) {
  if (abs === null || abs === undefined || pct === null || pct === undefined) return "";
  const absText = `${Number(abs) >= 0 ? "+" : ""}$${Math.abs(Number(abs)).toFixed(2)}`;
  const pctText = `${Number(pct) >= 0 ? "+" : ""}${(Number(pct) * 100).toFixed(1)}%`;
  return ` (${absText}, ${pctText})`;
}

function renderOverviewChanges(changes) {
  setText("overview-change-conclusion", changes.conclusion || "Nog geen vergelijking beschikbaar.");
  const items = [
    ...(changes.positive || []).map((item) => ({...item, direction: "positief"})),
    ...(changes.negative || []).map((item) => ({...item, direction: "negatief"}))
  ];
  const target = document.getElementById("overview-changes");
  if (changes.all_unchanged_message) {
    const p = document.createElement("p");
    p.className = "plain";
    p.textContent = changes.all_unchanged_message;
    target.replaceChildren(p);
    return;
  }
  const nodes = [];
  if (changes.positive_empty_message) nodes.push(emptyChangeCard(changes.positive_empty_message));
  nodes.push(...(changes.positive || []).map((item) => changeCard(item, "positief")));
  if (changes.negative_empty_message) nodes.push(emptyChangeCard(changes.negative_empty_message));
  nodes.push(...(changes.negative || []).map((item) => changeCard(item, "negatief")));
  target.replaceChildren(...nodes);
}

function changeCard(item, direction) {
    const card = document.createElement("article");
    card.className = `change-card ${item.score_delta >= 0 ? "positive" : "negative"}`;
    const span = document.createElement("span");
    span.textContent = direction === "positief" ? "Grootste positieve driver" : "Grootste negatieve driver";
    const strong = document.createElement("strong");
    strong.textContent = item.label;
    const delta = document.createElement("p");
    delta.textContent = `${formatBlockDelta(item.score_delta)}; ${item.change_label}.`;
    card.append(span, strong, delta);
    return card;
}

function emptyChangeCard(message) {
  const card = document.createElement("article");
  card.className = "change-card neutral";
  const span = document.createElement("span");
  span.textContent = "Geen materiële verandering";
  const p = document.createElement("p");
  p.textContent = message;
  card.append(span, p);
  return card;
}

function renderHistoryRangeControls(rows, transitions) {
  const target = document.getElementById("history-range");
  const options = [
    ["30", "30 runs"],
    ["90", "90 runs"],
    ["365", "365 runs"],
    ["all", "Alles"]
  ];
  target.replaceChildren(...options.map(([value, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = value === "90" ? "button active-range" : "button";
    button.textContent = label;
    button.addEventListener("click", () => {
      target.querySelectorAll("button").forEach((b) => b.classList.remove("active-range"));
      button.classList.add("active-range");
      renderScoreHistory(rows, transitions, value === "all" ? rows.length : Number(value));
    });
    return button;
  }));
}

function renderScoreHistory(rows, transitions, limit) {
  const canvas = document.getElementById("score-history-chart");
  if (!canvas || !window.Chart) return;
  const selected = rows.slice(Math.max(rows.length - limit, 0));
  const labels = selected.map((row) => String(row.run_at_utc || "").slice(0, 10));
  const datasets = segmentedScoreDatasets(selected);
  const visibleTransitions = (transitions || []).filter((transition) =>
    selected.some((row) => row.run_at_utc === transition.run_at_utc)
  );
  if (scoreHistoryChart) scoreHistoryChart.destroy();
  const transitionPlugin = {
    id: "methodTransitions",
    afterDatasetsDraw(chart) {
      const {ctx, chartArea, scales} = chart;
      visibleTransitions.forEach((transition) => {
        const index = selected.findIndex((row) => row.run_at_utc === transition.run_at_utc);
        if (index < 0) return;
        const x = scales.x.getPixelForValue(index);
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = "#7a4a00";
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#7a4a00";
        ctx.font = "12px sans-serif";
        ctx.fillText(String(transition.new_version || ""), x + 4, chartArea.top + 14);
        ctx.restore();
      });
    }
  };
  scoreHistoryChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {mode: "index", intersect: false},
      scales: {y: {min: 0, max: 100, title: {display: true, text: "Score 0-100"}}},
      plugins: {
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const row = selected[items[0].dataIndex] || {};
              return [
                `Run: ${formatDateTime(row.run_at_utc)}`,
                `Data t/m: ${row.data_cutoff_utc || "n.v.t."}`,
                `Regime: ${row.regime_title || row.regime || "n.v.t."}`,
                `SOL: ${formatMoney(row.sol_price)}`,
                `Methode: ${row.method_version || "n.v.t."}`
              ];
            }
          }
        }
      }
    },
    plugins: [transitionPlugin]
  });
}

function segmentedScoreDatasets(rows) {
  const versions = Array.from(new Set(rows.map((row) => row.method_version || "onbekend")));
  const datasets = [];
  versions.forEach((version, versionIndex) => {
    const dash = versionIndex ? [6, 4] : [];
    datasets.push({
      label: `Huidige sterkte · methode ${version}`,
      data: rows.map((row) => row.method_version === version ? row.current_strength_score : null),
      borderColor: "#167a64",
      backgroundColor: "transparent",
      borderDash: dash,
      tension: 0.25,
      spanGaps: false
    });
    datasets.push({
      label: `Onderbouwing · methode ${version}`,
      data: rows.map((row) => row.method_version === version ? row.support_score : null),
      borderColor: "#2e5fb8",
      backgroundColor: "transparent",
      borderDash: dash,
      tension: 0.25,
      spanGaps: false
    });
  });
  return datasets;
}

function renderMethodVersionNote(rows, transitions) {
  const versions = Array.from(new Set(rows.map((row) => row.method_version).filter(Boolean)));
  setText("method-version-note", versions.length > 1
    ? `Let op: deze historie bevat ${versions.length} methodeversies. Scores over verschillende methodeversies zijn niet altijd één-op-één vergelijkbaar.`
    : "Alle getoonde runs gebruiken dezelfde methodeversie.");
  const target = document.getElementById("method-transition-list");
  if (!target) return;
  if (!transitions.length) {
    target.textContent = "Methodewijzigingen: geen overgang in de getoonde historie.";
    return;
  }
  const list = document.createElement("ul");
  list.className = "clean compact";
  transitions.forEach((transition) => {
    const li = document.createElement("li");
    li.textContent = `${formatDateTime(transition.run_at_utc)}: methode ${transition.new_version} gestart. ${transition.description || "Geen toelichting beschikbaar."}`;
    list.append(li);
  });
  target.replaceChildren(document.createTextNode("Methodewijzigingen:"), list);
}

function renderWaterfall(waterfall, drivers) {
  const target = document.getElementById("waterfall-chart");
  setText("waterfall-note", waterfall.available
    ? "Gewogen scorebrug sinds de vorige officiële productierun. Blokveranderingen worden vermenigvuldigd met hun weging in de eindscore."
    : (waterfall.reason_unavailable || "Waterfall niet beschikbaar."));
  setText("waterfall-summary", waterfall.summary || "");
  if (!waterfall.available) {
    target.replaceChildren(...drivers.map(rawDriverCard));
    return;
  }
  target.replaceChildren(scoreBridgeTable(waterfall));
}

function scoreBridgeItems(waterfall) {
  const items = [{
    label: "Vorige score",
    value: Number(waterfall.start_score),
    delta: null,
    kind: "score"
  }];
  (waterfall.steps || []).forEach((step) => {
    items.push({
      label: step.label,
      value: Number(step.end),
      delta: Number(step.delta),
      kind: step.kind || "driver"
    });
  });
  items.push({
    label: "Huidige score",
    value: Number(waterfall.end_score),
    delta: null,
    kind: "score current"
  });
  return items;
}

function scoreBridgeTable(waterfall) {
  const wrap = document.createElement("div");
  wrap.className = "score-bridge";
  const header = document.createElement("div");
  header.className = "score-bridge-row score-bridge-head";
  header.append(scoreBridgeCell("Stap"), scoreBridgeCell("Bijdrage aan eindscore"));
  wrap.append(header);
  scoreBridgeItems(waterfall).forEach((item) => {
    const row = document.createElement("div");
    row.className = `score-bridge-row ${scoreBridgeRowClass(item)}`;
    row.append(
      scoreBridgeCell(item.label),
      scoreBridgeCell(
        item.kind.includes("score") ? fmtScore100(item.value) : formatSignedPoint(item.delta),
        true
      )
    );
    wrap.append(row);
  });
  return wrap;
}

function scoreBridgeCell(text, numeric = false) {
  const cell = document.createElement("div");
  cell.className = numeric ? "numeric" : "";
  cell.textContent = text;
  return cell;
}

function scoreBridgeRowClass(item) {
  if (item.kind.includes("current")) return "score-row current";
  if (item.kind.includes("score")) return "score-row";
  if (!Number.isFinite(Number(item.delta)) || Math.abs(Number(item.delta)) < 0.005) {
    return "neutral-row";
  }
  return Number(item.delta) > 0 ? "positive-row" : "negative-row";
}

function formatSignedPoint(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)} scorepunten`;
}

function rawDriverCard(driver) {
  const card = document.createElement("article");
  card.className = "change-card";
  const span = document.createElement("span");
  span.textContent = driver.label;
  const strong = document.createElement("strong");
  strong.textContent = formatBlockDelta(driver.score_delta);
  const p = document.createElement("p");
  p.textContent = "Ruwe scoreverandering; gewogen bijdrage niet betrouwbaar vergelijkbaar.";
  card.append(span, strong, p);
  return card;
}

function renderTrackRecord(track) {
  const cards = [
    {
      label: "Publiek forward-trackrecord",
      value: `${track.official_signal_count || 0} signalen`,
      text: `${track.maturity_status || "Startfase"}${track.next_maturity_threshold ? ` · op weg naar ${track.next_maturity_threshold} runs` : ""}`,
      interpretation: `${track.forward_status || "Nog geen afgeronde publieke voorspellingen."} Technische updates: ${track.technical_run_count || 0}.`
    },
    {
      label: "Afgeronde forward-uitkomsten",
      value: String(track.resolved_outcome_count || 0),
      text: `${track.open_signal_count || 0} officiële signalen staan nog open.`,
      interpretation: `Unieke voorspeldagen: ${track.unique_prediction_days || 0}. Eerste voorspelling: ${formatDateTime(track.first_prediction_at_utc)}.`
    },
    {
      label: "Historische backtest 7d",
      value: `${track.backtest_7d?.prediction_count || 0} runs`,
      text: `Richting ${formatPctLike(track.backtest_7d?.directional_accuracy)} · Brier ${formatDecimal(track.backtest_7d?.brier_score)}.`,
      interpretation: `${track.backtest_status || "Backteststatus niet beschikbaar."} Brier skill ${formatDecimal(track.backtest_7d?.brier_skill)}.`
    },
    {
      label: "Datakwaliteit en methode",
      value: `${track.method_version_count || 0} versie(s)`,
      text: `Actueel: ${track.current_method_version || "n.v.t."}.`,
      interpretation: (track.quality_caps || []).join(" ") || `Onderbouwing: ${track.evidence_status || "n.v.t."}.`
    }
  ];
  const target = document.getElementById("trackrecord-cards");
  const explanation = document.createElement("p");
  explanation.className = "plain trackrecord-explanation";
  explanation.textContent = "De historische backtest test de methode op oudere marktdata. Het publieke forward-trackrecord volgt voorspellingen die daadwerkelijk vooraf zijn vastgelegd. Deze vormen van bewijs mogen niet met elkaar worden verward.";
  target.replaceChildren(...cards.map(explainerCard), explanation);
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

function renderInterpretationPage(interpretation, archiveIndex) {
  setText("llm-title", interpretation.title || "Duiding niet beschikbaar");
  setText("llm-date", interpretationDateText(interpretation));
  renderAnalysisText("llm-analysis", interpretation, {withDefaultHeadings: true});
  renderInterpretationAudit(interpretation);
  renderInterpretationInputs(interpretation.input_snapshot || {});
  setText("llm-note", interpretation.footer_note || "");
  renderInterpretationArchive(archiveIndex);
}

function renderAnalysisText(targetId, interpretation, options = {}) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const text = interpretation.analysis_text || interpretation.intro || "Geen analyse beschikbaar.";
  const blocks = parseAnalysisBlocks(text, options).slice(0, options.limit || Number.POSITIVE_INFINITY);
  target.replaceChildren(...blocks.map((block, index) => {
    const section = document.createElement("section");
    section.className = "analysis-block";
    const heading = block.heading || (options.withDefaultHeadings ? defaultAnalysisHeading(index) : "");
    if (heading) {
      const h3 = document.createElement("h3");
      h3.textContent = heading;
      section.append(h3);
    }
    const p = document.createElement("p");
    p.textContent = block.text;
    section.append(p);
    return section;
  }));
}

function parseAnalysisBlocks(text, options = {}) {
  const normalized = normalizeAnalysisTextForHeadings(text);
  const headingPattern = /(?:^|\n)\s*(Kort beeld|Wat trekt omhoog\?|Wat houdt tegen\?|Hoe stevig is dit\?|Conclusie|Kernbeeld|Spanning in de data|Bewijskracht|Waarop letten|Eindbeeld)\s*:\s*/g;
  const matches = Array.from(normalized.matchAll(headingPattern));
  if (!matches.length) {
    return splitPlainAnalysis(normalized, options);
  }
  const blocks = [];
  const prefix = normalized.slice(0, matches[0].index).trim();
  if (prefix) {
    blocks.push({
      heading: options.withDefaultHeadings ? defaultAnalysisHeading(0) : "",
      text: prefix
    });
  }
  matches.forEach((match, index) => {
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : normalized.length;
    blocks.push({heading: normalizeAnalysisHeading(match[1]), text: normalized.slice(start, end).trim()});
  });
  return blocks.filter((block) => block.text);
}

function normalizeAnalysisTextForHeadings(text) {
  const normalized = String(text || "").replace(/\r/g, "").trim();
  const headingLabels = "(Kort beeld|Wat trekt omhoog\\?|Wat houdt tegen\\?|Hoe stevig is dit\\?|Conclusie|Kernbeeld|Spanning in de data|Bewijskracht|Waarop letten|Eindbeeld)";
  return normalized.replace(new RegExp(`\\s+${headingLabels}\\s*:\\s*`, "g"), "\n$1: ");
}

function normalizeAnalysisHeading(heading) {
  const map = {
    "Kernbeeld": "Kort beeld",
    "Spanning in de data": "Wat trekt omhoog?",
    "Bewijskracht": "Hoe stevig is dit?",
    "Waarop letten": "Wat houdt tegen?",
    "Eindbeeld": "Conclusie"
  };
  return map[heading] || heading;
}

function splitPlainAnalysis(text, options = {}) {
  const paragraphs = text.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
  if (paragraphs.length > 1) {
    return paragraphs.map((part, index) => ({
      heading: options.withDefaultHeadings ? defaultAnalysisHeading(index) : "",
      text: part
    }));
  }
  const sentences = text.match(/[^.!?]+[.!?]+(?:\s|$)/g) || [text];
  const chunks = [];
  for (let index = 0; index < sentences.length; index += 3) {
    const chunkIndex = Math.floor(index / 3);
    chunks.push({
      heading: options.withDefaultHeadings ? defaultAnalysisHeading(chunkIndex) : "",
      text: sentences.slice(index, index + 3).join(" ").trim()
    });
  }
  return chunks.filter((block) => block.text);
}

function defaultAnalysisHeading(index) {
  return [
    "Kernbeeld",
    "Wat trekt omhoog?",
    "Wat houdt tegen?",
    "Hoe sterk is het bewijs?",
    "Waarop letten?"
  ][index] || "Vervolg";
}

function renderInterpretationAudit(interpretation) {
  const statusText = interpretation.status === "llm_success"
    ? "Automatische analyse gelukt"
    : "Vaste fallbacktekst gebruikt";
  const items = [
    ["Status", statusText],
    ["Model", interpretation.model || "n.v.t."],
    ["Provider", interpretation.provider || "n.v.t."],
    ["Analyse gemaakt", interpretation.llm_called_at_utc || "Niet aangeroepen"],
    ["Update", interpretation.generated_at_utc || "n.v.t."],
    ["Duiding voor", interpretation.interpretation_date || "n.v.t."],
    ["Data t/m", interpretation.data_cutoff_utc || "n.v.t."]
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

function interpretationDateText(interpretation) {
  const date = interpretation.interpretation_date || String(interpretation.data_cutoff_utc || "").slice(0, 10);
  const generated = interpretation.generated_at_utc || "n.v.t.";
  return `Duiding voor ${date || "n.v.t."} · gegenereerd ${generated}`;
}

function renderInterpretationArchive(archiveIndex) {
  const target = document.getElementById("llm-archive");
  const controls = document.getElementById("llm-archive-controls");
  const allEntries = archiveIndex?.entries || [];
  const entries = allEntries.slice(0, 8);
  if (!entries.length) {
    controls.replaceChildren();
    target.replaceChildren(emptyArchiveMessage());
    return;
  }
  controls.replaceChildren(archiveSelect(allEntries));
  target.replaceChildren(...entries.map((entry) => {
    const button = document.createElement("button");
    button.className = "archive-item";
    button.type = "button";
    const title = document.createElement("strong");
    title.textContent = entry.title || "Duiding";
    const meta = document.createElement("span");
    meta.textContent = `${entry.date} · sterkte ${entry.market_signal || "n.v.t."} · onderbouwing ${entry.evidence_quality || "n.v.t."}`;
    button.append(title, meta);
    button.addEventListener("click", async () => {
      try {
        const archived = await loadJson(entry.path);
        setText("llm-title", archived.title || "Duiding niet beschikbaar");
        setText("llm-date", interpretationDateText(archived));
        renderAnalysisText("llm-analysis", archived, {withDefaultHeadings: true});
        renderInterpretationAudit(archived);
        renderInterpretationInputs(archived.input_snapshot || {});
        setText("llm-note", archived.footer_note || "");
      } catch (error) {
        setText("llm-note", `Kon archiefitem niet laden: ${error.message}`);
      }
    });
    return button;
  }));
}

function archiveSelect(entries) {
  const wrap = document.createElement("div");
  wrap.className = "archive-select";
  const label = document.createElement("label");
  label.textContent = "Open oudere duiding";
  const select = document.createElement("select");
  entries.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.path;
    option.textContent = `${entry.date} · ${entry.title || "Duiding"}`;
    select.append(option);
  });
  const button = document.createElement("button");
  button.className = "button";
  button.type = "button";
  button.textContent = "Open";
  button.addEventListener("click", async () => {
    try {
      const archived = await loadJson(select.value);
      setText("llm-title", archived.title || "Duiding niet beschikbaar");
      setText("llm-date", interpretationDateText(archived));
      renderAnalysisText("llm-analysis", archived, {withDefaultHeadings: true});
      renderInterpretationAudit(archived);
      renderInterpretationInputs(archived.input_snapshot || {});
      setText("llm-note", archived.footer_note || "");
    } catch (error) {
      setText("llm-note", `Kon archiefitem niet laden: ${error.message}`);
    }
  });
  label.append(select);
  wrap.append(label, button);
  return wrap;
}

function emptyArchiveMessage() {
  const p = document.createElement("p");
  p.className = "plain";
  p.textContent = "Het archief wordt gevuld zodra de dagelijkse update duidingen publiceert.";
  return p;
}

function renderInterpretationInputs(facts) {
  const items = [
    ["Huidige sterkte", facts.market_signal],
    ["Onderbouwing", facts.evidence_quality],
    ["Koerskracht", facts.price_strength],
    ["Gebruik", facts.network_usage],
    ["Kapitaalstromen", facts.capital],
    ["Breedte ecosysteem", facts.ecosystem_breadth],
    ["SOL", facts.sol_price],
    ["Analoge dagen", facts.analog_count],
    ["Historisch positief", facts.analog_positive_frequency],
    ["Historische toets 7d", `${facts.backtest_7d?.prediction_count || 0} runs`]
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
    labeledValue("Onderbouwing", fmtScore100(dashboard.scores.evidence_quality)),
    labeledValue("Huidige sterkte", fmtScore100(dashboard.scores.market_signal)),
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
      label: "Test op ongeziene data",
      value: fmtScore100(components.out_of_sample_quality),
      text: "Meet prestaties op latere data die niet gebruikt is om het signaal te vormen.",
      interpretation: highIsBetter(components.out_of_sample_quality)
    },
    {
      label: "Historische toets 7d",
      value: formatDecimal(horizon7.brier_skill),
      text: "Vergelijkt de methode met een simpele basislijn.",
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
    text: `Richting: ${formatPctLike(row.directional_accuracy)}. Voorspelkwaliteit: ${formatDecimal(row.brier_skill)}.`,
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
    "Gemiddelde fout",
    "Voorspelkwaliteit",
    "Kans-afwijking"
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


function renderSignalResearch(research) {
  const rawRows = research.rows || [];
  const productionRows = rawRows.filter((row) => row.mode === "production");
  const filteredLegacyRows = rawRows.length !== productionRows.length;
  const totalRuns = filteredLegacyRows ? productionRows.length : (research.row_count_total || productionRows.length);
  setText("signal-research-summary", research.summary || "Nog geen signaalonderzoek beschikbaar.");
  renderStats("signal-research-stats", [
    {label: "Totaal runs", value: String(totalRuns)},
    {label: "Zichtbaar", value: `${productionRows.length} laatste runs`},
    {label: "Laatste update", value: research.generated_at_utc || "n.v.t."},
    {label: "Opslag", value: research.storage || "Parquet + JSON"}
  ]);
  const rows = productionRows.slice().reverse();
  const tableRows = rows.map((row) => [
    formatDateTime(row.run_at_utc),
    formatMoney(row.sol_price),
    formatMoney(row.btc_price),
    fmtScore100(row.current_strength_score),
    fmtScore100(row.support_score),
    fmtScore100(row.price_strength_score),
    fmtScore100(row.network_usage_score),
    fmtScore100(row.capital_flows_score),
    fmtScore100(row.ecosystem_breadth_score),
    row.regime_title || row.regime || "n.v.t."
  ]);
  document.getElementById("signal-research-table").replaceChildren(table([
    "Run",
    "SOL",
    "BTC",
    "Sterkte",
    "Onderbouwing",
    "Koerskracht",
    "Gebruik",
    "Kapitaal",
    "Breedte",
    "Beeld"
  ], tableRows));
}

function renderPredictivePower(power) {
  setText("predictive-summary", power.summary || "Nog geen voorspellingskracht beschikbaar.");
  const maturity = power.maturity || {};
  renderStats("predictive-scorecard", [
    {label: "Status", value: maturity.status || "Trackrecord in opbouw"},
    {label: "Unieke signaaldagen", value: String(maturity.unique_signal_days || 0)},
    {label: "Forward observaties", value: String(maturity.usable_forward_observations || 0)},
    {label: "Redelijke ondergrens", value: `${maturity.min_reasonable_observations || 20} observaties`}
  ]);
  renderPredictiveHighlights(power);
  const target = document.getElementById("predictive-sections");
  const sections = power.sections || [];
  target.replaceChildren(...sections.map(predictiveSectionElement));
  const combination = power.combination || {};
  setText("predictive-combination-definition", combination.definition || "Nog geen combinatie-analyse beschikbaar.");
  document.getElementById("predictive-combination-table").replaceChildren(
    predictiveTable(combination.rows || [])
  );
  document.getElementById("predictive-methodology").replaceChildren(
    ...(power.methodology || []).map(listItem)
  );
  document.getElementById("predictive-warnings").replaceChildren(
    ...(power.warnings || []).map(listItem)
  );
}

function renderPredictiveHighlights(power) {
  const target = document.getElementById("predictive-highlights");
  const sections = power.sections || [];
  const bestRows = sections.map((section) => ({section, row: section.best})).filter((item) => item.row);
  const cards = [];
  if (bestRows.length) {
    bestRows.forEach(({section, row}) => {
      cards.push(predictiveHighlightCard(
        section.title,
        `${row.bucket_label}, ${row.horizon_days} dagen`,
        `${formatPctPlain(row.positive_rate)} historisch positief; ${formatPp(row.difference_vs_baseline)} vs baseline.`
      ));
    });
  } else {
    cards.push(predictiveHighlightCard(
      "Nog geen volwassen signaal",
      power.maturity?.status || "Trackrecord in opbouw",
      "Er zijn nog te weinig forward observaties om één horizon of bucket als voorspellend te markeren."
    ));
  }
  cards.push(predictiveHighlightCard(
    "Bron",
    power.source || "signaalonderzoek",
    "Alleen vastgelegde productieruns uit het append-only signaalonderzoek tellen mee."
  ));
  cards.push(predictiveHighlightCard(
    "Interpretatie",
    "Baseline is leidend",
    "Een hit-rate is pas interessant als die duidelijk boven de algemene baseline in dezelfde periode ligt."
  ));
  target.replaceChildren(...cards);
}

function predictiveHighlightCard(label, value, text) {
  const card = document.createElement("article");
  card.className = "explainer-card";
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  const p = document.createElement("p");
  p.textContent = text;
  card.append(span, strong, p);
  return card;
}

function predictiveSectionElement(section) {
  const wrap = document.createElement("section");
  wrap.className = "predictive-section";
  const h3 = document.createElement("h3");
  h3.textContent = section.title;
  const p = document.createElement("p");
  p.className = "plain";
  p.textContent = section.description || "";
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap compact-table";
  tableWrap.append(predictiveTable(section.rows || []));
  wrap.append(h3, p, tableWrap);
  return wrap;
}

function predictiveTable(rows) {
  const tableRows = (rows || []).map((row) => [
    `${row.horizon_days}d`,
    row.bucket_label,
    formatPctPlain(row.positive_rate),
    formatSignedPct(row.median_return),
    String(row.observations || 0),
    formatPp(row.difference_vs_baseline),
    row.reliability || "n.v.t."
  ]);
  return table([
    "Horizon",
    "Scorebucket",
    "Historisch positief",
    "Mediaan rendement",
    "Observaties",
    "Vs baseline",
    "Betrouwbaarheid"
  ], tableRows);
}

function listItem(text) {
  const li = document.createElement("li");
  li.textContent = text;
  return li;
}

function formatDateTime(value) {
  if (!value) return "n.v.t.";
  return String(value).replace("T", " ").replace("Z", " UTC");
}

function formatMoney(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  return `$${Number(value).toLocaleString("en-US", {maximumFractionDigits: 2})}`;
}

function formatSignedPct(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  const pct = Number(value) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function formatPctPlain(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatPp(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "n.v.t.";
  const pp = Number(value) * 100;
  const sign = pp > 0 ? "+" : "";
  return `${sign}${pp.toFixed(1)} pp`;
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
      label: "Test op ongeziene data",
      value: "Controle buiten trainingsdata",
      text: "De methode wordt beoordeeld op latere data die niet gebruikt is om het signaal te bepalen.",
      interpretation: "Hoger is beter; laag betekent dat het signaal historisch nog kwetsbaar is."
    },
    {
      label: "Voorspelkwaliteit",
      value: "Meerwaarde t.o.v. basislijn",
      text: "Vergelijkt de fout van dit model met een simpele referentie zoals historische frequentie.",
      interpretation: "Boven 0 is beter dan de basislijn; onder 0 is slechter."
    },
    {
      label: "Kans-afwijking",
      value: "Betrouwbaarheid van kansen",
      text: "Meet of uitspraken over waarschijnlijkheid passen bij wat later werkelijk gebeurde.",
      interpretation: "Lager is beter; hoog betekent dat kansen te zeker of te voorzichtig kunnen zijn."
    },
    {
      label: "Voorzichtigheidsregels",
      value: "Voorzichtigheidsregels",
      text: "Beperkingen die voorkomen dat een score te stellig wordt bij beperkte onderbouwing.",
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
  sourceTitle.textContent = "Datakwaliteit voor dit blok";
  const sourceIntro = document.createElement("p");
  sourceIntro.className = "plain";
  sourceIntro.textContent = "Compacte bronstatus. De volledige broncontrole staat onder Bewijs.";
  const sourceStats = document.createElement("div");
  sourceStats.className = "stat-row";
  const rows = tab.sources || [];
  const ok = rows.filter((source) => source.status === "Succesvol").length;
  sourceStats.replaceChildren(
    statNode("Bronnen", String(rows.length)),
    statNode("Succesvol", `${ok}/${rows.length || 0}`),
    statNode("Laatste status", rows.map((source) => source.name).slice(0, 3).join(", ") || "n.v.t.")
  );
  const sourceLink = document.createElement("button");
  sourceLink.type = "button";
  sourceLink.className = "button link-button";
  sourceLink.textContent = "Bekijk volledige broncontrole";
  sourceLink.addEventListener("click", () => navigateTo("#bewijs-kwaliteit"));
  sources.append(sourceTitle, sourceIntro, sourceStats, sourceLink);

  target.replaceChildren(hero, components, trend, sources);
}

function statNode(label, value) {
  const div = document.createElement("div");
  div.className = "stat";
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  div.append(span, strong);
  return div;
}

function ecosystemTabFromDashboard(dashboard) {
  const networkTab = dashboard.indicator_tabs?.network || {};
  const ecosystemBlock = (dashboard.scores?.block_details || []).find((item) => item.key === "ecosystem_breadth")
    || (dashboard.scores?.block_details || []).find((item) => String(item.title || "").toLowerCase().includes("ecosysteem"))
    || {};
  const keywords = ["ecosysteem", "breedte", "token", "concentratie"];
  const components = (networkTab.components || []).filter((component) => {
    const text = `${component.label || ""} ${component.description || ""}`.toLowerCase();
    return keywords.some((keyword) => text.includes(keyword));
  });
  const sources = [
    ...(networkTab.sources || []),
    ...(dashboard.data_audit?.sources || [])
  ].filter((source, index, all) => {
    const text = `${source.name || ""} ${source.role || ""}`.toLowerCase();
    return (text.includes("coingecko") || text.includes("ecosysteem"))
      && all.findIndex((candidate) => candidate.name === source.name && candidate.role === source.role) === index;
  });
  return {
    title: "Ecosysteem",
    subtitle: "Breedte van beweging binnen het Solana-ecosysteem.",
    summary: ecosystemBlock.summary || "Meet of de beweging breder is dan alleen SOL zelf.",
    note: ecosystemBlock.status || "Experimenteel: deze indicator weegt beperkt mee.",
    score: ecosystemBlock.score ?? dashboard.current?.ecosystem_breadth_score,
    weight: ecosystemBlock.weight ?? 0.1,
    status: ecosystemBlock.status || "Experimenteel, beperkt meegewogen",
    components: components.length ? components : (ecosystemBlock.metrics || []).map((metric) => ({
      label: metric.label,
      value: metric.value,
      score: ecosystemBlock.score,
      weight: "Binnen ecosysteemblok",
      description: "Onderliggende maatstaf voor ecosysteembreedte."
    })),
    trend: {
      rows: networkTab.trend?.rows || [],
      series: (networkTab.trend?.series || []).filter((series) => {
        const text = `${series.label || ""} ${series.key || ""}`.toLowerCase();
        return keywords.some((keyword) => text.includes(keyword));
      })
    },
    sources
  };
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
  return `De onderbouwing is ${fmtScore100(dashboard.scores.evidence_quality)}. De huidige conclusie steunt op ${count} vergelijkbare eerdere dagen en een historische toets met ${skillText}.`;
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
    return "Deze horizon draagt voorzichtig positieve onderbouwing bij.";
  }
  if ((skill || 0) > 0) return "De foutscore is licht positief, maar richting blijft gemengd.";
  return "Deze horizon toont nog weinig voorspellende meerwaarde.";
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
  activateNavigation();
  const [dashboard, backtest, ledger, glossary, interpretation, interpretationArchive, signalResearch, predictivePower, overview, overviewHistory] = await Promise.all([
    loadJson("./data/dashboard.json"),
    loadJson("./data/backtest_summary.json"),
    loadJson("./data/ledger.json"),
    loadJson("./data/glossary.json"),
    loadJson("./data/interpretation.json"),
    loadJson("./data/interpretations/index.json").catch(() => ({entries: []})),
    loadJson("./data/signaalonderzoek.json").catch(() => ({rows: [], row_count_total: 0, row_count_visible: 0})),
    loadJson("./data/predictive_power.json").catch(() => ({sections: [], warnings: [], methodology: []})),
    loadJson("./data/overview.json").catch(() => ({current_run: null, previous_run: null, warnings: []})),
    loadJson("./data/overview_history.json").catch(() => ({rows: []}))
  ]);
  if (dashboard.demo_notice) {
    const notice = document.getElementById("demo-notice");
    notice.hidden = false;
    notice.textContent = dashboard.demo_notice;
  }
  const solPrice = dashboard.current.live_sol_price ?? dashboard.current.sol_price;
  setText("sol-price", Number.isFinite(Number(solPrice)) ? `$${Number(solPrice).toFixed(2)}` : "n.v.t.");
  setText("updated-at", dashboard.generated_at_utc);
  setText("data-cutoff", dashboard.data_cutoff_utc);
  setText("method-version", dashboard.method_version);
  renderIndicatorTab("price-tab", dashboard.indicator_tabs?.price);
  renderIndicatorTab("network-tab", dashboard.indicator_tabs?.network);
  renderIndicatorTab("capital-tab", dashboard.indicator_tabs?.capital);
  renderIndicatorTab("ecosystem-tab", ecosystemTabFromDashboard(dashboard));
  setText("analog-summary", dashboard.historical_context?.summary || "");
  renderStats("analog-stats", dashboard.historical_context?.stats || []);
  setText("audit-summary", dashboard.data_audit?.summary || "");
  renderStats("audit-stats", dashboard.data_audit?.freshness || []);
  renderSources(dashboard.data_audit);
  setText("audit-warnings", (dashboard.data_audit?.warnings || []).join(" ") || "Geen waarschuwingen bij deze update.");
  window.renderGlossary(glossary);
  renderSignalResearch(signalResearch);
  renderPredictivePower(predictivePower);
  renderEvidencePage(dashboard, backtest, ledger);
  renderInterpretationPage(interpretation, interpretationArchive);
  renderAnalysisText("actueel-duiding", interpretation, {withDefaultHeadings: true, limit: 5});
  const effectiveOverview = overview.current_run ? overview : fallbackOverview(dashboard);
  effectiveOverview.dashboard = dashboard;
  renderOverview(effectiveOverview, overviewHistory);
  applyRouteFromHash();
}

function fallbackOverview(dashboard) {
  return {
    current_run: {
      run_at_utc: dashboard.generated_at_utc,
      data_cutoff_utc: dashboard.data_cutoff_utc,
      method_version: dashboard.method_version,
      sol_price: dashboard.current?.sol_price,
      current_strength_score: dashboard.scores?.market_signal,
      support_score: dashboard.scores?.evidence_quality,
      regime: dashboard.summary?.regime,
      regime_title: dashboard.summary?.regime_title
    },
    previous_run: null,
    changes: {available: false},
    largest_changes: {},
    drivers: [],
    waterfall: {available: false, reason_unavailable: "Nog onvoldoende officiële runs voor een waterfall."},
    track_record: {},
    what_would_change: dashboard.summary?.what_would_change || []
  };
}

main().catch((error) => {
  document.body.prepend(Object.assign(document.createElement("p"), {className: "notice", textContent: error.message}));
});
