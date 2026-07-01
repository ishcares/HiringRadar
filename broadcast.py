import os
import asyncio
from telegram import Bot
from telegram.error import Forbidden, RetryAfter
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

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
    students = supabase.table("students").select("chat_id, name").execute().data
    total = len(students)
    sent, failed = 0, 0

    print(f"📢 Broadcasting to {total} users...\n")

    for s in students:
        try:
            await bot.send_message(
                chat_id=s["chat_id"],
                text=MESSAGE,
                parse_mode="Markdown"
            )
            sent += 1
            print(f"  ✅ Sent to {s.get('name', s['chat_id'])}")
            await asyncio.sleep(0.1)
        except Forbidden:
            failed += 1
            print(f"  ⚠️  {s['chat_id']} has blocked the bot")
        except RetryAfter as e:
            print(f"  ⏳ Rate limited — waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id=s["chat_id"], text=MESSAGE, parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ Failed {s['chat_id']}: {e}")

    print(f"\n🎉 Done! Sent: {sent} | Failed: {failed} | Total: {total}")

if __name__ == "__main__":
    asyncio.run(broadcast())
