import os
import asyncio
import logging
from fastapi import FastAPI
import uvicorn
from bot import create_app

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Prevent logging of HEAD / requests to avoid log spam
        if record.args and len(record.args) >= 3:
            method = record.args[1]
            path = record.args[2]
            if method == "HEAD" and path == "/":
                return False
        
        # Fallback check on formatted message
        message = record.getMessage()
        if "HEAD / " in message:
            return False
        return True

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
    # Filter out HEAD / HTTP/1.1 logs from uvicorn.access
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    # Start the Telegram bot in a background task
    asyncio.create_task(run_telegram_bot())

if __name__ == "__main__":
    # Hugging Face Spaces always expose port 7860
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
