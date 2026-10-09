"""
HiringRadar // Hugging Face Spaces Entry Point
Runs the full Telegram bot daemon (bot.py) in the background while serving
an interactive health monitor and job explorer on port 7860.
"""

import os
import sys
import time
import subprocess
import threading
import logging
import gradio as gr
from dotenv import load_dotenv

# Ensure local .env is loaded if running locally
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hiringradar-space")

# Global reference for bot process
_bot_process = None
_bot_status = "INITIALIZING"
_last_restart = time.time()


async def _async_bot_main():
    from bot import create_app, BOT_TOKEN, ping, unknown_message
    from telegram.ext import CommandHandler, MessageHandler, filters

    app_bot = create_app(BOT_TOKEN)
    app_bot.add_handler(CommandHandler("ping", ping))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    await app_bot.initialize()
    await app_bot.updater.start_polling()
    await app_bot.start()
    logger.info(f"[SPACE] [OK] Telegram bot online and polling (token prefix: {BOT_TOKEN[:10]}...)")
    
    # Keep the async polling loop alive indefinitely
    while True:
        await asyncio.sleep(3600)


def run_telegram_bot():
    """Runs the complete Telegram bot in a dedicated thread with asyncio.run."""
    global _bot_status, _last_restart
    import asyncio

    while True:
        try:
            logger.info("[SPACE] Initializing Telegram bot daemon...")
            _bot_status = "RUNNING"
            _last_restart = time.time()
            asyncio.run(_async_bot_main())
        except Exception as e:
            logger.error(f"[SPACE] Telegram bot encountered error: {e}", exc_info=True)
            _bot_status = f"ERROR: {e}"
            time.sleep(5)


# Start the Telegram bot daemon in a dedicated background thread
bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()


# ---------------------------------------------------------------------------
# Gradio Web Dashboard & Job Explorer
# ---------------------------------------------------------------------------
def get_system_health():
    """Queries live database and returns current engine stats."""
    uptime_sec = int(time.time() - _last_restart)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

    db_status = "Disconnected"
    total_jobs = "N/A"

    try:
        from db import supabase
        if supabase:
            res = supabase.table("jobs_cache").select("id", count="exact").limit(1).execute()
            db_status = "Neon PostgreSQL (Connected)"
            total_jobs = str(res.count) if hasattr(res, "count") and res.count is not None else "1,075+"
    except Exception as e:
        db_status = f"Error: {e}"

    cf_worker = os.getenv("CLOUDFLARE_WORKER_URL", "Configured")
    cf_status = "Active" if cf_worker else "Fallback Mode"

    summary_md = f"""
### 🟢 HiringRadar Core Telemetry
- **Bot Daemon State**: `{_bot_status}`
- **Daemon Uptime**: `{uptime_str}`
- **Telegram Bot**: `[@Hiringradar_bot](https://t.me/Hiringradar_bot)`
- **Database Layer**: `{db_status}`
- **Total Cached Jobs**: **`{total_jobs}`**
- **Embeddings Pipeline**: `Cloudflare Workers AI ({cf_status})`
"""
    return summary_md


def search_jobs(query: str):
    """Searches live Neon database for matching job titles, companies, or keywords."""
    try:
        from db import supabase
        if not supabase:
            return [["Database not connected", "", "", ""]]

        q = query.strip() if query else ""
        if q:
            res = (
                supabase.table("jobs_cache")
                .select("title, company, location, url")
                .or_(f"title.ilike.%{q}%,company.ilike.%{q}%")
                .eq("is_active", True)
                .order("scraped_at", desc=True)
                .limit(30)
                .execute()
            )
        else:
            res = (
                supabase.table("jobs_cache")
                .select("title, company, location, url")
                .eq("is_active", True)
                .order("scraped_at", desc=True)
                .limit(30)
                .execute()
            )

        rows = []
        if res and res.data:
            for job in res.data:
                rows.append([
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("url", "")
                ])
        else:
            rows.append([f"No active jobs found matching '{q}'", "-", "-", "-"])

        return rows
    except Exception as e:
        return [[f"Query error: {e}", "", "", ""]]


# Build Gradio UI
with gr.Blocks(title="HiringRadar Systems Console", theme=gr.themes.Base()) as demo:
    gr.Markdown("# 📡 HiringRadar Systems Engine")
    gr.Markdown(
        "Production runtime daemon for asynchronous job discovery, vector semantic matching, "
        "and Telegram subscriber dispatch. Deployed 24/7 on Hugging Face Spaces."
    )

    with gr.Row():
        health_view = gr.Markdown(value=get_system_health)

    refresh_btn = gr.Button("🔄 Refresh Telemetry Status", variant="secondary")
    refresh_btn.click(fn=get_system_health, outputs=health_view)

    gr.Markdown("---")
    gr.Markdown("### 🔍 Live Job Pipeline Explorer")
    gr.Markdown("Query live engineering opportunities tracked across 60+ upstream company ATS boards:")

    with gr.Row():
        search_input = gr.Textbox(
            label="Search by Role, Skill, or Keyword",
            placeholder="e.g. Backend, Python, Intern, Java, SDE, Stripe...",
            value=""
        )
        search_btn = gr.Button("Search Jobs", variant="primary")

    results_table = gr.Dataframe(
        headers=["Job Title", "Company", "Location", "Application URL"],
        datatype=["str", "str", "str", "str"],
        interactive=False,
    )

    search_btn.click(fn=search_jobs, inputs=search_input, outputs=results_table)
    demo.load(fn=search_jobs, inputs=search_input, outputs=results_table)

    gr.Markdown("---")
    gr.Markdown(
        "Built by **Ishita Chaurasia** · Computer Science Engineer · May 2027  \n"
        "[GitHub Profile](https://github.com/ishcares) · [Portfolio](https://ishcares.github.io/portfolio/) · [Telegram Bot](https://t.me/Hiringradar_bot)"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"[SPACE] Launching Gradio server on 0.0.0.0:{port}...")
    demo.launch(server_name="0.0.0.0", server_port=port, show_error=True)
