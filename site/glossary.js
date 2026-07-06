window.renderGlossary = function renderGlossary(items) {
  const root = document.getElementById("glossary");
  root.replaceChildren(...items.map((item) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = item.term;
    [
      ["Kort", item.short],
      ["Waarom", item.why],
      ["Berekening", item.calculation],
      ["Beperking", item.limitation],
      ["Voorbeeld", item.example]
    ].forEach(([label, value]) => {
      const p = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = `${label}: `;
      p.append(strong, document.createTextNode(value));
      details.append(p);
    });
    details.prepend(summary);
    return details;
  }));
};
