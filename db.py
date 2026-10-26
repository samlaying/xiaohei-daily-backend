"""SQLite database setup and operations.

时间约定：
- 存储：一律存「机器本地时间的 naive ISO 字符串」（如 2026-10-25T14:30:00）。
- 业务日：日期参数（YYYY-MM-DD）与"今天"一律按业务时区（config.REPORT_TIMEZONE，
  默认北京时间）解释——北京一个工作日可能横跨机器本地两个日期，边界在查询处换算。
- 显示/聚合：对外输出（活跃时段、热力图小时、时间线时刻）都换算成业务时区。
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import contextmanager

import config

BIZ_TZ = ZoneInfo(config.REPORT_TIMEZONE)   # 业务时区（默认北京时间）
SYS_TZ = datetime.now().astimezone().tzinfo  # 机器本地时区


def biz_today() -> str:
    """业务时区的今天（YYYY-MM-DD）。"""
    return datetime.now(BIZ_TZ).strftime("%Y-%m-%d")


def _to_biz(dt: datetime) -> datetime:
    """naive 机器本地时间 → naive 业务时区时间（用于显示与按日聚合）。"""
    return dt.replace(tzinfo=SYS_TZ).astimezone(BIZ_TZ).replace(tzinfo=None)


def biz_bounds(date_str: str) -> tuple:
    """业务时区某一天 → 机器本地 naive ISO 边界（供 SQL 字符串比较）。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    start = d.replace(tzinfo=BIZ_TZ).astimezone(SYS_TZ).replace(tzinfo=None)
    end = d.replace(hour=23, minute=59, second=59, tzinfo=BIZ_TZ).astimezone(SYS_TZ).replace(tzinfo=None)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def _now_local():
    """当前本地时间，naive ISO（秒级）。"""
    return datetime.now().isoformat(timespec="seconds")


def _today_range():
    """业务时区"今天"对应的机器本地 ISO 边界。"""
    return biz_bounds(biz_today())


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
            is_deliverable INTEGER NOT NULL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS daily_inputs (
            id TEXT PRIMARY KEY,
            input_date TEXT NOT NULL,
            key_data TEXT,
            blocker TEXT,
            judgment TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_daily_inputs_date ON daily_inputs(input_date);

        CREATE TABLE IF NOT EXISTS day_analysis (
            id TEXT PRIMARY KEY,
            analysis_date TEXT NOT NULL UNIQUE,
            content_json TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        # 旧库迁移：work_records 补 is_deliverable 列
        try:
            conn.execute("ALTER TABLE work_records ADD COLUMN is_deliverable INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass


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
                       details=None, is_deliverable=0):
    rid = str(uuid.uuid4())
    now = _now_local()
    started_at = started_at or now
    ended_at = ended_at or now
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO work_records (id, started_at, ended_at, category, summary, "
            "details_json, confidence, source, screenshot_path, is_deliverable, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, started_at, ended_at, category, summary,
             details, confidence, source, screenshot_path, is_deliverable, now, now)
        )
    return rid


def _normalize_date_range(start_date, end_date):
    """日期参数按业务时区解释：YYYY-MM-DD → 机器本地 ISO 边界；完整 ISO 原样透传。"""
    if start_date and len(start_date) == 10:  # YYYY-MM-DD
        start_date = biz_bounds(start_date)[0]
    if end_date and len(end_date) == 10:  # YYYY-MM-DD
        end_date = biz_bounds(end_date)[1]
    return start_date, end_date


def query_work_records(start_date=None, end_date=None, deliverables_only=False):
    start_date, end_date = _normalize_date_range(start_date, end_date)
    extra = " AND is_deliverable = 1" if deliverables_only else ""
    with get_conn() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ? AND started_at <= ?"
                + extra + " ORDER BY started_at",
                (start_date, end_date)
            ).fetchall()
        elif start_date:
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ?"
                + extra + " ORDER BY started_at",
                (start_date,)
            ).fetchall()
        else:
            start, end = _today_range()
            rows = conn.execute(
                "SELECT * FROM work_records WHERE started_at >= ? AND started_at <= ?"
                + extra + " ORDER BY started_at",
                (start, end)
            ).fetchall()
    return [dict(r) for r in rows]


# ── App Usage ──

def create_app_usage(app_name, started_at, ended_at, duration_sec):
    rid = str(uuid.uuid4())
    now = _now_local()
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

def _report_bounds(start_date: str, end_date: str) -> tuple:
    """写入/查询统一：日期字符串补全为当天完整边界，保证字符串比较一致。"""
    if start_date and len(start_date) == 10:
        start_date += "T00:00:00"
    if end_date and len(end_date) == 10:
        end_date += "T23:59:59"
    return start_date, end_date


