"""
Generate the weekly territory cards data file from OSR dashboard snapshots.

This keeps the weekly cards site static while letting it consume the same
source snapshots as the dashboard repo. The report is month-to-date: each
weekly email shows the current month's progress through the latest snapshot
date, not a Monday-Sunday reset.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


TERRITORY_MAP = {
    "LTO-1": "Yemaira Hernandez",
    "LTO-2": "Omar Corona",
    "LTO-3": "Joseph Guerra",
    "LTO-4": "Francisco Gonzalez",
    "LTO-5": "Jared Midkiff",
    "LTO-7": "Stephanie Whitlock",
    "RIC-1": "Cesar Flores",
    "RIC-2": "Claudia Gerhardt",
    "RIC-4": "Richard Herrera",
    "RIC-6": "Phillip Mason",
    "RIC-7": "DeLon Phoenix",
    "RIC-8": "Eric Henderson",
    "RIC-9": "Matthew MacDonald",
}

# Names whose production should still roll up to a territory during a transition
# (departed reps, mid-month handoffs). Remove entries after the relevant month
# is closed in historical-totals.json so the card reflects the new rep cleanly.
TERRITORY_ALIASES = {
    "RIC-4": ["Jeremy Moore"],  # Jeremy's April production rolls into RIC-4 through April close
}

TERRITORY_AREAS = {
    "LTO-1": "FL - Miami-Dade/Broward",
    "LTO-2": "TX - S. Houston/Valley/El Paso",
    "LTO-3": "TX - State Manager",
    "LTO-4": "TX - Dallas Metro",
    "LTO-5": "FL - State Manager",
    "LTO-7": "GA / NE FL / Panhandle",
    "RIC-1": "CA - LA Metro Core",
    "RIC-2": "CA - IE South/San Diego",
    "RIC-4": "CA - Orange County/SE LA",
    "RIC-6": "CA - Sacramento/NorCal",
    "RIC-7": "NV - Las Vegas/Reno",
    "RIC-8": "PA - 4 Metros",
    "RIC-9": "AZ + NM/UT/ID",
}

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


MAX_SNAPSHOT_STALENESS_DAYS = 4

# Earliest month for which we publish a rankings archive. Months before this
# are skipped to avoid surfacing transition-month quirks (e.g. RIC-1 / RIC-4
# rep changes pre-April 2026 leave incomplete per-territory data).
ARCHIVE_MIN_YEAR_MONTH = (2026, 4)

# A closed month's rankings archive is re-written on each run for this many days
# after rollover, letting Budget % self-heal as late funded $ settles (the
# dashboard refreshes the prior month's monthly_quota.json through day 7). After
# the window, the auto numbers freeze. A `"locked": true` archive is never
# touched regardless of the window (used for manual Sales Ops patches).
SETTLEMENT_WINDOW_DAYS = 8


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly territory cards data")
    parser.add_argument(
        "--dashboard-root",
        default=r"C:\Users\kevin.villegas\OneDrive - Duvera\Claude\osr enrollment dash",
        help="Path to the existing OSR dashboard repo",
    )
    parser.add_argument(
        "--output",
        default="data/weekly-data.js",
        help="Output JS file for this static site",
    )
    parser.add_argument(
        "--historical",
        default="data/historical-totals.json",
        help="Closed-month company-wide totals (overrides snapshot-derived totals for those months)",
    )
    parser.add_argument(
        "--archive-dir",
        default="data/monthly-archives",
        help="Per-territory closed-month rankings archives (one JSON per month)",
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Skip the freshness guard (for backfills or testing only)",
    )
    args = parser.parse_args()

    dashboard_root = Path(args.dashboard_root)
    snapshot_root = dashboard_root / "data" / "snapshots"
    output_path = Path(args.output)
    historical_path = Path(args.historical)
    archive_dir = Path(args.archive_dir)

    report = build_report(snapshot_root, historical_path, archive_dir, allow_stale=args.allow_stale)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.weeklyTerritoryReport = "
        + json.dumps(report, indent=2, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} from {snapshot_root}")


def build_report(snapshot_root: Path, historical_path: Path, archive_dir: Path, allow_stale: bool = False) -> dict:
    current_dir = _latest_snapshot_dir(snapshot_root)
    year, month = _parse_snapshot_name(current_dir.name)

    quota_rows = _load_json(current_dir / "monthly_quota.json")
    credited_rows = _load_json(current_dir / "credited_enrollments.json")
    checkin_rows = _load_json(current_dir / "maps_check_ins.json")

    through_date = _latest_activity_date(credited_rows, checkin_rows) or date.today()
    _guard_freshness(through_date, allow_stale)
    biz_remaining = _business_days_remaining(through_date)
    expected_attainment = _business_days_elapsed(through_date) / max(
        _business_days_in_month(through_date.year, through_date.month),
        1,
    ) * 100

    quota_by_terr = _quota_by_territory(quota_rows)
    enrollments_by_terr = _enrollments_by_territory(credited_rows)
    activity_by_terr = _activity_by_territory(checkin_rows)

    territories = []
    for code, rep in TERRITORY_MAP.items():
        quota = quota_by_terr.get(code, {})
        actual = quota.get("actual", 0.0)
        budget = quota.get("budget", 0.0)
        attainment = (actual / budget * 100) if budget else 0.0

        activity = activity_by_terr.get(code, _empty_activity())
        new_merchants = enrollments_by_terr.get(code, 0)
        prospect_stops = activity["prospect"]
        lead_conversion = (new_merchants / prospect_stops * 100) if prospect_stops else 0.0

        territories.append(
            {
                "code": code,
                "rep": rep,
                "area": TERRITORY_AREAS[code],
                "status": "on-track" if attainment >= expected_attainment * 0.9 else "watch",
                "attainment": round(attainment, 1),
                "actual": round(actual, 2),
                "budget": round(budget, 2),
                "newMerchants": new_merchants,
                "leadConversion": round(lead_conversion, 1),
                "stops": activity["total"],
                "stopSplit": f'{activity["prospect"]}P / {activity["existing"]}A',
                "avgDay": _format_h_mm(activity["avg_hours"]),
                "activeDays": f'{activity["active_days"]} / {activity["total_visited"]}',
                "stopEfficiency": round(activity["efficiency"], 1),
                "mix": activity["mix"],
            }
        )

    _attach_ranks(territories)
    territories.sort(key=lambda item: item["attainment"], reverse=True)
    for idx, item in enumerate(territories, start=1):
        item["rank"] = idx

    _freeze_closed_months(snapshot_root, current_dir, historical_path)
    _archive_closed_months(snapshot_root, current_dir, archive_dir)
    archives = _list_archives(archive_dir)

    # The dashboard's snapshot rollover is data-driven (depends on SF returning
    # data for the new month), so the calendar can be ahead of the latest
    # snapshot folder by several days. When that happens — i.e. today's calendar
    # month is already past the snapshot's month — the snapshot is fully closed
    # and we should label it "Final" instead of "MTD".
    today = date.today()
    month_complete = (today.year, today.month) > (year, month)

    totals = _build_totals(current_dir, historical_path, through_date, month_complete=month_complete)
    current_row = next(
        (row for row in totals if MONTH_NAMES[month] in row.get("period", "") and "Total" not in row.get("period", "")),
        None,
    )
    if current_row is None:
        current_row = next((row for row in totals if row.get("period", "").endswith("MTD")), None)

    if month_complete and current_row is not None:
        totals_note = (
            f"{MONTH_NAMES[month]} {year} closed at {current_row['attainment']:.1f}% attainment. "
            f"Awaiting Sales Ops final reconciliation; numbers may shift slightly with corrections."
        )
    elif current_row is not None:
        totals_note = (
            f"{MONTH_NAMES[month]} MTD is a partial month - "
            f"{current_row['attainment']:.1f}% attainment through "
            f"{_format_date_short(through_date)} with {biz_remaining} business "
            f"day{'s' if biz_remaining != 1 else ''} remaining."
        )
    else:
        totals_note = ""

    return {
        "meta": {
            "updatedThrough": _format_date_long(through_date),
            "stopsLogged": sum(item["stops"] for item in territories),
            "newMerchants": sum(item["newMerchants"] for item in territories),
            "businessDaysRemaining": biz_remaining,
            "monthStatus": "final" if month_complete else "mtd",
            "note": _build_executive_note(territories, through_date, biz_remaining),
            "totalsNote": totals_note,
            "archives": archives,
        },
        "totals": totals,
        "territories": territories,
    }


def _latest_snapshot_dir(snapshot_root: Path) -> Path:
    dirs = [p for p in snapshot_root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"No snapshot directories found under {snapshot_root}")
    return sorted(dirs, key=lambda p: p.name)[-1]


def _parse_snapshot_name(name: str) -> tuple[int, int]:
    year_s, month_s = name.split("-", 1)
    return int(year_s), int(month_s)


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


LEAD_ATTRIBUTION_WINDOW_MONTHS = 6  # rolling window for cumulative lead conversion
LEAD_LINK_FIELD = "Converted from - Lead ID"  # column on credited_enrollments report
BUSINESS_SUFFIXES = {"inc", "llc", "ltd", "corp", "co", "company", "incorporated", "lp", "llp"}


def _name_to_territory() -> dict[str, str]:
    """Build a name → territory code map, including TERRITORY_ALIASES (transitions)."""
    mapping: dict[str, str] = {}
    for code, primary in TERRITORY_MAP.items():
        mapping[primary] = code
        for alias in TERRITORY_ALIASES.get(code, []):
            mapping[alias] = code
    return mapping


def _normalize_merchant_tokens(name: str | None) -> frozenset[str]:
    """Lowercase, strip punctuation (incl. smart quotes), drop business suffixes; return token set."""
    if not name:
        return frozenset()
    text = name.lower()
    # Replace ASCII + unicode punctuation with spaces.
    for ch in ",.&'\"/-()\u2018\u2019\u201c\u201d":
        text = text.replace(ch, " ")
    return frozenset(t for t in text.split() if t and t not in BUSINESS_SUFFIXES)


def _normalize_merchant_name(name: str | None) -> str:
    """String form of the normalized name (used as a stable key for set lookup)."""
    return " ".join(sorted(_normalize_merchant_tokens(name)))


def _cumulative_lead_attribution(snapshot_root: Path, current_dir: Path) -> dict[str, dict]:
    """DORMANT — kept for ad-hoc analysis. Not currently displayed on the report.

    Rationale for dormancy (April 2026): only ~12% of credited enrollments have the SF
    "Converted from - Lead ID" field populated, so 88% of matches fall back to the
    token-subset name heuristic. That under-counts real conversions enough that the
    metric reads more like a data-hygiene scoreboard than a sales metric.

    Re-enable once the populated rate climbs above ~50% (likely needs SF web-enrollment
    merge process improvements). Wiring is just one call in build_report.

    Per-territory cumulative lead conversion across the trailing window.

    For each territory:
      - unique_leads = distinct merchants visited as a Lead (Lead field populated on a Maps row)
      - matched_enrollments = credited enrollments whose merchant name normalized-matches one of those leads
      - lead_conversion = matched_enrollments / unique_leads × 100  (capped at 100% by construction)

    A merchant visited multiple times counts once. Lead stops + enrollments are pooled across the
    primary rep + any TERRITORY_ALIASES so a transition month doesn't reset the metric.
    """
    name_to_terr = _name_to_territory()
    cur_year, cur_month = _parse_snapshot_name(current_dir.name)

    # Compute window cutoff (inclusive) — trailing N months ending at current month.
    cutoff_year, cutoff_month = cur_year, cur_month - (LEAD_ATTRIBUTION_WINDOW_MONTHS - 1)
    while cutoff_month <= 0:
        cutoff_year -= 1
        cutoff_month += 12
    cutoff = (cutoff_year, cutoff_month)

    # Per territory: lead IDs (for deterministic match) + token map (for fallback)
    leads_by_terr_ids: dict[str, set[str]] = defaultdict(set)
    leads_by_terr_tokens: dict[str, dict[str, frozenset[str]]] = defaultdict(dict)

    # Per territory: list of enrollment metadata
    enrollments_by_terr: dict[str, list[dict]] = defaultdict(list)

    # Account ID → originating Lead ID (built across all rows in the window so we can
    # resolve the parent → lead chain match).
    account_to_origin_lead: dict[str, str] = {}

    for snapshot_dir in sorted(p for p in snapshot_root.iterdir() if p.is_dir()):
        try:
            year, month = _parse_snapshot_name(snapshot_dir.name)
        except (ValueError, IndexError):
            continue
        if (year, month) < cutoff or (year, month) > (cur_year, cur_month):
            continue

        for row in _load_json(snapshot_dir / "maps_check_ins.json"):
            lead_id = (row.get("Lead") or "").strip()
            if lead_id in ("", "null"):
                continue
            code = name_to_terr.get((row.get("_label_Assigned") or "").strip())
            if not code:
                continue
            leads_by_terr_ids[code].add(lead_id)
            tokens = _normalize_merchant_tokens(row.get("_label_Company / Account"))
            if tokens:
                leads_by_terr_tokens[code][" ".join(sorted(tokens))] = tokens

        for row in _load_json(snapshot_dir / "credited_enrollments.json"):
            code = name_to_terr.get((row.get("OSR Enrollment Credit") or "").strip())
            if not code:
                continue
            account_id = str(row.get("Account ID") or "").strip()
            origin_lead = str(row.get(LEAD_LINK_FIELD) or "").strip()
            if origin_lead in ("", "null", "-"):
                origin_lead = ""
            if account_id and origin_lead:
                account_to_origin_lead[account_id] = origin_lead
            enrollments_by_terr[code].append({
                "account_id": account_id,
                "parent_account_id": str(row.get("Parent Account") or "").strip(),
                "origin_lead": origin_lead,
                "tokens": _normalize_merchant_tokens(row.get("_label_Account Name")),
            })

    MIN_LEAD_TOKENS = 2

    result: dict[str, dict] = {}
    for code in TERRITORY_MAP:
        rep_lead_ids = leads_by_terr_ids.get(code, set())
        rep_lead_tokens = leads_by_terr_tokens.get(code, {})
        enrollments = enrollments_by_terr.get(code, [])

        # Dedup enrollments: by account_id when present (most stable), otherwise normalized name.
        dedup: dict[str, dict] = {}
        for e in enrollments:
            key = e["account_id"] or " ".join(sorted(e["tokens"]))
            if key:
                dedup[key] = e

        matched = 0
        for e in dedup.values():
            # 1. Direct exact ID match — Account converted directly from a tracked Lead.
            if e["origin_lead"] and e["origin_lead"] in rep_lead_ids:
                matched += 1
                continue
            # 2. Chain match — parent Account converted from a tracked Lead, branch rolls up to it.
            parent_origin = account_to_origin_lead.get(e["parent_account_id"])
            if parent_origin and parent_origin in rep_lead_ids:
                matched += 1
                continue
            # 3. Fallback: token-subset match on display names (covers nulls + chain cases the
            #    parent-lookup can't reach because the parent isn't in this report).
            enroll_tokens = e["tokens"]
            if enroll_tokens:
                key = " ".join(sorted(enroll_tokens))
                if key in rep_lead_tokens:
                    matched += 1
                    continue
                if any(len(lt) >= MIN_LEAD_TOKENS and lt.issubset(enroll_tokens) for lt in rep_lead_tokens.values()):
                    matched += 1
                    continue

        denominator = len(rep_lead_tokens)
        result[code] = {
            "unique_leads": denominator,
            "matched_enrollments": matched,
            "lead_conversion": (matched / denominator * 100) if denominator else 0.0,
        }
    return result


def _quota_by_territory(rows: list[dict]) -> dict[str, dict]:
    """Sum funded $ across primary + alias reps. Budget = the OUTGOING rep's (the alias)
    when one exists — the territory's monthly plan was set with that rep, so the transition
    doesn't change the target. Falls back to primary's budget when there's no alias.
    """
    primaries = {name: code for code, name in TERRITORY_MAP.items()}
    alias_lookup = {alias: code for code, names in TERRITORY_ALIASES.items() for alias in names}

    primary_data: dict[str, dict] = {}
    alias_data: dict[str, dict] = {}

    for row in rows:
        rep = (row.get("_label_User") or "").strip()
        actual = _currency(row.get("Funded Dollars"))
        projected = _currency(row.get("Funding Projected"))
        budget = _currency(row.get("Funded Dollars Quota"))

        if rep in primaries:
            bucket = primary_data.setdefault(primaries[rep], {"budget": 0.0, "actual": 0.0, "projected": 0.0})
        elif rep in alias_lookup:
            bucket = alias_data.setdefault(alias_lookup[rep], {"budget": 0.0, "actual": 0.0, "projected": 0.0})
        else:
            continue
        bucket["budget"] += budget
        bucket["actual"] += actual
        bucket["projected"] += projected

    result: dict[str, dict] = {}
    for code in set(primary_data) | set(alias_data):
        p = primary_data.get(code, {"budget": 0.0, "actual": 0.0, "projected": 0.0})
        a = alias_data.get(code, {"budget": 0.0, "actual": 0.0, "projected": 0.0})
        result[code] = {
            "actual": p["actual"] + a["actual"],
            "projected": p["projected"] + a["projected"],
            "budget": a["budget"] if a["budget"] > 0 else p["budget"],
        }
    return result


def _enrollments_by_territory(rows: list[dict]) -> Counter:
    counts: Counter = Counter()
    name_to_terr = _name_to_territory()
    for row in rows:
        rep = (row.get("OSR Enrollment Credit") or "").strip()
        code = name_to_terr.get(rep)
        if code:
            counts[code] += 1
    return counts


SHORT_NOTE_THRESHOLD = 18  # comments shorter than this default to No Contact


def _activity_by_territory(rows: list[dict]) -> dict[str, dict]:
    """Dedup by (territory, stop_name, date) so a transition month merges the outgoing + incoming reps."""
    name_to_terr = _name_to_territory()
    deduped: dict[tuple[str, str, date], dict] = {}

    for row in rows:
        rep = (row.get("_label_Assigned") or "").strip()
        code = name_to_terr.get(rep)
        if not code:
            continue

        dt = _parse_checkin_datetime(row.get("_label_Created Date/Time"))
        if not dt:
            continue

        stop_name = (row.get("_label_Company / Account") or "Unknown").strip()
        comment = str(row.get("_label_Full Comments") or "")
        lead_val = row.get("Lead")
        is_existing = lead_val in (None, "", "null")

        key = (code, stop_name, dt.date())
        existing_entry = deduped.get(key)
        if existing_entry is None or len(comment) > len(existing_entry["comment"]):
            deduped[key] = {
                "code": code,
                "datetime": dt,
                "comment": comment,
                "is_existing": is_existing,
            }

    by_terr: dict[str, dict] = defaultdict(
        lambda: {
            "total": 0,
            "existing": 0,
            "prospect": 0,
            "timestamps_by_date": defaultdict(list),
            "classifications": [],
        }
    )
    for stop in deduped.values():
        code = stop["code"]
        dt = stop["datetime"]
        bucket = by_terr[code]
        bucket["total"] += 1
        bucket["existing" if stop["is_existing"] else "prospect"] += 1
        bucket["timestamps_by_date"][dt.date()].append(dt)
        bucket["classifications"].append(_classify_stop(stop["comment"]))

    result = {}
    for code, item in by_terr.items():
        active_days, avg_hours = _active_metrics(item["timestamps_by_date"])
        result[code] = {
            "total": item["total"],
            "existing": item["existing"],
            "prospect": item["prospect"],
            "active_days": active_days,
            "total_visited": len(item["timestamps_by_date"]),
            "avg_hours": avg_hours,
            "efficiency": _stop_efficiency(item["classifications"], item["total"]),
            "mix": _build_card_mix(item["classifications"], item["total"]),
        }
    return result


def _classify_stop(comment: str) -> str:
    """Classify a single stop into one of 8 outcome buckets. Precedence: friction first, defaults last."""
    text = comment.strip().lower()

    if len(text) < SHORT_NOTE_THRESHOLD:
        return "No Contact"
    if _has_any(text, ("closed", "locked", "not in", "not available", "no one", "left card", "no contact", "drop off", "drop-off", "owner not present", "owner not in", "too busy")):
        return "No Contact"

    if _has_any(text, ("complaint", "system error", "system issue", "audit", "escalat", "broken", "refund issue", "issue with")):
        return "Issue"

    if _has_any(text, ("not interested", "declined", "won't use", "wont use", "cash only", "cash business", "no financing", "not a fit", "no opportunity", "does not use financing")):
        return "Not Int."

    if _has_any(text, ("snap finance", "uses snap", "koalafi", "koala fi", "affirm", "synchrony", "klarna", "afterpay", "sema financing", "uses aff ", "competitor")):
        return "Competitor"

    if _has_any(text, ("enrolled", "signed up", "sign up", "application submitted", "sent enrollment", "got them set", "completed enrollment", "submitted app")):
        return "Enrolled"

    if _has_any(text, ("training", "demo", "portal", "login", "onboarding", "walkthrough", "set up account", "account setup", "qr code", "rewards program", "pop materials")):
        return "Training"

    if _has_any(text, ("interested", "follow up", "follow-up", "return next", "come back", "asked me to return", "asked rep to return", "circle back", "will revisit", "revisit next")):
        return "Int/FU"

    return "Rel. Check-In"


def _stop_efficiency(classifications: list[str], total: int) -> float:
    """Productive ÷ total × 100. Productive = Int/FU + Enrolled + Training + Rel. Check-In."""
    if total == 0:
        return 0.0
    productive = sum(1 for label in classifications if label in ("Int/FU", "Enrolled", "Training", "Rel. Check-In"))
    return productive / total * 100


def _active_metrics(timestamps_by_date: dict) -> tuple[int, float]:
    """Active day = 3+ unique merchant stops. Avg hours = mean span(first→last) across active days only."""
    active_days = 0
    spans = []
    for ts in timestamps_by_date.values():
        if len(ts) < 3:
            continue
        active_days += 1
        sorted_ts = sorted(ts)
        hours = (sorted_ts[-1] - sorted_ts[0]).total_seconds() / 3600
        if hours > 0:
            spans.append(hours)
    avg_hours = (sum(spans) / len(spans)) if spans else 0.0
    return active_days, avg_hours


def _build_card_mix(classifications: list[str], total: int) -> dict[str, int]:
    """Cards show 6 buckets; Competitor + Issue collapse into Not Int. for visual simplicity."""
    raw = {"No Contact": 0, "Int/FU": 0, "Rel. Check-In": 0, "Training": 0, "Enrolled": 0, "Not Int.": 0}
    for label in classifications:
        if label in ("Competitor", "Issue"):
            raw["Not Int."] += 1
        else:
            raw[label] = raw.get(label, 0) + 1
    return _normalize_percent_mix(raw, max(total, 1))


def _normalize_percent_mix(raw: dict[str, int], total: int) -> dict[str, int]:
    values = {key: round(value / total * 100) for key, value in raw.items()}
    current = sum(values.values())
    if current != 100:
        largest_key = max(values, key=values.get)
        values[largest_key] = max(0, values[largest_key] + (100 - current))
    return values


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _format_h_mm(hours: float) -> str:
    if hours <= 0:
        return "0:00"
    total_minutes = int(round(hours * 60))
    return f"{total_minutes // 60}:{total_minutes % 60:02d}"


def _h_mm_to_hours(text: str) -> float:
    parts = str(text or "").split(":")
    if len(parts) != 2:
        return 0.0
    try:
        return int(parts[0]) + int(parts[1]) / 60
    except ValueError:
        return 0.0


def _freeze_closed_months(snapshot_root: Path, current_dir: Path, historical_path: Path) -> None:
    """For every snapshot older than current_dir, write its roster-sum totals to historical_path.

    Mirrors the archive's self-heal behavior so the totals table and the rankings
    archive never diverge: a closed month's totals are RE-WRITTEN on each run during
    the settlement window (SETTLEMENT_WINDOW_DAYS after rollover) so the funded-$
    figure climbs to accurate as late transactions settle, then freezes.

    A month entry with `"locked": true` is never overwritten — set it after pasting
    Sales Ops authoritative numbers. Entries already past the settlement window are
    also left untouched (their `locked` flag is irrelevant at that point).
    """
    payload: dict = {}
    existing_by_month: dict[tuple[int, int], dict] = {}
    if historical_path.exists():
        payload = json.loads(historical_path.read_text(encoding="utf-8"))
        for entry in payload.get("months", []):
            existing_by_month[(int(entry["year"]), int(entry["month"]))] = entry

    current_year, current_month = _parse_snapshot_name(current_dir.name)
    today = date.today()
    changed = False
    for snapshot_dir in sorted(p for p in snapshot_root.iterdir() if p.is_dir()):
        try:
            year, month = _parse_snapshot_name(snapshot_dir.name)
        except (ValueError, IndexError):
            continue
        if (year, month) >= (current_year, current_month):
            continue

        existing = existing_by_month.get((year, month))
        if existing is not None:
            # Respect manual Sales Ops patches.
            if existing.get("locked"):
                continue
            # Outside the settlement window — freeze as-is.
            days_since_rollover = (today - _first_day_of_next_month(year, month)).days
            if days_since_rollover > SETTLEMENT_WINDOW_DAYS:
                continue
            # else within window, unlocked — fall through and refresh in place.

        quota_rows = _load_json(snapshot_dir / "monthly_quota.json")
        if not quota_rows:
            continue
        quota = _quota_by_territory(quota_rows)
        actual = sum(item["actual"] for item in quota.values())
        budget = sum(item["budget"] for item in quota.values())
        if not (actual or budget):
            continue

        new_budget = round(budget, 2)
        new_actual = round(actual, 2)
        if existing is not None:
            if existing.get("budget") == new_budget and existing.get("actual") == new_actual:
                continue  # no change this run
            existing["budget"] = new_budget
            existing["actual"] = new_actual
            changed = True
            print(f"Refreshed {MONTH_NAMES[month]} {year} totals in {historical_path} (settling)")
        else:
            existing_by_month[(year, month)] = {
                "year": year, "month": month, "budget": new_budget, "actual": new_actual,
            }
            changed = True
            print(f"Froze {MONTH_NAMES[month]} {year} into {historical_path}")

    if not changed:
        return

    months = list(existing_by_month.values())
    months.sort(key=lambda m: (int(m["year"]), int(m["month"])))
    payload["months"] = months
    if "_source" not in payload:
        payload["_source"] = "Auto-frozen closed-month roster totals. Edit individual months to override with authoritative numbers; set \"locked\": true on an entry to pin it."
    historical_path.parent.mkdir(parents=True, exist_ok=True)
    historical_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _archive_closed_months(snapshot_root: Path, current_dir: Path, archive_dir: Path) -> None:
    """For every snapshot older than current_dir, write per-territory rankings data
    to archive_dir/YYYY-MM.json.

    A closed month is archived IMMEDIATELY at rollover so it's available for the
    start-of-month leadership screenshot. Four of the five ranking columns
    (merchants, lead conversion, stops, avg time) are field-activity metrics that
    are final the moment the month closes; only Budget % drifts upward as late
    funded-dollar transactions settle over the new month's first week.

    To handle that drift, an unlocked archive is RE-WRITTEN on each run during the
    settlement window (SETTLEMENT_WINDOW_DAYS after rollover) so Budget % self-heals
    to accurate without manual work. The dashboard refreshes the prior month's
    monthly_quota.json through day 7, so the window is set just beyond that.

    Two ways an archive becomes permanent:
      • `"locked": true` in the JSON — set this after patching with Sales Ops
        authoritative numbers; the cron will never overwrite it again.
      • The settlement window elapses — after that, the auto numbers are frozen
        as-is and no longer re-written.
    """
    current_year, current_month = _parse_snapshot_name(current_dir.name)
    today = date.today()

    for snapshot_dir in sorted(p for p in snapshot_root.iterdir() if p.is_dir()):
        try:
            year, month = _parse_snapshot_name(snapshot_dir.name)
        except (ValueError, IndexError):
            continue
        if (year, month) >= (current_year, current_month):
            continue
        if (year, month) < ARCHIVE_MIN_YEAR_MONTH:
            continue

        archive_path = archive_dir / f"{year:04d}-{month:02d}.json"
        existing = None
        if archive_path.exists():
            try:
                existing = json.loads(archive_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}
            # Manual Sales Ops patch — never clobber.
            if existing.get("locked"):
                print(f"Skipping {MONTH_NAMES[month]} {year} archive (locked)")
                continue
            # Past the settlement window — freeze the auto numbers as-is.
            days_since_rollover = (today - _first_day_of_next_month(year, month)).days
            if days_since_rollover > SETTLEMENT_WINDOW_DAYS:
                continue
            # else: within window, unlocked — fall through and refresh in place.

        quota_rows = _load_json(snapshot_dir / "monthly_quota.json")
        if not quota_rows:
            continue
        credited_rows = _load_json(snapshot_dir / "credited_enrollments.json")
        checkin_rows = _load_json(snapshot_dir / "maps_check_ins.json")

        quota_by_terr = _quota_by_territory(quota_rows)
        enrollments_by_terr = _enrollments_by_territory(credited_rows)
        activity_by_terr = _activity_by_territory(checkin_rows)

        territories = []
        actual_sum = 0.0
        budget_sum = 0.0
        for code, rep in TERRITORY_MAP.items():
            quota = quota_by_terr.get(code, {})
            actual = quota.get("actual", 0.0)
            budget = quota.get("budget", 0.0)
            attainment = (actual / budget * 100) if budget else 0.0
            actual_sum += actual
            budget_sum += budget

            activity = activity_by_terr.get(code, _empty_activity())
            new_merchants = enrollments_by_terr.get(code, 0)
            prospect_stops = activity["prospect"]
            lead_conversion = (new_merchants / prospect_stops * 100) if prospect_stops else 0.0

            territories.append(
                {
                    "code": code,
                    "rep": rep,
                    "attainment": round(attainment, 1),
                    "newMerchants": new_merchants,
                    "leadConversion": round(lead_conversion, 1),
                    "stops": activity["total"],
                    "avgDay": _format_h_mm(activity["avg_hours"]),
                }
            )

        attainment_sum = (actual_sum / budget_sum * 100) if budget_sum else 0.0
        totals_block = {
            "actual": round(actual_sum, 2),
            "budget": round(budget_sum, 2),
            "attainment": round(attainment_sum, 1),
        }

        # Skip the write entirely if the substantive data is unchanged from the
        # existing file. Otherwise the timestamp alone would change on every run
        # during the settlement window, producing a daily no-op commit.
        if archive_path.exists() and isinstance(existing, dict):
            if existing.get("totals") == totals_block and existing.get("territories") == territories:
                continue

        archive_payload = {
            "year": year,
            "month": month,
            "monthName": MONTH_NAMES[month],
            "frozenAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "locked": False,
            "_note": (
                "Auto-generated rankings archive. Budget %/actual/budget self-heal "
                "during the first week as late funded $ settles. To pin Sales Ops "
                "authoritative numbers, edit the values and set \"locked\": true — "
                "the pipeline will then never overwrite this file."
            ),
            "totals": totals_block,
            "territories": territories,
        }

        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(
            json.dumps(archive_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Archived {MONTH_NAMES[month]} {year} -> {archive_path}")


def _first_day_of_next_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def _list_archives(archive_dir: Path) -> list[dict]:
    """List archives present on disk. Returned newest-first for the dropdown."""
    if not archive_dir.exists():
        return []
    found: list[dict] = []
    for path in sorted(archive_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            year = int(data["year"])
            month = int(data["month"])
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            continue
        if (year, month) < ARCHIVE_MIN_YEAR_MONTH:
            continue
        found.append(
            {
                "year": year,
                "month": month,
                "monthName": data.get("monthName") or MONTH_NAMES.get(month, ""),
                "key": f"{year:04d}-{month:02d}",
            }
        )
    return sorted(found, key=lambda m: (m["year"], m["month"]), reverse=True)


def _build_totals(current_dir: Path, historical_path: Path, through_date: date, month_complete: bool = False) -> list[dict]:
    """Historical closed months from historical_path, current month from the snapshot (company-wide, no roster filter).

    If month_complete is True, the current snapshot's month is calendar-closed (the
    dashboard simply hasn't rolled over yet because SF doesn't have new-month data),
    so we label it "Final" instead of "MTD" and drop the "Through Apr 30" sub.
    """
    rows = []
    historical_months: set[tuple[int, int]] = set()

    if historical_path.exists():
        payload = json.loads(historical_path.read_text(encoding="utf-8"))
        for entry in payload.get("months", []):
            year = int(entry["year"])
            month = int(entry["month"])
            actual = float(entry["actual"])
            budget = float(entry["budget"])
            attainment = (actual / budget * 100) if budget else 0.0
            historical_months.add((year, month))
            rows.append(
                {
                    "period": f"{MONTH_NAMES[month]} {year}",
                    "sub": "",
                    "actual": round(actual, 2),
                    "budget": round(budget, 2),
                    "attainment": round(attainment, 1),
                }
            )

    current_year, current_month = _parse_snapshot_name(current_dir.name)
    if (current_year, current_month) not in historical_months:
        quota_rows = _load_json(current_dir / "monthly_quota.json")
        if quota_rows:
            quota = _quota_by_territory(quota_rows)
            actual = sum(item["actual"] for item in quota.values())
            budget = sum(item["budget"] for item in quota.values())
            if actual or budget:
                attainment = (actual / budget * 100) if budget else 0.0
                if month_complete:
                    period = f"{MONTH_NAMES[current_month]} {current_year} Final"
                    sub = "Pending Sales Ops reconciliation"
                else:
                    period = f"{MONTH_NAMES[current_month]} MTD"
                    sub = f"Through {_format_date_short(through_date)}"
                rows.append(
                    {
                        "period": period,
                        "sub": sub,
                        "actual": round(actual, 2),
                        "budget": round(budget, 2),
                        "attainment": round(attainment, 1),
                    }
                )

    if len(rows) >= 2:
        total_actual = sum(row["actual"] for row in rows)
        total_budget = sum(row["budget"] for row in rows)
        rows.append(
            {
                "period": "YTD Total",
                "actual": round(total_actual, 2),
                "budget": round(total_budget, 2),
                "attainment": round((total_actual / total_budget * 100) if total_budget else 0.0, 1),
                "tone": "total",
            }
        )
    return rows


def _guard_freshness(through_date: date, allow_stale: bool) -> None:
    if allow_stale:
        return
    staleness = (date.today() - through_date).days
    if staleness > MAX_SNAPSHOT_STALENESS_DAYS:
        raise SystemExit(
            f"ERROR: latest activity date is {through_date} ({staleness} days old). "
            f"Refusing to generate report older than {MAX_SNAPSHOT_STALENESS_DAYS} days. "
            f"Run the dashboard refresh first, or pass --allow-stale to override."
        )


def _attach_ranks(items: list[dict]) -> None:
    rank_specs = [
        ("attainment", "attainment"),
        ("efficiency", "stopEfficiency"),
        ("merchants", "newMerchants"),
        ("conversion", "leadConversion"),
        ("stops", "stops"),
        ("avgDay", "avg_hours_sort"),
    ]
    for item in items:
        item["avg_hours_sort"] = _h_mm_to_hours(item["avgDay"])

    for rank_name, field in rank_specs:
        sorted_values = sorted({item[field] for item in items}, reverse=True)
        for item in items:
            item.setdefault("ranks", {})[rank_name] = sorted_values.index(item[field]) + 1

    for item in items:
        item.pop("avg_hours_sort", None)


def _build_executive_note(territories: list[dict], through_date: date, biz_remaining: int) -> str:
    stops = sum(item["stops"] for item in territories)
    merchants = sum(item["newMerchants"] for item in territories)
    leader = max(territories, key=lambda item: item["attainment"])
    enrollment_leader = max(territories, key=lambda item: item["newMerchants"])
    return (
        f"Updated budget origination data through {_format_date_long(through_date)}. "
        f"{stops:,} stops logged, {merchants} new merchants enrolled. "
        f"{biz_remaining} business days remain. {leader['code']} leads attainment at "
        f"{leader['attainment']:.1f}%, while {enrollment_leader['rep']} leads new merchant volume."
    )


def _latest_activity_date(credited_rows: list[dict], checkin_rows: list[dict]) -> date | None:
    dates = []
    for row in credited_rows:
        dt = _parse_date(row.get("Enrollment Date"))
        if dt:
            dates.append(dt)
    for row in checkin_rows:
        dt = _parse_checkin_datetime(row.get("_label_Created Date/Time"))
        if dt:
            dates.append(dt.date())
    return max(dates) if dates else None


def _parse_date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _parse_checkin_datetime(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y, %I:%M %p", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%m/%d/%Y":
                parsed = parsed.replace(hour=12)
            return parsed
        except ValueError:
            pass
    return None


def _currency(value) -> float:
    if isinstance(value, dict):
        return _safe_float(value.get("amount"))
    return _safe_float(value)


def _safe_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _business_days_in_month(year: int, month: int) -> int:
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    current = date(year, month, 1)
    count = 0
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _business_days_elapsed(day: date) -> int:
    current = date(day.year, day.month, 1)
    count = 0
    while current <= day:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _business_days_remaining(day: date) -> int:
    if day.month == 12:
        end = date(day.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(day.year, day.month + 1, 1) - timedelta(days=1)
    current = day + timedelta(days=1)
    count = 0
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _format_date_long(day: date) -> str:
    return f"{MONTH_NAMES[day.month]} {day.day}, {day.year}"


def _format_date_short(day: date) -> str:
    return f"{MONTH_NAMES[day.month][:3]} {day.day}"


def _empty_activity() -> dict:
    return {
        "total": 0,
        "existing": 0,
        "prospect": 0,
        "active_days": 0,
        "total_visited": 0,
        "avg_hours": 0.0,
        "efficiency": 0.0,
        "mix": {
            "No Contact": 0,
            "Int/FU": 0,
            "Rel. Check-In": 0,
            "Training": 0,
            "Enrolled": 0,
            "Not Int.": 0,
        },
    }


if __name__ == "__main__":
    main()
