# Weekly Territory Cards

Static weekly TSR territory report site for EasyPay Finance. Email-friendly companion to the OSR Enrollment Dashboard. Renders a month-to-date summary table plus territory cards for all 12 assigned territories, plus a final standings leaderboard.

**Live site:** https://weekly-territory-progression.netlify.app/

## Architecture, data sources, metrics, and operations

See [`PROJECT_ARCHITECTURE.md`](PROJECT_ARCHITECTURE.md) for the comprehensive reference — system diagram, where each metric comes from, exact formulas, classifier rules, hosting setup, and operational playbooks.

## Quick start

```bash
# Regenerate data from the dashboard's snapshot files:
python automation/generate_weekly_data.py \
  --dashboard-root <path to osr-enrollmentdash repo>

# Serve locally:
python -m http.server 8000
```

## Stack

- Static HTML/CSS/JS, no build step.
- Python 3.12+ generator (`automation/generate_weekly_data.py`), standard library only.
- Hosted on Netlify, deployed from GitHub. Refresh button proxies through a Netlify Function.
- Weekly auto-refresh via GitHub Actions cron (Mondays 13:00 UTC).
