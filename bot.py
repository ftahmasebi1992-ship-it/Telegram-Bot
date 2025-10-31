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
    print("❌ BOT_TOKEN not found.")
    exit(1)

# -----------------------------
# فایل‌ها
# -----------------------------
foc_file = "FOC.xlsx"
liga_file = "Rliga 140408 - TG.xlsx"

# -----------------------------
# بارگذاری داده‌ها یک بار
# -----------------------------
try:
    # شیت ۰: طرح‌ها
    df_plans = pd.read_excel(foc_file, sheet_name=0)
    required_columns_plans = ["شماره طرح", "عنوان طرح", "TableName"]
    for col in required_columns_plans:
        if col not in df_plans.columns:
            raise ValueError(f"❌ ستون '{col}' در شیت ۰ فایل FOC موجود نیست.")
    title_to_number = dict(zip(df_plans["عنوان طرح"], df_plans["شماره طرح"]))
    title_to_table = dict(zip(df_plans["عنوان طرح"], df_plans["TableName"]))

    # شیت ۲: سوالات مرتبط با هر طرح
    df_questions_by_plan = pd.read_excel(foc_file, sheet_name=1)
    question_column = None
    for col in df_questions_by_plan.columns:
        if "سؤال" in col or "سوال" in col:
            question_column = col
            break
    if not question_column:
        raise ValueError("❌ ستون سوالات در شیت ۲ فایل FOC موجود نیست.")

except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط لیست طرح‌ها (بدون سوال اولیه)
    keyboard_plans = [[KeyboardButton(p)] for p in title_to_number.keys()]
    reply_markup_plans = ReplyKeyboardMarkup(keyboard_plans, one_time_keyboard=True)
    await update.message.reply_text(
        "📋 لطفاً طرح مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup_plans
    )
    context.user_data["state"] = "choosing_plan"

# -----------------------------
# مدیریت پیام‌ها
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("state", "")

    try:
        # -------------------
        # مرحله انتخاب طرح
        # -------------------
        if state == "choosing_plan":
            selected_number = title_to_number.get(text)
            if not selected_number:
                await update.message.reply_text("❌ طرح یافت نشد، لطفاً دوباره انتخاب کنید.")
                return

            context.user_data["selected_number"] = selected_number
            context.user_data["selected_table"] = title_to_table[text]

            # پیدا کردن سوالات مربوط به طرح
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
            if not questions:
                await update.message.reply_text("❌ سوالی برای این طرح موجود نیست.")
                return

            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=reply_markup_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        # -------------------
        # مرحله انتخاب سوال و پاسخ
        # -------------------
        elif state == "choosing_question":
            table_name = context.user_data.get("selected_table")
            selected_number = context.user_data.get("selected_number")

            # فقط از شیت فروشنده می‌خوانیم
            df_seller = pd.read_excel(liga_file, sheet_name="فروشنده")

            # فقط ردیف‌های مربوط به Table انتخاب‌شده
            df_table = df_seller[df_seller["TableName"] == table_name]

            if df_table.empty:
                await update.message.reply_text(f"❌ Table '{table_name}' در شیت فروشنده یافت نشد.")
                return

            # اگر سوال "رتبه خودش" باشد
            if "رتبه خودش" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            # پیدا کردن جواب سوال دیگر
            if "نفر اول" in text:
                top_person = df_table.sort_values(by="رتبه").iloc[0]
                name = top_person["نام"] + " " + top_person["نام خانوادگی"]
                await update.message.reply_text(f"🏆 {name} رتبه اول است.")
                return

            await update.message.reply_text("🤖 سوال شناسایی نشد یا در داده‌ها تعریف نشده است.")
            return

        # -------------------
        # مرحله دریافت کد پرسنلی
        # -------------------
        elif state == "waiting_for_id":
            emp_id = text
            table_name = context.user_data.get("selected_table")

            df_seller = pd.read_excel(liga_file, sheet_name="فروشنده")
            df_table = df_seller[df_seller["TableName"] == table_name]

            row = df_table[df_table["کد پرسنلی"] == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                rank = row["رتبه"].values[0]
                await update.message.reply_text(f"💡 رتبه شما: {rank}")

            # نمایش مجدد سوالات
            selected_number = context.user_data.get("selected_number")
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=reply_markup_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        else:
            await start(update, context)

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در پردازش پیام: {e}")

# -----------------------------
# افزودن Handler ها
# -----------------------------
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
