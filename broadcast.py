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

async def broadcast():
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # Fetch credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        supabase_url = input("Enter your Supabase URL: ").strip()
    if not supabase_key:
        supabase_key = input("Enter your Supabase Anon/Public Key: ").strip()

    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return

    # Dynamic inline button for instant update redirection
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Update College & Department", callback_data="onboard:edit")]
    ])

    if "--all" not in sys.argv:
        # Test mode — sends only to the ADMIN_CHAT_ID
        admin_id = os.getenv("ADMIN_CHAT_ID")
        if not admin_id:
            admin_id = input("Enter your Telegram ADMIN_CHAT_ID: ").strip()
        
        print("Test mode - sending only to you (ADMIN_CHAT_ID).\n")
        
        # Pull your mock referral stats
        res = supabase.table("students").select("referral_code, college").eq("chat_id", int(admin_id)).execute()
        ref_code = res.data[0].get("referral_code") if res.data else "test_code"
        college = res.data[0].get("college") if res.data else "your college"
        
        college_str = f" to join your college circle ({college})" if college else ""
        custom_msg = (
            f"🎓 *HiringRadar Upgraded: College & Multi-Dept Support!* 🎓\n\n"
            f"We’ve completely updated our matching engine to support college campus drives and non-tech placement tracking!\n\n"
            f"🏢 *What's New:*\n"
            f"1. *College Tracking:* Update your college to get prioritized campus drive alerts.\n"
            f"2. *MBA & Business Roles:* We now track Product Management (PM), Business Analyst, Strategy, Consulting, and Finance roles!\n\n"
            f"✏️ *Action Required:*\n"
            f"Click the button below to update your profile in 10 seconds!\n\n"
            f"🔗 *Invite your classmates{college_str}:*\n"
            f"Copy and forward this message to your college groups! If 3 people join using your link, you get *HiringRadar Premium* (Instant alerts instead of 2hr delay) for 7 days:\n"
            f"👉 https://t.me/{bot_username}?start=ref_{ref_code}"
        )
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=custom_msg,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            print("✅ Sent! Check your Telegram.")
            print("\nHappy with it? Run this to send to all users:  python broadcast.py --all")
        except Exception as e:
            print(f"❌ Failed to send test message: {e}")
        return

    # Full broadcast mode
    try:
        students = supabase.table("students").select("chat_id, name, referral_code, college").execute().data
    except Exception as e:
        print(f"❌ Failed to query students: {e}")
        return

    total = len(students)
    sent, failed = 0, 0

    print(f"🚀 Broadcasting to {total} users...\n")

    for s in students:
        ref_code = s.get("referral_code") or "invite"
        college = s.get("college")
        college_str = f" to join your college circle ({college})" if college else ""
        
        custom_msg = (
            f"🎓 *HiringRadar Upgraded: College & Multi-Dept Support!* 🎓\n\n"
            f"We’ve completely updated our matching engine to support college campus drives and non-tech placement tracking!\n\n"
            f"🏢 *What's New:*\n"
            f"1. *College Tracking:* Update your college to get prioritized campus drive alerts.\n"
            f"2. *MBA & Business Roles:* We now track Product Management (PM), Business Analyst, Strategy, Consulting, and Finance roles!\n\n"
            f"✏️ *Action Required:*\n"
            f"Click the button below to update your profile in 10 seconds!\n\n"
            f"🔗 *Invite your classmates{college_str}:*\n"
            f"Copy and forward this message to your college groups! If 3 people join using your link, you get *HiringRadar Premium* (Instant alerts instead of 2hr delay) for 7 days:\n"
            f"👉 https://t.me/{bot_username}?start=ref_{ref_code}"
        )

        try:
            await bot.send_message(
                chat_id=s["chat_id"],
                text=custom_msg,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            sent += 1
            print(f"  ✅ Sent to {s.get('name', s['chat_id'])}")
            await asyncio.sleep(0.1)  # Rate limiting prevention
        except Forbidden:
            failed += 1
            print(f"  ❌ {s['chat_id']} has blocked the bot")
        except RetryAfter as e:
            print(f"  ⚠️ Rate limited - waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=s["chat_id"],
                    text=custom_msg,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ Failed {s['chat_id']}: {e}")

    print(f"\n🎉 Done! Sent: {sent} | Failed: {failed} | Total: {total}")

if __name__ == "__main__":
    asyncio.run(broadcast())
