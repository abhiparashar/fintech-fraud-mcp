from app import mcp
import tools  # noqa: F401 — registers all @mcp.tool() decorators as a side effect

if __name__ == "__main__":
    import sys
    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
