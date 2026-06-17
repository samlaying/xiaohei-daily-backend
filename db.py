"""SQLite database setup and operations."""

import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

import config


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _today_range():
    """Return (start, end) ISO strings for today in local time."""
    from datetime import datetime, timedelta
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start.isoformat(), end.isoformat()


def init_db():
    """Create tables if not exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS work_records (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            details_json TEXT,
            confidence REAL,
            source TEXT NOT NULL DEFAULT 'screenshot',
            screenshot_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_work_records_started_at ON work_records(started_at);
        CREATE INDEX IF NOT EXISTS idx_work_records_category ON work_records(category);

        CREATE TABLE IF NOT EXISTS app_usage_sessions (
            id TEXT PRIMARY KEY,
            app_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_app_usage_started ON app_usage_sessions(started_at);
        CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage_sessions(app_name);

        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            language TEXT NOT NULL DEFAULT 'zh-CN',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_type_created ON reports(type, created_at);
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Work Records ──

def create_work_record(category, summary, started_at=None, ended_at=None,
                       confidence=0.8, source="screenshot", screenshot_path=None,
                       details=None):
    rid = str(uuid.uuid4())
    now = _now_iso()
    started_at = started_at or now
    ended_at = ended_at or now
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO work_records (id, started_at, ended_at, category, summary, "
            "details_json, confidence, source, screenshot_path, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, started_at, ended_at, category, summary,
             details, confidence, source, screenshot_path, now, now)
        )
    return rid


def _normalize_date_range(start_date, end_date):
    """Normalize date strings to full ISO range for proper comparison."""
    if start_date and len(start_date) == 10:  # YYYY-MM-DD
        start_date = start_date + "T00:00:00"
    if end_date and len(end_date) == 10:  # YYYY-MM-DD
        end_date = end_date + "T23:59:59"
    return start_date, end_date


def query_work_records(start_date=None, end_date=None):
    start_date, end_date = _normalize_date_range(start_date, end_date)
    with get_conn() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ? AND started_at <= ? ORDER BY started_at",
                (start_date, end_date)
            ).fetchall()
        elif start_date:
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ? ORDER BY started_at",
                (start_date,)
            ).fetchall()
        else:
            start, end = _today_range()
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ? AND started_at <= ? ORDER BY started_at",
                (start, end)
            ).fetchall()
    return [dict(r) for r in rows]


# ── App Usage ──

def create_app_usage(app_name, started_at, ended_at, duration_sec):
    rid = str(uuid.uuid4())
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO app_usage_sessions (id, app_name, started_at, ended_at, duration_sec, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (rid, app_name, started_at, ended_at, duration_sec, now)
        )
    return rid


def query_app_usage(start_date=None, end_date=None):
    with get_conn() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT app_name as appName, SUM(duration_sec) as totalDurationSec, "
                "MIN(started_at) as firstUsedAt, MAX(ended_at) as lastUsedAt "
                "FROM app_usage_sessions WHERE started_at >= ? AND started_at <= ? "
                "GROUP BY app_name ORDER BY totalDurationSec DESC",
                (start_date, end_date)
            ).fetchall()
        else:
            start, end = _today_range()
            rows = conn.execute(
                "SELECT app_name as appName, SUM(duration_sec) as totalDurationSec, "
                "MIN(started_at) as firstUsedAt, MAX(ended_at) as lastUsedAt "
                "FROM app_usage_sessions WHERE started_at >= ? AND started_at <= ? "
                "GROUP BY app_name ORDER BY totalDurationSec DESC",
                (start, end)
            ).fetchall()
    return [dict(r) for r in rows]


# ── Reports ──

def create_report(report_type, title, content, start_date, end_date, status="completed"):
    rid = str(uuid.uuid4())
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (id, type, title, content, start_date, end_date, "
            "status, language, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, report_type, title, content, start_date, end_date, status, "zh-CN", now, now)
        )
    return rid


def query_reports(start_date=None, end_date=None):
    with get_conn() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT * FROM reports WHERE start_date >= ? AND end_date <= ? ORDER BY created_at DESC",
                (start_date, end_date)
            ).fetchall()
        else:
            start, end = _today_range()
            rows = conn.execute(
                "SELECT * FROM reports WHERE start_date >= ? AND end_date <= ? ORDER BY created_at DESC",
                (start, end)
            ).fetchall()
    return [dict(r) for r in rows]


def query_daily_summary(start_date=None, end_date=None):
    """聚合统计：记录条数、专注时长、活跃时段、分类时长分布。"""
    records = query_work_records(start_date, end_date)
    if not records:
        return None

    focus_seconds = 0.0
    category_secs = {}
    timestamps = []
    for r in records:
        t0 = _parse_ts(r["started_at"])
        t1 = _parse_ts(r["ended_at"])
        if t0 and t1:
            dur = max(0, (t1 - t0).total_seconds())
            focus_seconds += dur
            cat = r.get("category", "其他")
            category_secs[cat] = category_secs.get(cat, 0) + dur
            timestamps.append(t0)
            timestamps.append(t1)

    earliest = min(timestamps).astimezone()
    latest = max(timestamps).astimezone()

    return {
        "recordCount": len(records),
        "focusMinutes": round(focus_seconds / 60),
        "activePeriod": f"{earliest.strftime('%H:%M')} — {latest.strftime('%H:%M')}",
        "activeStart": earliest.isoformat(),
        "activeEnd": latest.isoformat(),
        "categoryBreakdown": {k: round(v / 60) for k, v in
                              sorted(category_secs.items(), key=lambda x: -x[1])},
    }


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def query_heat_map(start_date=None, end_date=None):
    """Return hourly activity counts per day."""
    records = query_work_records(start_date, end_date)
    day_map = {}
    for r in records:
        day = r["started_at"][:10]
        if day not in day_map:
            day_map[day] = {"date": day, "hourlyCounts": [0]*24, "focusMinutes": 0,
                            "totalRecords": 0, "categories": {}}
        entry = day_map[day]
        try:
            hour = int(r["started_at"][11:13])
        except (ValueError, IndexError):
            hour = 0
        entry["hourlyCounts"][hour] += 1
        entry["totalRecords"] += 1
        cat = r.get("category", "其他")
        entry["categories"][cat] = entry["categories"].get(cat, 0) + 1
        # estimate focus minutes from started_at/ended_at
        try:
            t0 = datetime.fromisoformat(r["started_at"])
            t1 = datetime.fromisoformat(r["ended_at"])
            entry["focusMinutes"] += max(0, (t1 - t0).total_seconds() / 60)
        except Exception:
            pass
    results = []
    for day in sorted(day_map):
        e = day_map[day]
        e["focusMinutes"] = round(e["focusMinutes"])
        top_cat = max(e["categories"], key=e["categories"].get) if e["categories"] else "其他"
        e["topCategory"] = top_cat
        del e["categories"]
        # activePeriod: first and last active hour
        active_hours = [h for h, c in enumerate(e["hourlyCounts"]) if c > 0]
        if active_hours:
            e["activePeriod"] = f"{active_hours[0]:02d}:00 — {active_hours[-1]+1:02d}:00"
        else:
            e["activePeriod"] = "暂无"
        results.append(e)
    return results
