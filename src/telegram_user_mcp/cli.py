import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def _parse_val(v: str) -> Any:
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if v.lstrip("-").isdigit() and not v.startswith("+"):
        return int(v)
    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        try:
            return json.loads(v)
        except Exception:
            pass
    return v


def _parse_args(argv: list[str]) -> dict[str, Any]:
    if not argv:
        return {}
    if len(argv) == 1 and argv[0].strip().startswith("{"):
        return json.loads(argv[0])

    kwargs: dict[str, Any] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            key = tok[2:].replace("-", "_")
            if "=" in key:
                k, v = key.split("=", 1)
                kwargs[k] = _parse_val(v)
                i += 1
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--") and "=" not in argv[i + 1]:
                kwargs[key] = _parse_val(argv[i + 1])
                i += 2
            else:
                kwargs[key] = True
                i += 1
        elif "=" in tok:
            k, v = tok.split("=", 1)
            kwargs[k] = _parse_val(v)
            i += 1
        else:
            i += 1
    return kwargs


async def _run() -> None:
    from telegram_user_mcp import server

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "list"):
        tools = await server.mcp.list_tools()
        print(
            json.dumps(
                [{"name": t.name, "description": t.description} for t in tools],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    tool_name = sys.argv[1]
    kwargs = _parse_args(sys.argv[2:])
    try:
        res = await server.mcp.call_tool(tool_name, kwargs)
        items = getattr(res, "content", None) or (res[0] if isinstance(res, tuple) else res)
        for item in items:
            text = getattr(item, "text", None)
            print(text if text is not None else item)
    finally:
        if server._client is not None and server._client.is_connected():
            await server._client.disconnect()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
