import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_name = update.message.text
    response_text = f"🎬 {movie_name} ဇာတ်ကားအတွက် Review တောင်းဆိုမှုကို လက်ခံရရှိပါပြီ။"
    await update.message.reply_text(response_text, parse_mode="Markdown")

if name == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    PORT = int(os.environ.get("PORT", "10000"))
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Render အတွက် Webhook ပုံစံဖြင့် ချိတ်ဆက်ခြင်း
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
