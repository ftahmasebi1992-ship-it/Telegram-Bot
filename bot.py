import os
import logging
import asyncio
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# -----------------------------
# تنظیمات اولیه
# -----------------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# لاگ‌ها
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -----------------------------
# تعریف هندلرها
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام 👋 من بات تلگرام هستم و فعالم!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"گفتی: {update.message.text}")

# -----------------------------
# ساخت اپ تلگرام
# -----------------------------
telegram_app = (
    ApplicationBuilder()
    .token(TOKEN)
    .build()
)

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# -----------------------------
# ساخت سرور Flask برای Webhook
# -----------------------------
app = Flask(__name__)

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    """دریافت آپدیت از تلگرام"""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
    return "OK"

@app.route("/", methods=["GET", "HEAD"])
def index():
    return "🤖 Bot is live!"

# -----------------------------
# اجرای نهایی
# -----------------------------
async def main():
    """اجرای بات و Flask"""
    webhook_url = f"https://telegram-bot-1-fp27.onrender.com/{TOKEN}"
    logger.info(f"Setting webhook to {webhook_url}")

    # آماده‌سازی و شروع اپلیکیشن
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set to {webhook_url}")

    # اجرای Flask روی Render
    app.run(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    asyncio.run(main())
