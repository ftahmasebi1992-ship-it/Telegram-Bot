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

except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# بارگذاری فایل Excel اصلی
# -----------------------------
try:
    wb_liga = load_workbook(liga_file, data_only=True)
    ws_liga = wb_liga["فروشنده"]
except Exception as e:
    print(f"❌ خطا در بارگذاری فایل Rliga: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# -----------------------------
# دستور /start
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_names = [str(p) for p in title_to_number.keys() if str(p).strip() != ""]
    keyboard_plans = [[KeyboardButton(name)] for name in plan_names]
    reply_markup_plans = ReplyKeyboardMarkup(keyboard_plans, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:",
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
        # ------------------- انتخاب طرح -------------------
        if state == "choosing_plan":
            selected_number = title_to_number.get(text)
            if not selected_number:
                await update.message.reply_text("❌ طرح یافت نشد، لطفاً دوباره انتخاب کنید.")
                return

            context.user_data["selected_number"] = selected_number
            context.user_data["selected_table"] = title_to_table[text]

            # لیست سوال‌های همان طرح
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number].iloc[:, 1:].fillna("").values.flatten()
            questions = [q for q in questions if q]
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                "📋 لطفاً سوال خود را انتخاب کنید:",
                reply_markup=reply_markup_questions
            )
            context.user_data["state"] = "choosing_question"
            return

        # ------------------- پاسخ به سوال -------------------
        elif state == "choosing_question":
            table_name = context.user_data.get("selected_table")
            selected_number = context.user_data.get("selected_number")

            if table_name not in ws_liga.tables:
                await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
                return

            tbl = ws_liga.tables[table_name]
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws_liga.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            columns = data[0]
            rows = data[1:]
            df_table = pd.DataFrame(rows, columns=columns)

            # تحلیل سوال‌ها
            match_rank = re.search(r"رتبه (\d+) کیه", text)
            if match_rank:
                rank_number = int(match_rank.group(1))
                row = df_table[df_table["رتبه"] == rank_number]
                if row.empty:
                    await update.message.reply_text(f"❌ هیچ فردی با رتبه {rank_number} یافت نشد.")
                else:
                    await update.message.reply_text(f"💡 رتبه {rank_number}: {row['نام'].values[0]} {row['نام خانوادگی'].values[0]}")
                return

            elif "رتبه من" in text or "رتبه خودش" in text or "فاصله من با" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            elif "5نفر اول" in text or "5 نفر اول" in text:
                top5 = df_table.sort_values("رتبه").head(5)
                result = "\n".join([f"{r['رتبه']}: {r['نام']} {r['نام خانوادگی']}" for idx, r in top5.iterrows()])
                await update.message.reply_text(f"💡 5 نفر اول:\n{result}")
                return

            else:
                await update.message.reply_text("💡 این سوال بر اساس Table تحلیل شد اما جواب مستقیم یافت نشد.")
                return

        # ------------------- دریافت کد پرسنلی -------------------
        elif state == "waiting_for_id":
            emp_id = text
            table_name = context.user_data.get("selected_table")
            last_question = context.user_data.get("last_question")

            tbl = ws_liga.tables[table_name]
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws_liga.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            df_table = pd.DataFrame(data[1:], columns=data[0])

            row = df_table[df_table["کد پرسنلی"] == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                if "رتبه من" in last_question or "رتبه خودش" in last_question:
                    rank = row["رتبه"].values[0]
                    await update.message.reply_text(f"💡 رتبه شما: {rank}")
                elif "فاصله من با" in last_question:
                    target_rank = 1 if "نفر اول" in last_question else 5
                    target_row = df_table[df_table["رتبه"] == target_rank]
                    if target_row.empty:
                        await update.message.reply_text("❌ فرد هدف یافت نشد.")
                    else:
                        num_cols = [c for c in df_table.columns if c not in ["رتبه","کد پرسنلی","نام","نام خانوادگی"]]
                        if not num_cols:
                            await update.message.reply_text("❌ ستونی برای محاسبه فاصله یافت نشد.")
                        else:
                            col = num_cols[0]
                            diff = target_row[col].values[0] - row[col].values[0]
                            await update.message.reply_text(f"💡 فاصله شما با نفر {target_rank}: {diff}")

            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == context.user_data.get("selected_number")].iloc[:, 1:].fillna("").values.flatten()
            questions = [q for q in questions if q]
            keyboard_questions = [[KeyboardButton(q)] for q in questions]
            reply_markup_questions = ReplyKeyboardMarkup(keyboard_questions, resize_keyboard=True, one_time_keyboard=True)
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
