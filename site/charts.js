window.renderAnalogChart = function renderAnalogChart(rows) {
  const canvas = document.getElementById("analog-chart");
  if (!canvas || !window.Chart) return;
  const values = rows.map((r) => r.return_7d).filter((x) => Number.isFinite(x));
  const buckets = [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3];
  const counts = buckets.map((b, i) => values.filter((v) => v >= b && v < (buckets[i + 1] ?? 1)).length);
  new Chart(canvas, {
    type: "bar",
    data: { labels: buckets.map((b) => `${Math.round(b * 100)}%`), datasets: [{ label: "Aantal analogieën", data: counts, backgroundColor: "#167a64" }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });
};

