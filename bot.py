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

def group_jobs(jobs):
    """
    Collapses duplicate title+company+location entries into one card
    showing '(N openings)' — keeps the first URL as the apply link.
    """
    seen = {}
    for job in jobs:
        key = (job['company'], job['title'].strip(), job['location'])
        if key not in seen:
            seen[key] = {**job, 'count': 1}
        else:
            seen[key]['count'] += 1
    return list(seen.values())

def get_experience_tag(title):
    """Infers experience level from job title for quick visual filtering."""
    t = title.lower()
    if any(k in t for k in ["intern", "internship", "trainee", "campus", "fresher", "new grad", "graduate engineer"]):
        return "🌱 Fresher / Intern"
    if any(k in t for k in ["director", "vp ", "vice president", "head of", "chief"]):
        return "👑 Director / VP"
    if any(k in t for k in ["engineering manager", "tech lead", "team lead", "group product"]):
        return "🏆 Manager / Lead"
    if any(k in t for k in ["principal", "staff", "architect", "sde-3", "sde iii", "sde3"]):
        return "⚡ Staff / Principal"
    if any(k in t for k in ["senior", "sr.", "sde-2", "sde ii", "sde2", "ii "]):
        return "🚀 Senior (5+ yrs)"
    if any(k in t for k in ["junior", "jr.", "sde-1", "sde i ", "sde1", "associate engineer"]):
        return "🔵 Junior (0-2 yrs)"
    return "💼 Mid-level (2-5 yrs)"

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
    
    jobs = get_all_jobs()
    if jobs:
        # Group duplicate title+company entries, then show top 5
        grouped = group_jobs(jobs)
        preview = grouped[:5]
        lines = []
        for job in preview:
            count_label = f" _({job['count']} openings)_" if job['count'] > 1 else ""
            lines.append(
                f"🏢 *{job['company']}*\n"
                f"💼 {job['title']}{count_label}\n"
                f"🏷️ *Experience:* {get_experience_tag(job['title'])}\n"
                f"📍 {job['location']}\n"
                f"[→ Apply Now]({job['url']})"
            )
        digest = f"*Here are {len(preview)} live roles right now:*\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines)
        await update.message.reply_text(
            digest,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
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

    # --- Group duplicates, then build individual job lines ---
    grouped_jobs = group_jobs(new_jobs)
    total = len(new_jobs)  # raw count for the header (e.g. "8 New Openings")
    job_lines = []
    for job in grouped_jobs:
        count_label = f" _({job['count']} openings)_" if job['count'] > 1 else ""
        job_lines.append(
            f"🏢 *{job['company']}*\n"
            f"💼 {job['title']}{count_label}\n"
            f"🏷️ *Experience:* {get_experience_tag(job['title'])}\n"
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
