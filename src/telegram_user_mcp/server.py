import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from telethon import TelegramClient, functions, types
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

# Strictly log to stderr so stdout remains clean for MCP stdio JSON-RPC
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("telegram-mcp")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "telegram_user"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "TelegramMCP"

API_ID_RAW = os.getenv("TELEGRAM_API_ID", "").strip()
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
DEFAULT_PHONE = os.getenv("TELEGRAM_PHONE", "").strip()

_client: TelegramClient | None = None
_client_lock = asyncio.Lock()
_idle_task: asyncio.Task | None = None
_pending_auth: dict[str, str] = {}


def _is_read_only() -> bool:
    return os.getenv("TELEGRAM_READ_ONLY", "").strip().lower() in ("1", "true", "yes", "on")


def _require_write_permission(action: str) -> None:
    if _is_read_only():
        raise PermissionError(
            f"Operation '{action}' is blocked because TELEGRAM_READ_ONLY is enabled."
        )


def _json_out(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _schedule_idle_disconnect(delay: float = 20.0) -> None:
    global _idle_task
    if _idle_task is not None and not _idle_task.done():
        _idle_task.cancel()

    async def _disconnect_later() -> None:
        await asyncio.sleep(delay)
        if _pending_auth:
            return
        async with _client_lock:
            if _client is not None and _client.is_connected():
                await _client.disconnect()

    try:
        loop = asyncio.get_running_loop()
        _idle_task = loop.create_task(_disconnect_later())
    except RuntimeError:
        pass


async def _get_client() -> TelegramClient:
    global _client
    async with _client_lock:
        if not API_ID_RAW or not API_HASH:
            raise RuntimeError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env or environment."
            )
        for attempt in range(5):
            try:
                if _client is None:
                    _client = TelegramClient(
                        str(SESSION_PATH),
                        int(API_ID_RAW),
                        API_HASH,
                        device_model=os.getenv("TELEGRAM_DEVICE_MODEL", "Telegram User MCP"),
                        system_version=os.getenv("TELEGRAM_SYSTEM_VERSION", "MCP Host"),
                        app_version="0.3.0",
                    )
                if not _client.is_connected():
                    await _client.connect()
                break
            except Exception as exc:
                if "database is locked" in str(exc).lower() and attempt < 4:
                    _client = None
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
                raise
        _schedule_idle_disconnect()
        return _client


async def _require_authorized_client() -> TelegramClient:
    client = await _get_client()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram session is NOT logged in yet. Run auth_send_code first, then auth_verify_code with the code sent to your Telegram app."
        )
    return client


async def _resolve_entity(client: TelegramClient, target: str) -> Any:
    t = target.strip()
    if t.lower() in ("me", "saved", "saved messages", "self"):
        return "me"

    # Numeric chat/user/channel ID
    if t.lstrip("-").isdigit():
        num_id = int(t)
        try:
            return await client.get_entity(num_id)
        except Exception:
            await client.get_dialogs(limit=300)
            return await client.get_entity(num_id)

    # Username, t.me link, or phone number
    if t.startswith("@") or t.startswith("+") or "t.me/" in t:
        return await client.get_entity(t)

    # Try direct lookup first, then fallback to dialog title search
    try:
        return await client.get_entity(t)
    except Exception:
        t_lower = t.lower()
        partial_match = None
        async for dialog in client.iter_dialogs(limit=400):
            d_name = (dialog.name or "").strip()
            if d_name.lower() == t_lower:
                return dialog.entity
            if partial_match is None and t_lower in d_name.lower():
                partial_match = dialog.entity
        if partial_match is not None:
            return partial_match
        raise ValueError(
            f"Could not find chat/user matching '{target}'. Try list_chats or search_chats to get the exact ID or @username."
        )


def _entity_type(entity: Any) -> str:
    if isinstance(entity, types.User):
        return "bot" if getattr(entity, "bot", False) else "user"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel):
        return "group" if getattr(entity, "megagroup", False) else "channel"
    return type(entity).__name__.lower()


