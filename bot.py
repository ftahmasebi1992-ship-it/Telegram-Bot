import os
import pandas as pd
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

# -------------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

FOC_FILE = "FOC.xlsx"
RLIGA_FILE = "Rliga 140408 - TG.xlsx"

# خواندن داده‌ها
foc_sheet1 = pd.read_excel(FOC_FILE, sheet_name=0)
foc_sheet2 = pd.read_excel(FOC_FILE, sheet_name=1)

# -------------------------
app = Flask(__name__)
telegram_app = ApplicationBuilder().token(TOKEN).build()

# مرحله‌های Conversation
ASK_PERSONNEL = 1

user_context = {}  # برای ذخیره انتخاب طرح و سوال و کد پرسنلی

# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(title, callback_data=f"plan_{idx}")]
        for idx, title in enumerate(foc_sheet1['عنوان طرح'])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفا یک طرح انتخاب کنید:", reply_markup=reply_markup)

# -------------------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("plan_"):
        idx = int(data.split("_")[1])
        plan_no = foc_sheet1.loc[idx, 'شماره طرح']
        plan_title = foc_sheet1.loc[idx, 'عنوان طرح']

        user_context[query.from_user.id] = {"plan_idx": idx}

        # لیست سوالات مرتبط
        questions = foc_sheet2[foc_sheet2['شماره طرح'] == plan_no]['سوالات اول'].tolist()
        # تشخیص اینکه سوال نیاز به کد پرسنلی دارد
        question_needs_code = foc_sheet2[foc_sheet2['شماره طرح'] == plan_no]['سوال دوم'].notna().tolist()

        keyboard = [
            [InlineKeyboardButton(q, callback_data=f"question_{idx}_{i}_{int(needs_code)}")]
            for i, (q, needs_code) in enumerate(zip(questions, question_needs_code))
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"طرح انتخاب شد: {plan_title}\nسوال مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)

    elif data.startswith("question_"):
        _, plan_idx, q_idx, needs_code = data.split("_")
        plan_idx, q_idx, needs_code = int(plan_idx), int(q_idx), int(needs_code)
        user_context[query.from_user.id].update({"q_idx": q_idx, "needs_code": needs_code})

        question_text = foc_sheet2[foc_sheet2['شماره طرح'] == foc_sheet1.loc[plan_idx, 'شماره طرح']]['سوالات اول'].iloc[q_idx]

        if needs_code:
            await query.edit_message_text(f"لطفا کد پرسنلی خود را وارد کنید برای پاسخ به سوال:\n{question_text}")
            return ASK_PERSONNEL
        else:
            # محاسبه پاسخ بدون کد پرسنلی
            answer = compute_answer(plan_idx, q_idx, None)
            await query.edit_message_text(f"سوال: {question_text}\nپاسخ: {answer}")
            return ConversationHandler.END

# -------------------------
async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    code = update.message.text.strip()
    ctx = user_context.get(user_id)
    if not ctx:
        await update.message.reply_text("خطا: اطلاعات طرح پیدا نشد. دوباره /start کنید.")
        return ConversationHandler.END

    answer = compute_answer(ctx['plan_idx'], ctx['q_idx'], code)
    question_text = foc_sheet2[foc_sheet2['شماره طرح'] == foc_sheet1.loc[ctx['plan_idx'], 'شماره طرح']]['سوالات اول'].iloc[ctx['q_idx']]
    await update.message.reply_text(f"سوال: {question_text}\nپاسخ: {answer}")
    return ConversationHandler.END

# -------------------------
def compute_answer(plan_idx, q_idx, personnel_code):
    plan_no = foc_sheet1.loc[plan_idx, 'شماره طرح']
    table_name = foc_sheet1.loc[plan_idx, 'TableNam']
    df_plan = pd.read_excel(RLIGA_FILE, sheet_name="فروشنده", engine='openpyxl')

    # انتخاب Table مرتبط
    if table_name in df_plan.columns:
        df_table = df_plan[[table_name, 'کد پرسنلی']].copy() if 'کد پرسنلی' in df_plan.columns else df_plan[[table_name]]
    else:
        df_table = df_plan[[c for c in df_plan.columns if table_name in c]]

    # مرتب سازی نزولی
    df_table_sorted = df_table.sort_values(by=table_name, ascending=False)

    # پاسخ‌ها
    if personnel_code:
        if 'کد پرسنلی' in df_table_sorted.columns and personnel_code in df_table_sorted['کد پرسنلی'].astype(str).values:
            row = df_table_sorted[df_table_sorted['کد پرسنلی'].astype(str) == personnel_code].iloc[0]
            rank = df_table_sorted.reset_index().index[df_table_sorted['کد پرسنلی'].astype(str) == personnel_code][0] + 1
            top5 = df_table_sorted.head(5)[table_name].tolist()
            distance_first = df_table_sorted.iloc[0][table_name] - row[table_name]
            distance_fifth = df_table_sorted.iloc[4][table_name] - row[table_name] if len(df_table_sorted) >=5 else None
            return f"رتبه شما: {rank}\nنفر اول: {df_table_sorted.iloc[0][table_name]}\n۵ نفر اول: {top5}\nفاصله با نفر اول: {distance_first}\nفاصله با نفر پنجم: {distance_fifth}"
        else:
            return "کد پرسنلی یافت نشد."
    else:
        return df_table_sorted.iloc[0][table_name] if not df_table_sorted.empty else "پاسخی یافت نشد"

# -------------------------
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        ASK_PERSONNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)]
    },
    fallbacks=[]
)

telegram_app.add_handler(conv_handler)
telegram_app.add_handler(CallbackQueryHandler(button))

# -------------------------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put(update)
    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    telegram_app.start()
    app.run(host="0.0.0.0", port=port)
