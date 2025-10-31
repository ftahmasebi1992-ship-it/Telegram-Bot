import os
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# بارگذاری متغیرهای محیطی
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in environment variables.")
    exit(1)

app = ApplicationBuilder().token(BOT_TOKEN).build()

# --- فایل‌ها ---
foc_file = "FOC.xlsx"
liga_file = "Rliga 140408 - TG.xlsx"

# --- شروع بات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = pd.read_excel(foc_file, sheet_name=0)
    plans = df["طرح"].dropna().tolist()

    keyboard = [[KeyboardButton(p)] for p in plans]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("👋 سلام! لطفاً طرح مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)

# --- پاسخ به انتخاب طرح ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    df1 = pd.read_excel(foc_file, sheet_name=0)
    df2 = pd.read_excel(foc_file, sheet_name=1)

    if text in df1["طرح"].values:
        table_name = df1.loc[df1["طرح"] == text, "TableName"].values[0]
        questions = df2.loc[df2["طرح"] == text, "سؤال"].dropna().tolist()
        questions_text = "\n".join([f"- {q}" for q in questions])
        await update.message.reply_text(f"📋 سؤالات مربوط به طرح {text}:\n\n{questions_text}")
        context.user_data["selected_table"] = table_name
    else:
        await update.message.reply_text("❌ طرح یافت نشد. لطفاً از لیست انتخاب کنید.")

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    print("✅ Bot is starting...")
    app.run_polling()