def _format_message(msg: types.Message) -> dict[str, Any]:
    sender_name = None
    if msg.sender:
        if isinstance(msg.sender, types.User):
            parts = [msg.sender.first_name or "", msg.sender.last_name or ""]
            sender_name = " ".join(p for p in parts if p).strip() or msg.sender.username
        else:
            sender_name = getattr(msg.sender, "title", None)

    media_info = None
    if msg.media:
        file_obj = msg.file
        media_info = {
            "media_class": type(msg.media).__name__,
            "mime_type": getattr(file_obj, "mime_type", None) if file_obj else None,
            "file_name": getattr(file_obj, "name", None) if file_obj else None,
            "size_mb": round(file_obj.size / (1024 * 1024), 2)
            if file_obj and getattr(file_obj, "size", None)
            else None,
        }

    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "out": bool(msg.out),
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "text": msg.message or "",
        "reply_to_msg_id": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        "views": getattr(msg, "views", None),
        "forwards": getattr(msg, "forwards", None),
        "media": media_info,
    }


@asynccontextmanager
async def _lifespan(_server: MCPServer):
    try:
        yield {}
    finally:
        global _client
        if _client is not None and _client.is_connected():
            await _client.disconnect()


mcp = MCPServer(
    name="telegram",
    instructions=(
        "Personal Telegram controller via Telethon MTProto. "
        "Use list_chats / list_folders / search_chats to discover chats, "
        "get_messages / search_messages_global to read messages, "
        "send_message / send_file / forward_messages to send content, "
        "and download_media to save files from Telegram channels or chats."
    ),
    lifespan=_lifespan,
)


@mcp.tool()
async def auth_status() -> str:
    """Check whether the Telegram personal account session is authorized."""
    client = await _get_client()
    authorized = await client.is_user_authorized()
    if not authorized:
        return _json_out(
            {
                "authorized": False,
                "read_only": _is_read_only(),
                "default_phone": DEFAULT_PHONE,
                "hint": "Call auth_send_code() to receive a login code in Telegram, then auth_verify_code(code=...).",
            }
        )
    me = await client.get_me()
    return _json_out(
        {
            "authorized": True,
            "read_only": _is_read_only(),
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone,
            "premium": bool(getattr(me, "premium", False)),
        }
    )


@mcp.tool()
async def auth_send_code(phone: str = "") -> str:
    """Send a Telegram login verification code to your phone/Telegram app."""
    client = await _get_client()
    if await client.is_user_authorized():
        me = await client.get_me()
        return _json_out(
            {
                "status": "already_authorized",
                "username": me.username,
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            }
        )
    use_phone = (phone or DEFAULT_PHONE).strip()
    if not use_phone:
        raise ValueError("Phone number is required (e.g. '+15550109999').")
    sent = await client.send_code_request(use_phone)
    _pending_auth["phone"] = use_phone
    _pending_auth["phone_code_hash"] = sent.phone_code_hash
    return _json_out(
        {
            "status": "code_sent",
            "phone": use_phone,
            "delivery_type": type(sent.type).__name__,
            "next_step": "Ask the user for the verification code sent to their Telegram app, then call auth_verify_code(code=...).",
        }
    )


@mcp.tool()
async def auth_verify_code(code: str, password: str = "") -> str:
    """Complete Telegram login with the verification code (and optional 2FA cloud password)."""
    client = await _get_client()
    clean_code = code.strip().replace(" ", "").replace("-", "")
    phone = _pending_auth.get("phone") or DEFAULT_PHONE
    phone_code_hash = _pending_auth.get("phone_code_hash")

    try:
        if clean_code and not await client.is_user_authorized():
            await client.sign_in(
                phone=phone,
                code=clean_code,
                phone_code_hash=phone_code_hash,
            )
    except SessionPasswordNeededError:
        if not password:
            return _json_out(
                {
                    "status": "2fa_password_required",
                    "message": "Two-Step Verification (2FA) is enabled on this Telegram account. Ask the user for their 2FA cloud password and call auth_verify_code(code='', password='...').",
                }
            )
        await client.sign_in(password=password)
    except PhoneCodeInvalidError:
        return _json_out({"status": "error", "error": "Invalid verification code."})
    except PhoneCodeExpiredError:
        return _json_out(
            {
                "status": "error",
                "error": "Verification code expired. Call auth_send_code() again for a fresh code.",
            }
        )

    if password and not await client.is_user_authorized():
        await client.sign_in(password=password)

    me = await client.get_me()
    _pending_auth.clear()
    return _json_out(
        {
            "status": "authorized",
            "id": me.id,
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username,
            "phone": me.phone,
        }
    )


@mcp.tool()
async def get_me() -> str:
    """Get profile information of the currently logged-in Telegram user."""
    client = await _require_authorized_client()
    me = await client.get_me()
    return _json_out(
        {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone,
            "premium": bool(getattr(me, "premium", False)),
        }
    )


