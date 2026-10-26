"""记忆模块 — 报告生成时统一读取。

记忆 = 人货场 profile + 当日人工补录素材 + output-log 素材链 + 昨日日报的明日计划。
生成流程固定为：到点 → 读记忆 → 分析 → 生成 → 自检（本模块只负责"读"）。
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml

import config
import db

log = logging.getLogger("memory")

# output-log 里最多回看的素材链天数（供分析 pass 参考连续性）
RECENT_LOG_DAYS = 14

_PROFILE_DEFAULTS = {
    "reader": "协作者和自己",          # 日报写给谁（周报自动切换为上级视角）
    "bossStyle": "关注结果数据与风险延期，反感空话和邀功",
    "teamKpi": "",                    # 团队目标/KPI + 我负责的部分
    "maxChars": config.REPORT_MAX_CHARS,
}

_PROFILE_TEMPLATE = """\
# 人货场定位 — 报告生成时自动读取，改动即时生效
# 人（写给谁）/ 货（什么算产出）/ 场（字数、结构）都在这里定义

# 日报写给谁：协作者和自己（默认）| 上级
reader: 协作者和自己

# 读者最关心什么/反感什么（分析 pass 与自检都会参考）
bossStyle: 关注结果数据与风险延期，反感空话和邀功

# 团队目标/KPI + 我负责的部分（示例：提升社区参与率至50%，我负责内容运营与活动）
teamKpi: ""

# 正文四段合计字数上限
maxChars: 500
"""


def ensure_profile():
    """首次运行时生成 profile 模板。"""
    path = config.PROFILE_PATH
    if not path.exists():
        path.write_text(_PROFILE_TEMPLATE, encoding="utf-8")
        log.info("已生成 profile 模板: %s（请补充 teamKpi）", path)


def load_profile() -> dict:
    """读取 profile.yaml，缺失字段用默认值兜底。"""
    prof = dict(_PROFILE_DEFAULTS)
    try:
        raw = yaml.safe_load(config.PROFILE_PATH.read_text(encoding="utf-8")) or {}
        for k in _PROFILE_DEFAULTS:
            if raw.get(k) not in (None, ""):
                prof[k] = raw[k]
    except Exception as e:
        log.warning("读取 profile 失败（使用默认值）: %s", e)
    return prof


# ── output-log 素材链 ──

def read_output_log() -> list[dict]:
    """
    解析 output-log.md，返回 [{date, text}, ...]（时间正序）。
    每个日期段的格式：
    ## 2026-10-25
    - 产出：...
    - 数据：...
    - 结论：...
    """
    path = config.OUTPUT_LOG_PATH
    if not path.exists():
        return []
    entries = []
    cur_date, cur_lines = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", line.strip())
        if m:
            if cur_date:
                entries.append({"date": cur_date, "text": "\n".join(cur_lines).strip()})
            cur_date, cur_lines = m.group(1), []
        elif cur_date:
            cur_lines.append(line)
    if cur_date:
        entries.append({"date": cur_date, "text": "\n".join(cur_lines).strip()})
    return entries


def append_output_log(date: str, lines: list[str]):
    """追加一天的素材链条目（产出物+数据+结论）；同日重复生成时跳过。"""
    path = config.OUTPUT_LOG_PATH
    if not path.exists():
        path.write_text("# 产出素材链（Timeline）\n\n", encoding="utf-8")
    if any(e["date"] == date for e in read_output_log()):
        log.debug("output-log 已有 %s 条目，跳过追加", date)
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## {date}\n")
        for ln in lines:
            f.write(f"{ln}\n")


# ── 昨日日报的明日计划（连续性核对）──

def _extract_section(md_text: str, section: str) -> str:
    """提取 markdown 中某个二级标题下的内容。"""
    m = re.search(rf"^##\s*{re.escape(section)}\s*$(.*?)(?=^##\s|\Z)",
                  md_text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def get_yesterday_plan(date: str = None) -> str:
    """从昨日日报（reports 表优先，文件兜底）提取「明日计划」段。日期按业务时区。"""
    if not date:
        date = db.biz_today()
    yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = db.query_reports(yesterday, yesterday, report_type="daily")
    content = rows[0]["content"] if rows else ""
    if not content:
        f = config.REPORT_DIR / f"{yesterday}.md"
        if f.exists():
            content = f.read_text(encoding="utf-8")
    return _extract_section(content, "明日计划")


# ── 生成上下文（到点后读取的全部记忆）──

def _format_record(r: dict) -> str:
    # 时刻按业务时区（北京时间）显示
    t0 = db._parse_ts(r["started_at"])
    t = db._to_biz(t0).strftime("%H:%M") if t0 else r["started_at"][:16]
    mark = "【产出】" if r.get("is_deliverable") else ""
    app = ""
    try:
        import json
        d = json.loads(r.get("details_json") or "{}")
        if d.get("frontmostApp") and d["frontmostApp"] != "Unknown":
            app = f" @ {d['frontmostApp']}"
    except Exception:
        pass
    return f"- {t} [{r['category']}]{app} {mark}{r['summary']}"


def _format_inputs(inputs: list[dict]) -> str:
    lines = []
    for i in inputs:
        if i.get("key_data"):
            lines.append(f"- 关键数据/现象：{i['key_data']}")
        if i.get("blocker"):
            lines.append(f"- 卡点：{i['blocker']}")
        if i.get("judgment"):
            lines.append(f"- 我的判断：{i['judgment']}")
    return "\n".join(lines)


def build_generation_context(date: str = None) -> dict:
    """
    汇总某天生成报告所需的全部记忆（日期按业务时区/北京时间解释）。
    返回 {date, profile, inputs, inputsText, records, deliverableRecords,
          recordsText, yesterdayPlan, recentLog}。
    """
    if not date:
        date = db.biz_today()

    profile = load_profile()
    inputs = db.query_daily_inputs(date)
    records = db.query_work_records(date, date)
    deliverable_records = [r for r in records if r.get("is_deliverable")]

    # 产出物排前面（货优先），其余按时间
    records_sorted = deliverable_records + [r for r in records if not r.get("is_deliverable")]
    records_text = "\n".join(_format_record(r) for r in records_sorted) or "（今日无截图记录）"

    # 近 N 天素材链（不含当天，当天还没写入）
    cutoff = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=RECENT_LOG_DAYS)).strftime("%Y-%m-%d")
    recent = [e for e in read_output_log() if cutoff <= e["date"] < date]
    recent_log = "\n\n".join(f"[{e['date']}]\n{e['text']}" for e in reversed(recent))

    return {
        "date": date,
        "profile": profile,
        "inputs": inputs,
        "inputsText": _format_inputs(inputs),
        "records": records,
        "deliverableRecords": deliverable_records,
        "recordsText": records_text,
        "yesterdayPlan": get_yesterday_plan(date),
        "recentLog": recent_log,
    }
