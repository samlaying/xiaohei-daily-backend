# 日报助手 — Python Backend

定时截屏 → AI Vision 分析 → 分类存储 → **读记忆 → 分析 → 生成 → 自检** → 自动生成高质量 Markdown 日报 + 周报/月报。

## 核心能力

### 采集端（持续运行）
- **定时截图** — 可配置间隔（30s / 1min / 5min），macOS screencapture
- **前台应用聚焦** — 同时抓取当前前台 App + 窗口标题，喂给 AI 作为重点提示
- **AI Vision 分析** — 多模态模型分析截图内容（local-proxy，OpenAI 兼容）
- **隐私脱敏** — prompt 内置隐私规则：脱敏人员身份、聊天原文、敏感字段，只保留工作事项
- **11 类工作分类** — 开发、会议、沟通、文档、测试、设计、数据分析、学习、管理、产品、生活
- **产出物标记** — 截图分析时识别"真正留下痕迹的产出"（文档/代码/结论），记 📦 标记，日报重点优先写产出
- **应用使用时长** — 追踪前台应用切换，统计各应用使用时长
- **启动自检** — 首次截图自动检测屏幕录制权限（三路信号：锐利边缘/Laplacian/多帧变化）

### 报告端（到点触发：每天 18:00）
流水线固定为四段，AI 负责**分析和措辞**，你负责**素材和判断**：

```
到点 ──► 读记忆 ──► 分析 pass ──► 四段式生成 ──► 自检 pass ──► 落盘
         (memory)    (analyzer)    (report)       (checker)     + 素材链追加
```

1. **读记忆**（`memory.py`）— 人货场 profile + 当日人工补录（关键数据/卡点/判断）+ output-log 素材链（近 14 天）+ 昨日日报的「明日计划」（连续性核对）
2. **分析 pass**（`analyzer.py`）— 先判断再动笔：今天最值得让读者知道的一件事（headline + 理由）、2-4 条重点事项、应压缩的 KPI 无关事项、杂活按「业务理解/技能习得/产出物」归类、值得下钻的数据点、结构化卡点。结论 JSON 落库，可经 `/api/analysis` 审阅重跑
3. **四段式生成**（`report.py`）— 正文给人看：`今日重点进展`（产出优先带数字）/ `问题与风险`（已做动作—卡点—影响—下一步）/ `明日计划`（衔接昨日）/ `需要支持`（利他式：卡住影响什么目标、对方一个动作解锁什么），≤500 字；统计与全量时间线降级为附录，给"三个月后写简历/述职的自己"
4. **自检 pass**（`checker.py`）— 规则查硬指标（四段齐全/字数/数字/下一步/空话黑名单），AI 查软指标（写的是"做完了什么"吗、重点选对吗）；不合格自动带问题重写一轮，仍不过则在报告头部标注 warning
5. **素材链积累**（`data/output-log.md`）— 每天追加「产出+数据+结论」；**周报**（周五 18:30，阶段成果视角）与**月报**（月末 18:45，独立产出 Timeline，述职/简历素材）都基于它裁剪生成，同一素材三种场景

AI 全挂时自动降级为规则模板（status=fallback），报告不缺席。

## 快速开始

```bash
# 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 首次运行会生成 data/profile.yaml，请补充 teamKpi（人货场定位）
python3 main.py

# 指定截图间隔
SCREENSHOT_INTERVAL_SEC=30 python3 main.py    # 30秒
SCREENSHOT_INTERVAL_SEC=300 python3 main.py   # 5分钟
```

## HTTP API

启动后提供以下接口（默认 `http://127.0.0.1:8089`）：

| 接口 | 说明 |
|------|------|
| `GET /` | API 文档（Markdown） |
| `GET /api/health` | 健康检查 |
| `GET /api/timeline?startDate=&endDate=` | 工作时间线（全量记录） |
| `GET /api/daily-summary?startDate=&endDate=` | 聚合统计（条数、产出物数、专注时长、分类分布） |
| `GET /api/heat-map?startDate=&endDate=` | 时段热力图 |
| `GET /api/app-usage?startDate=&endDate=` | 应用使用时长 |
| `GET /api/report?startDate=&endDate=` | 已生成的报告列表 |
| `POST /api/capture` | 手动触发截图分析 |
| `GET/POST /api/daily-input` | 补录当日素材（`keyData` 关键数据 / `blocker` 卡点 / `judgment` 我的判断） |
| `GET /api/analysis?date=&force=1` | 当日分析结论（读缓存 / 强制重跑） |
| `POST /api/report/generate` | 手动生成报告（`{"reportType": "daily\|weekly\|monthly", "date": "..."}`） |
| `GET /api/profile` | 人货场配置（编辑 `data/profile.yaml` 即时生效） |

