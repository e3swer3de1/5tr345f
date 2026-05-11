from telethon import TelegramClient
from telethon.network import MTProtoSender
from telethon.sessions import SQLiteSession
import asyncio

API_ID = 38366240
API_HASH = "5af3729a84e9d2ebce55ef6aa5f7d0ee"
SESSION = "session_1_970_559_6671"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    await client.get_me()
    
    # This creates a permanent auth key on DC2 and saves it to the session
    dc2 = await client._get_dc(2)
    sender = await client._borrow_exported_sender(2)
    await client._return_exported_sender(sender)
    
    # Now read from DB - should have DC2 permanent key
    import sqlite3
    conn = sqlite3.connect(SESSION + ".session")
    cur = conn.cursor()
    cur.execute("SELECT dc_id, auth_key FROM sessions")
    for row in cur.fetchall():
        if row[1]:
            print(f"DC{row[0]}: {row[1].hex()}")
    conn.close()
    await client.disconnect()

asyncio.run(main())