import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --------------------------------------
# تنظیمات اولیه و لاگ‌ها
# --------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
URL = "https://telegram-bot-1-fp27.onrender.com"  # آدرس سرویس در Render

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN در متغیرهای محیطی تنظیم نشده است!")

# --------------------------------------
# تنظیم Flask برای Health Check و Webhook
# --------------------------------------
app = Flask(__name__)
telegram_app = ApplicationBuilder().token(TOKEN).build()

# --------------------------------------
# هندلرهای بات
# --------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("سلام 👋")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "سلام! من بات تلگرام هستم 🤖\nارسال کن تا پاسخت رو بدم.", reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "سلام" in text:
        await update.message.reply_text("سلام 🌸 حالت چطوره؟")
    else:
        await update.message.reply_text(f"گفتی: {text}")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --------------------------------------
# مسیرها (Routes)
# --------------------------------------
@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot is running and healthy!"

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    """دریافت آپدیت‌ها از تلگرام"""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        logging.error(f"Error in webhook: {e}")
    return "OK"

# --------------------------------------
# اجرای سرور و تنظیم Webhook
# --------------------------------------
if __name__ == "__main__":
    async def main():
        webhook_url = f"{URL}/{TOKEN}"
        await telegram_app.bot.set_webhook(webhook_url)
        logging.info(f"✅ Webhook set to {webhook_url}")

    asyncio.run(main())
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Starting Flask server on port {port}")
    app.run(host="0.0.0.0", port=port)
