// Price history line chart (Chart.js). Data comes from monitor/history.py via
// <script type="application/json" id="price-chart-data"> in product.html.
(function () {
  var dataElement = document.getElementById("price-chart-data");
  var canvas = document.getElementById("price-chart");
  if (!dataElement || !canvas || !window.Chart) return;

  var data = JSON.parse(dataElement.textContent);

  // Colors come from the CSS variables, so the chart follows light/dark mode.
  var styles = getComputedStyle(document.documentElement);
  function cssVar(name) { return styles.getPropertyValue(name).trim(); }
  var colors = [1, 2, 3, 4, 5].map(function (i) { return cssVar("--series-" + i); });

  // Each store also gets its own line style, so it never depends on color alone.
  var dashes = [[], [6, 4], [2, 3], [10, 3, 2, 3], [1, 2]];
  var pointStyles = ["circle", "rect", "triangle", "rectRot", "crossRot"];

  // Same font as the rest of the site.
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

  var money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var datasets = data.series.map(function (series, i) {
    var color = colors[i % colors.length];
    return {
      label: series.store,
      // Prices arrive as text ("929.99"); Number() only here, just to draw.
      data: series.prices.map(function (price) { return price === null ? null : Number(price); }),
      borderColor: color,
      backgroundColor: color,
      borderDash: dashes[i % dashes.length],
      borderWidth: 2,
      pointStyle: pointStyles[i % pointStyles.length],
      pointRadius: 3.5,
      pointHoverRadius: 6,
      spanGaps: true,
      tension: 0,
    };
  });

  new Chart(canvas, {
    type: "line",
    data: { labels: data.labels, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion ? false : { duration: 250 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: cssVar("--text"), usePointStyle: true, padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: function (context) {
              return " " + context.dataset.label + ": " + money.format(context.parsed.y);
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: cssVar("--muted") }, grid: { color: cssVar("--border") } },
        y: {
          ticks: { color: cssVar("--muted"), callback: function (value) { return money.format(value); } },
          grid: { color: cssVar("--border") },
        },
      },
    },
  });
})();
