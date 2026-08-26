import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from server.config import config
from server.agent.core import agent
from server.services.error_logger import error_logger

# Set up logging for telegram bot
logging.getLogger("httpx").setLevel(logging.WARNING)

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
        # Call the existing AI core
        response = await agent.chat(user_text)
        
        # Telegram has a 4096 char limit, chunk if necessary
        for i in range(0, len(response), 4000):
            await update.message.reply_text(response[i:i+4000])
            
    except Exception as e:
        friendly_error = error_logger.log_error(e, context="Telegram Bot")
        await update.message.reply_text(f"❌ Error: {friendly_error}")

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Starting Telegram Bot Channel...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Run forever
    while True:
        await asyncio.sleep(3600)
