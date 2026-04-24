# Weekly Territory Cards - Project Architecture

## Purpose

Weekly Territory Cards is a standalone EasyPay Finance report site for TSR territory performance. It is designed to be shared by weekly email link so TSRs and leadership can view month-to-date performance across all active territories.

The project is intentionally separate from the production OSR Enrollment Dashboard. It borrows the same data pipeline concepts and snapshot files, but renders a focused card-based experience for weekly field reporting.

## Current Product Direction

The report is month-to-date, not a Monday-through-Sunday weekly slice. Each weekly refresh answers: "How is the current month pacing as of the latest available data?"

That decision matters because the main business metrics are monthly:

- Budget origination attainment
- Funded dollar actuals versus budget target
- New merchant enrollments
- Business days remaining
- Territory rank and pace

The weekly email cadence is the distribution rhythm. The measurement period remains the current month.

## Repository Structure

```text
weekly-territory-cards/
  index.html
  styles.css
  scripts/
    app.js
  data/
    weekly-data.js
  automation/
    generate_weekly_data.py
    __init__.py
  README.md
  PROJECT_ARCHITECTURE.md
  netlify.toml
  .gitignore
```

## Frontend Architecture

The frontend is static HTML, CSS, and JavaScript. There is no build step, package manager, framework, or bundler.

### `index.html`

Defines the page structure:

- Branded EasyPay report header
- Executive summary stats
- Team origination totals table
- Search, status filter, and sort controls
- Territory card grid mount point

It loads data and behavior in this order:

```html
<script src="data/weekly-data.js"></script>
<script src="scripts/app.js"></script>
```

The data file must load first because `app.js` reads `window.weeklyTerritoryReport`.

### `styles.css`

Contains the full visual system for the report. The current design follows the EasyPay Finance brand skill:

- EasyPay Blue: `#1F5577`
- EasyPay Green: `#1AC668`
- EasyPay Teal: `#1BCEAC`
- Off-white report background
- White cards with subtle shadows
- Green-to-teal accent bars
- Amber styling for watch/attention states

The layout is responsive:

- Desktop uses a 3-column card grid.
- Tablet uses a 2-column card grid.
- Mobile uses a single-column card grid.
- The team totals table becomes stacked rows on mobile.

### `scripts/app.js`

Renders all dynamic UI from `window.weeklyTerritoryReport`.

Responsibilities:

- Populate top-level stats and executive note
- Render the team totals table
- Render territory cards
- Support search by rep, territory code, or area
- Filter cards by status
- Sort cards by attainment, new merchants, stops, or lead conversion
- Expand short data labels into human-readable context

Important examples:

- `79P / 142A` is rendered as `79 prospect stops / 142 existing account stops`.
- `Int/FU` is rendered as `Interested / Follow-Up`.
- `Rel. Check-In` is rendered as `Relationship Check-In`.

## Data Contract

The frontend expects one global object:

```js
window.weeklyTerritoryReport = {
  meta: {},
  totals: [],
  territories: []
};
```

### `meta`

Used for the page header and executive summary.

```js
{
  updatedThrough: "April 23, 2026",
  stopsLogged: 1995,
  newMerchants: 97,
  businessDaysRemaining: 5,
  note: "...",
  totalsNote: "..."
}
```

### `totals`

Used for the team origination table.

```js
{
  period: "April MTD",
  sub: "Through Apr 23",
  actual: 6100743.8,
  budget: 8735345,
  attainment: 69.8
}
```

### `territories`

Used for each territory card.

```js
{
  code: "RIC-1",
  rep: "Cesar Flores",
  area: "CA - LA Metro Core",
  status: "on-track",
  attainment: 92.0,
  actual: 150259.53,
  budget: 163279,
  newMerchants: 10,
  leadConversion: 12.7,
  stops: 221,
  stopSplit: "79P / 142A",
  avgDay: "5.8h",
  activeDays: "11 / 17",
  mix: {
    "No Contact": 15,
    "Int/FU": 0,
    "Rel. Check-In": 38,
    "Training": 41,
    "Enrolled": 0,
    "Not Int.": 6
  },
  insight: "...",
  ranks: {
    attainment: 1,
    merchants: 4,
    conversion: 7,
    stops: 1,
    avgDay: 3
  },
  rank: 1
}
```

## Data Generation

### Current Source

The current generator reads the existing dashboard snapshots from:

```text
C:\Codex\osr-enrollmentdash\data\snapshots
```

The command is:

```powershell
py automation/generate_weekly_data.py --dashboard-root C:\Codex\osr-enrollmentdash
```

That command writes:

```text
data/weekly-data.js
```

### Snapshot Files Used

The generator currently depends on these dashboard snapshot files:

- `monthly_quota.json`
- `credited_enrollments.json`
- `maps_check_ins.json`

### Metrics Computed

The generator computes:

- Latest available activity/enrollment date
- Business days elapsed and remaining
- Territory actual funded dollars
- Territory budget target
- Budget attainment percentage
- New merchant count by OSR enrollment credit
- Field stop count
- Prospect versus existing account stop split
- Lead conversion percentage
- Active field days
- Average field hours per active day
- Activity mix
- Per-metric ranks
- Overall territory rank by attainment
- Executive summary note

