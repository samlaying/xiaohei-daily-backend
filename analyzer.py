"""分析 pass — 日报生成的灵魂：先判断什么值得写，再动笔。

输出结构化分析（JSON 落库，可经 /api/analysis 审阅）：
  headline / topItems / compress / misc(业务理解·技能习得·产出物)
  deliverables / drillDown / risks
"""

from __future__ import annotations

import logging
import json
from datetime import datetime

import ai_client
import db
import memory
import prompt as prompts
import config

log = logging.getLogger("analyzer")

_REQUIRED_KEYS = ("headline", "topItems", "compress", "misc",
                  "deliverables", "drillDown", "risks")


def analyze_day(date: str = None, force: bool = False) -> dict | None:
    """
    对某天做分析。无素材返回 None；AI 失败抛异常（由报告层降级）。
    force=True 时忽略缓存重跑。
    """
    if not date:
        date = db.biz_today()

    ctx = memory.build_generation_context(date)

    if not ctx["records"] and not ctx["inputs"]:
        log.info("[%s] 无素材，跳过分析", date)
        return None

    if not force:
        cached = db.get_day_analysis(date)
        if cached:
            try:
                analysis = json.loads(cached["content_json"])
                log.info("[%s] 使用缓存分析（headline: %s）", date,
                         str(analysis.get("headline"))[:50])
                return analysis
            except Exception:
                pass  # 缓存损坏，重跑

    user_prompt = prompts.build_analysis_user_prompt(
        profile=ctx["profile"],
        inputs_text=ctx["inputsText"],
        records_text=ctx["recordsText"],
        yesterday_plan=ctx["yesterdayPlan"],
        recent_log=ctx["recentLog"],
    )

    full_system = (prompts.ANALYSIS_SYSTEM_PROMPT
                   + "\n\n输出 JSON 结构：\n" + prompts.ANALYSIS_OUTPUT_SCHEMA)

    analysis = ai_client.chat_json(full_system, user_prompt, max_tokens=3000)

    # 兜底：缺失字段补空，保证下游可用
    for k in _REQUIRED_KEYS:
        analysis.setdefault(k, [] if k != "headline" and k != "headline_reason" else "")
    analysis.setdefault("headline_reason", "")

    db.upsert_day_analysis(date, json.dumps(analysis, ensure_ascii=False),
                           model=config.AI_TEXT_MODEL)
    log.info("[%s] 分析完成 — %s", date, analysis.get("headline", ""))

    return analysis


def get_cached(date: str = None) -> dict | None:
    """只读缓存的分析（不触发 AI 调用），供 API 展示。"""
    if not date:
        date = db.biz_today()
    row = db.get_day_analysis(date)
    if not row:
        return None
    try:
        return json.loads(row["content_json"])
    except Exception:
        return None
