import os
import threading
import pandas as pd
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# برای خواندن Excel Table با نام
from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

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
# توابع کمکی
# -----------------------------
def read_excel_table_by_name(xlsx_path: str, table_name: str) -> pd.DataFrame:
    """
    جدول (Excel Table) با نام table_name را در فایل xlsx_path پیدا می‌کند،
    محدوده‌اش را می‌گیرد و آن را به pandas.DataFrame تبدیل می‌کند.
    اگر یافت نشد، ValueError پرتاب می‌کند.
    """
    wb = load_workbook(xlsx_path, data_only=True)
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if table_name in ws.tables:
            table = ws.tables[table_name]
            ref = table.ref  # مثل "B2:F101"
            min_col, min_row, max_col, max_row = range_boundaries(ref)
            # خواندن کل شیت با pandas (بدون header) و سپس برش ناحیه‌ی جدول
            df_sheet = pd.read_excel(xlsx_path, sheet_name=sheet_name, engine="openpyxl", header=None)
            df_table = df_sheet.iloc[min_row - 1 : max_row, min_col - 1 : max_col].copy()
            # ردیف اولِ این ناحیه را بعنوان header قرار می‌دهیم
            df_table.columns = df_table.iloc[0].values
            df_table = df_table.iloc[1:].reset_index(drop=True)
            return df_table
    raise ValueError(f"Table named '{table_name}' not found in {xlsx_path}.")

# -----------------------------
# بارگذاری داده‌ها یک بار
# -----------------------------
try:
    # شیت 0: اطلاعات طرح‌ها (شماره طرح, عنوان طرح, TableName)
    df_plans = pd.read_excel(foc_file, sheet_name=0, engine="openpyxl")
    required_columns_plans = ["شماره طرح", "عنوان طرح", "TableName"]
    for col in required_columns_plans:
        if col not in df_plans.columns:
            raise ValueError(f"❌ ستون '{col}' در شیت ۰ فایل FOC موجود نیست.")
    title_to_number = dict(zip(df_plans["عنوان طرح"], df_plans["شماره طرح"]))
    title_to_table = dict(zip(df_plans["عنوان طرح"], df_plans["TableName"]))

    # شیت 1: سوالات مرتبط با هر طرح (شیت اندیس 1)
    df_questions_by_plan = pd.read_excel(foc_file, sheet_name=1, engine="openpyxl")
    question_column = None
    for col in df_questions_by_plan.columns:
        if "سؤال" in str(col) or "سوال" in str(col):
            question_column = col
            break
    if not question_column:
        raise ValueError("❌ ستون سوالات در شیت ۱ فایل FOC موجود نیست.")
