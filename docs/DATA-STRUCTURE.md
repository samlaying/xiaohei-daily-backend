# 数据目录结构设计（data/ 资产层）

> 状态：设计稿，待实施（2026-10-25）
> 定位：定义 data/ 的目录树与四个关键决策，作为「文件是 canonical、DB 降级为缓存」改造的依据。
> 实施后需同步更新 README 的「项目结构」一节。

## 文件夹结构

```
data/
├── memory/                      # ① 长期记忆 —— agent 每次对话都加载
│   ├── profile.yaml             #    人货场定位 + 写作偏好
│   ├── facts.md                 #    基本信息档案：角色、项目列表、术语表、长期目标
│   └── output-log.md            #    素材链：每天追加「产出+数据+结论」，周报月报的原料
│
├── days/                        # ② 每日记录 —— 纯文件夹，一天一目录
│   └── 2026-10-26/
│       ├── daily.md             #    日报（四段式正文 + 附录）
│       ├── analysis.md          #    当日分析结论（headline/topItems/卡点，人可读）
│       ├── inputs.yaml          #    当日补录：keyData / blocker / judgment
│       └── timeline.md          #    当日全量明细（60s 级记录，从 DB 导出归档）
│
├── weeks/2026-W43.md            # ③ 周报
├── months/2026-10.md            #    月报
│
├── screenshots/                 # 截图：7 天轮转，不入 git（唯一的二进制区）
└── xiaohei.db                   # SQLite：采集写入队列 + 检索索引，可由文件重建
```

## 四个关键决策

### 1. 文件是 canonical，DB 降级为缓存

现在反过来（DB 是真相，报告只是导出），要倒过来：采集循环往 DB 写（吞吐和查询方便），但每个周期结束把内容固化成文件。DB 坏了，丢的只是秒级原始明细，资产层无损。网站/线上 agent 同步的就是 `days/ + weeks/ + months/ + memory/` 这棵纯文本树，git 友好，一天一个 commit 都行。

### 2. "每日纯文件夹"里放什么，由温度决定

`timeline.md`（全量明细）放日目录，因为它是温数据的人类可读归档——热数据（截图 + DB）不进这个树；周报生成时清理截图、明细退出默认视图，但文件永远在。`daily.md` 是给人看的门面，`timeline.md` 是给"三个月后的自己/agent"查证的后院。

### 3. 记忆分两类，都是 agent 的必读上下文

- **偏好类**（`profile.yaml`）：读者是谁、老板风格、字数、结构、teamKPI——写周报前必读，这就是"方便准确写出周报"的机制。
- **事实类**（`facts.md`）：项目名词表（如"ego lite = 浏览器自动化项目"）、长期目标、协作关系。截图分析只能看到"当下在干嘛"，跨天连贯性（"这周都在推进域名自动化"）靠这个补。`output-log.md` 则是按天增长的事实流。

### 4. Agent 读取协议（比文件本身更重要）

| 上下文量 | 加载内容 |
| --- | --- |
| 每次对话必读 | memory/ 全部（profile + facts + output-log 近 30 天） |
| 聊某一天 | + 该日 daily.md + analysis.md |
| 写周报 | + 该周各日 daily.md（不需要 timeline） |
| 追查细节 | + 该日 timeline.md（按需，大文件） |

对话中产生的增量记忆（纠正措辞、新偏好）agent 写回 `memory/profile.yaml` 对应段落——记忆闭环就通了。

## 对现有代码的改动量（小）

- `report.py` 落盘路径：`days/{date}/daily.md`；`analyzer.py` 同步写 `analysis.md`；`daily-input` 接口落 `inputs.yaml`
- 新增 `days/{date}/timeline.md` 导出（日报生成时顺手做，数据从 DB 来）
- `memory.py` 的读取路径指向 `memory/` 目录，新增 `facts.md` 支持
- 周报/月报路径改 `weeks/`、`months/`，周报命名用 ISO 周号
- 现有 `data/reports/`、`data/profile.yaml`、`data/output-log.md` 做一次性迁移

## 实施注意（待确认）

- 当前 `.gitignore` 忽略整个 `data/`。若要让 `days/ + weeks/ + months/ + memory/` 这棵树"git 友好、一天一个 commit"，需调整忽略规则：仅忽略 `data/screenshots/` 与 `data/xiaohei.db`（或迁出到独立数据仓），其余纳入版本控制。
- 网站静态生成与线上 agent 同步依赖同一棵树，注意同步副本的只读约定。
