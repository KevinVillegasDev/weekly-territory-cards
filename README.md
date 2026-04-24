# Weekly Territory Cards

Static weekly TSR territory report site.

This project is intended to be a separate, email-friendly companion to the OSR dashboard. It renders a weekly summary table plus territory cards for all assigned territories.

## Current State

- Static HTML/CSS/JS, no build step.
- Data lives in `data/weekly-data.js`.
- `automation/generate_weekly_data.py` can regenerate the data from the existing OSR dashboard snapshots.

## Local Preview

Open `index.html` in a browser, or serve the folder with any static file server.

## Generate Real Data

From this repo:

```powershell
py automation/generate_weekly_data.py --dashboard-root C:\Codex\osr-enrollmentdash
```

The report is month-to-date. Each weekly refresh shows how the current month is pacing through the latest available snapshot date.

## Pipeline Notes

The existing dashboard already has most source data:

- Monthly quota / budget attainment
- Credited enrollments
- Maps check-ins
- Territory and roster mappings

The included generator writes `data/weekly-data.js` from the dashboard snapshots. Longer term, this can be pointed directly at Salesforce exports if you want the weekly report to refresh without depending on checked-in dashboard snapshot files.

The current activity mix uses keyword-based classification from Maps comments for categories such as training, no contact, and not interested. If Salesforce has structured activity types, those should replace the keyword heuristic.
