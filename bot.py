import os
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask, request
import asyncio

# --- بارگذاری توکن از محیط ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in environment variables.")
    exit(1)

# --- مسیر فایل‌ها ---
foc_file = "FOC.xlsx"
liga_file = "Rliga 140408 - TG.xlsx"

# --- ایجاد اپ تلگرام ---
app = Application.builder().token(BOT_TOKEN).build()

# --- مرحله شروع ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = pd.read_excel(foc_file, sheet_name=0)
    plans = df[["شماره طرح", "عنوان طرح"]].dropna()

    keyboard = [[KeyboardButton(row["عنوان طرح"])] for _, row in plans.iterrows()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text("👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)
    context.user_data["plans"] = plans  # ذخیره لیست طرح‌ها برای مراحل بعدی

# --- پردازش انتخاب‌ها ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # مرحله 1: انتخاب طرح
    if "selected_plan" not in context.user_data:
        plans = context.user_data.get("plans", pd.DataFrame())
        match = plans[plans["عنوان طرح"] == text]

        if match.empty:
            await update.message.reply_text("❌ لطفاً یکی از طرح‌های موجود را انتخاب کنید.")
            return

        selected_plan = match.iloc[0]
        context.user_data["selected_plan"] = selected_plan
        plan_number = selected_plan["شماره طرح"]

        # خواندن سوالات مربوط به طرح
        df_questions = pd.read_excel(foc_file, sheet_name=1)
        question_col = next((c for c in df_questions.columns if "سؤال" in c or "سوال" in c), None)
        if not question_col:
            await update.message.reply_text("❌ ستون 'سؤال' در فایل FOC یافت نشد.")
            return

        questions = df_questions[df_questions["شماره طرح"] == plan_number][question_col].dropna().tolist()

        if not questions:
            await update.message.reply_text("❌ برای این طرح سؤالی ثبت نشده است.")
            return

        keyboard = [[KeyboardButton(q)] for q in questions]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(f"📝 لطفاً یکی از سؤالات طرح '{selected_plan['عنوان طرح']}' را انتخاب کنید:", reply_markup=reply_markup)
        context.user_data["questions"] = questions
        return

    # مرحله 2: انتخاب سؤال
    selected_plan = context.user_data["selected_plan"]
    table_name = selected_plan["TableName"]

    # باز کردن Table از فایل liga
    try:
        xl = pd.ExcelFile(liga_file)
        df_all = xl.parse("فروشنده", header=None)
        df_table = None

        # استخراج جدول از میان Tableها
        for name, tbl in xl.book.defined_names.items():
            if name == table_name:
                ref = tbl.attr_text
                sheet_name, cell_range = ref.split("!")
                df_table = xl.parse(sheet_name, header=0)
                break

        if df_table is None:
            await update.message.reply_text(f"❌ Table با نام '{table_name}' در فایل یافت نشد.")
            return

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در خواندن فایل: {e}")
        return

    question = text

    # نمونه تحلیل ساده بر اساس نوع سؤال
    if "نفر اول" in question or "رتبه اول" in question:
        if "رتبه" not in df_table.columns:
            await update.message.reply_text("❌ ستون 'رتبه' در جدول موجود نیست.")
            return
        top_row = df_table.loc[df_table["رتبه"] == 1]
        if not top_row.empty:
            name = top_row.iloc[0].get("نام و نام خانوادگی", "ناشناخته")
            await update.message.reply_text(f"🏆 نفر اول: {name}")
        else:
            await update.message.reply_text("❌ نفر اول یافت نشد.")

    elif "رتبه من" in question or "رتبه خودم" in question:
        await update.message.reply_text("🔢 لطفاً کد پرسنلی خود را وارد کنید:")
        context.user_data["awaiting_code"] = True

    elif context.user_data.get("awaiting_code"):
        code = text
        context.user_data["awaiting_code"] = False
        if "کد پرسنلی" not in df_table.columns or "رتبه" not in df_table.columns:
            await update.message.reply_text("❌ ستون‌های لازم در جدول وجود ندارند.")
            return
        match = df_table[df_table["کد پرسنلی"].astype(str) == str(code)]
        if not match.empty:
            rank = match.iloc[0]["رتبه"]
            await update.message.reply_text(f"📊 رتبه شما در طرح '{selected_plan['عنوان طرح']}': {rank}")
        else:
            await update.message.reply_text("❌ کد پرسنلی شما در جدول یافت نشد.")

    else:
        await update.message.reply_text("❌ متوجه سؤال نشدم. لطفاً یکی از گزینه‌ها را انتخاب کنید.")

# --- اضافه کردن هندلرها ---
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Flask برای Webhook ---
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

@flask_app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put_nowait(update)
    return "ok", 200

async def set_webhook():
    webhook_url = "https://telegram-bot-1-fp27.onrender.com"  # آدرس سرویس Render شما
    await app.bot.set_webhook(webhook_url)
    print(f"✅ Webhook set to {webhook_url}")

if __name__ == "__main__":
    print("✅ Bot is starting with Webhook...")
    asyncio.run(set_webhook())
    flask_app.run(host="0.0.0.0", port=10000)