@mcp.tool()
async def list_folders() -> str:
    """List custom Telegram chat folders (filters) such as work, courses, graphics, etc."""
    client = await _require_authorized_client()
    result = await client(functions.messages.GetDialogFiltersRequest())
    raw_filters = getattr(result, "filters", result)
    folders = []
    for f in raw_filters:
        if isinstance(f, types.DialogFilterDefault):
            continue
        raw_title = getattr(f, "title", None)
        if raw_title is None:
            continue
        title = raw_title.text if hasattr(raw_title, "text") else str(raw_title)
        include_peers = getattr(f, "include_peers", []) or []
        pinned_peers = getattr(f, "pinned_peers", []) or []
        folders.append(
            {
                "id": getattr(f, "id", None),
                "title": title,
                "emoticon": getattr(f, "emoticon", None),
                "included_chats_count": len(include_peers) + len(pinned_peers),
                "contacts": bool(getattr(f, "contacts", False)),
                "groups": bool(getattr(f, "groups", False)),
                "broadcasts": bool(getattr(f, "broadcasts", False)),
                "bots": bool(getattr(f, "bots", False)),
            }
        )
    return _json_out({"count": len(folders), "folders": folders})


@mcp.tool()
async def get_folder_chats(folder: str) -> str:
    """List all chats/channels/groups inside a custom Telegram folder (by folder title like 'Work' or folder ID)."""
    client = await _require_authorized_client()
    result = await client(functions.messages.GetDialogFiltersRequest())
    raw_filters = getattr(result, "filters", result)

    target_filter = None
    f_clean = folder.strip().lower()
    for f in raw_filters:
        if isinstance(f, types.DialogFilterDefault):
            continue
        raw_title = getattr(f, "title", None)
        if raw_title is None:
            continue
        title = raw_title.text if hasattr(raw_title, "text") else str(raw_title)
        fid = str(getattr(f, "id", ""))
        if fid == f_clean or title.lower() == f_clean or f_clean in title.lower():
            target_filter = (f, title)
            break

    if target_filter is None:
        raise ValueError(f"Folder '{folder}' not found. Run list_folders() to see available folders.")

    f_obj, f_title = target_filter
    peers = list(getattr(f_obj, "pinned_peers", []) or []) + list(getattr(f_obj, "include_peers", []) or [])
    await client.get_dialogs(limit=400)

    chats = []
    seen: set[int] = set()
    for p in peers:
        try:
            ent = await client.get_entity(p)
            if ent.id in seen:
                continue
            seen.add(ent.id)
            name = getattr(ent, "title", None) or (
                f"{getattr(ent, 'first_name', '') or ''} {getattr(ent, 'last_name', '') or ''}".strip()
            )
            chats.append(
                {
                    "id": ent.id,
                    "name": name,
                    "username": getattr(ent, "username", None),
                    "type": _entity_type(ent),
                }
            )
        except Exception as exc:
            logger.warning("Could not resolve peer in folder %s: %s", f_title, exc)

    return _json_out({"folder": f_title, "count": len(chats), "chats": chats})


@mcp.tool()
async def list_chats(
    limit: int = 30,
    chat_type: str = "all",
    unread_only: bool = False,
    archived: bool = False,
) -> str:
    """
    List recent Telegram dialogs/chats.
    chat_type: 'all', 'user', 'bot', 'group', or 'channel'.
    """
    client = await _require_authorized_client()
    limit = max(1, min(limit, 200))
    wanted_type = chat_type.strip().lower()
    folder_arg = 1 if archived else 0

    chats = []
    async for d in client.iter_dialogs(folder=folder_arg):
        etype = _entity_type(d.entity)
        if wanted_type != "all" and etype != wanted_type:
            continue
        if unread_only and d.unread_count == 0:
            continue

        last_msg_text = ""
        if d.message:
            last_msg_text = (d.message.message or "").strip()
            if not last_msg_text and d.message.media:
                last_msg_text = f"[{type(d.message.media).__name__}]"
            if len(last_msg_text) > 120:
                last_msg_text = last_msg_text[:117] + "..."

        chats.append(
            {
                "id": d.id,
                "name": d.name,
                "username": getattr(d.entity, "username", None),
                "type": etype,
                "unread_count": d.unread_count,
                "pinned": bool(d.pinned),
                "last_date": d.date.isoformat() if d.date else None,
                "last_message": last_msg_text,
            }
        )
        if len(chats) >= limit:
            break

    return _json_out({"count": len(chats), "chats": chats})


