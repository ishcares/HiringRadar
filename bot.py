import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden,  RetryAfter
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
        "👋 Welcome to *HiringRadar*!\n\n"
        "Whether you're a fresher hunting your first product role, or an experienced "
        "engineer looking to switch — you'll get alerts the moment new openings drop "
        "at top Indian product companies like Razorpay, CRED, Groww, Meesho, PhonePe, Rubrik and more.\n\n"
        "⚡ We check every 5 minutes. LinkedIn finds out hours later.",
        parse_mode="Markdown"
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
    Periodic job loop. Scrapes for new openings and sends each subscriber
    digest message(s) — chunked to stay under Telegram's 4096-char limit.
    """
    new_jobs = get_new_jobs()
    if not new_jobs:
        return

    # --- Build individual job lines ---
    total = len(new_jobs)
    job_lines = []
    for job in new_jobs:
        job_lines.append(
            f"🏢 *{job['company']}*\n"
            f"💼 {job['title']}\n"
            f"📍 {job['location']}\n"
            f"[→ Apply Now]({job['url']})"
        )

    # --- Pack lines into chunks under Telegram's 4096-char limit ---
    TELEGRAM_LIMIT = 4000  # safe margin below 4096
    chunks = []
    current_chunk = []
    current_len = 0

    for line in job_lines:
        # +2 for the "\n\n" separator between entries
        if current_len + len(line) + 2 > TELEGRAM_LIMIT and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0
        current_chunk.append(line)
        current_len += len(line) + 2

    if current_chunk:
        chunks.append(current_chunk)

    # --- Broadcast each chunk to every subscriber ---
    for chat_id in list(subscribers):
        try:
            for i, chunk in enumerate(chunks):
                part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n"
                header += "━━━━━━━━━━━━━━━━━━━━━\n"
                digest = header + "\n\n".join(chunk)
                digest += "\n\n━━━━━━━━━━━━━━━━━━━━━"

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=digest,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                await asyncio.sleep(0.1)

        except Forbidden:
            subscribers.discard(chat_id)
            remove_subscriber(chat_id)
        except RetryAfter as e:
            print(f"Rate limited — backing off for {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            print(f"Failed to send digest to {chat_id}: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = count_subscribers()
    await update.message.reply_text(f"🎯 HiringRadar is actively tracking roles for {count} candidates.")

if __name__ == "__main__":
    # Initialize the core app framework
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    
    # Poll every 5 minutes — beats LinkedIn's hours-long indexing delay
    app.job_queue.run_repeating(send_alerts, interval=300, first=10)
    
    print("🚀 HiringRadar backend engine online and scanning...")
    app.run_polling()
