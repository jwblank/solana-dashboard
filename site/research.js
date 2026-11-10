/* Versioned research alongside the original monitor. Values are never edited in the UI. */
(() => {
  const number = new Intl.NumberFormat("nl-NL", {maximumFractionDigits: 3});
  const integer = new Intl.NumberFormat("nl-NL", {maximumFractionDigits: 0});
  const percent = new Intl.NumberFormat("nl-NL", {maximumFractionDigits: 1});
  const pct = (x) => x == null ? "—" : `${percent.format(x * 100)}%`;
  const decimal = (x) => x == null ? "—" : number.format(x);
  const date = (x) => x ? new Date(x.length === 10 ? `${x}T12:00:00Z` : x)
    .toLocaleDateString("nl-NL", {day: "numeric", month: "short", year: "numeric"}) : "—";
  const direction = (x) => ({up: "Stijging", down: "Daling", flat: "Ongewijzigd"}[x] || "—");
  let evidenceChart = null;

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function replace(id, ...nodes) { document.getElementById(id).replaceChildren(...nodes); }
  function text(id, value) { document.getElementById(id).textContent = value; }
  function table(headers, rows) {
    const node = el("table");
    const head = el("thead");
    const title = el("tr");
    headers.forEach((label) => {
      const th = el("th", label); th.scope = "col"; title.append(th);
    });
    head.append(title);
    const body = el("tbody");
    rows.forEach((cells) => {
      const row = el("tr");
      cells.forEach((value, i) => {
        const cell = el(i === 0 ? "th" : "td");
        if (i === 0) cell.scope = "row";
        cell.append(value instanceof Node ? value : document.createTextNode(value));
        row.append(cell);
      });
      body.append(row);
    });
    node.append(head, body);
    return node;
  }
  function link(label, path) {
    const a = el("a", label, "button"); a.href = path; a.download = ""; return a;
  }
  function tally(label, value, note) {
    const card = el("div", null, "research-tally");
    card.append(el("span", label), el("strong", value), el("small", note));
    return card;
  }
  function countCorrect(correct, total) {
    return total ? `${correct}/${total} · ${pct(correct / total)}` : "Nog geen uitkomsten";
  }
  function evaluation(candidate, phase, horizon) {
    return candidate.evaluations.find((x) => x.phase === phase && x.horizon_days === horizon);
  }

  window.renderResearchMonitor = (payload) => {
    if (!payload?.protocol) {
      text("research-state", "Onderzoeksgegevens konden niet worden geladen. De bestaande monitor staat hieronder.");
      document.getElementById("research-content").hidden = true;
      return;
    }
    const protocol = payload.protocol;
    const selector = document.getElementById("research-phase");
    const horizons = document.getElementById("research-horizon");
    text("research-state", `Protocol vastgelegd op ${date(protocol.locked_at_utc)}. Gegevens t/m ${date(payload.data_cutoff)}. Zeven dagen is de primaire toets.`);
    const newRows = payload.records.filter((r) => r.phase === "prospective" && r.horizon_days === 7);
    const days = new Set(newRows.map((r) => r.date)).size;
    const completed = new Set(newRows.filter((r) => r.sol_return != null).map((r) => r.date)).size;
    replace("research-progress",
      tally("Vaste onderzoekskandidaten", "3", "Elke kandidaat heeft een eigen definitie en vergelijking."),
      tally("Nieuw vastgelegde meetdagen", integer.format(days), "Voorspelling geregistreerd vóór het instapslot."),
      tally("Afgeronde meetdagen · 7 dagen", integer.format(completed), "Eén meetdag kan voor alle drie kandidaten worden getoetst.")
    );
    replace("research-candidates", ...payload.candidates.map((candidate) => {
      const card = el("article", null, "research-candidate");
      const latest = candidate.latest;
      const value = latest?.feature_value;
      const result = value == null ? "Onvoldoende invoer"
        : candidate.unit === "fraction" ? pct(value) : value ? "Actief" : "Niet actief";
      card.append(el("h4", candidate.name), el("strong", result, "research-current-value"),
        el("p", candidate.definition, "plain"));
      card.append(el("small", `Eerste publicatie bij datadag ${date(latest?.date)}.`, "plain"));
      if (latest?.phase === "prospective" && latest.probability_up != null) {
        const details = el("details", null, "research-detail");
        details.append(el("summary", "Vastgelegde modelvoorspelling · 7 dagen"),
          el("p", `Het model combineert dit kenmerk met de koersbasis. Modelrichting: ${direction(latest.predicted_direction).toLowerCase()}; koersbasis: ${latest.baseline_probability_up >= .5 ? "stijging" : "daling"}.`),
          el("p", `Modeluitvoer voor stijging: ${pct(latest.probability_up)}; basis: ${pct(latest.baseline_probability_up)}. Dit zijn nog geen betrouwbaar vastgestelde kansen.`, "plain"));
        card.append(details);
      } else {
        card.append(el("p", latest?.phase === "prospective" ? latest.unavailable_reason
          : "De eerste nieuwe voorspelling volgt bij een productierun na de protocolstart.", "research-experimental"));
      }
      return card;
    }));

    function draw() {
      const phase = selector.value;
      const horizon = Number(horizons.value);
      const selected = payload.candidates.map((candidate) => ({candidate, metrics: evaluation(candidate, phase, horizon)}));
      const rows = payload.records.filter((r) => r.phase === phase && r.horizon_days === horizon);
      const prospective = phase === "prospective";
      const mature = rows.filter((r) => r.sol_return != null);
      text("research-scope", prospective
        ? `Nieuwe toets · ${horizon} dagen. Alleen vóór instap vastgelegde voorspellingen tellen hier mee.`
        : `Historische reconstructie · ${horizon} dagen. Deze periode is gebruikt bij het vinden van de kandidaten en bevestigt ze niet onafhankelijk.`);
      document.getElementById("research-scope").classList.toggle("notice", !prospective);
      const dayCount = new Set(rows.map((r) => r.date)).size;
      const matureDays = new Set(mature.map((r) => r.date)).size;
      const scoredReference = selected.find(({metrics: m}) => m.scored_n)?.metrics;
      text("research-result-status", !dayCount ? "Nog geen nieuwe meetdagen. De dagelijkse productierun registreert de eerste voorspellingen automatisch."
        : !matureDays ? `${dayCount} ${dayCount === 1 ? "meetdag" : "meetdagen"} vastgelegd; de uitkomsten zijn nog niet beschikbaar.`
          : `${matureDays} afgeronde van ${dayCount} meetdagen. Vergelijk de uitbreiding steeds met haar eigen basis op dezelfde dagen.`);
      text("research-simple-baselines", scoredReference
        ? `Eenvoudige vergelijkingen op dezelfde modeldagen — kansfout bij 50/50: 0,25; altijd stijging: ${decimal(scoredReference.always_up_brier)}; altijd daling: ${decimal(scoredReference.always_down_brier)}. Ook hier is lager beter.`
        : "De vergelijking met 50/50, altijd stijging en altijd daling verschijnt zodra modeluitkomsten beschikbaar zijn.");
      const names = ["Kandidaat", "Kansfout: basis → uitbreiding", "Verbetering + 95%-interval", "Stijgingen herkend", "Dalingen herkend", "Modeluitkomsten / losse vensters"];
      replace("research-model-table", table(names, selected.map(({candidate, metrics: m}) => {
        const improvement = el("div");
        improvement.append(el("strong", decimal(m.brier_improvement)));
        const [lo, hi] = m.brier_improvement_ci95;
        improvement.append(el("small", lo == null ? "Nog te weinig losse vensters voor een interval."
          : `${decimal(lo)} tot ${decimal(hi)}${lo <= 0 && hi >= 0 ? " · nul valt binnen het interval" : ""}`));
        return [candidate.name, m.scored_n ? `${decimal(m.baseline_brier)} → ${decimal(m.brier)}` : "Nog geen modeluitkomsten",
          improvement, countCorrect(m.up_correct_n, m.actual_up_n),
          countCorrect(m.down_correct_n, m.actual_down_n), `${m.scored_n} / ${m.nonoverlap_n}`];
      })));
      drawChart(selected);
      replace("research-rule-table", table(
        ["Dalingsregel", "Actieve dagen / losse vensters", "Daarna gedaald", "SOL daarna", "Overige dagen", "SOL minus BTC"],
        selected.filter(({candidate}) => candidate.unit === "boolean").map(({candidate, metrics: m}) => [
          candidate.name, `${m.active_n} / ${m.active_nonoverlap_n}`,
          countCorrect(m.active_negative_n, m.active_n), pct(m.active_mean_sol),
          `${pct(m.inactive_mean_sol)} · n=${m.inactive_n}`, pct(m.active_mean_relative)
        ])
      ));
      replace("research-calibration", table(
        ["Kandidaat", "Voorspelde kans", "Gemiddelde modelkans", "Werkelijk gestegen", "Aantal"],
        selected.flatMap(({candidate, metrics: m}) => m.calibration.filter((b) => b.n).map((b) => [
          candidate.name, `${pct(b.from)}–${pct(b.through)}`, pct(b.predicted), pct(b.observed), String(b.n)
        ]))
      ));
      text("research-calibration-empty", selected.some(({metrics: m}) => m.scored_n) ? ""
        : "Nog geen afgeronde modelvoorspellingen in deze selectie.");
      const logRows = [...rows].sort((a, b) => b.date.localeCompare(a.date) || a.candidate_id.localeCompare(b.candidate_id));
      const limited = logRows.slice(0, 60);
      text("research-log-count", `${logRows.length} voorspellingen; de laatste ${limited.length} staan hieronder. De download bevat alle regels en controlehashes.`);
      replace("research-log", table(
        ["Datadag", "Kandidaat", "Verwachting model", "Kans stijging / basis", "SOL-uitkomst", "Status"],
        limited.map((r) => [date(r.date), payload.candidates.find((c) => c.candidate_id === r.candidate_id)?.name || r.candidate_id,
          direction(r.predicted_direction), `${pct(r.probability_up)} / ${pct(r.baseline_probability_up)}`,
          pct(r.sol_return), r.sol_return != null ? "Afgerond"
            : `Open · vanaf ${date(r.outcome_after_utc)}${r.model_available ? "" : " · model niet beschikbaar"}`])
      ));
      text("research-log-empty", logRows.length ? "" : "Nog geen voorspellingen in deze selectie.");
    }
    selector.addEventListener("change", draw);
    horizons.addEventListener("change", draw);
    draw();

    const weekdays = payload.weekday_diagnostics || [];
    replace("research-weekdays", table(["Datadag", "Score precies 55", "Aantal dagen"], weekdays.map((r) => [
      r.weekday, `${r.capped_n}/${r.n} · ${pct(r.capped_n / r.n)}`, String(r.n)
    ])));
    const shadow = payload.shadow_quality.at(-1);
    text("research-shadow-status", !shadow ? "De alternatieve score start bij de eerstvolgende volledige productierun. Er wordt geen alternatieve historie achteraf verzonnen."
        : shadow.alternative_quality == null ? `Alternatieve score nog niet beschikbaar: ${shadow.evaluation.reason}`
        : `Datadag ${date(shadow.data_cutoff_utc.slice(0, 10))}: oorspronkelijke onderbouwing ${decimal(shadow.original_quality)}; alternatieve onderbouwing ${decimal(shadow.alternative_quality)}. Dit zijn scores op 100, geen koerskansen.`);
    if (shadow?.evaluation?.available) {
      text("research-shadow-period", `Alternatieve backtest: ${date(shadow.evaluation.from)} t/m ${date(shadow.evaluation.through)}; 26 testmomenten per weekdag. De dagelijkse weekuitkomsten overlappen.`);
    }
    const archive = payload.baseline_archive;
    text("research-archive-status", `${archive.file_count} oorspronkelijke bestanden veiliggesteld. Archief, alle oorspronkelijke ledgerregels en alle oorspronkelijke Parquet-cellen gecontroleerd.`);
    text("research-archive-hash", `SHA-256: ${archive.sha256}`);
    replace("research-downloads", link("Oorspronkelijk data-archief", archive.archive_path),
      link("Archiefcontrole", archive.manifest_path),
      ...payload.downloads.map((r) => link(r.name, r.path)));
    replace("research-limitations", ...payload.limitations.map((r) => el("li", r)));
    replace("research-protocol", ...[
      ["Protocol", `${protocol.protocol_id} · versie ${protocol.version}`],
      ["Oorspronkelijke bronnen", payload.source_policy],
      ["Instap en uitstap", protocol.entry_policy],
      ["Vooraf vastgelegd", protocol.prospective_policy],
      ["Training", protocol.training_policy],
      ["Vergelijking", protocol.comparison_policy],
      ["Onzekerheid", protocol.uncertainty_policy],
      ["Wijzigingen", protocol.change_policy]
    ].flatMap(([label, value]) => [el("dt", label), el("dd", value)]));
  };

  function drawChart(selected) {
    if (evidenceChart) evidenceChart.destroy();
    const available = selected.filter(({metrics: m}) => m.scored_n);
    document.getElementById("research-chart-wrap").hidden = !available.length;
    if (!available.length || typeof Chart === "undefined") return;
    evidenceChart = new Chart(document.getElementById("research-brier-chart"), {
      type: "bar",
      data: {
        labels: available.map(({candidate}) => candidate.name),
        datasets: [
          {label: "Basis: koersontwikkeling + kalender", data: available.map(({metrics: m}) => m.baseline_brier), backgroundColor: "#94a3b8"},
          {label: "Basis + onderzoekskandidaat", data: available.map(({metrics: m}) => m.brier), backgroundColor: "#0f766e"}
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {legend: {position: "bottom"}, tooltip: {callbacks: {label: (ctx) => `${ctx.dataset.label}: ${decimal(ctx.raw)}`}}},
        scales: {y: {beginAtZero: true, title: {display: true, text: "Kansfout (Brier) · lager is beter"}}}
      }
    });
  }
})();
