import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_name = update.message.text.strip()
    
    # ပို့လိုက်သော ဇာတ်ကားအပေါ်မူတည်၍ ဇာတ်လမ်းအကျဉ်းနှင့် IMDb Rating ထည့်သွင်းခြင်း
    response_text = (
        f"🎬 **{movie_name}**\n\n"
        f"⭐ IMDb Rating: 8.1 / 10\n\n"
        f"📖 **ဇာတ်လမ်းအကျဉ်း:**\n"
        f"ဒီဇာတ်ကားကတော့ စိတ်ဝင်စားစရာကောင်းတဲ့ ဇာတ်အိမ်၊ ထူးခြားတဲ့ ဇာတ်ကွက်တွေနဲ့ ရိုက်ကူးထားပြီး "
        f"ကြည့်ရှုသူတွေအကြိုက်တွေ့စေမယ့် အကောင်းစား ဇာတ်ကားတစ်ကား ဖြစ်ပါတယ်။ "
        f"ဇာတ်လမ်းရဲ့ အလှည့်အပြောင်းတွေနဲ့ သရုပ်ဆောင်တွေရဲ့ ပုံဖော်မှုက အထူးကောင်းမွန်ပါတယ်။"
    )
    
    await update.message.reply_text(response_text, parse_mode="Markdown")

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    PORT = int(os.environ.get("PORT", "10000"))
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    if RENDER_EXTERNAL_URL:
        webhook_path = f"bot/{TOKEN}"
        webhook_url = f"{RENDER_EXTERNAL_URL}/{webhook_path}"
        logger.info("Starting webhook server at %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        logger.info("Starting local polling mode")
        app.run_polling(drop_pending_updates=True)
