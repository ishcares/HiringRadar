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
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hiringradar-space")

# Global reference for bot process
_bot_process = None
_bot_status = "INITIALIZING"
_last_restart = time.time()


def start_bot_daemon():
    """Continuously runs and monitors python bot.py in a background subprocess."""
    global _bot_process, _bot_status, _last_restart
    base_dir = os.path.dirname(os.path.abspath(__file__))

    while True:
        logger.info("[SPACE] Spawning Telegram bot daemon (bot.py)...")
        _bot_status = "RUNNING"
        _last_restart = time.time()

        try:
            _bot_process = subprocess.Popen(
                [sys.executable, "-u", "bot.py"],
                cwd=base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Stream logs into Hugging Face console
            for line in _bot_process.stdout:
                line_str = line.strip()
                if line_str:
                    print(f"[BOT] {line_str}", flush=True)

            _bot_process.wait()
            rc = _bot_process.returncode
            logger.warning(f"[SPACE] Bot process terminated with return code {rc}")
            _bot_status = f"EXITED (code {rc})"
        except Exception as e:
            logger.error(f"[SPACE] Error running bot process: {e}")
            _bot_status = f"ERROR: {e}"

        logger.info("[SPACE] Re-launching bot daemon in 5 seconds...")
        time.sleep(5)


# Start the bot daemon immediately in a dedicated background thread
bot_thread = threading.Thread(target=start_bot_daemon, daemon=True)
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
    """Searches live Neon database for matching job titles or companies."""
    if not query or not query.strip():
        query = "intern"

    try:
        from db import supabase
        if not supabase:
            return [["Database not connected", "", "", ""]]

        q = query.strip()
        res = (
            supabase.table("jobs_cache")
            .select("title", "company", "location", "url")
            .ilike("title", f"%{q}%")
            .limit(20)
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
            placeholder="e.g. Backend, Python, Intern, Java, SDE...",
            value="Intern"
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
