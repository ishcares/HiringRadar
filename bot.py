import os
import asyncio
from telegram import Update
from telegram.error import Forbidden
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from scraper import get_new_jobs, get_all_jobs, save_subscriber, load_subscribers, count_subscribers, remove_subscriber
from dotenv import load_dotenv



load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# store all user chat ids
subscribers = load_subscribers()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    save_subscriber(chat_id) # save to database
    await update.message.reply_text("Welcome to HiringRadar! You'll get alerts when new jobs are posted at top Indian product companies 🚀")
   
   #send current open roles immediately
    
    jobs = get_all_jobs()
    if jobs:
        await update.message.reply_text("here are the latesr open roles right now:")
        for job in jobs:
            message = f"🆕 {job['company']} - {job['title']}\n📍 {job['location']}\n🔗 {job['url']}"
            await context.bot.send_message(chat_id=chat_id,text=message)
    else:
     await update.message.reply_text("No open roles right now. you'll be notified as soon as something new is posted!")

async def send_alerts(context):
    jobs = get_new_jobs()
    for job in jobs:
        message = f"🆕 {job['company']} - {job['title']}\n📍 {job['location']}\n🔗 {job['url']}"
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=message)
            except Forbidden:
                subscribers.discard(chat_id)
                remove_subscriber(chat_id)
                print(f"Removed blocked user {chat_id}")
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = count_subscribers()
    await update.message.reply_text(f"HiringRadar has {count} subscribers 🎯")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_repeating(send_alerts, interval=3600, first=10)
    app.add_handler(CommandHandler("stats", stats))
    app.run_polling()