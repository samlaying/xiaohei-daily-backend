"""Work category classifier — keyword rules reverse-engineered from xiaohei-daily-assistant."""

import re

CATEGORY_RULES = [
    {
        "category": "开发",
        "keywords": ["代码", "编程", "开发", "调试", "接口", "API", "前端", "后端", "全栈",
                     "仓库", "git", "commit", "PR", "部署", "构建", "编译", "运行", "报错",
                     "修复", "重构", "架构", "框架", "组件", "模块", "函数", "算法", "性能",
                     "缓存", "队列", "微服务", "容器", "docker", "脚本", "数据库", "日志",
                     "监控", "SDK", "coding", "debugging", "frontend", "backend", "repository",
                     "build", "compile", "error", "fix", "refactor", "component", "algorithm",
                     "performance", "queue", "script", "database", "log", "monitor"],
        "strong_keywords": ["VS Code", "IntelliJ", "IDEA", "PyCharm", "WebStorm", "Xcode",
                           "Postman", "Swagger", "Navicat", "DataGrip", "DBeaver", "GitHub",
                           "GitLab", "npm", "yarn", "vite", "jest", "pytest"],
        "patterns": [r"\b(REST|GraphQL|gRPC|WebSocket|OAuth|JWT|npm|yarn|webpack|vite|"
                     r"babel|eslint|jest|pytest|maven|gradle|CI/CD|DevOps)\b"],
    },
    {
        "category": "会议",
        "keywords": ["会议", "评审", "讨论", "同步", "纪要", "汇报", "周会", "晨会", "站会",
                     "复盘", "决策", "对齐", "meeting", "review", "discussion", "sync", "standup",
                     "report", "weekly", "brainstorm", "alignment"],
        "strong_keywords": ["腾讯会议", "Zoom", "飞书会议", "钉钉会议", "Google Meet", "会议室"],
    },
    {
        "category": "沟通",
        "keywords": ["沟通", "聊天", "消息", "邮件", "回复", "协作", "确认", "询问", "通知",
                     "提醒", "私聊", "群聊", "语音", "视频通话", "reply", "confirm", "ask",
                     "private", "group", "video call"],
        "strong_keywords": ["微信", "飞书", "钉钉", "企业微信", "Slack", "Telegram",
                           "Outlook", "QQ"],
    },
    {
        "category": "文档",
        "keywords": ["文档", "资料", "撰写", "整理", "方案", "说明", "手册", "指南", "教程",
                     "规范", "流程", "模板", "Wiki", "笔记", "脑图", "大纲", "归档",
                     "material", "organize", "description", "template", "outline"],
        "strong_keywords": ["Notion", "Confluence", "腾讯文档", "Google Docs", "Word", "WPS",
                           "Obsidian", "语雀", "石墨文档", "XMind"],
    },
    {
        "category": "测试",
        "keywords": ["测试", "验收", "冒烟", "回归", "单元测试", "集成测试", "性能测试",
                     "安全测试", "Bug", "缺陷", "复现", "验证", "断言", "QA", "质检",
                     "预发", "灰度", "smoke", "regression", "assert", "coverage"],
        "strong_keywords": ["Jira", "TestRail", "Selenium", "Playwright", "Puppeteer"],
    },
    {
        "category": "设计",
        "keywords": ["设计", "UI", "UX", "界面", "原型", "切图", "标注", "配色", "排版",
                     "视觉", "交互", "动效", "图标", "素材", "线框图", "品牌", "海报",
                     "prototype", "wireframe", "mockup"],
        "strong_keywords": ["Figma", "Sketch", "Adobe XD", "Illustrator", "Axure", "墨刀",
                           "MasterGo", "即时设计"],
    },
    {
        "category": "数据分析",
        "keywords": ["数据分析", "数据挖掘", "报表", "仪表盘", "指标", "KPI", "漏斗",
                     "留存", "转化", "归因", "趋势", "对比", "统计", "预测", "A/B测试",
                     "埋点", "用户画像", "analytics", "dashboard", "metrics", "funnel"],
        "strong_keywords": ["Excel", "Tableau", "FineBI", "Metabase", "ClickHouse",
                           "Spark", "Hive", "Presto", "Pandas"],
    },
    {
        "category": "学习",
        "keywords": ["学习", "阅读", "看书", "教程", "课程", "培训", "认证", "考试",
                     "刷题", "笔记", "总结", "研究", "调研", "了解", "熟悉", "掌握",
                     "入门", "进阶", "精通", "最佳实践", "learn", "study", "course",
                     "tutorial", "training", "research"],
        "strong_keywords": ["Coursera", "Udemy", "慕课网", "YouTube", "知乎", "掘金", "CSDN",
                           "LeetCode"],
    },
    {
        "category": "管理",
        "keywords": ["管理", "项目管理", "排期", "计划", "进度", "跟踪", "风险", "资源",
                     "协调", "安排", "分工", "考核", "绩效", "目标", "OKR", "预算",
                     "团队", "人员", "招聘", "面试", "入职", "离职", "周报", "月报",
                     "management", "project", "schedule", "plan", "okr", "kpi"],
        "strong_keywords": ["Jira", "Asana", "Monday", "飞书项目", "钉钉项目", "Tower"],
    },
    {
        "category": "产品",
        "keywords": ["产品", "需求", "PRD", "用户调研", "竞品分析", "功能", "特性",
                     "版本", "迭代", "规划", "排期", "价值", "痛点", "场景", "验收",
                     "requirement", "feature", "backlog", "epic", "MVP"],
        "strong_keywords": ["Axure", "墨刀", "MasterGo", "飞书多维表格"],
    },
    {
        "category": "生活",
        "keywords": ["私人", "脱敏", "不纳入日报", "休息", "娱乐", "游戏", "视频", "刷剧",
                     "购物", "社交", "新闻", "外卖", "吃饭", "喝水", "散步", "发呆",
                     "private", "personal", "entertainment", "gaming", "shopping", "break"],
        "strong_keywords": ["抖音", "快手", "B站", "小红书", "微博", "淘宝", "京东",
                           "美团", "Steam", "Netflix", "Spotify"],
    },
]


def classify(summary: str) -> str:
    """Classify a work summary into a category using keyword matching."""
    text = summary.lower()
    best_cat = "其他"
    best_score = 0

    for rule in CATEGORY_RULES:
        score = 0
        # strong keywords count 3x
        for kw in rule.get("strong_keywords", []):
            if kw.lower() in text:
                score += 3
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                score += 1
        for pat in rule.get("patterns", []):
            if re.search(pat, summary, re.IGNORECASE):
                score += 2
        if score > best_score:
            best_score = score
            best_cat = rule["category"]

    return best_cat
