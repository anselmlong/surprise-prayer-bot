"""Surprise Prayer Bot — anonymous prayer pairing and messaging."""
from __future__ import annotations

import logging
from datetime import time, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Config
from .storage import Storage

log = logging.getLogger(__name__)

# In-memory: user_id -> awaiting message for send
_awaiting_send: set[int] = set()


def build_application(config: Config, storage: Storage) -> Application:
    app = Application.builder().token(config.telegram_bot_token).build()
    app.bot_data["config"] = config
    app.bot_data["storage"] = storage
    app.bot_data["startup_time"] = None  # set in main()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("leave", cmd_leave))
    app.add_handler(CommandHandler(["match", "myperson"], cmd_match))
    app.add_handler(CommandHandler("send", cmd_send))
    # Catch text messages for the send flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Weekly reshuffle + reminder every Monday 0000 SGT = 1600 UTC Sunday
    app.job_queue.run_daily(
        weekly_reminder,
        time=time(hour=16, minute=0, tzinfo=timezone.utc),
        days=(0,),  # Monday
        name="weekly-reshuffle",
    )

    return app


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    user = update.effective_user
    if not user:
        return

    joined = storage.join_pool(user.id, user.username or "", user.full_name)
    if joined:
        await update.effective_message.reply_text(
            "🙏 welcome! you're in the prayer pool.\n\n"
            "• /match — get assigned someone to pray for\n"
            "• /send — send them an anonymous message\n"
            "• /leave — leave the pool\n"
            "• /help — show this again"
        )
    else:
        await update.effective_message.reply_text(
            "you're already in the pool! 🙏\n\n"
            "• /match — get assigned someone to pray for\n"
            "• /send — send them an anonymous message"
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🙏 surprise prayer bot\n\n"
        "i pair you with someone in the pool anonymously. "
        "you pray for them, and you can send them an encouraging message "
        "through me — they won't know it's you.\n\n"
        "• /start — join the prayer pool\n"
        "• /match — get assigned someone to pray for\n"
        "• /send — send an anonymous message to your person\n"
        "• /leave — leave the pool\n\n"
        "pairings reshuffle every monday 🙌"
    )


async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    user = update.effective_user
    if not user:
        return

    if storage.leave_pool(user.id):
        await update.effective_message.reply_text(
            "you've left the prayer pool. "
            "if you ever want back in, just /start again 🙏"
        )
    else:
        await update.effective_message.reply_text(
            "you weren't in the pool. use /start to join!"
        )


async def cmd_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    user = update.effective_user
    if not user:
        return

    if not storage.is_in_pool(user.id):
        await update.effective_message.reply_text(
            "you're not in the pool! use /start to join 🙏"
        )
        return

    pool_size = storage.get_pool_size()
    if pool_size < 2:
        await update.effective_message.reply_text(
            "need at least 2 people in the pool to pair up! "
            "invite your friends 🙏"
        )
        return

    prayee_id = storage.assign_prayee(user.id)
    if prayee_id is None:
        await update.effective_message.reply_text(
            "couldn't find anyone to pair you with right now. "
            "try again later — maybe more people will join! 🙏"
        )
        return

    prayee = storage.get_user(prayee_id)
    name = prayee.display_name if prayee else "someone"
    await update.effective_message.reply_text(
        f"🙏 you're praying for **{name}**! "
        f"take a moment to lift them up.\n\n"
        f"you can send them an encouraging message with /send",
    )


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.bot_data["storage"]
    user = update.effective_user
    if not user:
        return

    if not storage.is_in_pool(user.id):
        await update.effective_message.reply_text(
            "you're not in the pool! use /start to join 🙏"
        )
        return

    pairing = storage.get_pairing(user.id)
    if pairing is None:
        await update.effective_message.reply_text(
            "you haven't been assigned someone yet! use /match first 🙏"
        )
        return

    _awaiting_send.add(user.id)
    await update.effective_message.reply_text(
        "what do you want to send? just type it as a reply to this message 🙏"
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages — used for the send flow."""
    user = update.effective_user
    if not user or user.id not in _awaiting_send:
        return

    _awaiting_send.discard(user.id)

    storage: Storage = context.bot_data["storage"]
    pairing = storage.get_pairing(user.id)
    if pairing is None:
        await update.effective_message.reply_text(
            "your pairing expired while you were typing. try /match again 🙏"
        )
        return

    message = update.effective_message.text
    if not message:
        return

    try:
        await context.bot.send_message(
            chat_id=pairing.prayee_id,
            text=f"📬 someone is praying for you! 🙏\n\n"
                 f"they sent:\n"
                 f"\"{message}\"\n\n"
                 f"keep praying, keep going 🙌",
        )
        await update.effective_message.reply_text(
            "message sent! your person will receive it anonymously 🙏"
        )
    except Exception as exc:
        log.warning("failed to send message to %d: %s", pairing.prayee_id, exc)
        await update.effective_message.reply_text(
            "couldn't deliver the message. maybe they've left the pool? 😅"
        )


async def weekly_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reshuffle pairings and remind everyone to pray."""
    storage: Storage = context.bot_data["storage"]
    storage.reshuffle()

    members = storage.get_all_pool_members()
    for member in members:
        try:
            await context.bot.send_message(
                chat_id=member.user_id,
                text="🙏 new week, new person! use /match to get "
                     "assigned someone to pray for this week.\n\n"
                     "and don't forget to send them an encouraging "
                     "message with /send 💌",
            )
        except Exception as exc:
            log.warning("failed to remind %d: %s", member.user_id, exc)