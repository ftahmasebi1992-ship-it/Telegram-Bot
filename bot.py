import os
import pandas as pd
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# بارگذاری توکن از Environment Variable
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables!")

# بارگذاری Excel
EXCEL_FILE = "data.xlsx"  # نام فایل Excel خودت
SHEET_NAME = "فروشنده"

try:
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine="openpyxl")
except FileNotFoundError:
    print(f"File {EXCEL_FILE} not found!")
    df = pd.DataFrame()

# استخراج نام طرح‌ها (نام تیبل‌ها)
if not df.empty and 'طرح' in df.columns:
    PLANS = df['طرح'].unique().tolist()
else:
    PLANS = []

# استارت بات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if PLANS:
        buttons = [[KeyboardButton(plan)] for plan in PLANS]
        reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        await update.message.reply_text("سلام! لطفاً یک طرح انتخاب کن:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("هیچ طرحی پیدا نشد.")

# پاسخ به پیام کاربر
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in PLANS:
        plan_data = df[df['طرح'] == text]
        if not plan_data.empty:
            response = plan_data.to_string(index=False)
            await update.message.reply_text(f"اطلاعات طرح {text}:\n{response}")
        else:
            await update.message.reply_text("هیچ اطلاعاتی برای این طرح پیدا نشد.")
    else:
        await update.message.reply_text("لطفاً یکی از طرح‌های موجود را انتخاب کن.")

# ساخت اپلیکیشن و اضافه کردن هندلرها
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# اجرای بات با Polling
if __name__ == "__main__":
    print("Bot is running...")
    app.run_polling()
