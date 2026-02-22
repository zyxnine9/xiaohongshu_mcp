# Social Media Operations Bot / 社交媒体自动运营机器人

基于 Playwright + 固定 Workflow 的社交媒体自动化工具，支持小红书等平台。读操作以 DOM 为主，写操作采用固定流程（类似 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)）。



## 快速开始

### 1. 安装依赖

```bash
cd social_media_op
pip install -r requirements.txt
playwright install chromium
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
