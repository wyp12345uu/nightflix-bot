"""Telegram movie automation bot.

The bot is intentionally admin-only. It copies an existing Telegram message into the
Drive channel, enriches the movie with OMDb data, generates Burmese copy with OpenAI,
and requires an explicit approval before publishing to the Club and Main channels.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

# Channels are configurable through environment variables while retaining the values
# supplied for this deployment as defaults.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAIN_CHANNEL_ID = os.environ.get("MAIN_CHANNEL_ID", "@nightflixmyanmar")
CLUB_CHANNEL_ID = os.environ.get("CLUB_CHANNEL_ID", "@nightflixclub")
DRIVE_CHANNEL_ID = os.environ.get("DRIVE_CHANNEL_ID", "@nightflixdrive")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DIGITAL_SHOP_LINK = os.environ.get("DIGITAL_SHOP_LINK", "YOUR_DIGITAL_SHOP_LINK_HERE")
ADMIN_IDS = {
    int(value.strip())
    for value in os.environ.get("ADMIN_IDS", "").split(",")
    if value.strip().lstrip("-").isdigit()
}
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

LINK, NAME, POSTER, PREVIEW = range(4)
APPROVE = "approve"
CANCEL = "cancel"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("telegram-movie-bot")


@dataclass
class MovieData:
    title: str
    year: str = "N/A"
    rating: str = "N/A"
    genre: str = "N/A"
    plot: str = ""
    director: str = "N/A"
    actors: str = "N/A"
    runtime: str = "N/A"


class BotError(Exception):
    """An expected, user-facing workflow error."""


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ADMIN_IDS)


def channel_link(channel: str, message_id: int) -> str:
    """Build a usable link for a public @username channel."""
    username = channel.strip().lstrip("@").strip()
    if username and not username.lstrip("-").isdigit():
        return f"https://t.me/{username}/{message_id}"
    return f"https://t.me/c/{str(channel).replace('-100', '')}/{message_id}"


def parse_telegram_message_link(value: str) -> tuple[str, int]:
    """Parse public t.me links, t.me/c links, and @channel/message-id shorthand."""
    value = value.strip()
    match = re.match(r"^(?:https?://)?t\.me/([^/?#]+)/([0-9]+)(?:\?.*)?$", value)
    if match:
        source, message_id = match.group(1), int(match.group(2))
        if source == "c":
            raise BotError("`t.me/c/...` private link ကို မပို့ပါနှင့်။ Telegram channel username နှင့် message ID ကို ပေးပါ။")
        return (source, message_id)
    match = re.match(r"^@([A-Za-z0-9_]{4,})/([0-9]+)$", value)
    if match:
        return (f"@{match.group(1)}", int(match.group(2)))
    raise BotError("Telegram Link ပုံစံမမှန်ပါ။ ဥပမာ `https://t.me/channel_name/123` ဖြစ်ရပါမည်။")


def source_chat_id(source: str) -> str | int:
    if source == "c":
        raise BotError("Private `t.me/c/...` link များကို username သို့မဟုတ် numeric chat ID ဖြင့် ပေးပို့ပါ။")
    return source if source.startswith("@") else f"@{source}"


def render_main(movie: MovieData, short_intro: str, drive_link: str, club_link: str) -> str:
    return (
        f"🎬 {movie.title}\n"
        f"⭐️ Rating: {movie.rating} | 🎭 Genre: {movie.genre}\n"
        "----------------------------------\n"
        "📝 အညွှန်း:\n"
        f"{short_intro}\n\n"
        f"📖 Review ဖတ်ရန် Link: {club_link}\n"
        f"▶️ ဇာတ်ကားကြည့်ရန် Link: {drive_link}\n"
        f"💡 Digital App များနှင့် Services များ ဝယ်ယူရန်: {DIGITAL_SHOP_LINK}"
    )


def render_club(movie: MovieData, review: str, drive_link: str) -> str:
    return (
        f"🍿 {movie.title} - Detailed Review\n"
        "----------------------------------\n"
        f"{review}\n"
        "----------------------------------\n"
        f"▶️ ဇာတ်ကားကြည့်ရန် Link: {drive_link}\n"
        f"💡 Digital App များနှင့် Services များ ဝယ်ယူရန်: {DIGITAL_SHOP_LINK}"
    )


def safe_caption(text: str, limit: int = 1024) -> str:
    """Keep Telegram photo captions within the Bot API limit."""
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\\n[Review shortened]"


async def fetch_omdb(title: str) -> MovieData:
    if not OMDB_API_KEY:
        raise BotError("OMDB_API_KEY မထည့်ရသေးပါ။ Render Environment Variables ကို စစ်ဆေးပါ။")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "t": title, "plot": "full"},
        )
        response.raise_for_status()
        data = response.json()
    if data.get("Response") != "True":
        raise BotError(f"OMDb တွင် `{title}` ကို မတွေ့ပါ။ Movie Name ကို ပြန်စစ်ပါ။")
    return MovieData(
        title=data.get("Title") or title,
        year=data.get("Year", "N/A"),
        rating=data.get("imdbRating", "N/A"),
        genre=data.get("Genre", "N/A"),
        plot=data.get("Plot", ""),
        director=data.get("Director", "N/A"),
        actors=data.get("Actors", "N/A"),
        runtime=data.get("Runtime", "N/A"),
    )


async def generate_copy(movie: MovieData) -> tuple[str, str]:
    if not OPENAI_API_KEY:
        raise BotError("OPENAI_API_KEY မထည့်ရသေးပါ။ Render Environment Variables ကို စစ်ဆေးပါ။")
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    prompt = f"""Movie metadata:
Title: {movie.title}
Year: {movie.year}
IMDb rating: {movie.rating}
Genre: {movie.genre}
Runtime: {movie.runtime}
Director: {movie.director}
Actors: {movie.actors}
Plot: {movie.plot}

