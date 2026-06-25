import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, FloodPattern, RetryAfter
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from scraper import get_new_jobs, get_all_jobs, save_subscriber, load_subscribers, count_subscribers, remove_subscriber
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store all user chat ids locally for quick in-memory lookups
subscribers = load_subscribers()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Check if they are already subbed to prevent spamming welcome msgs
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscriber(chat_id) 
        
    await update.message.reply_text(
        "Welcome to HiringRadar! 🚀\n\n"
        "You'll get real-time alerts the millisecond new jobs or internships "
        "open up at top Indian product companies (Razorpay, CRED, Groww, PhonePe)."
    )
   
    await update.message.reply_text("Checking current live roles for you, hold on...")
    
    # Optimization: To avoid blocking the bot, grab the list but don't flood chat.
    # Production note: In the future, read these from your DB instead of hitting live APIs here!
    jobs = get_all_jobs()
    if jobs:
        # Show only the top 5 most recent openings to prevent spamming the user
        recent_jobs = jobs[:5]
        for job in recent_jobs:
            keyboard = [[InlineKeyboardButton("⚡ Apply Directly", url=job['url'])]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                f"🏢 **Company:** {job['company']}\n"
                f"💼 **Role:** {job['title']}\n"
                f"📍 **Location:** {job['location']}"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            await asyncio.sleep(0.1) # Small pause between individual messages
    else:
        await update.message.reply_text("No open roles tracked right now. You're locked in for the next alert drop!")

async def send_alerts(context: ContextTypes.DEFAULT_TYPE):
    """
    Periodic job loop. Scrapes targets and broadcasts new openings
    safely while strictly observing Telegram flood restrictions.
    """
    new_jobs = get_new_jobs()
    if not new_jobs:
        return

    for job in new_jobs:
        keyboard = [[InlineKeyboardButton("⚡ Apply Now", url=job['url'])]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"🚨 **New Opening Detected!**\n\n"
            f"🏢 **Company:** {job['company']}\n"
            f"💼 **Role:** {job['title']}\n"
            f"📍 **Location:** {job['location']}"
        )
        
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=message, 
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
                # CRITICAL: Sleep for 50ms between users to strictly enforce 
                # Telegram's maximum 30 messages/sec limit across channels.
                await asyncio.sleep(0.05)
                
            except Forbidden:
                subscribers.discard(chat_id)
                remove_subscriber(chat_id)
                print(f"Purged blocked user: {chat_id}")
            except RetryAfter as e:
                # Catch severe rate limits dynamically and wait it out
                print(f"Rate limited. Sleeping for {e.retry_after} seconds")
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                print(f"Could not send alert to user {chat_id}: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = count_subscribers()
    await update.message.reply_text(f"🎯 HiringRadar is actively tracking roles for {count} candidates.")

if __name__ == "__main__":
    # Initialize the core app framework
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    
    # Trigger job loop checker every 15 minutes (900s) instead of an hour (3600s)
    # 1 hour is too long for Indian tech openings; they fill up way faster!
    app.job_queue.run_repeating(send_alerts, interval=900, first=10)
    
    print("🚀 HiringRadar backend engine online and scanning...")
    app.run_polling()
