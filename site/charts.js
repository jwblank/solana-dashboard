window.renderAnalogChart = function renderAnalogChart(rows) {
  const canvas = document.getElementById("analog-chart");
  if (!canvas || !window.Chart) return;
  const values = rows.map((r) => r.return_7d).filter((x) => Number.isFinite(x));
  const bins = [
    {label: "< -20%", min: -Infinity, max: -0.2},
    {label: "-20% tot -10%", min: -0.2, max: -0.1},
    {label: "-10% tot 0%", min: -0.1, max: 0},
    {label: "0% tot 10%", min: 0, max: 0.1},
    {label: "10% tot 20%", min: 0.1, max: 0.2},
    {label: "> 20%", min: 0.2, max: Infinity}
  ];
  const counts = bins.map((bin) => values.filter((v) => v >= bin.min && v < bin.max).length);
  new Chart(canvas, {
    type: "bar",
    data: { labels: bins.map((bin) => bin.label), datasets: [{ label: "Aantal analogieën", data: counts, backgroundColor: "#167a64" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });
};
