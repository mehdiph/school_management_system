/*
 * Absent students per day (director/attendance.html).
 *
 * Progressive enhancement: the page ships the same numbers as a table
 * (open by default). When Chart.js (vendored under static/vendor) and
 * the data are here, the chart is shown and the table folds away into
 * its <details>, still one click from every value.
 *
 * One series -- the number of absent students (absent + excused) -- so
 * no legend box: the heading names it. A holiday is a neutral
 * full-height band with its own tooltip ("تعطیل: ..."), never a zero; a
 * day without attendance yet is a gap. Time runs right to left (RTL),
 * the y axis sits on the right.
 */
(function () {
  "use strict";

  var host = document.getElementById("absenceChart");
  var source = document.getElementById("absence-chart-data");
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

  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }

  // A round top a little above the largest day, so the bands reach it.
  var largest = Math.max.apply(null, data.absences.map(function (v) { return v || 0; }).concat([1]));
  var top = Math.max(4, Math.ceil(largest * 1.15));

  window.Chart.defaults.font.family = "Vazirmatn, Tahoma, sans-serif";
  window.Chart.defaults.font.size = 14;
  window.Chart.defaults.color = INK;

  var canvas = host.querySelector("canvas");
  new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [
        {
          label: "غایب",
          data: data.absences,
          backgroundColor: SERIES,
          hoverBackgroundColor: SERIES,
          borderRadius: { topLeft: 4, topRight: 4 },
          borderSkipped: "bottom",
          maxBarThickness: 28,
          categoryPercentage: 0.7,
          barPercentage: 0.9,
          grouped: false,
          order: 1
        },
        {
          label: "تعطیل",
          data: data.kinds.map(function (kind) { return kind === "closed" ? top : null; }),
          backgroundColor: BAND,
          hoverBackgroundColor: GRID,
          borderWidth: 0,
          categoryPercentage: 1,
          barPercentage: 1,
          grouped: false,
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
          max: top,
          border: { display: false },
          grid: { color: GRID, lineWidth: 1 },
          ticks: {
            precision: 0,
            callback: function (value) { return fa(value); }
          }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: true,
          textDirection: "rtl",
          backgroundColor: "#1f2937",
          padding: 12,
          displayColors: false,
          titleFont: { size: 15 },
          bodyFont: { size: 15 },
          filter: function (item) { return item.raw !== null; },
          callbacks: {
            title: function (items) {
              return items.length ? data.titles[items[0].dataIndex] : "";
            },
            label: function (item) {
              var i = item.dataIndex;
              if (item.datasetIndex === 1) {
                return "تعطیل" + (data.closures[i] ? ": " + data.closures[i] : "");
              }
              var text = fa(item.raw) + " دانش‌آموز غایب";
              if (data.excused[i]) text += " (" + fa(data.excused[i]) + " موجه)";
              return text;
            },
            afterBody: function (items) {
              if (!items.length || items[0].datasetIndex === 1) return "";
              var i = items[0].dataIndex;
              var lines = [];
              if (data.late[i]) lines.push(fa(data.late[i]) + " تأخیر");
              if (data.missing[i]) lines.push(fa(data.missing[i]) + " کلاس ثبت نشده");
              return lines;
            }
          }
        }
      }
    }
  });

  host.hidden = false;
  var table = document.getElementById("absenceTable");
  if (table) table.open = false;
})();