## Relationship To The Original Dashboard

The original dashboard lives at:

```text
C:\Codex\osr-enrollmentdash
```

It already has Salesforce authentication, report fetching, parsing, and snapshot writing. The relevant files are:

```text
automation/config.py
automation/salesforce_auth.py
automation/salesforce_reports.py
automation/main.py
automation/processors/field_activity.py
```

The weekly cards app currently reads the dashboard's saved snapshots rather than authenticating directly with Salesforce.

## Salesforce Reports Already Known

The original dashboard defines these Salesforce report IDs:

| Key | Report ID | Primary Use |
| --- | --- | --- |
| `new_enrollments` | `00OTO000009L49t2AC` | All new enrollment rows |
| `credited_enrollments` | `00OTO000007Mhrt2AC` | OSR-credited merchant enrollments |
| `current_month_activity` | `00OTO00000671Gr2AI` | Current cohort funding/activity |
| `last_month_activity` | `00OTO000009Iw1x2AC` | Prior cohort funding/activity |
| `maps_check_ins` | `00OTO000009NEbN2AW` | Maps field check-ins |
| `monthly_quota` | `00OTO000009YYWj2AO` | Quota, funded dollars, budget attainment |
| `isr_notes` | `00O8Y0000098j62UAA` | ISR notes and touch points |

For this report, the first live-data integration should use:

- `monthly_quota`
- `credited_enrollments`
- `maps_check_ins`

Those three reports cover the current card experience.

## Recommended Live Data Architecture

The safest next step is to add a live generation mode to `automation/generate_weekly_data.py`.

Recommended flow:

1. Reuse Salesforce auth and report fetch code from the dashboard repo.
2. Fetch only the reports needed by this app.
3. Normalize rows using the same parser as the dashboard.
4. Generate the same `window.weeklyTerritoryReport` object.
5. Write `data/weekly-data.js`.
6. Keep snapshot mode as a fallback.

Proposed command shape:

```powershell
py automation/generate_weekly_data.py --dashboard-root C:\Codex\osr-enrollmentdash --live
```

Fallback snapshot mode should remain:

```powershell
py automation/generate_weekly_data.py --dashboard-root C:\Codex\osr-enrollmentdash
```

## Current Data Caveats

Most values are grounded in real dashboard snapshot data. A few areas still need refinement before this becomes a fully authoritative leadership report.

### Activity Mix

Activity mix is currently inferred from Maps check-in comments using keywords. For example, comments containing terms such as "training", "portal", or "onboarding" are classified as training.

This is useful for a prototype but not ideal for CFO-grade reporting. A structured Salesforce field for check-in outcome, visit type, or disposition would be better.

### Deduplication

The original dashboard has more detailed field activity deduplication logic in:

```text
C:\Codex\osr-enrollmentdash\automation\processors\field_activity.py
```

The weekly generator should eventually reuse that logic so stop counts match the dashboard exactly.

### Enrollment Attribution To Visits

The report shows new merchant counts separately from visit mix. It does not yet know which specific check-in led to an enrollment, so the `Enrolled` segment in activity mix is not authoritative.

### Historical Totals

The totals table includes months where `monthly_quota.json` exists. If leadership wants a fixed Jan-Apr or YTD view every month, the app should fetch or preserve historical quota/origination data.

## Deployment

The project is static and can be hosted anywhere that serves plain HTML/CSS/JS.

`netlify.toml` is included for Netlify:

```toml
[build]
  publish = "."
```

No build command is required.

## Local Preview

Open the file directly:

```text
file:///C:/Codex/weekly-territory-cards/index.html
```

Or serve the folder with any static server.

## Verification Checklist

After changing data or UI:

```powershell
node --check scripts\app.js
node --check data\weekly-data.js
py automation/generate_weekly_data.py --dashboard-root C:\Codex\osr-enrollmentdash
```

For visual QA, render desktop and mobile screenshots with Chrome headless:

```powershell
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --headless --disable-gpu --window-size=1440,1700 --screenshot='C:\Codex\weekly-territory-cards\preview.png' 'file:///C:/Codex/weekly-territory-cards/index.html'

& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --headless --disable-gpu --window-size=390,2800 --screenshot='C:\Codex\weekly-territory-cards\preview-mobile-tall.png' 'file:///C:/Codex/weekly-territory-cards/index.html'
```

Preview screenshots are ignored by git.

## Design Notes

The app follows the EasyPay Finance branding skill:

- Use EasyPay Blue for headers and institutional surfaces.
- Use EasyPay Green for primary positive/accent states.
- Use EasyPay Teal for links, secondary accents, and data visualization.
- Use amber/gold for watch or attention states.
- Keep copy clear and non-jargony.
- Spell out abbreviations where a TSR or executive might not know the shorthand.

The current design intentionally avoids a marketing landing page. The first screen is the actual report.

