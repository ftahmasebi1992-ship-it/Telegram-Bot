import os
import threading
import pandas as pd
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openpyxl import load_workbook
from openpyxl.utils import range_boundaries
import re

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
# بارگذاری داده‌ها از FOC
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

    # شیت ۱: سوالات طرح‌ها
    df_questions_by_plan = pd.read_excel(foc_file, sheet_name=1)
    question_column = "سوالات اول"  # می‌توانیم همه ستون‌ها را بعدا ترکیب کنیم

except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# لیست سوالات اولیه (ستون سوال اول)
initial_questions = df_questions_by_plan[question_column].dropna().tolist()
keyboard_initial_questions = [[KeyboardButton(q)] for q in initial_questions]
reply_markup_initial_questions = ReplyKeyboardMarkup(keyboard_initial_questions, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! لطفاً یک سوال اولیه انتخاب کنید:",
        reply_markup=reply_markup_initial_questions
    )
    context.user_data["state"] = "choosing_initial_question"

# -----------------------------
# مدیریت پیام‌ها و تحلیل سوال‌ها
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("state", "")

    try:
        # ------------------- مرحله سوال اولیه -------------------
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

        # ------------------- مرحله انتخاب طرح -------------------
        elif state == "choosing_plan":
            selected_number = title_to_number.get(text)
            if not selected_number:
                await update.message.reply_text("❌ طرح یافت نشد، لطفاً دوباره انتخاب کنید.")
                return

            context.user_data["selected_number"] = selected_number
            context.user_data["selected_table"] = title_to_table[text]

            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, "سوالات اول"].dropna().tolist()
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=keyboard_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        # ------------------- مرحله پاسخ به سوال -------------------
        elif state == "choosing_question":
            table_name = context.user_data.get("selected_table")
            selected_number = context.user_data.get("selected_number")

            wb = load_workbook(liga_file, data_only=True)
            ws = wb["فروشنده"]

            if table_name not in ws.tables:
                await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
                return

            # خواندن Table
            tbl = ws.tables[table_name]
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            columns = data[0]
            rows = data[1:]
            df_table = pd.DataFrame(rows, columns=columns)

            # تشخیص ستون‌ها
            question_cols = [c for c in df_table.columns if c and ("سؤال" in str(c) or "سوال" in str(c))]
            question_col = question_cols[0] if question_cols else None
            answer_cols = [c for c in df_table.columns if c != question_col]
            answer_col = answer_cols[0] if answer_cols else None

            # ---- تحلیل سوال‌ها ----
            # رتبه X کیه؟
            if re.search(r"رتبه (\d+) کیه", text):
                match = re.search(r"رتبه (\d+) کیه", text)
                rank_number = int(match.group(1))
                if "رتبه" not in df_table.columns or "نام" not in df_table.columns or "نام خانوادگی" not in df_table.columns:
                    await update.message.reply_text("❌ ستون‌های لازم برای رتبه‌ها یافت نشد.")
                    return
                row = df_table[df_table["رتبه"] == rank_number]
                if row.empty:
                    await update.message.reply_text(f"❌ هیچ فردی با رتبه {rank_number} یافت نشد.")
                    return
                await update.message.reply_text(f"💡 رتبه {rank_number}: {row['نام'].values[0]} {row['نام خانوادگی'].values[0]}")
                return

            # رتبه من چندمه؟
            elif "رتبه من" in text or "رتبه خودش" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            # 5 نفر اول چه کسانی هستند؟
            elif "5نفر اول" in text or "5 نفر اول" in text:
                if "رتبه" not in df_table.columns or "نام" not in df_table.columns or "نام خانوادگی" not in df_table.columns:
                    await update.message.reply_text("❌ ستون‌های لازم برای رتبه‌ها یافت نشد.")
                    return
                top5 = df_table.sort_values("رتبه").head(5)
                result = "\n".join([f"{r['رتبه']}: {r['نام']} {r['نام خانوادگی']}" for idx, r in top5.iterrows()])
                await update.message.reply_text(f"💡 5 نفر اول:\n{result}")
                return

            # فاصله من با نفر اول/پنجم
            elif "فاصله من با" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            # سایر سوال‌ها: lookup ساده
            else:
                if question_col and answer_col:
                    row = df_table[df_table[question_col] == text]
                    if row.empty:
                        await update.message.reply_text("💡 جواب بر اساس Table تحلیل شد اما یافت نشد.")
                        return
                    await update.message.reply_text(f"💡 جواب تحلیل شده:\n{row[answer_col].values[0]}")
                    return
                else:
                    await update.message.reply_text("❌ ستون‌های لازم برای پاسخ یافت نشد.")
                    return

        # ------------------- مرحله دریافت کد پرسنلی -------------------
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
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            df_table = pd.DataFrame(data[1:], columns=data[0])

            if "کد پرسنلی" not in df_table.columns:
                await update.message.reply_text("❌ ستون کد پرسنلی یافت نشد.")
                return

            row = df_table[df_table["کد پرسنلی"] == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                # رتبه من چندمه؟
                if "رتبه" in df_table.columns and ("رتبه من" in last_question or "رتبه خودش" in last_question):
                    rank = row["رتبه"].values[0]
                    await update.message.reply_text(f"💡 رتبه شما: {rank}")
                # فاصله من با نفر اول/پنجم
                elif "فاصله من با" in last_question:
                    if "رتبه" in df_table.columns:
                        target_rank = 1 if "نفر اول" in last_question else 5
                        target_row = df_table[df_table["رتبه"] == target_rank]
                        if target_row.empty:
                            await update.message.reply_text("❌ فرد هدف یافت نشد.")
                        else:
                            num_cols = [c for c in df_table.columns if c not in ["رتبه", "کد پرسنلی", "نام", "نام خانوادگی"]]
                            if not num_cols:
                                await update.message.reply_text("❌ ستونی برای محاسبه فاصله یافت نشد.")
                            else:
                                col = num_cols[0]
                                diff = target_row[col].values[0] - row[col].values[0]
                                await update.message.reply_text(f"💡 فاصله شما با نفر {target_rank}: {diff}")
                else:
                    await update.message.reply_text("❌ سوال نامشخص است.")

            # بازگرداندن کیبورد سوالات طرح
            selected_number = context.user_data.get("selected_number")
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, "سوالات اول"].dropna().tolist()
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=keyboard_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        # ------------------- حالت پیش‌فرض -------------------
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
    app.run_polling()
