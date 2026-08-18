import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# သင့်ရဲ့ Channel များကို ဤနေရာတွင် ထည့်ပါ (Bot သည် ထို Channel များတွင် Admin ဖြစ်ရပါမည်)
CHANNEL_MAP = {
    "@drive": "@nightflixclub",       # ဥပမာ - "@my_drive_channel"
    "@club": "@nightflixdrive",         # ဥပမာ - "@my_club_channel"
    "@nightflix": "@nightflixmyanmar" # ဥပမာ - "@my_nightflix_channel"
}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    message_text = message.text or message.caption or ""
    
    target_channel = None
    cleaned_text = message_text

    # စာထဲမှာ ဘယ် Channel ကို ညွှန်ပြထားလဲ စစ်ဆေးခြင်း
    for keyword, channel_target in CHANNEL_MAP.items():
        if keyword.lower() in message_text.lower():
            target_channel = channel_target
            cleaned_text = message_text.replace(keyword, "").strip()
            break

    if target_channel:
        try:
            # Video ပါလာပါက Forward ပုံစံမဟုတ်ဘဲ သီးသန့် Video အသစ်အနေဖြင့် တင်ပေးခြင်း
            if message.video:
                await context.bot.send_video(
                    chat_id=target_channel,
                    video=message.video.file_id,
                    caption=cleaned_text,
                    parse_mode="Markdown"
                )
            # ပုံ (Photo) ပါလာပါက
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=target_channel,
                    photo=message.photo[-1].file_id,
                    caption=cleaned_text,
                    parse_mode="Markdown"
                )
            # စာသက်သက် (Review သို့မဟုတ် စာသား) ဖြစ်ပါက
            else:
                await context.bot.send_message(
                    chat_id=target_channel,
                    text=cleaned_text,
                    parse_mode="Markdown"
                )
            
            await message.reply_text(f"✅ {target_channel} သို့ အောင်မြင်စွာ တင်ပြီးပါပြီ။")
        except Exception as e:
            await message.reply_text(f"❌ ပို့၍မရပါ။ Error: {e}")
    else:
        await message.reply_text(
            "⚠️ ဘယ် Channel တင်ရမလဲ မသိရသေးပါ။\n"
            "ကျေးဇူးပြု၍ စာ သို့မဟုတ် ဗီဒီယို ပို့သည့်အခါ @drive, @club သို့မဟုတ် @nightflix ထည့်ရေးပေးပါ။"
        )

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    PORT = int(os.environ.get("PORT", "10000"))
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_message))
    
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
        app.run_polling(drop_pending_updates=True)
