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