def create_report(report_type, title, content, start_date, end_date, status="completed"):
    rid = str(uuid.uuid4())
    now = _now_local()
    start_date, end_date = _report_bounds(start_date, end_date)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (id, type, title, content, start_date, end_date, "
            "status, language, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, report_type, title, content, start_date, end_date, status, "zh-CN", now, now)
        )
    return rid


def replace_report(report_type, title, content, start_date, end_date, status="completed"):
    """同日同类型重复生成时替换旧行（保留最新一份）。"""
    rid = str(uuid.uuid4())
    now = _now_local()
    start_date, end_date = _report_bounds(start_date, end_date)
    with get_conn() as conn:
        conn.execute("DELETE FROM reports WHERE type = ? AND start_date = ? AND end_date = ?",
                     (report_type, start_date, end_date))
        conn.execute(
            "INSERT INTO reports (id, type, title, content, start_date, end_date, "
            "status, language, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, report_type, title, content, start_date, end_date, status, "zh-CN", now, now)
        )
    return rid


def query_reports(start_date=None, end_date=None, report_type=None):
    start_date, end_date = _report_bounds(start_date, end_date)
    cond, args = "", []
    if report_type:
        cond += " AND type = ?"
        args.append(report_type)
    if not start_date and not end_date:
        start_date, end_date = _today_range()
    if start_date and end_date:
        cond = "start_date <= ? AND end_date >= ?" + cond
        args = [end_date, start_date, *args]  # 区间重叠匹配：报告区间与查询区间有交集即返回
    elif start_date:
        cond = "end_date >= ?" + cond
        args = [start_date, *args]
    else:
        cond = "start_date <= ?" + cond
        args = [end_date, *args]
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE " + cond + " ORDER BY created_at DESC", args
        ).fetchall()
    return [dict(r) for r in rows]


# ── Daily Inputs（④ 关键数据 / ⑤ 卡点+判断，人工补录素材）──

def add_daily_input(key_data=None, blocker=None, judgment=None, input_date=None):
    rid = str(uuid.uuid4())
    input_date = input_date or biz_today()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO daily_inputs (id, input_date, key_data, blocker, judgment, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (rid, input_date, key_data, blocker, judgment, _now_local())
        )
    return rid


def query_daily_inputs(input_date=None):
    input_date = input_date or biz_today()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_inputs WHERE input_date = ? ORDER BY created_at",
            (input_date,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Day Analysis（分析 pass 结果，可审阅）──

def upsert_day_analysis(analysis_date, content_json, model=None):
    now = _now_local()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO day_analysis (id, analysis_date, content_json, model, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(analysis_date) DO UPDATE SET "
            "content_json=excluded.content_json, model=excluded.model, updated_at=excluded.updated_at",
            (str(uuid.uuid4()), analysis_date, content_json, model, now, now)
        )


def get_day_analysis(analysis_date):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM day_analysis WHERE analysis_date = ?", (analysis_date,)
        ).fetchone()
    return dict(row) if row else None


# ── Aggregations ──

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

    earliest = _to_biz(min(timestamps))   # 活跃时段按业务时区（北京时间）显示
    latest = _to_biz(max(timestamps))

    return {
        "recordCount": len(records),
        "deliverableCount": sum(1 for r in records if r.get("is_deliverable")),
        "focusMinutes": round(focus_seconds / 60),
        "activePeriod": f"{earliest.strftime('%H:%M')} — {latest.strftime('%H:%M')}",
        "activeStart": earliest.isoformat(),
        "activeEnd": latest.isoformat(),
        "categoryBreakdown": {k: round(v / 60) for k, v in
                              sorted(category_secs.items(), key=lambda x: -x[1])},
    }


def _parse_ts(s):
    """解析 ISO 时间戳 → naive 本地时间。兼容旧的带时区格式（含 UTC）。"""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def query_heat_map(start_date=None, end_date=None):
    """Return hourly activity counts per day."""
    records = query_work_records(start_date, end_date)
    day_map = {}
    for r in records:
        # 按业务日分桶：记录时刻换算到业务时区后取日期与小时
        t = _parse_ts(r["started_at"])
        if t:
            bt = _to_biz(t)
            day = bt.date().isoformat()
            hour = bt.hour
        else:
            day, hour = r["started_at"][:10], 0
        if day not in day_map:
            day_map[day] = {"date": day, "hourlyCounts": [0]*24, "focusMinutes": 0,
                            "totalRecords": 0, "categories": {}}
        entry = day_map[day]
        entry["hourlyCounts"][hour] += 1
        entry["totalRecords"] += 1
        cat = r.get("category", "其他")
        entry["categories"][cat] = entry["categories"].get(cat, 0) + 1
        t1 = _parse_ts(r["ended_at"])
        if t and t1:
            entry["focusMinutes"] += max(0, (t1 - t).total_seconds() / 60)
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
