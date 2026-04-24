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

    renderTotals();
    bindControls();
    renderCards();
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
      miniBlock(item.avgDay, "avg field hours/day", "first to last check-in", item.ranks.avgDay),
      miniBlock(item.activeDays, "active business days", "days with at least one stop", null),
      '</div>',
      '<div class="mix-heading"><span>Activity Mix</span><small>MTD touch profile</small></div>',
      renderMix(item.mix),
      '<p class="insight">' + item.insight + '</p>',
      '<footer class="card-footer"><span>' + money(item.actual) + ' actual</span><span>' + money(item.budget) + ' budget</span></footer>',
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