@mcp.tool()
async def search_chats(query: str, limit: int = 20) -> str:
    """Search your Telegram dialogs and global directory by name or @username."""
    client = await _require_authorized_client()
    q = query.strip()
    if not q:
        raise ValueError("Search query cannot be empty.")
    limit = max(1, min(limit, 100))

    matches = []
    seen_ids: set[int] = set()
    q_lower = q.lower()

    async for d in client.iter_dialogs(limit=400):
        uname = getattr(d.entity, "username", None) or ""
        if q_lower in (d.name or "").lower() or q_lower in uname.lower():
            seen_ids.add(d.id)
            matches.append(
                {
                    "source": "my_dialogs",
                    "id": d.id,
                    "name": d.name,
                    "username": uname or None,
                    "type": _entity_type(d.entity),
                    "unread_count": d.unread_count,
                }
            )
            if len(matches) >= limit:
                break

    if len(matches) < limit:
        try:
            found = await client(functions.contacts.SearchRequest(q=q, limit=limit))
            for ent in list(found.users) + list(found.chats):
                eid = ent.id
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)
                name = getattr(ent, "title", None) or (
                    f"{getattr(ent, 'first_name', '') or ''} {getattr(ent, 'last_name', '') or ''}".strip()
                )
                matches.append(
                    {
                        "source": "global_search",
                        "id": eid,
                        "name": name,
                        "username": getattr(ent, "username", None),
                        "type": _entity_type(ent),
                    }
                )
                if len(matches) >= limit:
                    break
        except Exception as exc:
            logger.warning("Global contact search warning: %s", exc)

    return _json_out({"query": q, "count": len(matches), "results": matches})


@mcp.tool()
async def get_chat_info(target: str) -> str:
    """Get detailed info about a user, group, or channel by ID, @username, or chat title."""
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    if entity == "me":
        entity = await client.get_me()

    info: dict[str, Any] = {
        "id": entity.id,
        "type": _entity_type(entity),
        "username": getattr(entity, "username", None),
    }

    if isinstance(entity, types.User):
        info["first_name"] = entity.first_name
        info["last_name"] = entity.last_name
        info["phone"] = entity.phone
        info["bot"] = bool(entity.bot)
        full = await client(functions.users.GetFullUserRequest(entity))
        info["bio"] = getattr(full.full_user, "about", None)
    elif isinstance(entity, types.Channel):
        info["title"] = entity.title
        full = await client(functions.channels.GetFullChannelRequest(entity))
        info["about"] = getattr(full.full_chat, "about", None)
        info["participants_count"] = getattr(full.full_chat, "participants_count", None)
    elif isinstance(entity, types.Chat):
        info["title"] = entity.title
        info["participants_count"] = getattr(entity, "participants_count", None)

    return _json_out(info)


@mcp.tool()
async def get_messages(
    target: str,
    limit: int = 20,
    search: str = "",
    offset_id: int = 0,
) -> str:
    """
    Read messages from a chat/group/channel ('me', @username, numeric ID, or chat title).
    Optionally filter messages inside that chat using 'search'.
    """
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    limit = max(1, min(limit, 100))

    kwargs: dict[str, Any] = {"limit": limit}
    if search.strip():
        kwargs["search"] = search.strip()
    if offset_id > 0:
        kwargs["offset_id"] = offset_id

    msgs = []
    async for m in client.iter_messages(entity, **kwargs):
        msgs.append(_format_message(m))

    return _json_out({"target": target, "count": len(msgs), "messages": msgs})


@mcp.tool()
async def search_messages_global(query: str, limit: int = 25) -> str:
    """Search messages across ALL your Telegram chats, groups, and channels."""
    client = await _require_authorized_client()
    q = query.strip()
    if not q:
        raise ValueError("Search query cannot be empty.")
    limit = max(1, min(limit, 100))

    results = []
    async for m in client.iter_messages(None, search=q, limit=limit):
        chat_title = None
        if m.chat:
            chat_title = getattr(m.chat, "title", None) or (
                f"{getattr(m.chat, 'first_name', '') or ''} {getattr(m.chat, 'last_name', '') or ''}".strip()
            )
        item = _format_message(m)
        item["chat_id"] = m.chat_id
        item["chat_title"] = chat_title
        item["chat_username"] = getattr(m.chat, "username", None) if m.chat else None
        results.append(item)

    return _json_out({"query": q, "count": len(results), "results": results})


