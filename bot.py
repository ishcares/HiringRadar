import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from scraper import get_new_jobs
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# store all user chat ids
subscribers = set()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    await update.message.reply_text("Welcome to HiringRadar! You'll get alerts when new jobs are posted at top Indian product companies 🚀")

async def send_alerts(context):
    jobs = get_new_jobs()
    for job in jobs:
        message = f"🆕 {job['company']} - {job['title']}\n📍 {job['location']}\n🔗 {job['url']}"
        for chat_id in subscribers:
            await context.bot.send_message(chat_id=chat_id, text=message)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_repeating(send_alerts, interval=14400, first=10)
    app.run_polling()