except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# کیبورد طرح‌ها برای start
plans = list(title_to_number.keys())
keyboard_plans = [[KeyboardButton(p)] for p in plans]
reply_markup_plans = ReplyKeyboardMarkup(keyboard_plans, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start -> نمایش لیست طرح‌ها (عنوان طرح)
    """
    await update.message.reply_text(
        "👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup_plans
    )
    context.user_data["state"] = "choosing_plan"
    context.user_data["title_to_number"] = title_to_number
    context.user_data["title_to_table"] = title_to_table

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("state", "")

    try:
        # -------------------
        # انتخاب طرح (مرحله اول)
        # -------------------
        if state == "choosing_plan":
            selected_number = context.user_data["title_to_number"].get(text)
            if not selected_number:
                await update.message.reply_text("❌ طرح یافت نشد، لطفاً از لیست یکی را انتخاب کنید.")
                return

            table_name = context.user_data["title_to_table"].get(text)
            if not table_name:
                await update.message.reply_text("❌ Table مربوط به این طرح در FOC ثبت نشده.")
                return

            context.user_data["selected_number"] = selected_number
            context.user_data["selected_table"] = table_name
            # استخراج سوالات مرتبط از شیت 1 (FOC)
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
            if not questions:
                await update.message.reply_text("❌ سوالی برای این طرح موجود نیست.")
                return

            # نمایش کیبورد سوالات
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=reply_markup_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        # -------------------
        # انتخاب سوال (مرحله دوم)
        # -------------------
        elif state == "choosing_question":
            table_name = context.user_data.get("selected_table")
            selected_number = context.user_data.get("selected_number")
            if not table_name or not selected_number:
                await update.message.reply_text("❌ خطای داخلی: اطلاعات طرح موجود نیست. دوباره /start کنید.")
                context.user_data["state"] = "choosing_plan"
                return

            # خواندن Table از فایل Rliga بر اساس نام Table (نه sheet)
            try:
                df_table = read_excel_table_by_name(liga_file, table_name)
            except Exception as e:
                await update.message.reply_text(f"❌ خطا در خواندن Table '{table_name}': {e}")
                # بازگرداندن به انتخاب طرح
                await update.message.reply_text("📋 لطفاً یک طرح دیگر انتخاب کنید:", reply_markup=reply_markup_plans)
                context.user_data["state"] = "choosing_plan"
                return

            # پیدا کردن ستون سوال در df_table (انعطاف‌پذیر)
            question_cols = [c for c in df_table.columns if "سؤال" in str(c) or "سوال" in str(c)]
            if not question_cols:
                await update.message.reply_text("❌ ستون سؤال در جدول مربوطه یافت نشد.")
                context.user_data["state"] = "choosing_plan"
                return
            question_col = question_cols[0]

            # حالت خاص: سوالی که نیاز به کد پرسنلی دارد
            if "رتبه" in str(text) and ("خود" in str(text) or "خودش" in str(text) or "خودم" in str(text) or "شخصی" in str(text) or "خودم" in str(text)):
                # از کاربر کد پرسنلی طلب می‌کنیم
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_emp_id"
                context.user_data["last_question_text"] = text
                return

            # حالت معمولی: یافته سوال را در ستون سوال جستجو کن و جواب را از ستون پاسخ بگیر
            # فرض می‌کنیم ستون جواب، ستونی غیر از ستون سؤال است؛ اگر چند ستون غیر از سؤال باشد از اولین استفاده می‌کنیم.
            answer_cols = [c for c in df_table.columns if c != question_col]
            if not answer_cols:
                await update.message.reply_text("❌ ستون جواب در جدول مربوطه یافت نشد.")
                context.user_data["state"] = "choosing_plan"
                return
            answer_col = answer_cols[0]

            # جستجو بر اساس متن سوال
            row = df_table[df_table[question_col].astype(str).str.strip() == str(text).strip()]
            if row.empty:
                await update.message.reply_text("❌ جواب این سوال در جدول مربوطه یافت نشد.")
            else:
                answer = row.iloc[0][answer_col]
                await update.message.reply_text(f"💡 جواب:\n{answer}")

            # بعد از نمایش جواب، بازگشت به انتخاب طرح (یا می‌تونیم دوباره سوالات همان طرح رو نمایش بدیم)
            await update.message.reply_text("📋 لطفاً یک طرح دیگر انتخاب کنید:", reply_markup=reply_markup_plans)
            context.user_data["state"] = "choosing_plan"
            return

        # -------------------
        # دریافت کد پرسنلی برای سوال "رتبه خودش"
        # -------------------
        elif state == "waiting_for_emp_id":
            emp_id = str(text).strip()
            table_name = context.user_data.get("selected_table")
            if not table_name:
                await update.message.reply_text("❌ خطای داخلی: Table موجود نیست. دوباره /start کنید.")
                context.user_data["state"] = "choosing_plan"
                return

            try:
                df_table = read_excel_table_by_name(liga_file, table_name)
            except Exception as e:
                await update.message.reply_text(f"❌ خطا در خواندن Table '{table_name}': {e}")
                context.user_data["state"] = "choosing_plan"
                return

            # فرض می‌کنیم در جدول ستونی به نام "کد پرسنلی" و ستونی به نام "رتبه" وجود دارد.
            # اگر نام ستون‌ها متفاوت است می‌توانیم مشابه قبل انعطاف‌پذیر شناسایی کنیم.
            emp_id_col = None
            rank_col = None
            for c in df_table.columns:
                if "کد" in str(c) and "پرسن" in str(c):
                    emp_id_col = c
                if "رتبه" in str(c):
                    rank_col = c
            if not emp_id_col or not rank_col:
                await update.message.reply_text("❌ ستون‌های 'کد پرسنلی' یا 'رتبه' در جدول مربوطه یافت نشد.")
                context.user_data["state"] = "choosing_plan"
                return

            row = df_table[df_table[emp_id_col].astype(str).str.strip() == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                rank = row.iloc[0][rank_col]
                await update.message.reply_text(f"💡 رتبه شما: {rank}")

            # بعد از پاسخ، بازگرداندن کاربر برای انتخاب سوالات همان طرح
            selected_number = context.user_data.get("selected_number")
            if selected_number:
                questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
                keyboard_questions = [[KeyboardButton(q)] for q in questions]
                reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
                await update.message.reply_text("📋 سوالات مربوط به طرح:", reply_markup=reply_markup_questions)
                context.user_data["state"] = "choosing_question"
            else:
                await update.message.reply_text("📋 لطفاً یک طرح انتخاب کنید:", reply_markup=reply_markup_plans)
                context.user_data["state"] = "choosing_plan"
            return

        else:
            # اگر state مشخص نبود، از اول شروع کن
            await update.message.reply_text("👋 لطفاً طرح مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup_plans)
            context.user_data["state"] = "choosing_plan"
            return

    except Exception as e:
        # خطای عمومی را به کاربر گزارش کن
        await update.message.reply_text(f"❌ خطا در پردازش پیام: {e}")
        # برای ایمن بودن کاربر را به انتخاب طرح ببریم
        await update.message.reply_text("📋 لطفاً یک طرح انتخاب کنید:", reply_markup=reply_markup_plans)
        context.user_data["state"] = "choosing_plan"

# -----------------------------
# Handler ها
# -----------------------------
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -----------------------------
# Flask healthcheck برای Render
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
# اجرای ربات
# -----------------------------
if __name__ == "__main__":
    print("✅ Bot is starting...")
    app.run_polling()
