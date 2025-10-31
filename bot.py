import os
import threading
import pandas as pd
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openpyxl import load_workbook

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

    # شیت ۱: سوالات اولیه
    df_initial_questions = pd.read_excel(foc_file, sheet_name=0)
    initial_question_column = "عنوان طرح"

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

# کیبورد سوالات اولیه (شیت ۱ FOC)
initial_questions = df_initial_questions[initial_question_column].dropna().tolist()
keyboard_initial_questions = [[KeyboardButton(q)] for q in initial_questions]
reply_markup_initial_questions = ReplyKeyboardMarkup(keyboard_initial_questions, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! لطفاً یک سوال اولیه انتخاب کنید:",
        reply_markup=reply_markup_initial_questions
    )
    context.user_data["state"] = "choosing_initial_question"

# -----------------------------
# مدیریت پیام‌ها
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("state", "")

    try:
        # -------------------
        # مرحله سوال اولیه
        # -------------------
        if state == "choosing_initial_question":
            context.user_data["initial_question"] = text
            keyboard_plans = [[KeyboardButton(p)] for p in title_to_number.keys()]
            reply_markup_plans = ReplyKeyboardMarkup(keyboard_plans, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً طرح مورد نظر خود را انتخاب کنید:",
                reply_markup=reply_markup_plans
            )
            context.user_data["state"] = "choosing_plan"
            return

        # -------------------
        # مرحله انتخاب طرح
        # -------------------
        elif state == "choosing_plan":
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

            # خواندن Table از شیت "فروشنده"
            wb = load_workbook(liga_file, data_only=True)
            ws = wb["فروشنده"]

            if table_name not in ws.tables:
                await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
                return

            tbl = ws.tables[table_name]
            data = ws[tbl.ref]
            columns = [cell.value for cell in data[0]]
            rows = [[cell.value for cell in r] for r in data[1:]]
            df_table = pd.DataFrame(rows, columns=columns)

            question_col = [c for c in df_table.columns if "سؤال" in c or "سوال" in c][0]
            answer_col = [c for c in df_table.columns if c != question_col][0]

            if "رتبه خودش" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            row = df_table[df_table[question_col] == text]
            if row.empty:
                await update.message.reply_text("❌ جواب این سوال یافت نشد.")
                return
            answer = row[answer_col].values[0]
            await update.message.reply_text(f"💡 جواب سوال:\n{answer}")

            keyboard_plans = [[KeyboardButton(p)] for p in title_to_number.keys()]
            reply_markup_plans = ReplyKeyboardMarkup(keyboard_plans, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً طرح دیگری انتخاب کنید:",
                reply_markup=reply_markup_plans
            )
            context.user_data["state"] = "choosing_plan"
            return

        # -------------------
        # مرحله دریافت کد پرسنلی
        # -------------------
        elif state == "waiting_for_id":
            emp_id = text
            table_name = context.user_data.get("selected_table")
            last_question = context.user_data.get("last_question")

            wb = load_workbook(liga_file, data_only=True)
            ws = wb["فروشنده"]

            if table_name not in ws.tables:
                await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
                return

            tbl = ws.tables[table_name]
            data = ws[tbl.ref]
            columns = [cell.value for cell in data[0]]
            rows = [[cell.value for cell in r] for r in data[1:]]
            df_table = pd.DataFrame(rows, columns=columns)

            row = df_table[df_table["کد پرسنلی"] == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                rank = row["رتبه"].values[0]
                await update.message.reply_text(f"💡 رتبه شما: {rank}")

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
            await update.message.reply_text(
                "👋 لطفاً یک سوال اولیه انتخاب کنید:",
                reply_markup=reply_markup_initial_questions
            )
            context.user_data["state"] = "choosing_initial_question"

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
    app.run_polling() الان بات بالا میاد اما به درستی کار نمیکنه گیج میزنه  تو ببین میتونی متوجه بشی من کجای کارم اشتباه بوده و کدم چه ایرادی داره

