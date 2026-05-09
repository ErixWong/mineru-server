import sys
from pathlib import Path

sys.path.insert(0, str(Path("mcp-server/src")))
sys.path.insert(0, str(Path("src/mineru")))

from mineru_mcp.server import create_mcp_server
from mineru_mcp.config import get_config
import inspect

print("=== MCP Tools 列表 ===")
print()

config = get_config()
mcp = create_mcp_server(config)

tools = mcp._tool_manager._tools

print(f"总数: {len(tools)} 个")
print()

for name, tool in tools.items():
    func = tool.fn
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    
    # 过滤掉 ctx 参数
    params = [p for p in params if p != 'ctx']
    
    print(f"{name}")
    print(f"  参数: {', '.join(params)}")
    print()

print("=== REST API Endpoints 列表 ===")
print()

from mineru_mcp.api import create_api_app

app = create_api_app()

routes = []
for route in app.routes:
    if hasattr(route, 'methods'):
        for method in route.methods:
            routes.append(f"{method} {route.path}")
    elif hasattr(route, 'path'):
        routes.append(f"GET {route.path}")

print(f"总数: {len(routes)} 个")
print()

for route in sorted(routes):
    print(f"- {route}")

print()
print("Done!")