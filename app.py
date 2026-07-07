import os
import asyncio
from fastapi import FastAPI
import uvicorn
from bot import ApplicationBuilder, conv_handler, profile, jobs, stats, update_skills, update_roles, update_experience, pause_alerts, resume_alerts, feedback_handler, send_alerts, on_startup, CallbackQueryHandler, CommandHandler
from telegram.ext import MessageHandler, filters

app = FastAPI()

@app.get("/")
def home():
    return {"status": "HiringRadar Bot is active and running!"}

async def run_telegram_bot():
    """Runs the Telegram Bot alongside the FastAPI web server."""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN environment variable not set!")
        return

    # Build the application exactly like bot.py does
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    # Add all handlers from bot.py
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("jobs", jobs))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("skills", update_skills))
    application.add_handler(CommandHandler("roles", update_roles))
    application.add_handler(CommandHandler("experience", update_experience))
    application.add_handler(CommandHandler("pause", pause_alerts))
    application.add_handler(CommandHandler("resume", resume_alerts))
    application.add_handler(CallbackQueryHandler(feedback_handler, pattern="^feedback:"))
    
    # Run the background job queue (scrapes every 5 mins)
    application.job_queue.run_repeating(send_alerts, interval=300, first=10)

    print("🚀 Starting Telegram Bot polling...")
    
    # Initialize and start polling asynchronously
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        print("Stopping bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

@app.on_event("startup")
async def startup_event():
    # Start the Telegram bot in a background task
    asyncio.create_task(run_telegram_bot())

if __name__ == "__main__":
    # Hugging Face Spaces always expose port 7860
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