补录示例：
```bash
curl -X POST http://127.0.0.1:8089/api/daily-input \
  -H 'Content-Type: application/json' \
  -d '{"keyData": "参与率 32%→41%", "blocker": "物料等外部设计确认 3 天", "judgment": "不是进度慢，是外部链路影响排期"}'
```

## Markdown 日报示例

```markdown
# 2026-10-25 工作日报

## 今日重点进展
- 社区参与率本周 32% → 41%，距 50% 目标差 9pp，已完成分渠道数据核对。
- 日报流水线端到端联调通过：analyzer/checker/report 三模块完成。

## 问题与风险
- 已做动作：物料已提交外部设计确认。卡点：排队 3 天。影响：活动排期。
  下一步：给设计侧设截止时间，逾期升级。

## 明日计划
- 拆解参与率分渠道贡献，确定 41%→50% 补齐路径。

## 需要支持
- 请协助明确物料确认截止时间：直接关联参与率 KPI 节奏，一个日期即可解锁。

---

## 附录（数据与时间线）
### 概要
- 记录条数：9（其中产出物 3 条）
- 专注时长：6.8h
### 活动时间线（全量）
#### 11:20:00 `[文档]` · Typora 📦
...
```

## 权限要求

| 权限 | 用途 | 如何开启 |
|------|------|---------|
| 屏幕录制 | 截屏 | 系统设置 → 隐私与安全性 → 屏幕录制 → 给终端打勾 |
| 辅助功能 | 获取前台应用窗口标题 | 系统设置 → 隐私与安全性 → 辅助功能 → 给终端打勾 |

## AI 模型配置

默认走本机 local-proxy（OpenAI 兼容），API Key 自动读 `~/.myagents/config.json` 的 `providerApiKeys["local-proxy"]`：

```python
# config.py
AI_BASE_URL = "http://192.227.138.214:7863/v1"
AI_VISION_MODEL = "cn:glm-5v-turbo"   # 截图分析（多模态）
AI_TEXT_MODEL = "cn:glm-5.3-flash"    # 分析/生成/自检/周月报
```

模型名 `cn:` / `global:` 前缀选路由域。全部可用 `AI_BASE_URL` / `AI_API_KEY` / `AI_VISION_MODEL` / `AI_TEXT_MODEL` 环境变量覆盖。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_INTERVAL_SEC` | `60` | 截图间隔（秒） |
| `HTTP_PORT` | `8089` | API 端口 |
| `AI_API_KEY` | 读 myagents 配置 | 覆盖自动读取的 key |
| `AI_VISION_MODEL` / `AI_TEXT_MODEL` | 见上 | 模型覆盖 |
| `SCREENSHOT_KEEP_DAYS` | `7` | 截图保留天数（报告生成不删截图） |
| `SKIP_PERMISSION_CHECK` | - | 设置后跳过权限自检 |
| `EXIT_ON_PERMISSION_FAIL` | - | 权限未生效时直接退出 |

## 项目结构

```
├── main.py              # 入口：调度器（采集 60s / 日报 18:00 / 周报五 / 月报月末）+ HTTP 服务
├── config.py            # 配置（模型、路径、保留策略）
├── db.py                # SQLite（work_records / app_usage / reports / daily_inputs / day_analysis）
├── memory.py            # 记忆：profile + 补录素材 + output-log 素材链 + 昨日明日计划
├── analyzer.py          # 分析 pass：什么值得写 / 压缩什么 / 产出物 / 下钻点
├── report.py            # 日报（四段式+附录）/ 周报 / 月报，含降级模板
├── checker.py           # 自检 pass：规则硬指标 + AI 软指标 + 重写循环
├── collector.py         # 采集循环：截图→AI→分类→产出物标记→存储
├── screenshot.py        # macOS 截图（保留策略兜底清理）
├── app_tracker.py       # 前台应用追踪（osascript）
├── prompt.py            # 全部提示词（截图/分析/生成/自检/周月报）
├── permission_check.py  # 启动权限自检
├── server.py            # Flask HTTP API
└── data/                # 运行时数据（不入 git）
    ├── xiaohei.db
    ├── profile.yaml     # 人货场定位（首次运行生成，编辑即时生效）
    ├── output-log.md    # 产出素材链 Timeline
    ├── screenshots/
    └── reports/         # YYYY-MM-DD.md / weekly_*.md / monthly_*.md
```

## 文档

- [数据目录结构设计](docs/DATA-STRUCTURE.md) —— data/ 资产层结构（设计稿，待实施）
