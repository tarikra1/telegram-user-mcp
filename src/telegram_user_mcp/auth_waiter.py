import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "telegram_user"
INPUT_FILE = DATA_DIR / "auth_input.json"
STATUS_FILE = DATA_DIR / "auth_state.json"

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.environ["TELEGRAM_PHONE"]


def write_state(payload: dict) -> None:
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


async def main() -> None:
    if INPUT_FILE.exists():
        INPUT_FILE.unlink()

    client = TelegramClient(
        str(SESSION_PATH),
        API_ID,
        API_HASH,
        device_model=os.getenv("TELEGRAM_DEVICE_MODEL", "Telegram User MCP"),
        system_version=os.getenv("TELEGRAM_SYSTEM_VERSION", "MCP Host"),
        app_version="0.2.0",
    )
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            write_state({"status": "authorized", "username": me.username, "id": me.id})
            return

        sent = await client.send_code_request(PHONE)
        write_state(
            {
                "status": "waiting_for_code",
                "phone": PHONE,
                "delivery": type(sent.type).__name__,
            }
        )

        # Wait up to 15 minutes for code (and optional 2FA password)
        needs_2fa = False
        for _ in range(900):
            await asyncio.sleep(1.0)
            if not INPUT_FILE.exists():
                continue

            try:
                data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
                INPUT_FILE.unlink()
            except Exception:
                continue

            code = str(data.get("code", "")).strip().replace(" ", "").replace("-", "")
            password = str(data.get("password", ""))

            try:
                if not needs_2fa and code:
                    await client.sign_in(
                        phone=PHONE,
                        code=code,
                        phone_code_hash=sent.phone_code_hash,
                    )
                elif needs_2fa and password:
                    await client.sign_in(password=password)
            except SessionPasswordNeededError:
                needs_2fa = True
                if password:
                    try:
                        await client.sign_in(password=password)
                    except Exception as exc:
                        write_state({"status": "2fa_error", "error": str(exc)})
                        continue
                else:
                    write_state({"status": "waiting_for_2fa"})
                    continue
            except Exception as exc:
                write_state({"status": "code_error", "error": str(exc), "needs_2fa": needs_2fa})
                continue

            if await client.is_user_authorized():
                me = await client.get_me()
                write_state(
                    {
                        "status": "authorized",
                        "id": me.id,
                        "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                        "username": me.username,
                    }
                )
                return

        write_state({"status": "timeout"})
    finally:
        await client.disconnect()


def cli_main() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
