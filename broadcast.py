import os
import sys
import asyncio
from telegram import Bot
from telegram.error import Forbidden, RetryAfter
from dotenv import load_dotenv

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))

MESSAGE = """
🚀 *HiringRadar just got a big upgrade!*

Here's what's new for you:

🎯 *Match score* — every job now shows how well it fits your profile _(e.g. 84%)_
💡 *Why it matched* — a short reason with every job card
✏️ *Edit your profile anytime:*
  `/skills` Python, ML, SQL
  `/roles` backend, ml
  `/experience` internship / fulltime / both
⏸️ `/pause` and ▶️ `/resume` — control when you get alerts
👍 *Thumbs up / down* on job cards — help us send better matches

Type /profile to see your updated profile and all commands!
"""

async def broadcast():
    if "--all" not in sys.argv:
        # Test mode — reads ADMIN_CHAT_ID from .env automatically
        admin_id = os.getenv("ADMIN_CHAT_ID")
        if not admin_id:
            print("No ADMIN_CHAT_ID in .env. Run with your chat ID:")
            print("  python broadcast.py 123456789")
            return
        print("Test mode - sending only to you (ADMIN_CHAT_ID).\n")
        await bot.send_message(chat_id=int(admin_id), text=MESSAGE, parse_mode="Markdown")
        print("Sent! Check your Telegram.")
        print("\nHappy with it? Run on your server:  python broadcast.py --all")
        return

    # Full broadcast — only now do we need Supabase
    from supabase import create_client
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    students = supabase.table("students").select("chat_id, name").execute().data
    total = len(students)
    sent, failed = 0, 0

    print(f"Broadcasting to {total} users...\n")

    for s in students:
        try:
            await bot.send_message(chat_id=s["chat_id"], text=MESSAGE, parse_mode="Markdown")
            sent += 1
            print(f"  Sent to {s.get('name', s['chat_id'])}")
            await asyncio.sleep(0.1)
        except Forbidden:
            failed += 1
            print(f"  {s['chat_id']} has blocked the bot")
        except RetryAfter as e:
            print(f"  Rate limited - waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id=s["chat_id"], text=MESSAGE, parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  Failed {s['chat_id']}: {e}")

    print(f"\nDone! Sent: {sent} | Failed: {failed} | Total: {total}")

if __name__ == "__main__":
    asyncio.run(broadcast())
