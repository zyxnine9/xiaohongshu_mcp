"""
启动 MCP Server (HTTP / SSE 模式)
"""
import argparse
from src.servers.mcp_server import mcp

def main():
    parser = argparse.ArgumentParser(description="Start Social Media MCP HTTP Server")
    
    # 使用 SSE 传输层启动，这会自动拉起底层的 ASGI HTTP 服务，并触发你编写的 _mcp_lifespan
    mcp.run(
        'streamable-http'
    )

if __name__ == "__main__":
    main()