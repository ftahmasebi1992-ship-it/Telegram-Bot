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

            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
            if not questions:
                await update.message.reply_text("❌ سوالی برای این طرح موجود نیست.")
                return

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

            # خواندن Table به صورت DataFrame
            tbl = ws.tables[table_name]
            from openpyxl.utils import range_boundaries
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            columns = data[0]
            rows = data[1:]
            df_table = pd.DataFrame(rows, columns=columns)

            # شناسایی ستون‌ها
            question_cols = [c for c in df_table.columns if c and ("سؤال" in str(c) or "سوال" in str(c))]
            question_col = question_cols[0] if question_cols else None
            answer_cols = [c for c in df_table.columns if c != question_col]
            answer_col = answer_cols[0] if answer_cols else None

            # ----- تحلیل خودکار سوال‌ها -----
            # رتبه اول، دوم، … کیه؟
            if "رتبه" in text and "کیه" in text:
                if "رتبه" not in df_table.columns or "نام" not in df_table.columns or "نام خانوادگی" not in df_table.columns:
                    await update.message.reply_text("❌ ستون‌های لازم برای رتبه‌ها یافت نشد.")
                    return
                import re
                match = re.search(r"(\d+)", text)
                rank_number = int(match.group(1)) if match else 1  # پیش فرض 1
                row = df_table[df_table["رتبه"] == rank_number]
                if row.empty:
                    await update.message.reply_text(f"❌ هیچ فردی با رتبه {rank_number} یافت نشد.")
                    return
                first_name = row["نام"].values[0]
                last_name = row["نام خانوادگی"].values[0]
                await update.message.reply_text(f"💡 رتبه {rank_number}: {first_name} {last_name}")
                return

            # رتبه من چندمه
            elif "رتبه من" in text or "رتبه خودش" in text:
                await update.message.reply_text("لطفاً کد پرسنلی خود را وارد کنید:")
                context.user_data["state"] = "waiting_for_id"
                context.user_data["last_question"] = text
                return

            # سایر سوال‌ها: آنالیز Table
            else:
                if question_col and answer_col:
                    # جستجوی نزدیک‌ترین match یا محاسبه خودکار
                    row = df_table[df_table[question_col] == text]
                    if row.empty:
                        await update.message.reply_text("💡 اطلاعات بر اساس Table تحلیل شد: اما جواب دقیق یافت نشد.")
                        return
                    answer = row[answer_col].values[0]
                    await update.message.reply_text(f"💡 جواب تحلیل شده:\n{answer}")
                    return
                else:
                    await update.message.reply_text("❌ ستون‌های لازم برای پاسخ یافت نشد.")
                    return

        # ------------------- دریافت کد پرسنلی -------------------
        elif state == "waiting_for_id":
            emp_id = text
            table_name = context.user_data.get("selected_table")

            wb = load_workbook(liga_file, data_only=True)
            ws = wb["فروشنده"]
            if table_name not in ws.tables:
                await update.message.reply_text(f"❌ Table با نام '{table_name}' یافت نشد.")
                return
            tbl = ws.tables[table_name]
            from openpyxl.utils import range_boundaries
            min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
            data = [
                [ws.cell(row=r, column=c).value for c in range(min_col, max_col+1)]
                for r in range(min_row, max_row+1)
            ]
            df_table = pd.DataFrame(data[1:], columns=data[0])

            if "کد پرسنلی" not in df_table.columns or "رتبه" not in df_table.columns:
                await update.message.reply_text("❌ ستون‌های کد پرسنلی یا رتبه یافت نشد.")
                return

            row = df_table[df_table["کد پرسنلی"] == emp_id]
            if row.empty:
                await update.message.reply_text("❌ کد پرسنلی یافت نشد.")
            else:
                rank = row["رتبه"].values[0]
                await update.message.reply_text(f"💡 رتبه شما: {rank}")

            # بازگرداندن کیبورد سوالات طرح
            selected_number = context.user_data.get("selected_number")
            questions = df_questions_by_plan.loc[df_questions_by_plan["شماره طرح"] == selected_number, question_column].dropna().tolist()
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
