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
from datetime import date, datetime, timedelta
from pathlib import Path


TERRITORY_MAP = {
    "LTO-1": "Yemaira Hernandez",
    "LTO-2": "Omar Corona",
    "LTO-3": "Joseph Guerra",
    "LTO-5": "Jared Midkiff",
    "LTO-7": "Stephanie Whitlock",
    "RIC-1": "Cesar Flores",
    "RIC-2": "Claudia Gerhardt",
    "RIC-4": "Jeremy Moore",
    "RIC-6": "Phillip Mason",
    "RIC-7": "DeLon Phoenix",
    "RIC-8": "Eric Henderson",
    "RIC-9": "Matthew MacDonald",
}

TERRITORY_AREAS = {
    "LTO-1": "FL - Miami-Dade/Broward",
    "LTO-2": "TX - S. Houston/Valley/El Paso",
    "LTO-3": "TX - State Manager",
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
        "--allow-stale",
        action="store_true",
        help="Skip the freshness guard (for backfills or testing only)",
    )
    args = parser.parse_args()

    dashboard_root = Path(args.dashboard_root)
    snapshot_root = dashboard_root / "data" / "snapshots"
    output_path = Path(args.output)
    historical_path = Path(args.historical)

    report = build_report(snapshot_root, historical_path, allow_stale=args.allow_stale)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.weeklyTerritoryReport = "
        + json.dumps(report, indent=2, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} from {snapshot_root}")


