(function () {
  "use strict";

  var report = window.weeklyTerritoryReport;
  var state = {
    filter: "all",
    sort: "attainment",
    query: ""
  };

  var mixColors = {
    "No Contact": "#2A6B94",
    "Int/FU": "#1BCEAC",
    "Rel. Check-In": "#1F5577",
    "Training": "#1AC668",
    "Enrolled": "#15A857",
    "Not Int.": "#FFC107"
  };

  var mixLabels = {
    "No Contact": "No Contact",
    "Int/FU": "Interested / Follow-Up",
    "Rel. Check-In": "Relationship Check-In",
    "Training": "Training / Onboarding",
    "Enrolled": "Enrolled",
    "Not Int.": "Not Interested"
  };

  function money(value) {
    return "$" + Math.round(value).toLocaleString();
  }

  function pct(value) {
    return Number(value || 0).toFixed(1) + "%";
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function init() {
    if (!report) return;

    setText("statStops", report.meta.stopsLogged.toLocaleString());
    setText("statMerchants", report.meta.newMerchants.toLocaleString());
    setText("statDays", report.meta.businessDaysRemaining.toLocaleString());
    setText("updatedThrough", report.meta.updatedThrough);
    setText("executiveNote", report.meta.note);
    setText("totalsNote", report.meta.totalsNote);

    var monthMatch = String(report.meta.updatedThrough || "").match(/^(\w+)/);
    setText("rankingsPeriod", (monthMatch ? monthMatch[1] : "Current") + " MTD");
    setText("rankingsThrough", report.meta.updatedThrough || "-");

    renderTotals();
    bindControls();
    renderCards();
    renderRankings();
  }

  function renderTotals() {
    var body = document.getElementById("totalsBody");
    body.innerHTML = report.totals.map(function (row) {
      var tone = row.tone ? " is-" + row.tone : "";
      return [
        '<tr class="' + tone + '">',
        '<td><strong>' + row.period + '</strong>' + (row.sub ? '<small>' + row.sub + '</small>' : "") + '</td>',
        '<td>' + money(row.actual) + '</td>',
        '<td>' + money(row.budget) + '</td>',
        '<td><b>' + pct(row.attainment) + '</b></td>',
        '</tr>'
      ].join("");
    }).join("");
  }

  function bindControls() {
    var search = document.getElementById("searchInput");
    var sort = document.getElementById("sortSelect");

    search.addEventListener("input", function () {
      state.query = search.value.trim().toLowerCase();
      renderCards();
    });

    sort.addEventListener("change", function () {
      state.sort = sort.value;
      renderCards();
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-filter]"), function (btn) {
      btn.addEventListener("click", function () {
        state.filter = btn.getAttribute("data-filter");
        Array.prototype.forEach.call(document.querySelectorAll("[data-filter]"), function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        renderCards();
      });
    });
  }

  function getVisibleTerritories() {
    var items = report.territories.slice();

    if (state.filter !== "all") {
      items = items.filter(function (item) {
        return item.status === state.filter;
      });
    }

    if (state.query) {
      items = items.filter(function (item) {
        return (item.code + " " + item.rep + " " + item.area).toLowerCase().indexOf(state.query) !== -1;
      });
    }

    items.sort(function (a, b) {
      if (state.sort === "merchants") return b.newMerchants - a.newMerchants;
      if (state.sort === "stops") return b.stops - a.stops;
      if (state.sort === "leadConversion") return b.leadConversion - a.leadConversion;
      if (state.sort === "stopEfficiency") return (b.stopEfficiency || 0) - (a.stopEfficiency || 0);
      return b.attainment - a.attainment;
    });

    return items;
  }

  function renderCards() {
    var grid = document.getElementById("cardsGrid");
    var items = getVisibleTerritories();

    if (!items.length) {
      grid.innerHTML = '<p class="empty-state">No territory cards match the current view.</p>';
      return;
    }

    grid.innerHTML = items.map(renderCard).join("");
  }

  function renderCard(item) {
    var statusLabel = item.status === "on-track" ? "On Track" : "Watch";
    var statusText = item.status === "on-track" ? "Above team pace" : "Needs focus";
    return [
      '<article class="territory-card ' + (item.status === "on-track" ? "is-on-track" : "is-watch") + '">',
      '<header class="card-header">',
      '<div>',
      '<div class="card-kicker"><a class="territory-code" href="#' + item.code + '">' + item.code + '</a><span>' + statusLabel + '</span></div>',
      '<h3>' + item.rep + '</h3>',
      '<p>' + item.area + '</p>',
      '</div>',
      '<div class="rank-stack"><span>#' + item.rank + '</span><small>' + statusText + '</small></div>',
      '</header>',
      '<div class="attainment-row"><span>Budget attainment</span><strong>' + pct(item.attainment) + '</strong></div>',
      '<div class="progress-rail"><span style="width:' + Math.min(100, item.attainment) + '%"></span></div>',
      '<div class="hero-metrics">',
      metricBlock(item.newMerchants, "new merchants", "credited enrollments this month", item.ranks.merchants, true),
      metricBlock(pct(item.leadConversion), "lead conversion", "enrollments from prospect stops", item.ranks.conversion),
      '</div>',
      '<div class="mini-metrics">',
      miniBlock(item.stops, "field stops", expandStopSplit(item.stopSplit), item.ranks.stops),
      miniBlock(item.avgDay, "avg field time/active day", "first to last check-in (H:MM)", item.ranks.avgDay),
      miniBlock(item.activeDays, "active / total visited days", "active = days with 3+ unique merchant stops", null),
      '</div>',
      '<div class="mix-heading"><span>Activity Mix</span><small>MTD touch profile</small></div>',
      renderMix(item.mix),
      '<p class="insight">' + item.insight + '</p>',
      '</article>'
    ].join("");
  }

  function metricBlock(value, label, detail, rank, accent) {
    return [
      '<div class="metric-block' + (accent ? " is-accent" : "") + '">',
      '<b>' + value + '</b>',
      '<span>' + label + '</span>',
      detail ? '<small>' + detail + '</small>' : '',
      rank ? '<em>Rank #' + rank + '</em>' : '',
      '</div>'
    ].join("");
  }

  function miniBlock(value, label, detail, rank) {
    return [
      '<div class="mini-block">',
      '<b>' + value + '</b>',
      '<span>' + label + '</span>',
      detail ? '<small>' + detail + '</small>' : '',
      rank ? '<em>Rank #' + rank + '</em>' : '',
      '</div>'
    ].join("");
  }

  function expandStopSplit(split) {
    var match = String(split || "").match(/(\d+)P\s*\/\s*(\d+)A/);
    if (!match) return "prospect / account split";
    return match[1] + " prospect stops / " + match[2] + " existing account stops";
  }

  function renderRankings() {
    var grid = document.getElementById("rankingsGrid");
    if (!grid) return;

    var metrics = [
      {
        title: "Budget %",
        sub: "Attainment vs target",
        sortValue: function (i) { return i.attainment || 0; },
        display: function (i) { return pct(i.attainment); }
      },
      {
        title: "New Merchants",
        sub: "Credited enrollments MTD",
        sortValue: function (i) { return i.newMerchants || 0; },
        display: function (i) { return String(i.newMerchants || 0); }
      },
      {
        title: "Lead Conversion",
        sub: "Enrollments \u00f7 prospect stops",
        sortValue: function (i) { return i.leadConversion || 0; },
        display: function (i) { return pct(i.leadConversion); }
      },
      {
        title: "Field Stops",
        sub: "Total logged stops MTD",
        sortValue: function (i) { return i.stops || 0; },
        display: function (i) { return (i.stops || 0).toLocaleString(); }
      },
      {
        title: "Avg Time / Active Day",
        sub: "First \u2192 last check-in (H:MM)",
        sortValue: function (i) { return hoursFromHmm(i.avgDay); },
        display: function (i) { return i.avgDay || "0:00"; }
      }
    ];

    grid.innerHTML = metrics.map(renderRankingColumn).join("");
  }

  function renderRankingColumn(metric) {
    var entries = report.territories.slice().map(function (item) {
      return { item: item, value: metric.sortValue(item) };
    });
    entries.sort(function (a, b) { return b.value - a.value; });

    var rank = 0;
    var lastValue = null;
    var rowsHtml = entries.map(function (e) {
      if (lastValue === null || e.value !== lastValue) {
        rank += 1;
        lastValue = e.value;
      }
      var tier = rank === 1 ? "leader" : rank <= 3 ? "top" : "rest";
      return [
        '<li class="rk-row rk-tier-' + tier + '">',
          '<span class="rk-num">' + rank + '</span>',
          '<span class="rk-name">' + e.item.rep,
          ' <small>' + e.item.code + '</small>',
          '</span>',
          '<span class="rk-val">' + metric.display(e.item) + '</span>',
        '</li>'
      ].join("");
    }).join("");

    return [
      '<div class="rk-col">',
        '<div class="rk-head">',
          '<h3>' + metric.title + '</h3>',
          '<small>' + metric.sub + '</small>',
        '</div>',
        '<ol class="rk-list">' + rowsHtml + '</ol>',
      '</div>'
    ].join("");
  }

  function hoursFromHmm(text) {
    var parts = String(text || "").split(":");
    if (parts.length !== 2) return 0;
    var h = parseInt(parts[0], 10) || 0;
    var m = parseInt(parts[1], 10) || 0;
    return h + m / 60;
  }

  function renderMix(mix) {
    var keys = Object.keys(mix);
    var bar = keys.map(function (key) {
      return '<span style="width:' + mix[key] + '%;background:' + mixColors[key] + '"></span>';
    }).join("");

    var labels = keys.map(function (key) {
      return '<span><b>' + (mixLabels[key] || key) + '</b> ' + mix[key] + '%</span>';
    }).join("");

    return '<div class="mix-bar">' + bar + '</div><div class="mix-labels">' + labels + '</div>';
  }

  init();
})();
