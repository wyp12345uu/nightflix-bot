import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Bot တက်လာရင် Movie Name တောင်းမည့် ပုံစံ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_name = update.message.text
    
    # ဇာတ်ကားနာမည်အတွက် ညွှန်းဆိုချက်/အညွှန်း (Review) ရေးပေးခိုင်းရန် AI သို့မဟုတ် စာသားသတ်မှတ်ချက်
    # ဤနေရာတွင် Review ရေးပေးမည့် ပုံစံကို ထည့်သွင်းနိုင်ပါသည်
    response_text = (
        f"🎬 {movie_name} ဇာတ်ကားအတွက် Review:\n\n"
        f"ဒီဇာတ်ကားကတော့ အညွှန်းနဲ့ ဇာတ်အိမ်ခိုင်မာတဲ့ ဇာတ်ကားကောင်းတစ်ခု ဖြစ်ပါတယ်။ "
        f"ဇာတ်လမ်းဇာတ်ကွက်၊ သရုပ်ဆောင်ချက်နဲ့ ကြည့်ရှုသူတွေအတွက် စိတ်ဝင်စားစရာ အချက်အလက်တွေ အပြည့်အစုံပါဝင်ပါတယ်..."
    )
    
    await update.message.reply_text(response_text, parse_mode="Markdown")

if __ name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    
    # စာသား (Text) ပို့သမျှကို Review ပုံစံနဲ့ ပြန်ဖြေမည့် Handler
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Bot is running...")
    app.run_polling()