def build_report(snapshot_root: Path, historical_path: Path, allow_stale: bool = False) -> dict:
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

    quota_by_rep = _quota_by_rep(quota_rows)
    enrollments_by_rep = _enrollments_by_rep(credited_rows)
    activity_by_rep = _activity_by_rep(checkin_rows)

    territories = []
    for code, rep in TERRITORY_MAP.items():
        quota = quota_by_rep.get(rep, {})
        actual = quota.get("actual", 0.0)
        budget = quota.get("budget", 0.0)
        attainment = (actual / budget * 100) if budget else 0.0

        activity = activity_by_rep.get(rep, _empty_activity())
        new_merchants = enrollments_by_rep.get(rep, 0)
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
                "avgDay": f'{activity["avg_hours"]:.1f}h',
                "activeDays": f'{activity["active_days"]} / {_business_days_elapsed(through_date)}',
                "mix": activity["mix"],
                "insight": _build_insight(code, rep, attainment, new_merchants, activity, lead_conversion),
            }
        )

    _attach_ranks(territories)
    territories.sort(key=lambda item: item["attainment"], reverse=True)
    for idx, item in enumerate(territories, start=1):
        item["rank"] = idx

    _freeze_closed_months(snapshot_root, current_dir, historical_path)
    totals = _build_totals(current_dir, historical_path, through_date)
    current_row = next((row for row in totals if row.get("period", "").endswith("MTD")), None)

    return {
        "meta": {
            "updatedThrough": _format_date_long(through_date),
            "stopsLogged": sum(item["stops"] for item in territories),
            "newMerchants": sum(item["newMerchants"] for item in territories),
            "businessDaysRemaining": biz_remaining,
            "note": _build_executive_note(territories, through_date, biz_remaining),
            "totalsNote": (
                f"{MONTH_NAMES[month]} MTD is a partial month - "
                f"{current_row['attainment']:.1f}% attainment through "
                f"{_format_date_short(through_date)} with {biz_remaining} business "
                f"day{'s' if biz_remaining != 1 else ''} remaining."
            )
            if current_row
            else "",
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


def _quota_by_rep(rows: list[dict]) -> dict[str, dict]:
    result = {}
    roster = set(TERRITORY_MAP.values())
    for row in rows:
        rep = (row.get("_label_User") or "").strip()
        if rep not in roster:
            continue
        budget = _currency(row.get("Funded Dollars Quota"))
        actual = _currency(row.get("Funded Dollars"))
        projected = _currency(row.get("Funding Projected"))
        result[rep] = {"budget": budget, "actual": actual, "projected": projected}
    return result


def _enrollments_by_rep(rows: list[dict]) -> Counter:
    counts = Counter()
    roster = set(TERRITORY_MAP.values())
    for row in rows:
        rep = (row.get("OSR Enrollment Credit") or "").strip()
        if rep in roster:
            counts[rep] += 1
    return counts


def _activity_by_rep(rows: list[dict]) -> dict[str, dict]:
    """Match the dashboard's field_activity dedup: key by (rep, stop, date), keep the longest comment."""
    roster = set(TERRITORY_MAP.values())
    deduped: dict[tuple[str, str, date], dict] = {}

    for row in rows:
        rep = (row.get("_label_Assigned") or "").strip()
        if rep not in roster:
            continue

        dt = _parse_checkin_datetime(row.get("_label_Created Date/Time"))
        if not dt:
            continue

        stop_name = (row.get("_label_Company / Account") or "Unknown").strip()
        comment = str(row.get("_label_Full Comments") or "")
        lead_val = row.get("Lead")
        is_existing = lead_val in (None, "", "null")

        key = (rep, stop_name, dt.date())
        existing_entry = deduped.get(key)
        if existing_entry is None or len(comment) > len(existing_entry["comment"]):
            deduped[key] = {
                "rep": rep,
                "datetime": dt,
                "comment": comment,
                "is_existing": is_existing,
            }

    by_rep = defaultdict(
        lambda: {"total": 0, "existing": 0, "prospect": 0, "dates": set(), "timestamps": defaultdict(list), "comments": []}
    )
    for stop in deduped.values():
        rep = stop["rep"]
        dt = stop["datetime"]
        bucket = by_rep[rep]
        bucket["total"] += 1
        bucket["existing" if stop["is_existing"] else "prospect"] += 1
        bucket["dates"].add(dt.date())
        bucket["timestamps"][dt.date()].append(dt)
        bucket["comments"].append(stop["comment"])

    result = {}
    for rep, item in by_rep.items():
        result[rep] = {
            "total": item["total"],
            "existing": item["existing"],
            "prospect": item["prospect"],
            "active_days": len(item["dates"]),
            "avg_hours": _avg_field_hours(item["timestamps"]),
            "mix": _activity_mix(item),
        }
    return result


def _activity_mix(item: dict) -> dict[str, int]:
    total = max(item["total"], 1)
    comments = item["comments"]
    no_contact = sum(1 for c in comments if _has_any(c, ("closed", "not in", "not available", "no one", "left card", "no contact")))
    training = sum(1 for c in comments if _has_any(c, ("training", "demo", "portal", "login", "onboarding", "qr", "pop", "reward")))
    not_int = sum(1 for c in comments if _has_any(c, ("not interested", "declined", "no opportunity", "not a fit", "does not use financing")))

    enrolled = 0
    rel_checkin = item["existing"]
    int_fu = max(item["prospect"] - no_contact - training - not_int, 0)

    raw = {
        "No Contact": no_contact,
        "Int/FU": int_fu,
        "Rel. Check-In": rel_checkin,
        "Training": training,
        "Enrolled": enrolled,
        "Not Int.": not_int,
    }
    return _normalize_percent_mix(raw, total)


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


def _avg_field_hours(day_map: dict[date, list[datetime]]) -> float:
    spans = []
    for timestamps in day_map.values():
        if len(timestamps) < 2:
            continue
        timestamps = sorted(timestamps)
        hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        if hours > 0:
            spans.append(hours)
    return round(sum(spans) / len(spans), 1) if spans else 0.0


def _freeze_closed_months(snapshot_root: Path, current_dir: Path, historical_path: Path) -> None:
    """For every snapshot older than current_dir, append its roster-sum totals to historical_path if absent.

    Idempotent: existing entries are never overwritten, so user-supplied corrections (e.g. manually
    folded-in RIC-1 numbers) survive subsequent runs. Preserves the `_source` description.
    """
    payload: dict = {}
    existing_months: set[tuple[int, int]] = set()
    if historical_path.exists():
        payload = json.loads(historical_path.read_text(encoding="utf-8"))
        for entry in payload.get("months", []):
            existing_months.add((int(entry["year"]), int(entry["month"])))

    current_year, current_month = _parse_snapshot_name(current_dir.name)
    new_entries: list[dict] = []
    for snapshot_dir in sorted(p for p in snapshot_root.iterdir() if p.is_dir()):
        try:
            year, month = _parse_snapshot_name(snapshot_dir.name)
        except (ValueError, IndexError):
            continue
        if (year, month) >= (current_year, current_month):
            continue
        if (year, month) in existing_months:
            continue
        quota_rows = _load_json(snapshot_dir / "monthly_quota.json")
        if not quota_rows:
            continue
        quota = _quota_by_rep(quota_rows)
        actual = sum(item["actual"] for item in quota.values())
        budget = sum(item["budget"] for item in quota.values())
        if not (actual or budget):
            continue
        new_entries.append({"year": year, "month": month, "budget": round(budget, 2), "actual": round(actual, 2)})

    if not new_entries:
        return

    months = list(payload.get("months", [])) + new_entries
    months.sort(key=lambda m: (int(m["year"]), int(m["month"])))
    payload["months"] = months
    if "_source" not in payload:
        payload["_source"] = "Auto-frozen closed-month roster totals. Edit individual months to override with authoritative numbers."
    historical_path.parent.mkdir(parents=True, exist_ok=True)
    historical_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for entry in new_entries:
        print(f"Froze {MONTH_NAMES[entry['month']]} {entry['year']} into {historical_path}")


def _build_totals(current_dir: Path, historical_path: Path, through_date: date) -> list[dict]:
    """Historical closed months from historical_path, current month from the snapshot (company-wide, no roster filter)."""
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
            quota = _quota_by_rep(quota_rows)
            actual = sum(item["actual"] for item in quota.values())
            budget = sum(item["budget"] for item in quota.values())
            if actual or budget:
                attainment = (actual / budget * 100) if budget else 0.0
                rows.append(
                    {
                        "period": f"{MONTH_NAMES[current_month]} MTD",
                        "sub": f"Through {_format_date_short(through_date)}",
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
        ("merchants", "newMerchants"),
        ("conversion", "leadConversion"),
        ("stops", "stops"),
        ("avgDay", "avg_hours_sort"),
    ]
    for item in items:
        item["avg_hours_sort"] = _safe_float(str(item["avgDay"]).replace("h", ""))

    for rank_name, field in rank_specs:
        sorted_values = sorted({item[field] for item in items}, reverse=True)
        for item in items:
            item.setdefault("ranks", {})[rank_name] = sorted_values.index(item[field]) + 1

    for item in items:
        item.pop("avg_hours_sort", None)


def _build_insight(code: str, rep: str, attainment: float, new_merchants: int, activity: dict, conversion: float) -> str:
    if new_merchants == 0:
        return f"{code} has field activity but no credited new merchants in the current month snapshot. The cleanest focus is converting prospect stops into enrollments."
    if attainment >= 70:
        return f"{code} is pacing well on budget attainment with {new_merchants} credited new merchants and {activity['total']} logged stops month-to-date."
    if conversion >= 12:
        return f"{code} is converting prospect activity efficiently with {new_merchants} new merchants. Budget lift is the next lever to watch."
    return f"{code} has {activity['total']} logged stops and {new_merchants} new merchants. The opportunity is improving conversion from prospect activity."


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
        "avg_hours": 0.0,
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
