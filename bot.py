import os
import pandas as pd
from openpyxl import load_workbook
from dotenv import load_dotenv
from flask import Flask, request
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# -------------------------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# -------------------------
# بارگذاری دیتای فایل FOC
FOC_FILE = "FOC.xlsx"
Rliga_FILE = "Rliga 140408 - TG.xlsx"

# شیت ها
FOC_sheet1 = pd.read_excel(FOC_FILE, sheet_name=0)
FOC_sheet2 = pd.read_excel(FOC_FILE, sheet_name=1)

# شیت فروشنده فایل Rliga
Rliga_wb = load_workbook(Rliga_FILE, data_only=True)
Rliga_ws = Rliga_wb["فروشنده"]

# -------------------------
# Flask
app = Flask(__name__)

# -------------------------
# ساخت اپلیکیشن تلگرام
telegram_app = ApplicationBuilder().token(TOKEN).build()

# -------------------------
# نگهداری انتخاب طرح برای هر کاربر
user_state = {}  # user_id -> {"طرح": ..., "Table": ...}

# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # عنوان طرح ها
    titles = FOC_sheet1["عنوان طرح"].tolist()
    buttons = [[KeyboardButton(title)] for title in titles]
    markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("لطفا طرح مورد نظر را انتخاب کنید:", reply_markup=markup)

# -------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_state or "طرح" not in user_state[user_id]:
        # کاربر طرح را انتخاب کرده
        if text in FOC_sheet1["عنوان طرح"].values:
            # نگهداری TableName
            table_name = FOC_sheet1.loc[FOC_sheet1["عنوان طرح"] == text, "TableName"].values[0]
            user_state[user_id] = {"طرح": text, "Table": table_name}
            
            # سوالات مربوط به طرح
            questions = FOC_sheet2.loc[FOC_sheet2["شماره طرح"] == FOC_sheet1.loc[FOC_sheet1["عنوان طرح"] == text, "شماره طرح"].values[0], "سوالات اول"].tolist()
            buttons = [[KeyboardButton(q)] for q in questions if isinstance(q, str) and q.strip() != ""]
            markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("لطفا سوال مورد نظر را انتخاب کنید:", reply_markup=markup)
        else:
            await update.message.reply_text("لطفا یک طرح معتبر انتخاب کنید.")
    else:
        # کاربر سوال را انتخاب کرده -> پاسخ محاسبه شود
        table_name = user_state[user_id]["Table"]

        # خواندن Table از شیت فروشنده
        table = None
        for tbl in Rliga_ws._tables:
            if tbl.name == table_name:
                data_range = tbl.ref
                table = pd.DataFrame(Rliga_ws[data_range].values[1:], columns=[c.value for c in Rliga_ws[data_range].values[0]])
                break
        
        if table is None:
            await update.message.reply_text("Table مورد نظر پیدا نشد!")
            return

        # پاسخ هوشمند ساده (مثال: نفر اول یا رتبه شما)
        if "نفر اول" in text:
            answer = table.iloc[0, 0]
        elif "رتبه من" in text:
            answer = "رتبه شما محاسبه شد!"  # اینجا میتونی منطق خودت رو اضافه کنی
        else:
            answer = "پاسخ آماده شد!"

        await update.message.reply_text(f"پاسخ: {answer}")

# -------------------------
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -------------------------
# Flask webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.update_queue.put(update))
    return "ok"

# -------------------------
if __name__ == "__main__":
    print(f"Bot is running on port {PORT}...")
    telegram_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}"
    )
