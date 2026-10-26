"""HTTP API server — mimics xiaohei-daily-assistant's LobsterServer endpoints."""

import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify

import db
import ai_client
import config

log = logging.getLogger("server")

app = Flask(__name__)


def ok(data=None):
    return jsonify({"code": 0, "message": "success", "data": data})


def err(code, message):
    return jsonify({"code": code, "message": message, "data": None})


# ── API Documentation ──

@app.route("/", methods=["GET"])
def index():
    doc = """# 日报助手 — 接入 Agent API 文档

> 服务地址：http://{host}:{port}
> 文档版本：1.0.0 (Python backend)

---

## 通用约定

### 请求方式
所有接口均使用 **GET** 请求。

### 响应格式
所有接口统一返回 JSON：
```json
{{"code": 0, "message": "success", "data": null}}
```

### 日期时间参数格式
- 日期: `YYYY-MM-DD`
- 日期时间: `YYYY-MM-DD HH:mm:ss` 或 `YYYY-MM-DDTHH:mm:ss`
- 仅传日期时，查询范围为该日期的 00:00:00 ~ 23:59:59
- 未传参数时，默认查询今天

---

## 接口列表

### 1. 获取 API 文档
- `GET /`

### 2. 查询工作时间线
- `GET /api/timeline?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
- 返回全量记录，不做分页。

### 3. 查询工作报告
- `GET /api/report?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`

### 4. 查询时段热力图
- `GET /api/heat-map?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
- 默认近 7 天

### 5. 查询应用使用时长
- `GET /api/app-usage?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`

### 6. 健康检查
- `GET /api/health`

### 7. 手动触发截图分析
- `POST /api/capture` — 立即截图并分析

### 8. 补录当日素材（关键数据 / 卡点 / 我的判断）
- `POST /api/daily-input` — body JSON: `{{"keyData": "...", "blocker": "...", "judgment": "..."}}`
- `GET /api/daily-input?date=YYYY-MM-DD` — 查看已补录内容

### 9. 当日分析结论（生成日报前的分析 pass，可审阅）
- `GET /api/analysis?date=YYYY-MM-DD` — 读缓存
- `GET /api/analysis?date=YYYY-MM-DD&force=1` — 强制重跑

### 10. 手动生成报告
- `POST /api/report/generate` — body JSON: `{{"reportType": "daily|weekly|monthly", "date": "YYYY-MM-DD"}}`

### 11. 人货场配置
- `GET /api/profile` — 读取 data/profile.yaml 生效配置（编辑文件即可，即时生效）
""".format(host=config.HTTP_HOST, port=config.HTTP_PORT)
    return doc, 200, {"Content-Type": "text/markdown; charset=utf-8"}


# ── Work Timeline ──

@app.route("/api/timeline", methods=["GET"])
def timeline():
    start = request.args.get("startDate")
    end = request.args.get("endDate")
    records = db.query_work_records(start, end)
    return ok(records)


# ── Reports ──

@app.route("/api/report", methods=["GET"])
def report():
    start = request.args.get("startDate")
    end = request.args.get("endDate")
    records = db.query_reports(start, end)
    return ok(records)


# ── Heat Map ──

@app.route("/api/heat-map", methods=["GET"])
def heat_map():
    start = request.args.get("startDate")
    end = request.args.get("endDate")
    if not start and not end:
        from datetime import timedelta
        now = datetime.now()
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
    data = db.query_heat_map(start, end)
    return ok(data)


# ── App Usage ──

@app.route("/api/app-usage", methods=["GET"])
def app_usage():
    start = request.args.get("startDate")
    end = request.args.get("endDate")
    data = db.query_app_usage(start, end)
    return ok(data)


# ── Health ──

@app.route("/api/health", methods=["GET"])
def health():
    return ok({"status": "running", "interval_sec": config.SCREENSHOT_INTERVAL_SEC})


# ── Daily Summary (聚合统计) ──

@app.route("/api/daily-summary", methods=["GET"])
def daily_summary():
    start = request.args.get("startDate")
    end = request.args.get("endDate")
    data = db.query_daily_summary(start, end)
    return ok(data)


# ── Manual Capture ──

@app.route("/api/capture", methods=["POST"])
def manual_capture():
    """Manually trigger a screenshot capture and analysis."""
    import screenshot
    import collector
    try:
        images = screenshot.capture_screens()
        if not images:
            return err(400, "No screenshots captured")
        result = collector.analyze_and_store(images)
        return ok(result)
    except Exception as e:
        log.error("Manual capture failed: %s", e)
        return err(500, str(e))


# ── Daily Inputs（人工补录素材：④关键数据 ⑤卡点+判断）──

@app.route("/api/daily-input", methods=["GET"])
def get_daily_input():
    date = request.args.get("date")
    return ok(db.query_daily_inputs(date))


@app.route("/api/daily-input", methods=["POST"])
def add_daily_input():
    """补录当日素材。body JSON: {keyData, blocker, judgment, date?}，字段均可选。"""
    body = request.get_json(silent=True) or {}
    key_data = (body.get("keyData") or "").strip()
    blocker = (body.get("blocker") or "").strip()
    judgment = (body.get("judgment") or "").strip()
    if not any([key_data, blocker, judgment]):
        return err(400, "keyData/blocker/judgment 至少填一项")
    rid = db.add_daily_input(key_data=key_data or None,
                             blocker=blocker or None,
                             judgment=judgment or None,
                             input_date=body.get("date"))
    return ok({"id": rid})


# ── Day Analysis（当日分析结论，可审阅）──

@app.route("/api/analysis", methods=["GET"])
def get_analysis():
    import analyzer
    date = request.args.get("date")
    force = request.args.get("force") in ("1", "true")
    if force:
        try:
            data = analyzer.analyze_day(date, force=True)
        except Exception as e:
            log.error("Analysis failed: %s", e)
            return err(500, str(e))
    else:
        data = analyzer.get_cached(date)
    return ok(data)


# ── Report Generation（手动触发日报/周报/月报）──

@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    """body JSON: {reportType: daily|weekly|monthly, date?: YYYY-MM-DD}"""
    import report
    body = request.get_json(silent=True) or {}
    report_type = body.get("reportType", "daily")
    date = body.get("date")
    try:
        if report_type == "weekly":
            path = report.generate_weekly_and_save(end_date=date)
        elif report_type == "monthly":
            path = report.generate_monthly_and_save(month=date)
        else:
            path = report.generate_and_save(date=date)
        if not path:
            return err(400, "该时段无素材，未生成")
        return ok({"path": path})
    except Exception as e:
        log.error("Report generation failed: %s", e)
        return err(500, str(e))


# ── Profile（人货场定位）──

@app.route("/api/profile", methods=["GET"])
def get_profile():
    import memory
    return ok(memory.load_profile())


def start_server():
    """Start the HTTP server in a background thread."""
    import threading
    t = threading.Thread(
        target=lambda: app.run(host=config.HTTP_HOST, port=config.HTTP_PORT,
                               debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    log.info("HTTP server started on http://%s:%d", config.HTTP_HOST, config.HTTP_PORT)
    return t
