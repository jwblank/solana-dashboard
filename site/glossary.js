window.renderGlossary = function renderGlossary(items) {
  const root = document.getElementById("glossary");
  root.replaceChildren(...items.map((item) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = item.term;
    const p = document.createElement("p");
    p.textContent = `${item.short} Waarom: ${item.why} Berekening: ${item.calculation} Beperking: ${item.limitation} Voorbeeld: ${item.example}`;
    details.append(summary, p);
    return details;
  }));
};

