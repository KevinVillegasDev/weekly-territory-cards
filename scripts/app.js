(function () {
  "use strict";

  var report = window.weeklyTerritoryReport;
  var state = {
    filter: "all",
    sort: "attainment",
    query: "",
    standingsSort: "attainment"
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
    setText("standingsPeriod", (monthMatch ? monthMatch[1] : "Current") + " MTD");

    renderTotals();
    bindControls();
    renderCards();
    renderStandings();
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

    var standingsSort = document.getElementById("standingsSort");
    if (standingsSort) {
      standingsSort.addEventListener("change", function () {
        state.standingsSort = standingsSort.value;
        renderStandings();
      });
    }

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

  function rankTier(rank) {
    if (!rank) return "";
    if (rank <= 3) return "tier-top";
    if (rank <= 6) return "tier-mid";
    return "tier-bot";
  }

  function rankPill(rank) {
    if (!rank) return "";
    return '<span class="rank-pill ' + rankTier(rank) + '">#' + rank + '</span>';
  }

  function merchantsClass(value) {
    if (value === 0) return "val-amber";
    if (value <= 3) return "val-gray";
    if (value <= 7) return "val-blue";
    return "val-green";
  }

  function leadConversionClass(value) {
    if (!value) return "val-amber";
    if (value < 10) return "val-gray";
    if (value < 20) return "val-blue";
    return "val-green";
  }

  function efficiencyClass(rank) {
    if (!rank) return "";
    if (rank <= 3) return "val-green";
    if (rank <= 6) return "val-amber";
    return "val-gray";
  }

  function renderStandings() {
    var body = document.getElementById("standingsBody");
    if (!body) return;
    var items = report.territories.slice();

    items.sort(function (a, b) {
      switch (state.standingsSort) {
        case "stopEfficiency":   return (b.stopEfficiency || 0) - (a.stopEfficiency || 0);
        case "newMerchants":     return b.newMerchants - a.newMerchants;
        case "leadConversion":   return b.leadConversion - a.leadConversion;
        case "stops":            return b.stops - a.stops;
        case "avgDay":           return hoursFromHmm(b.avgDay) - hoursFromHmm(a.avgDay);
        default:                 return b.attainment - a.attainment;
      }
    });

    body.innerHTML = items.map(function (item, idx) {
      var ranks = item.ranks || {};
      return [
        '<tr>',
          '<td class="col-rank">' + (idx + 1) + '</td>',
          '<td class="col-rep"><span class="terr-code">' + item.code + '</span><span class="rep-name">' + item.rep + '</span></td>',
          '<td>' + item.stops + ' ' + rankPill(ranks.stops) + '</td>',
          '<td class="' + efficiencyClass(ranks.efficiency) + '"><b>' + pct(item.stopEfficiency) + '</b></td>',
          '<td class="' + merchantsClass(item.newMerchants) + '"><b>' + item.newMerchants + '</b></td>',
          '<td class="' + leadConversionClass(item.leadConversion) + '">' + pct(item.leadConversion) + '</td>',
          '<td>' + item.avgDay + ' ' + rankPill(ranks.avgDay) + '</td>',
          '<td class="' + (item.attainment >= 70 ? "val-green" : item.attainment >= 50 ? "val-amber" : "val-red") + '"><b>' + pct(item.attainment) + '</b></td>',
        '</tr>'
      ].join("");
    }).join("");
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
