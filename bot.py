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
current_dir = os.getcwd()
foc_file = os.path.join(current_dir, "FOC.xlsx")
liga_file = os.path.join(current_dir, "Rliga 140408 - TG.xlsx")

print(f"📁 جستجوی فایل‌ها در: {current_dir}")
print(f"📄 FOC file exists: {os.path.exists(foc_file)}")
print(f"📄 Liga file exists: {os.path.exists(liga_file)}")

# -----------------------------
# بارگذاری داده‌ها
# -----------------------------
try:
    # شیت ۰: طرح‌ها
    df_plans = pd.read_excel(foc_file, sheet_name=0)
    print(f"✅ شیت طرح‌ها بارگذاری شد. ستون‌ها: {list(df_plans.columns)}")
    
    # شیت ۲: سوالات مرتبط با هر طرح
    df_questions_by_plan = pd.read_excel(foc_file, sheet_name=2)
    print(f"✅ شیت سوالات طرح‌ها بارگذاری شد. ستون‌ها: {list(df_questions_by_plan.columns)}")
    
    # ایجاد مپینگ‌ها
    title_to_number = dict(zip(df_plans["عنوان طرح"], df_plans["شماره طرح"]))
    title_to_table = dict(zip(df_plans["عنوان طرح"], df_plans["TableName"]))
    
    # پیدا کردن ستون سوالات در شیت ۲
    question_column = None
    for col in df_questions_by_plan.columns:
        if "سؤال" in str(col) or "سوال" in str(col):
            question_column = col
            break
    
    if not question_column:
        question_column = df_questions_by_plan.columns[1] if len(df_questions_by_plan.columns) > 1 else df_questions_by_plan.columns[0]
        print(f"⚠️ ستون سوال پیش‌فرض استفاده شد: {question_column}")
    
    print(f"✅ طرح‌های موجود: {list(title_to_number.keys())}")
    
except Exception as e:
    print(f"❌ خطا در بارگذاری فایل‌ها: {e}")
    exit(1)

