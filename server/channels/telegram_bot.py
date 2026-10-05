import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
from server.config import config
from server.agent.core import agent
from server.selfmod.approvals import approvals
from server.services.error_logger import error_logger

# Set up logging for telegram bot
logging.getLogger("httpx").setLevel(logging.WARNING)

SESSION_ID = "default"
_app: Application | None = None  # set once the bot is running, so other parts of MIA can message the owner

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    if not _is_allowed(update):
        return
    await update.message.reply_text("🤖 MIA is online and ready for commands.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and pass them to the MIA AI agent."""
    if not _is_allowed(update):
        return

    user_text = update.message.text

    # Send a typing indicator while the agent processes
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        await _run_agent_and_reply(context, update.effective_chat.id, user_text, SESSION_ID)
    except Exception as e:
        friendly_error = error_logger.log_error(e, context="Telegram Bot")
        await update.message.reply_text(f"❌ Error: {friendly_error}")

async def pending_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pending — re-send every action still waiting for approval."""
    if not _is_allowed(update):
        return
    pending = approvals.pending()
    if not pending:
        await update.message.reply_text("✅ Nothing is waiting for approval.")
        return
    for request in pending:
        await _send_approval_request(context, update.effective_chat.id, request)

async def handle_approval_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve/Reject button pressed on an approval request."""
    query = update.callback_query
    if not _is_allowed(update):
        await query.answer("Not allowed.")
        return
    await query.answer()

    _, request_id, decision = query.data.split(":", 2)
    outcome = approvals.resolve(request_id, decision == "yes", via="telegram")
    request = outcome["request"]
    status = {"done": "✅ Approved and done", "failed": "⚠️ Approved, but it failed",
              "rejected": "❌ Rejected"}.get(request["status"] if request else "", "ℹ️")
    await query.edit_message_text(f"{query.message.text}\n\n{status}: {outcome['result']}"[:4000])

    if outcome["handled_now"]:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action='typing')
        await _run_agent_and_reply(context, query.message.chat_id, approvals.followup_message(request), request["session_id"])

async def _run_agent_and_reply(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message: str, session_id: str) -> None:
    """Run the agent, send its reply, then any approval requests it raised."""
    response = "Done."
    requests = []
    async for event in agent.stream_chat(message, session_id):
        if event["type"] == "done":
            response = event["message"]
        elif event["type"] == "error":
            response = f"❌ {event['message']}"
        elif event["type"] == "approval_request":
            requests.append(event["request"])

    # Telegram has a 4096 char limit, chunk if necessary
    for i in range(0, len(response), 4000):
        await context.bot.send_message(chat_id=chat_id, text=response[i:i+4000])
    for request in requests:
        await _send_approval_request(context, chat_id, request)

async def _send_approval_request(context: ContextTypes.DEFAULT_TYPE, chat_id: int, request: dict) -> None:
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approval:{request['id']}:yes"),
        InlineKeyboardButton("❌ Reject", callback_data=f"approval:{request['id']}:no"),
    ]])
    await context.bot.send_message(chat_id=chat_id, text=approvals.format_text(request), reply_markup=buttons)

async def send_to_owner(text: str, approval_requests: list = ()) -> bool:
    """Proactively message the allowed Telegram user (scheduled results, heartbeat alerts)."""
    if _app is None or not config.ALLOWED_TELEGRAM_USER_ID:
        return False
    chat_id = int(config.ALLOWED_TELEGRAM_USER_ID)
    for i in range(0, len(text), 4000):
        await _app.bot.send_message(chat_id=chat_id, text=text[i:i+4000])

    class _Ctx:  # _send_approval_request only needs .bot
        bot = _app.bot
    for request in approval_requests:
        await _send_approval_request(_Ctx, chat_id, request)
    return True

def _is_allowed(update: Update) -> bool:
    """Check if the user is authorized to use this bot."""
    if not config.TELEGRAM_BOT_TOKEN or not config.ALLOWED_TELEGRAM_USER_ID:
        return False
    user_id = str(update.effective_user.id)
    return user_id == str(config.ALLOWED_TELEGRAM_USER_ID)

async def start_telegram_bot():
    """Start the Telegram bot loop in the background."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("⚠️ Telegram bot token not configured. Skipping Telegram channel.")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending", pending_approvals))
    app.add_handler(CallbackQueryHandler(handle_approval_button, pattern=r"^approval:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Starting Telegram Bot Channel...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    global _app
    _app = app

    # Run forever
    while True:
        await asyncio.sleep(3600)
