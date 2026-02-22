# 系统架构设计

## 概述

社交媒体自动运营机器人采用**混合架构**：读操作以 DOM 为主，写操作以固定流程为主。

### 设计原则

1. **读操作**：直接 DOM 解析，轻量、快速，不易触发反爬
2. **写操作**：固定 Workflow（登录、发布、评论、回复），类似 xiaohongshu-mcp

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    对外接口层 (HTTP / MCP)                             │
│  HTTP: FastAPI 8000  |  MCP: Streamable HTTP 18060                    │
│  src/servers/http_app.py  |  src/servers/mcp_server.py                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────┐
│                         Scheduler / 调度层                            │
│  （每日定时：发布、拉取 Feed、回复评论等）                               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Platform Adapters / 平台适配层                    │
│  XiaohongshuPlatform | TwitterPlatform | LinkedInPlatform             │
│  统一接口: login, check_login, get_feeds, search, get_post_detail,    │
│           publish, comment, reply                                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
         ┌─────────────────┐             ┌─────────────────────┐
         │  Reader (DOM)   │             │  Writer (Workflows)  │
         │  读操作         │             │  固定流程写操作       │
         │  - get_feeds    │             │  - login             │
         │  - search       │             │  - publish           │
         │  - get_detail   │             │  - comment           │
         └─────────────────┘             └─────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BrowserManager (Playwright)                        │
│  管理浏览器生命周期、Cookie、Page                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
social_media_op/
├── src/
│   ├── core/                    # 核心模块
│   │   ├── browser_manager.py   # 浏览器管理
│   │   └── types.py             # 通用类型
│   ├── platforms/               # 平台适配器
│   │   ├── base.py              # 抽象基类
│   │   └── xiaohongshu/         # 小红书
│   │       ├── platform.py      # 平台实现
│   │       ├── workflows.py     # 固定操作流程
│   │       └── constants.py     # URL、选择器
│   └── servers/                 # 对外接口层 ★
│       ├── http_app.py          # FastAPI HTTP API
│       ├── mcp_server.py        # MCP 服务（工具：check_login, publish, comment 等）
│       └── state.py             # 共享 platform 状态
├── scripts/
│   ├── login.py                 # 登录工具
│   ├── run_bot.py               # 主入口（演示）
│   ├── run_http.py              # 启动 HTTP API（端口 8000）
│   └── run_mcp.py               # 启动 MCP 服务（端口 18060）
├── config/
├── data/cookies/                # Cookie 存储
├── docs/
└── requirements.txt
```

---

## 统一接口 (PlatformBase)

所有平台实现需遵循以下接口：

| 方法 | 类型 | 说明 |
|------|------|------|
| `login()` | 写 | 打开登录页，等待手动登录，保存 Cookie |
| `check_login()` | 读 | 检查当前是否已登录 |
| `get_feeds(limit)` | 读 | 获取推荐列表 |
| `search(keyword, limit)` | 读 | 搜索内容 |
| `get_post_detail(post_id, xsec_token)` | 读 | 获取帖子详情（含评论） |
| `publish(content)` | 写 | 发布图文/视频 |
| `comment(post_id, content, xsec_token)` | 写 | 发表评论 |
| `reply(post_id, comment_id, content, xsec_token)` | 写 | 回复评论 |

---

## 读操作 vs 写操作

| 操作 | 实现方式 | 说明 |
|------|----------|------|
| 读 | DOM + Playwright | `page.query_selector`, `page.evaluate`，或解析 `__INITIAL_STATE__` |
| 写 | 固定 Workflow | 明确的 `goto → click → fill → click` 流程 |

---

## 与 xiaohongshu-mcp 的对应关系

| xiaohongshu-mcp | 本系统 |
|-----------------|--------|
| check_login_status | check_login() |
| publish_content | publish(PublishContent) |
| publish_with_video | publish(PublishContent(video=...)) |
| list_feeds | get_feeds() |
| search_feeds | search() |
| get_feed_detail | get_post_detail() |
| post_comment_to_feed | comment() |
| user_profile | get_user_profile() |

---

## 对外接口：HTTP 与 MCP

### HTTP API（FastAPI）

- **位置**：`src/servers/http_app.py`
- **启动**：`python scripts/run_http.py`，默认 `http://0.0.0.0:8000`
- **路由示例**：
  - `GET /health` — 健康检查
  - `GET /xiaohongshu/check_login` — 检查登录
  - `GET /xiaohongshu/feeds?limit=20` — 推荐列表
  - `GET /xiaohongshu/search?keyword=xxx` — 搜索
  - `POST /xiaohongshu/post_detail` — 帖子详情（body: post_id, xsec_token）
  - `POST /xiaohongshu/publish` — 发布（body: title, content, images, tags）
  - `POST /xiaohongshu/comment` — 评论（body: post_id, content, xsec_token）

### MCP 服务（Model Context Protocol）

- **位置**：`src/servers/mcp_server.py`
- **启动**：`python scripts/run_mcp.py`，默认 `http://0.0.0.0:18060/mcp`（与 xiaohongshu-mcp 端口一致）
- **工具**：`check_login_status`、`list_feeds`、`search_feeds`、`get_feed_detail`、`publish_content`、`post_comment_to_feed`
- **客户端配置**（如 Cursor）：`.cursor/mcp.json` 中配置 `"url": "http://localhost:18060/mcp"`

---

## 扩展新平台

1. 在 `src/platforms/` 下新建 `{platform}/`
2. 实现 `PlatformBase` 子类
3. 在 `workflows.py` 中编写固定操作流程
4. 调整 DOM 选择器以适配实际页面

---

## 风险与建议

- **反爬**：固定 Workflow 比纯 DOM 脚本更接近人类行为；适当加入随机延迟
- **Cookie 过期**：定期检查 `check_login()`，失败时提示重新运行 `login.py`
- **小红书**：同账号不可多端同时登录；每日发帖量建议 ≤ 50
