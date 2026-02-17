"""
启动 MCP Server (HTTP / SSE 模式)
"""
import argparse
import uvicorn

# 假设你的原始代码保存在 src/servers/mcp_server.py 中
# 请根据你的实际文件名进行修改
from src.servers.mcp_server import mcp

def main():
    parser = argparse.ArgumentParser(description="Start Social Media MCP HTTP Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()
    
    # 使用 SSE 传输层启动，这会自动拉起底层的 ASGI HTTP 服务，并触发你编写的 _mcp_lifespan
    mcp.run(
        'streamable-http'
    )

if __name__ == "__main__":
    main()