# -----------------------------
# ربات تلگرام
# -----------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# -----------------------------
# توابع اصلی بات
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بات - نمایش لیست طرح‌ها"""
    # لیست طرح‌ها از شیت ۰
    plans_list = list(title_to_number.keys())
    
    keyboard = [[KeyboardButton(plan)] for plan in plans_list]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "👋 سلام! لطفاً یک طرح را انتخاب کنید:",
        reply_markup=reply_markup
    )
    
    # پاک کردن state قبلی
    context.user_data.clear()
    context.user_data["state"] = "choosing_plan"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_data = context.user_data
    state = user_data.get("state", "")
    
    print(f"🔍 وضعیت: {state}, متن: {text}")
    
    try:
        if state == "choosing_plan":
            await handle_plan_selection(update, context, text)
            
        elif state == "choosing_question":
            await handle_question_selection(update, context, text)
            
        elif state == "waiting_for_personal_id":
            await handle_personal_id(update, context)
            
        else:
            # state نامعتبر - شروع مجدد
            await start(update, context)
            
    except Exception as e:
        print(f"❌ خطا در handle_message: {e}")
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً /start را بزنید.")

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_plan):
    """مدیریت انتخاب طرح"""
    if selected_plan not in title_to_number:
        await update.message.reply_text("❌ طرح نامعتبر، لطفاً از گزینه‌ها انتخاب کنید:")
        return

    # ذخیره اطلاعات طرح انتخاب شده
    plan_number = title_to_number[selected_plan]
    table_name = title_to_table[selected_plan]
    
    context.user_data["selected_plan"] = selected_plan
    context.user_data["selected_number"] = plan_number
    context.user_data["selected_table"] = table_name
    
    # پیدا کردن سوالات مربوط به این طرح از شیت ۲
    questions = df_questions_by_plan[
        df_questions_by_plan["شماره طرح"] == plan_number
    ][question_column].dropna().unique().tolist()
    
    if questions:
        # نمایش سوالات مربوط به طرح انتخاب شده
        keyboard = [[KeyboardButton(q)] for q in questions]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"✅ طرح '{selected_plan}' انتخاب شد.\n"
            f"📋 لطفاً یکی از سوالات زیر را انتخاب کنید:",
            reply_markup=reply_markup
        )
        
        context.user_data["state"] = "choosing_question"
        context.user_data["available_questions"] = questions
        
    else:
        await update.message.reply_text(
            f"✅ طرح '{selected_plan}' انتخاب شد.\n"
            f"❌ متأسفانه سوالی برای این طرح تعریف نشده است.\n"
            f"لطفاً /start را بزنید و طرح دیگری انتخاب کنید."
        )

async def handle_question_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_question):
    """مدیریت انتخاب سوال و نمایش پاسخ"""
    available_questions = context.user_data.get("available_questions", [])
    
    if selected_question not in available_questions:
        await update.message.reply_text("❌ سوال نامعتبر، لطفاً از گزینه‌ها انتخاب کنید:")
        return

    table_name = context.user_data.get("selected_table")
    selected_plan = context.user_data.get("selected_plan")
    
    try:
        # خواندن داده‌ها از فایل لیگ
        wb = load_workbook(liga_file, data_only=True)
        
        if "فروشنده" not in wb.sheetnames:
            await update.message.reply_text("❌ شیت 'فروشنده' یافت نشد.")
            return
            
        ws = wb["فروشنده"]
        
        if table_name not in ws.tables:
            await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
            return
            
        # خواندن Table
        tbl = ws.tables[table_name]
        data = ws[tbl.ref]
        columns = [cell.value for cell in data[0]]
        rows = [[cell.value for cell in row] for row in data[1:]]
        df = pd.DataFrame(rows, columns=columns)
        
        print(f"✅ داده‌های Table بارگذاری شد. ستون‌ها: {list(df.columns)}")
        
        # بررسی اگر سوال مربوط به "رتبه خودش" باشد
        if "رتبه خودش" in selected_question:
            await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
            context.user_data["state"] = "waiting_for_personal_id"
            context.user_data["last_question"] = selected_question
            return
        
        # پیدا کردن ستون سوال و جواب
        question_cols = [c for c in df.columns if c and ("سؤال" in str(c) or "سوال" in str(c))]
        if not question_cols:
            await update.message.reply_text("❌ ستون سوال در داده‌ها یافت نشد.")
            return
            
        question_col = question_cols[0]
        answer_cols = [c for c in df.columns if c != question_col]
        answer_col = answer_cols[0] if answer_cols else None
        
        if not answer_col:
            await update.message.reply_text("❌ ستون پاسخ در داده‌ها یافت نشد.")
            return
        
        # پیدا کردن پاسخ
        result = df[df[question_col] == selected_question]
        if not result.empty:
            answer = result[answer_col].values[0]
            await update.message.reply_text(f"💡 پاسخ:\n{answer}")
        else:
            await update.message.reply_text("❌ پاسخ این سوال یافت نشد.")
        
        # بازگشت به انتخاب طرح
        plans_list = list(title_to_number.keys())
        keyboard = [[KeyboardButton(plan)] for plan in plans_list]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            "📋 لطفاً طرح دیگری انتخاب کنید یا /start برای شروع مجدد:",
            reply_markup=reply_markup
        )
        context.user_data["state"] = "choosing_plan"
        
    except Exception as e:
        print(f"❌ خطا در پردازش سوال: {e}")
        await update.message.reply_text(f"❌ خطا در پردازش سوال: {e}")

async def handle_personal_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دریافت کد پرسنلی برای سوال 'رتبه خودش'"""
    emp_id = update.message.text
    user_data = context.user_data
    table_name = user_data.get("selected_table")
    
    print(f"🔍 دریافت کد پرسنلی: {emp_id} برای Table: {table_name}")
    
    try:
        wb = load_workbook(liga_file, data_only=True)
        ws = wb["فروشنده"]
        tbl = ws.tables[table_name]
        data = ws[tbl.ref]
        columns = [cell.value for cell in data[0]]
        rows = [[cell.value for cell in row] for row in data[1:]]
        df = pd.DataFrame(rows, columns=columns)
        
        if "کد پرسنلی" in df.columns and "رتبه" in df.columns:
            # تبدیل به رشته برای مقایسه
            result = df[df["کد پرسنلی"].astype(str) == str(emp_id)]
            if not result.empty:
                rank = result["رتبه"].values[0]
                await update.message.reply_text(f"🎯 رتبه شما: {rank}")
            else:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
        else:
            await update.message.reply_text("❌ ستون‌های لازم در داده‌ها یافت نشد.")
            
    except Exception as e:
        print(f"❌ خطا در handle_personal_id: {e}")
        await update.message.reply_text(f"❌ خطا: {e}")
    
    # بازگشت به انتخاب طرح
    plans_list = list(title_to_number.keys())
    keyboard = [[KeyboardButton(plan)] for plan in plans_list]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📋 لطفاً طرح دیگری انتخاب کنید یا /start برای شروع مجدد:",
        reply_markup=reply_markup
    )
    user_data["state"] = "choosing_plan"

# اضافه کردن Handler ها
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Flask app برای Render
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    print("✅ Bot is starting...")
    threading.Thread(target=run_flask, daemon=True).start()
    app.run_polling()
