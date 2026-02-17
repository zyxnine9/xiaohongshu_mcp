# Social Media Operations Bot / 社交媒体自动运营机器人

基于 Playwright + 固定 Workflow 的社交媒体自动化工具，支持小红书等平台。读操作以 DOM 为主，写操作采用固定流程（类似 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)）。

## 架构概览

```
读操作 (DOM)         写操作 (固定 Workflow)
  get_feeds    →       login, publish, comment
  search       →       人机交互式流程
  get_post_detail
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 快速开始

### 1. 安装依赖

```bash
cd social_media_op
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置

复制 `.env.example` 为 `.env`（可选，用于覆盖默认配置）：

```bash
cp .env.example .env
```

### 3. 登录

首次使用需手动登录以保存 Cookie：

```bash
python scripts/login.py --platform xiaohongshu
# 浏览器会打开小红书登录页，完成登录后自动保存 Cookie
```

### 4. 运行

```bash
# 演示：检查登录、拉取 Feed、搜索
python scripts/run_bot.py --platform xiaohongshu --no-headless
```

### 5. 对外接口（HTTP / MCP）

```bash
# 启动 HTTP API（端口 8000）
python scripts/run_http.py

# 启动 MCP 服务（端口 18060，供 Cursor / Claude 等连接）
python scripts/run_mcp.py
```

- **HTTP**：见 [对外接口：HTTP 与 MCP](docs/ARCHITECTURE.md#对外接口http-与-mcp)，如 `GET /xiaohongshu/feeds`、`POST /xiaohongshu/publish` 等。
- **MCP**：连接 `http://localhost:18060/mcp`，工具包括 `check_login_status`、`list_feeds`、`search_feeds`、`publish_content`、`post_comment_to_feed` 等。

## 使用方式

### 作为库使用

```python
import asyncio
from pathlib import Path
from src.core.browser_manager import BrowserManager
from src.platforms.xiaohongshu import XiaohongshuPlatform
from src.core.models import PublishContent

async def main():
    data_dir = Path("data")
    cookies_path = data_dir / "cookies" / "xiaohongshu.json"

    async with BrowserManager(headless=True, cookies_path=cookies_path) as browser:
        platform = XiaohongshuPlatform(browser, cookies_path=cookies_path)

        # 检查登录
        if not await platform.check_login():
            print("请先运行 python scripts/login.py")

        # 拉取 Feed
        feeds = await platform.get_feeds(limit=10)
        for f in feeds:
            print(f.id, f.title)

        # 搜索
        results = await platform.search("美食", limit=5)

        # 发布（需已登录）
        # await platform.publish(PublishContent(
        #     title="测试标题",
        #     content="正文内容",
        #     images=["/path/to/image.jpg"],
        # ))

asyncio.run(main())
```

## 平台支持

| 平台 | 状态 | 说明 |
|------|------|------|
| 小红书 | ✅ 初步实现 | 登录、Feed、搜索、发布、评论 |
| X/Twitter | 🚧 待实现 | 接口已预留 |
| LinkedIn | 🚧 待实现 | 接口已预留 |

## 注意事项

1. **反爬与风控**：使用固定 Workflow 降低被封风险；避免高频请求。
2. **Cookie 过期**：如 `check_login()` 失败，请重新运行 `scripts/login.py`。
3. **小红书**：同一账号不可多端同时登录；每日发帖量建议 ≤ 50。

## License

MIT
