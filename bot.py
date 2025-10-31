import os
import threading
import pandas as pd
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# -----------------------------
# بارگذاری متغیرهای محیطی
# -----------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in environment variables.")
    exit(1)

# -----------------------------
# فایل‌ها
# -----------------------------
foc_file = "FOC.xlsx"
liga_file = "Rliga 140408 - TG.xlsx"

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        df = pd.read_excel(foc_file, sheet_name=0)
        if "شماره طرح" not in df.columns:
            await update.message.reply_text("❌ ستون 'شماره طرح' در فایل موجود نیست.")
            return

        plans = df["شماره طرح"].dropna().tolist()
        keyboard = [[KeyboardButton(p)] for p in plans]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در خواندن فایل: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        df1 = pd.read_excel(foc_file, sheet_name=0)
        df2 = pd.read_excel(foc_file, sheet_name=1)

        required_columns_df1 = ["شماره طرح", "TableName"]
        required_columns_df2 = ["شماره طرح", "سؤال"]

        for col in required_columns_df1:
            if col not in df1.columns:
                await update.message.reply_text(f"❌ ستون '{col}' در شیت ۰ فایل موجود نیست.")
                return
        for col in required_columns_df2:
            if col not in df2.columns:
                await update.message.reply_text(f"❌ ستون '{col}' در شیت ۱ فایل موجود نیست.")
                return

        if text in df1["شماره طرح"].values:
            table_name = df1.loc[df1["شماره طرح"] == text, "TableName"].values[0]
            questions = df2.loc[df2["شماره طرح"] == text, "سؤال"].dropna().tolist()
            questions_text = "\n".join([f"- {q}" for q in questions])
            await update.message.reply_text(f"📋 سؤالات مربوط به طرح {text}:\n\n{questions_text}")
            context.user_data["selected_table"] = table_name
        else:
            await update.message.reply_text("❌ طرح یافت نشد. لطفاً از لیست انتخاب کنید.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در پردازش پیام: {e}")

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -----------------------------
# Flask Healthcheck برای Render
# -----------------------------
flask_app = Flask("healthcheck")

@flask_app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# اجرای Flask در یک Thread جداگانه
threading.Thread(target=run_flask).start()

# -----------------------------
# اجرای ربات تلگرام
# -----------------------------
if __name__ == "__main__":
    print("✅ Bot is starting...")
    app.run_polling()
