# 日报助手 — Python Backend

纯后端服务，定时截屏 → AI Vision 分析 → 分类存储 → 自动生成 Markdown 日报。

## 核心能力

- **定时截图** — 可配置间隔（30s / 1min / 5min），macOS screencapture
- **前台应用聚焦** — 同时抓取当前前台 App + 窗口标题，喂给 AI 作为重点提示，提升识别精确度
- **AI Vision 分析** — 调用 Xiaomi Mimo（mimo-v2.5）多模态大模型分析截图内容
- **隐私脱敏** — prompt 内置隐私规则：脱敏人员身份、聊天原文、敏感字段，只保留工作事项
- **12 类工作分类** — 自动分类：开发、会议、沟通、文档、测试、设计、运维、数据分析、学习、管理、产品、生活
- **应用使用时长** — 追踪前台应用切换，统计各应用使用时长
- **Markdown 日报** — 自动生成精细日报（概要 + 分类分布 + 时间线），保存到 `data/reports/`
- **启动自检** — 首次截图自动检测屏幕录制权限，未生效立刻提醒
- **壁纸垃圾清理** — 启动时自动删除权限未生效期间的无用记录

## 快速开始

```bash
# 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动（默认 60s 间隔）
python3 main.py

# 指定间隔
SCREENSHOT_INTERVAL_SEC=30 python3 main.py    # 30秒
SCREENSHOT_INTERVAL_SEC=300 python3 main.py   # 5分钟
```

## HTTP API

启动后提供以下接口（默认 `http://127.0.0.1:8089`）：

| 接口 | 说明 |
|------|------|
| `GET /` | API 文档（Markdown） |
| `GET /api/health` | 健康检查 |
| `GET /api/timeline?startDate=&endDate=` | 工作时间线 |
| `GET /api/daily-summary?startDate=&endDate=` | 聚合统计（条数、专注时长、活跃时段、分类分布） |
| `GET /api/heat-map?startDate=&endDate=` | 时段热力图 |
| `GET /api/app-usage?startDate=&endDate=` | 应用使用时长 |
| `GET /api/report?startDate=&endDate=` | 已生成的报告列表 |
| `POST /api/capture` | 手动触发截图分析 |

## Markdown 日报示例

```markdown
# 2026-06-17 工作日报

## 概要
- 记录条数：30
- 专注时长：1.1h
- 活跃时段：12:32 — 13:37

## 分类时长分布
| 分类 | 时长 |
|------|------|
| 开发 | 0.8h |
| 产品 | 0.1h |
| 文档 | 0.1h |
| 沟通 | 2min |

## 活动时间线
### 13:37:37 `[开发]` · Terminal — main.py
正在调试截图分析功能...
```

## 权限要求

| 权限 | 用途 | 如何开启 |
|------|------|---------|
| 屏幕录制 | 截屏 | 系统设置 → 隐私与安全性 → 屏幕录制 → 给终端打勾 |
| 辅助功能 | 获取前台应用窗口标题 | 系统设置 → 隐私与安全性 → 辅助功能 → 给终端打勾 |

## AI 模型配置

默认使用 Xiaomi Mimo（mimo-v2.5），兼容 OpenAI 接口协议。

可在 `config.py` 修改：
```python
AI_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
AI_MODEL = "mimo-v2.5"
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_INTERVAL_SEC` | `60` | 截图间隔（秒） |
| `HTTP_PORT` | `8089` | API 端口 |
| `SKIP_PERMISSION_CHECK` | - | 设置后跳过权限自检 |
| `EXIT_ON_PERMISSION_FAIL` | - | 权限未生效时直接退出 |

## 项目结构

```
├── main.py              # 入口：调度器 + HTTP 服务
├── config.py            # 配置
├── db.py                # SQLite 数据库操作
├── screenshot.py        # macOS 截图
├── ai_client.py         # AI Vision API 调用
├── classifier.py        # 12 类工作分类规则
├── collector.py         # 核心循环：截图→AI→分类→存储
├── app_tracker.py       # 前台应用追踪（osascript）
├── prompt.py            # 截图分析 prompt
├── permission_check.py  # 启动权限自检
├── report.py            # Markdown 日报生成
├── server.py            # Flask HTTP API
├── requirements.txt
└── data/                # 运行时数据（不入 git）
    ├── xiaohei.db
    ├── screenshots/
    └── reports/
```