Write content in natural Burmese. Return valid JSON with exactly two string keys:
short_intro: a spoiler-free, appealing 2-4 sentence intro for a main Telegram channel.
club_review: a detailed but readable Burmese review and analysis for a movie club, no more than about 700 Burmese characters. Discuss story, themes, acting, direction, pacing, strengths, and who may enjoy it. Do not invent facts beyond the metadata and plot, and clearly avoid major spoilers.
"""
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a careful Burmese-language movie editor. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "movie_copy",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"short_intro": {"type": "string"}, "club_review": {"type": "string"}},
                    "required": ["short_intro", "club_review"],
                    "additionalProperties": False,
                },
            },
        },
        max_tokens=2500,
    )
    import json

    content = response.choices[0].message.content
    if not content:
        raise BotError("OpenAI မှ စာသားမရရှိပါ။")
    parsed = json.loads(content)
    return parsed["short_intro"].strip(), parsed["club_review"].strip()


async def ensure_admin(update: Update) -> bool:
    if is_admin(update):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("ဤ Bot ကို Admin များသာ အသုံးပြုနိုင်ပါသည်။")
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Movie automation စတင်ပါမည်။ အရင်ဆုံး External Telegram Video Link ကို ပို့ပါ။\n"
        "ဥပမာ: https://t.me/source_channel/123"
    )
    return LINK


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update):
        return ConversationHandler.END
    try:
        source, message_id = parse_telegram_message_link(update.effective_message.text or "")
        context.user_data["source"] = source
        context.user_data["source_message_id"] = message_id
        await update.effective_message.reply_text("ကောင်းပါပြီ။ Movie Name ကို ပို့ပေးပါ။")
        return NAME
    except BotError as exc:
        await update.effective_message.reply_text(str(exc))
        return LINK


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update):
        return ConversationHandler.END
    title = (update.effective_message.text or "").strip()
    if not title:
        await update.effective_message.reply_text("Movie Name ဗလာမဖြစ်ရပါ။")
        return NAME
    await update.effective_message.reply_text("Video ကို Drive Channel သို့ ကူးနေပါသည်။ ခဏစောင့်ပါ…")
    try:
        source = context.user_data["source"]
        copied = await context.bot.copy_message(
            chat_id=DRIVE_CHANNEL_ID,
            from_chat_id=source_chat_id(source),
            message_id=context.user_data["source_message_id"],
        )
        drive_link = channel_link(DRIVE_CHANNEL_ID, copied.message_id)
        await update.effective_message.reply_text("OMDb နှင့် OpenAI data များ ပြင်ဆင်နေပါသည်…")
        movie = await fetch_omdb(title)
        short_intro, club_review = await generate_copy(movie)
        context.user_data.update({
            "movie": movie.__dict__,
            "short_intro": short_intro,
            "club_review": club_review,
            "drive_link": drive_link,
        })
        await update.effective_message.reply_text(
            "ကျေးဇူးပြု၍ မိမိအသုံးပြုလိုသော Movie Poster ဓာတ်ပုံကို ပို့ပေးပါ။"
        )
        return POSTER
    except (BotError, KeyError) as exc:
        logger.exception("Movie preparation failed")
        await update.effective_message.reply_text(f"လုပ်ဆောင်မှု မအောင်မြင်ပါ: {exc}")
        return ConversationHandler.END
    except Exception:
        logger.exception("Unexpected preparation failure")
        await update.effective_message.reply_text("လုပ်ဆောင်မှု မအောင်မြင်ပါ။ Link/permissions/API keys များကို စစ်ဆေးပါ။")
        return ConversationHandler.END


async def receive_poster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update):
        return ConversationHandler.END
    if not update.effective_message.photo:
        await update.effective_message.reply_text("Poster ကို Photo အဖြစ် ပို့ပေးပါ (Document မဟုတ်ပါ)။")
        return POSTER
    poster = update.effective_message.photo[-1]
    context.user_data["poster_file_id"] = poster.file_id
    movie = MovieData(**context.user_data["movie"])
    club_preview = render_club(movie, context.user_data["club_review"], context.user_data["drive_link"])
    main_preview = render_main(movie, context.user_data["short_intro"], context.user_data["drive_link"], "(Approve ပြီးမှ ရရှိမည်)")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve & Post All", callback_data=APPROVE)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CANCEL)],
    ])
    await update.effective_message.reply_photo(
        photo=poster.file_id,
        caption="Poster လက်ခံရရှိပါပြီ။ အောက်ပါ Preview ကို စစ်ဆေးပါ။",
    )
    await update.effective_message.reply_text(
        f"CLUB PREVIEW\n\n{club_preview}\n\nMAIN PREVIEW\n\n{main_preview}",
        reply_markup=keyboard,
    )
    return PREVIEW


async def preview_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        await query.edit_message_text(text="Admin မဟုတ်သောကြောင့် ခွင့်ပြုချက်မရှိပါ။")
        return ConversationHandler.END
    if query.data == CANCEL:
        await query.edit_message_text(text="❌ Cancel လုပ်ပြီးပါပြီ။")
        context.user_data.clear()
        return ConversationHandler.END
    try:
        movie = MovieData(**context.user_data["movie"])
        poster_id = context.user_data["poster_file_id"]
        club_text = render_club(movie, context.user_data["club_review"], context.user_data["drive_link"])
        club_message = await context.bot.send_photo(
            chat_id=CLUB_CHANNEL_ID,
            photo=poster_id,
            caption=safe_caption(club_text),
        )
        club_link = channel_link(CLUB_CHANNEL_ID, club_message.message_id)
        main_text = render_main(movie, context.user_data["short_intro"], context.user_data["drive_link"], club_link)
        await context.bot.send_photo(chat_id=MAIN_CHANNEL_ID, photo=poster_id, caption=safe_caption(main_text))
        await query.edit_message_text(text=f"✅ အားလုံး Post လုပ်ပြီးပါပြီ။\nClub Link: {club_link}")
        context.user_data.clear()
        return ConversationHandler.END
    except Exception:
        logger.exception("Publishing failed")
        await query.edit_message_text(text="❌ Post မအောင်မြင်ပါ။ Bot ၏ channel admin permissions နှင့် link များကို စစ်ဆေးပါ။")
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message:
        await update.effective_message.reply_text("❌ Cancel လုပ်ပြီးပါပြီ။")
    context.user_data.clear()
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled Telegram error: %s", context.error, exc_info=context.error)


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    application = Application.builder().token(BOT_TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("new", start)],
        states={
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            POSTER: [MessageHandler(filters.PHOTO, receive_poster)],
            PREVIEW: [CallbackQueryHandler(preview_action, pattern=f"^({APPROVE}|{CANCEL})$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    application.add_handler(conversation)
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS must contain at least one numeric Telegram user ID")
    app = build_application()
    if RENDER_EXTERNAL_URL:
        webhook_path = os.environ.get("WEBHOOK_PATH", "telegram-webhook")
        webhook_url = f"{RENDER_EXTERNAL_URL}/{webhook_path}"
        logger.info("Starting webhook server at %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET or None,
            drop_pending_updates=True,
        )
    else:
        logger.info("Starting local polling mode")
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
