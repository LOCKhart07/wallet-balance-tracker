import logging
import os
import threading
import time

import schedule
from telegram import BotCommand, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from wallet_monitor import run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

DAILY_RUN_TIME = "01:28"


# --- Job runner ---
def job_wrapper():
    logger.info("Starting daily run...")
    run()
    logger.info("Run complete ✅")


def setup_scheduler():
    logger.info("Scheduler started. Waiting for next run...")
    schedule.every().day.at(DAILY_RUN_TIME).do(job_wrapper)
    while True:
        schedule.run_pending()
        time.sleep(30)


async def wallet_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When user sends /status, run() executes immediately."""
    logger.info("Received /status command.")
    await update.message.reply_text("⏳ Running now...")
    try:
        run(give_request_format=True)
        await update.message.reply_text("✅ Run completed successfully.")
    except Exception as e:
        logger.exception("Error while running task via /status")
        await update.message.reply_text(f"❌ Error: {e}")


async def set_bot_commands(application: Application):
    commands = [
        BotCommand("status", "Run the wallet monitor now"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    # Run scheduler in background thread
    t = threading.Thread(target=setup_scheduler, daemon=True)
    t.start()

    # Start Telegram bot
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("status", wallet_status_command))
    application.post_init = set_bot_commands

    # Start the bot (blocking)
    logger.info("Bot started. Listening for commands...")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
