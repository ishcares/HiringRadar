import os
import asyncio
from fastapi import FastAPI
import uvicorn
from bot import create_app

app = FastAPI()

@app.get("/")
@app.head("/")
def home():
    return {"status": "HiringRadar Bot is active and running!"}

async def run_telegram_bot():
    """Runs the Telegram Bot alongside the FastAPI web server."""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN environment variable not set!")
        return

    # Build the application using the creator function from bot.py
    application = create_app(BOT_TOKEN)

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
