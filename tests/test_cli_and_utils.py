import json
import sys
import types as pytypes
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Allow unit tests for pure parsing/formatting helpers to run even before optional runtime deps are installed
try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    stub_dotenv = pytypes.ModuleType("dotenv")
    stub_dotenv.load_dotenv = lambda *a, **kw: False
    sys.modules["dotenv"] = stub_dotenv

try:
    import mcp.server.mcpserver  # noqa: F401
except ModuleNotFoundError:
    stub_mcp = pytypes.ModuleType("mcp")
    stub_srv = pytypes.ModuleType("mcp.server")
    stub_msrv = pytypes.ModuleType("mcp.server.mcpserver")

    class _DummyMCPServer:
        def __init__(self, name: str, **kwargs):
            self.name = name
            self.registered_tools = []

        def tool(self):
            def _decorator(fn):
                self.registered_tools.append(fn.__name__)
                return fn
            return _decorator

    stub_msrv.MCPServer = _DummyMCPServer
    sys.modules["mcp"] = stub_mcp
    sys.modules["mcp.server"] = stub_srv
    sys.modules["mcp.server.mcpserver"] = stub_msrv

try:
    import telethon  # noqa: F401
except ModuleNotFoundError:
    stub_tl = pytypes.ModuleType("telethon")
    stub_tl_err = pytypes.ModuleType("telethon.errors")
    stub_tl.TelegramClient = object
    stub_tl.functions = SimpleNamespace()
    stub_tl.types = SimpleNamespace(User=type("User", (), {}), Chat=type("Chat", (), {}), Channel=type("Channel", (), {}), Message=object)
    stub_tl_err.PhoneCodeExpiredError = Exception
    stub_tl_err.PhoneCodeInvalidError = Exception
    stub_tl_err.SessionPasswordNeededError = Exception
    sys.modules["telethon"] = stub_tl
    sys.modules["telethon.errors"] = stub_tl_err

from telegram_user_mcp.cli import _parse_args, _parse_val
from telegram_user_mcp.server import _format_message, _json_out, mcp


class TestCliParser(unittest.TestCase):
    def test_parse_scalar_values(self) -> None:
        self.assertIs(_parse_val("true"), True)
        self.assertIs(_parse_val("FALSE"), False)
        self.assertEqual(_parse_val("42"), 42)
        self.assertEqual(_parse_val("-10012345"), -10012345)
        self.assertEqual(_parse_val("+15550109999"), "+15550109999")

    def test_parse_json_structures(self) -> None:
        self.assertEqual(_parse_val("[10, 20, 30]"), [10, 20, 30])
        self.assertEqual(_parse_val('{"limit": 5}'), {"limit": 5})

    def test_parse_cli_flags_and_kv(self) -> None:
        parsed = _parse_args(["--target", "@channel", "--limit=15", "--unread-only", "archived=false"])
        self.assertEqual(
            parsed,
            {
                "target": "@channel",
                "limit": 15,
                "unread_only": True,
                "archived": False,
            },
        )

    def test_parse_single_json_blob(self) -> None:
        parsed = _parse_args(['{"target": "me", "limit": 3}'])
        self.assertEqual(parsed, {"target": "me", "limit": 3})


class TestMessageFormattingAndServer(unittest.TestCase):
    def test_format_message_without_media(self) -> None:
        fake_msg = SimpleNamespace(
            id=101,
            date=datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc),
            out=True,
            sender_id=999,
            sender=SimpleNamespace(title="Engineering Updates"),
            message="Deployment succeeded.",
            reply_to=SimpleNamespace(reply_to_msg_id=98),
            views=240,
            forwards=4,
            media=None,
            file=None,
        )
        formatted = _format_message(fake_msg)
        self.assertEqual(formatted["id"], 101)
        self.assertTrue(formatted["out"])
        self.assertEqual(formatted["sender_name"], "Engineering Updates")
        self.assertEqual(formatted["reply_to_msg_id"], 98)
        self.assertIsNone(formatted["media"])

    def test_json_out_handles_unicode(self) -> None:
        dumped = _json_out({"greeting": "مرحبا", "count": 2})
        data = json.loads(dumped)
        self.assertEqual(data["greeting"], "مرحبا")

    def test_mcp_server_name_registered(self) -> None:
        self.assertEqual(mcp.name, "telegram")


if __name__ == "__main__":
    unittest.main()
