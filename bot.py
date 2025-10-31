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

# -----------------------------
# بارگذاری داده‌ها یک بار در حافظه
# -----------------------------
try:
    # شیت اول: اطلاعات طرح‌ها
    df1 = pd.read_excel(foc_file, sheet_name=0)
    required_columns_df1 = ["شماره طرح", "عنوان طرح", "TableName"]
    for col in required_columns_df1:
        if col not in df1.columns:
            raise ValueError(f"❌ ستون '{col}' در شیت ۰ فایل موجود نیست.")

    # دیکشنری عنوان → شماره طرح
    title_to_number = dict(zip(df1["عنوان طرح"], df1["شماره طرح"]))

    # شیت دوم: سؤالات
    df2 = pd.read_excel(foc_file, sheet_name=1)
    
    # پیدا کردن ستون سؤال (انعطاف‌پذیر)
    question_column = None
    for col in df2.columns:
        if "سؤال" in col or "سوال" in col:
            question_column = col
            break
    if not question_column:
        raise ValueError("❌ ستون مربوط به سوالات در شیت ۱ فایل موجود نیست.")

except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# کیبورد با عنوان طرح‌ها
plans = list(title_to_number.keys())
keyboard = [[KeyboardButton(p)] for p in plans]
reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    # ذخیره دیکشنری در user_data برای استفاده بعدی
    context.user_data["title_to_number"] = title_to_number

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        title_to_number_local = context.user_data.get("title_to_number", {})
        selected_number = title_to_number_local.get(text)

        if not selected_number:
            await update.message.reply_text("❌ طرح یافت نشد. لطفاً از لیست انتخاب کنید.")
            return

        # پیدا کردن TableName
        row = df1[df1["شماره طرح"] == selected_number]
        if row.empty:
            await update.message.reply_text("❌ اطلاعات مربوط به طرح یافت نشد.")
            return
        table_name = row["TableName"].values[0]

        # پیدا کردن سوالات
        questions = df2.loc[df2["شماره طرح"] == selected_number, question_column].dropna().tolist()
        if questions:
            questions_text = "\n".join([f"- {q}" for q in questions])
        else:
            questions_text = "❌ سوالی برای این طرح موجود نیست."

        await update.message.reply_text(f"📋 سؤالات مربوط به طرح '{text}':\n\n{questions_text}")

        context.user_data["selected_table"] = table_name

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

threading.Thread(target=run_flask).start()

# -----------------------------
# اجرای ربات تلگرام
# -----------------------------
if __name__ == "__main__":
    print("✅ Bot is starting...")
    app.run_polling()