@mcp.tool()
async def send_message(
    target: str,
    message: str,
    reply_to_msg_id: int = 0,
    parse_mode: str = "md",
) -> str:
    """
    Send a text message to a user, group, channel, or 'me' (Saved Messages).
    parse_mode: 'md' (Markdown), 'html', or 'none'.
    """
    _require_write_permission("send_message")
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    pm: str | None = parse_mode.lower()
    if pm == "none":
        pm = None

    sent = await client.send_message(
        entity,
        message,
        reply_to=reply_to_msg_id if reply_to_msg_id > 0 else None,
        parse_mode=pm,
    )
    return _json_out(
        {
            "status": "sent",
            "target": target,
            "message_id": sent.id,
            "date": sent.date.isoformat() if sent.date else None,
        }
    )


@mcp.tool()
async def send_file(
    target: str,
    file_path: str,
    caption: str = "",
    force_document: bool = False,
    reply_to_msg_id: int = 0,
) -> str:
    """Upload and send a local file, image, video, or document to a Telegram chat or 'me'."""
    _require_write_permission("send_file")
    client = await _require_authorized_client()
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File does not exist: {p}")

    entity = await _resolve_entity(client, target)
    sent = await client.send_file(
        entity,
        str(p),
        caption=caption or None,
        force_document=force_document,
        reply_to=reply_to_msg_id if reply_to_msg_id > 0 else None,
    )
    return _json_out(
        {
            "status": "file_sent",
            "target": target,
            "file_path": str(p),
            "message_id": sent.id,
        }
    )


@mcp.tool()
async def download_media(
    target: str,
    message_id: int,
    output_dir: str = "",
) -> str:
    """Download the attached file/photo/video/archive from a specific message_id in target chat."""
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    msg = await client.get_messages(entity, ids=message_id)
    if not msg:
        raise ValueError(f"Message {message_id} not found in '{target}'.")
    if not msg.media:
        raise ValueError(f"Message {message_id} in '{target}' has no attached media.")

    dest_dir = Path(output_dir).expanduser().resolve() if output_dir.strip() else DEFAULT_DOWNLOAD_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved_path = await client.download_media(msg, file=str(dest_dir))
    saved_file = Path(saved_path) if saved_path else None
    return _json_out(
        {
            "status": "downloaded",
            "message_id": message_id,
            "saved_path": str(saved_file) if saved_file else None,
            "size_mb": round(saved_file.stat().st_size / (1024 * 1024), 2)
            if saved_file and saved_file.exists()
            else None,
        }
    )


@mcp.tool()
async def forward_messages(
    from_target: str,
    to_target: str,
    message_ids: list[int],
) -> str:
    """Forward one or more messages from one chat to another (e.g. to 'me' Saved Messages)."""
    _require_write_permission("forward_messages")
    client = await _require_authorized_client()
    src = await _resolve_entity(client, from_target)
    dst = await _resolve_entity(client, to_target)
    forwarded = await client.forward_messages(dst, message_ids, src)
    fwd_list = forwarded if isinstance(forwarded, list) else [forwarded]
    return _json_out(
        {
            "status": "forwarded",
            "from": from_target,
            "to": to_target,
            "count": len(fwd_list),
            "new_message_ids": [m.id for m in fwd_list if m],
        }
    )


@mcp.tool()
async def edit_message(target: str, message_id: int, new_text: str) -> str:
    """Edit the text of a message you previously sent."""
    _require_write_permission("edit_message")
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    edited = await client.edit_message(entity, message_id, new_text)
    return _json_out(
        {
            "status": "edited",
            "target": target,
            "message_id": edited.id,
        }
    )


@mcp.tool()
async def delete_messages(
    target: str,
    message_ids: list[int],
    revoke: bool = True,
) -> str:
    """Delete one or more messages in a chat."""
    _require_write_permission("delete_messages")
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    await client.delete_messages(entity, message_ids, revoke=revoke)
    return _json_out(
        {
            "status": "deleted",
            "target": target,
            "deleted_ids": message_ids,
        }
    )


@mcp.tool()
async def mark_as_read(target: str) -> str:
    """Mark unread messages in a chat/group/channel as read."""
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    await client.send_read_acknowledge(entity)
    return _json_out({"status": "marked_as_read", "target": target})


@mcp.tool()
async def pin_message(target: str, message_id: int, notify: bool = False) -> str:
    """Pin a message in a chat/group/channel."""
    _require_write_permission("pin_message")
    client = await _require_authorized_client()
    entity = await _resolve_entity(client, target)
    await client.pin_message(entity, message_id, notify=notify)
    return _json_out(
        {"status": "pinned", "target": target, "message_id": message_id}
    )


def main() -> None:
    """Run the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
