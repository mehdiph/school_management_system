/*
 * Daily attendance-rate trend (director/attendance.html).
 *
 * Progressive enhancement: the page ships the same numbers as a table
 * (open by default). When Chart.js (vendored under static/vendor) and
 * the data are here, the chart is shown and the table folds away into
 * its <details>, still one click from every value.
 *
 * One series -- the attendance rate -- so no legend box: the heading
 * names it. Closure days are a neutral full-height band with their own
 * tooltip ("تعطیل: ..."), never a zero; days without records are gaps.
 * Time runs right to left (RTL), the y axis sits on the right.
 */
(function () {
  "use strict";

  var host = document.getElementById("attendanceTrend");
  var source = document.getElementById("attendance-trend-data");
  if (!host || !source || !window.Chart) return;

  var data = JSON.parse(source.textContent);
  var css = getComputedStyle(document.documentElement);
  function token(name, fallback) {
    return (css.getPropertyValue(name) || "").trim() || fallback;
  }

  var SERIES = token("--primary", "#d96a30");
  var BAND = token("--gray-100", "#f3f4f6");
  var GRID = token("--gray-200", "#e5e7eb");
  var INK = token("--gray-600", "#4b5563");
  var SURFACE = "#ffffff";

  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }

  // A vertical hairline on the hovered day: the reader aims at a date.
  var crosshair = {
    id: "crosshair",
    afterDatasetsDraw: function (chart) {
      var active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      var x = active[0].element.x;
      var area = chart.chartArea;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = INK;
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, area.top);
      ctx.lineTo(x, area.bottom);
      ctx.stroke();
      ctx.restore();
    }
  };

  window.Chart.defaults.font.family = "Vazirmatn, Tahoma, sans-serif";
  window.Chart.defaults.color = INK;

  var canvas = host.querySelector("canvas");
  new window.Chart(canvas, {
    data: {
      labels: data.labels,
      datasets: [
        {
          type: "line",
          label: "نرخ حضور",
          data: data.rates,
          borderColor: SERIES,
          backgroundColor: SERIES,
          borderWidth: 2,
          borderJoinStyle: "round",
          borderCapStyle: "round",
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBorderColor: SURFACE,
          pointBorderWidth: 2,
          pointHitRadius: 14,
          spanGaps: false,
          order: 1
        },
        {
          type: "bar",
          label: "تعطیل",
          data: data.closed.map(function (closed) { return closed ? 100 : null; }),
          backgroundColor: BAND,
          hoverBackgroundColor: GRID,
          borderWidth: 0,
          barPercentage: 1,
          categoryPercentage: 1,
          order: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { top: 8 } },
      scales: {
        x: {
          reverse: true,
          grid: { display: false },
          border: { color: GRID },
          ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 12 }
        },
        y: {
          position: "right",
          min: 0,
          max: 100,
          border: { display: false },
          grid: { color: GRID, lineWidth: 1 },
          ticks: {
            stepSize: 25,
            callback: function (value) { return fa(value) + "٪"; }
          }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: true,
          textDirection: "rtl",
          backgroundColor: "#1f2937",
          padding: 10,
          displayColors: false,
          filter: function (item) { return item.raw !== null; },
          callbacks: {
            title: function (items) {
              return items.length ? data.titles[items[0].dataIndex] : "";
            },
            label: function (item) {
              var i = item.dataIndex;
              if (item.dataset.type === "bar") {
                return "تعطیل" + (data.closures[i] ? ": " + data.closures[i] : "");
              }
              return "حضور " + fa(item.raw) + "٪";
            },
            afterBody: function (items) {
              if (!items.length) return "";
              var i = items[0].dataIndex;
              if (!data.totals[i]) return "";
              return fa(data.totals[i]) + " رکورد · " + fa(data.absents[i]) + " غیبت · " +
                fa(data.lates[i]) + " تأخیر";
            }
          }
        }
      }
    },
    plugins: [crosshair]
  });

  host.hidden = false;
  var table = document.getElementById("attendanceTrendTable");
  if (table) table.open = false;
})();
