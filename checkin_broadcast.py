import os
import sys
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = input("Enter your Telegram BOT_TOKEN: ").strip()

bot = Bot(token=BOT_TOKEN)

MESSAGE = "👋 Quick check-in from *HiringRadar*.\n\nWe want to make sure you're still getting relevant alerts. Are you still actively job hunting?"

# Inline Keyboard Buttons
buttons = [
    [
        InlineKeyboardButton("✅ Yes, still looking", callback_data="checkin:active"),
        InlineKeyboardButton("❌ Not right now", callback_data="checkin:inactive")
    ]
]
keyboard = InlineKeyboardMarkup(buttons)

async def checkin_broadcast():
    if "--all" not in sys.argv:
        # Test mode — sends only to the ADMIN_CHAT_ID
        admin_id = os.getenv("ADMIN_CHAT_ID")
        if not admin_id:
            admin_id = input("Enter your Telegram ADMIN_CHAT_ID: ").strip()
        
        print("Test mode - sending check-in only to you (ADMIN_CHAT_ID).\n")
        try:
            await bot.send_message(
                chat_id=int(admin_id), 
                text=MESSAGE, 
                parse_mode="Markdown", 
                reply_markup=keyboard
            )
            print("✅ Sent! Check your Telegram.")
            print("\nHappy with it? Run this to send to all users:  python checkin_broadcast.py --all")
        except Exception as e:
            print(f"❌ Failed to send test check-in: {e}")
        return

    # Full broadcast mode
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        supabase_url = input("Enter your Supabase URL: ").strip()
    if not supabase_key:
        supabase_key = input("Enter your Supabase Anon/Public Key: ").strip()

    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        students = supabase.table("students").select("chat_id, name").execute().data
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return

    total = len(students)
    sent, failed = 0, 0

    print(f"🚀 Sending check-in to {total} users...\n")

    for s in students:
        try:
            await bot.send_message(
                chat_id=s["chat_id"], 
                text=MESSAGE, 
                parse_mode="Markdown", 
                reply_markup=keyboard
            )
            sent += 1
            print(f"  ✅ Sent to {s.get('name', s['chat_id'])}")
            await asyncio.sleep(0.1)  # Rate limit buffer
        except Forbidden:
            failed += 1
            print(f"  ❌ {s['chat_id']} has blocked the bot")
        except RetryAfter as e:
            print(f"  ⚠️ Rate limited - waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=s["chat_id"], 
                    text=MESSAGE, 
                    parse_mode="Markdown", 
                    reply_markup=keyboard
                )
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ Failed {s['chat_id']}: {e}")

    print(f"\n🎉 Done! Sent: {sent} | Failed: {failed} | Total: {total}")

if __name__ == "__main__":
    asyncio.run(checkin_broadcast())
