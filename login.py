from telethon import TelegramClient
import asyncio

API_ID = 38366240
API_HASH = "5af3729a84e9d2ebce55ef6aa5f7d0ee"

async def main():
    client = TelegramClient('new_session', API_ID, API_HASH)
    await client.start(phone=input("Phone number (with country code e.g. +19705596671): "))
    me = await client.get_me()
    print(f"Logged in as {me.first_name}")
    await client.disconnect()

asyncio.run(main())