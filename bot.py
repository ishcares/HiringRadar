import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import Forbidden, RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes,
    ConversationHandler, CallbackQueryHandler, filters
)
import hashlib
from scraper import get_new_jobs, get_all_jobs
from db import (
    supabase,
    has_student_seen_job,
    mark_student_seen_jobs,
    load_seen_jobs,
    save_seen_jobs,
    count_subscribers,
    upsert_jobs_cache,
    get_cached_jobs,
    deactivate_stale_jobs,
    ensure_referral_code,
    record_referral,
    get_referral_stats,
    is_student_premium,
)
from datetime import datetime
from dotenv import load_dotenv
from matching import (
    group_jobs,
    get_experience_tag,
    get_graduation_tag,
    match_jobs_for_student,
    build_match_reason,
    keyword_map,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Conversation states
NAME, COLLEGE, DEPARTMENT, BRANCH, GRAD_YEAR, SKILLS, ROLES, JOB_TYPE, EDIT_COLLEGE, EDIT_DEPARTMENT = range(10)

def format_job_card(job: dict, grad_year: int = 2026, score: float = 0.0, student: dict = None) -> str:
    """Single place to format a job card — used everywhere"""
    count_label = f" _({job['count']} openings)_" if job.get('count', 1) > 1 else ""
    score_line = f"🎯 Match: {round(score * 100)}%\n" if score > 0 else ""
    reason_line = f"💡 _{build_match_reason(job, student)}_\n" if student and score > 0 else ""
    return (
        f"🏢 *{job['company']}*\n"
        f"💼 {job['title']}{count_label}\n"
        f"🏷️ {get_experience_tag(job['title'])}\n"
        f"🎓 {get_graduation_tag(job['title'], grad_year)}\n"
        f"📍 {job['location']}\n"
        f"{score_line}"
        f"{reason_line}"
        f"[→ Apply Now]({job['url']})"
    )

# ── Onboarding conversation ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()
    
    # Check if this is a new signup via referral deep link
    referrer_code = None
    if context.args and context.args[0].startswith("ref_"):
        referrer_code = context.args[0].replace("ref_", "").strip()

    if res.data:
        student = res.data[0]
        paused_status = "⏸️ Paused" if student.get("paused") else "🟢 Active"
        code = await asyncio.to_thread(ensure_referral_code, chat_id)
        
        # Display the Welcome Back card with an Edit Profile button
        keyboard = [[InlineKeyboardButton("✏️ Edit Profile / Settings", callback_data="onboard:edit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 Welcome back, *{student['name']}*!\n\n"
            f"🔔 Alerts: {paused_status}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Initialize user_data and save referrer if present
    context.user_data['referred_by_code'] = referrer_code

    await update.message.reply_text(
        "👋 Welcome to *HiringRadar!*\n\n"
        "Get real-time job alerts from top Indian product companies — "
        "Razorpay, CRED, Groww, PhonePe and more.\n\n"
        "Let's set up your profile in 5 quick steps 🚀\n\n"
        "*What's your name?*",
        parse_mode="Markdown"
    )
    return NAME

async def start_onboarding_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "✏️ *Let's quickly update your profile with our new features!*\n\n"
        "🏢 *Which college are you from?*\n\ne.g., VIT Vellore, BITS Pilani, IIM Bangalore",
        parse_mode="Markdown"
    )
    return EDIT_COLLEGE

async def get_edit_college(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['college'] = update.message.text.strip()
    
    keyboard = [
        [
            InlineKeyboardButton("🖥️ CSE/IT", callback_data="edept:cse"),
            InlineKeyboardButton("📊 MBA/Business", callback_data="edept:mba"),
        ],
        [
            InlineKeyboardButton("🎨 Design", callback_data="edept:design"),
            InlineKeyboardButton("Other", callback_data="edept:other"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📊 *Select your department:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return EDIT_DEPARTMENT

async def get_edit_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    
    if query:
        await query.answer()
        dept_val = query.data.replace("edept:", "")
    else:
        dept_val = update.message.text.strip().lower()
        
    college = context.user_data.get('college')
    
    try:
        # Update ONLY college and department in Supabase, keeping existing fields intact!
        supabase.table("students").update({
            "college": college,
            "department": dept_val,
        }).eq("chat_id", chat_id).execute()
        
        dept_names = {"cse": "CSE/IT", "mba": "MBA/Business", "design": "Design", "other": "Other"}
        dept_label = dept_names.get(dept_val, 'Other')
        
        msg_text = (
            f"✅ *Profile updated successfully!*\n\n"
            f"🏢 College: {college} ({dept_label})\n\n"
            f"Your alerts are active! Type /profile to view your complete card. 🚀"
        )
        if query:
            await query.message.reply_text(msg_text, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg_text, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Supabase update failed: {e}")
        await update.message.reply_text("⚠️ Couldn't update your profile right now. Try /start again.")
        
    return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text.strip()
    await update.message.reply_text("🏢 *Which college are you from?*\n\ne.g., VIT Vellore, BITS Pilani, IIM Bangalore", parse_mode="Markdown")
    return COLLEGE

async def get_college(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['college'] = update.message.text.strip()
    
    # We display inline buttons for clean department classification
    keyboard = [
        [
            InlineKeyboardButton("🖥️ CSE/IT", callback_data="dept:cse"),
            InlineKeyboardButton("📊 MBA/Business", callback_data="dept:mba"),
        ],
        [
            InlineKeyboardButton("🎨 Design", callback_data="dept:design"),
            InlineKeyboardButton("Other", callback_data="dept:other"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📊 *Select your department:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return DEPARTMENT

async def get_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        dept_val = query.data.replace("dept:", "")
        context.user_data['department'] = dept_val
        
        # Guide them to provide specific branch
        dept_names = {"cse": "CSE/IT", "mba": "MBA/Business", "design": "Design", "other": "Other"}
        await query.message.reply_text(
            f"Selected: *{dept_names.get(dept_val, dept_val)}*\n\n"
            f"📚 *What is your specific branch?*\n\ne.g. Computer Science, Finance, UX Design",
            parse_mode="Markdown"
        )
    else:
        # Fallback if they typed instead of clicking
        context.user_data['department'] = update.message.text.strip().lower()
        await update.message.reply_text("📚 *What is your specific branch?*\n\ne.g. Computer Science, Finance, UX Design", parse_mode="Markdown")
        
    return BRANCH

async def get_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['branch'] = update.message.text.strip().upper()
    await update.message.reply_text("📅 *What is your graduation year?*\n\ne.g. 2025 / 2026 / 2027", parse_mode="Markdown")
    return GRAD_YEAR

async def get_grad_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_year = datetime.now().year
    try:
        year = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(f"Please send a valid year like {current_year}.")
        return GRAD_YEAR
    if not (current_year - 10 <= year <= current_year + 6):
        await update.message.reply_text(
            f"That doesn't look right - please send a graduation year between "
            f"{current_year - 10} and {current_year + 6}."
        )
        return GRAD_YEAR
    context.user_data['graduation_year'] = year
    
    await update.message.reply_text(
        "💻 What are your top skills?\n\nSend comma separated: *Python, React, SQL, ML*",
        parse_mode="Markdown"
    )
    return SKILLS

async def get_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skills = [s.strip() for s in update.message.text.split(",")]
    context.user_data['skills'] = skills
    await update.message.reply_text(
        "🎯 What roles are you interested in?\n\n"
        "Choose from: backend / frontend / ml / data / devops / fullstack / android / ios\n\n"
        "Send comma separated: *backend, ml*",
        parse_mode="Markdown"
    )
    return ROLES

async def get_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid = list(keyword_map.keys())
    roles = [r.strip().lower() for r in update.message.text.split(",")]
    invalid = [r for r in roles if r not in valid]
    if invalid:
        await update.message.reply_text(
            f"❌ Unknown roles: {', '.join(invalid)}\n\n"
            f"Please choose from: {', '.join(valid)}\n\n"
            f"Send comma separated (e.g., *backend, ml*):",
            parse_mode="Markdown"
        )
        return ROLES

    context.user_data['preferred_roles'] = roles
    await update.message.reply_text(
        "💼 Are you looking for?\n\n*internship* / *fulltime* / *both*",
        parse_mode="Markdown"
    )
    return JOB_TYPE

async def get_job_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_type = update.message.text.strip().lower()
    if job_type not in ["internship", "fulltime", "both"]:
        await update.message.reply_text("Please send: internship / fulltime / both")
        return JOB_TYPE

    context.user_data['job_type'] = job_type
    data = context.user_data
    chat_id = update.effective_chat.id

    # Generate their own referral code deterministically
    referral_code = await asyncio.to_thread(ensure_referral_code, chat_id)

    try:
        supabase.table("students").upsert({
            "chat_id": chat_id,
            "name": data['name'],
            "college": data.get('college'),
            "department": data.get('department', 'cse'),
            "branch": data['branch'],
            "graduation_year": data['graduation_year'],
            "skills": data['skills'],
            "preferred_roles": data['preferred_roles'],
            "job_type": data['job_type'],
            "referral_code": referral_code,
        }).execute()

        # If referred by someone, record it and potentially reward the referrer
        referred_by_code = data.get("referred_by_code")
        if referred_by_code:
            upgraded = await asyncio.to_thread(record_referral, chat_id, referred_by_code)
            if upgraded:
                # Notify the referrer that they got premium!
                try:
                    ref_res = supabase.table("students").select("chat_id, name").eq("referral_code", referred_by_code).execute()
                    if ref_res.data:
                        ref_user = ref_res.data[0]
                        await context.bot.send_message(
                            chat_id=ref_user["chat_id"],
                            text=f"🎁 *Premium Unlocked!*\n\n"
                                 f"3 friends joined using your link! You have been upgraded to "
                                 f"*HiringRadar Premium* for 7 days. Instant alerts are now active! ⚡",
                            parse_mode="Markdown"
                        )
                except Exception as notify_err:
                    print(f"Failed to notify referrer: {notify_err}")

    except Exception as e:
        print(f"Supabase upsert failed: {e}")
        await update.message.reply_text("⚠️ Couldn't save profile right now. Try /start again.")
        return ConversationHandler.END

    dept_names = {"cse": "CSE/IT", "mba": "MBA/Business", "design": "Design", "other": "Other"}
    dept_label = dept_names.get(data.get('department'), 'Other')
    await update.message.reply_text(
        f"✅ *Profile saved, {data['name']}!*\n\n"
        f"🏢 College: {data.get('college')} ({dept_label})\n"
        f"🎓 Branch: {data['branch']} | Graduating: {data['graduation_year']}\n"
        f"💻 Skills: {', '.join(data['skills'])}\n"
        f"🎯 Roles: {', '.join(data['preferred_roles'])}\n"
        f"💼 Looking for: {data['job_type']}\n\n"
        f"You'll now get *personalized* job alerts! 🚀",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Setup cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ── Other commands ─────────────────────────────────────────────────────────

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()
    if not res.data:
        await update.message.reply_text("No profile found. Type /start to set one up.")
        return
    s = res.data[0]
    paused_status = "⏸️ Paused" if s.get("paused") else "🟢 Active"
    await update.message.reply_text(
        f"👤 *Your Profile*\n\n"
        f"🙋 Name: {s['name']}\n"
        f"🎓 Branch: {s['branch']} | {s['graduation_year']}\n"
        f"💻 Skills: {', '.join(s['skills'] or [])}\n"
        f"🎯 Roles: {', '.join(s['preferred_roles'] or [])}\n"
        f"💼 Job type: {s['job_type']}\n"
        f"🔔 Alerts: {paused_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✏️ *Update your profile:*\n"
        f"`/skills` Python, ML, SQL\n"
        f"`/roles` backend, ml\n"
        f"`/experience` internship\n"
        f"`/pause` · `/resume` alerts",
        parse_mode="Markdown"
    )

async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()

    # WHY get_cached_jobs() instead of get_all_jobs():
    # get_all_jobs() scrapes 36 companies live — takes 15-20 seconds.
    # get_cached_jobs() reads from Supabase — takes <100ms.
    # The scrape_job scheduler keeps the cache fresh every 5 minutes.
    all_jobs = await asyncio.to_thread(get_cached_jobs)

    if not all_jobs:
        # Cache is empty — scrape_job hasn't run yet (bot just started)
        await update.message.reply_text(
            "⏳ Job data is warming up (first run takes ~30s). "
            "Try again in a minute — you'll get instant results after that!"
        )
        return

    await update.message.reply_text("🔍 Finding your best matches...")

    grouped = group_jobs(all_jobs)
    grad_year = res.data[0].get("graduation_year", datetime.now().year) if res.data else datetime.now().year

    if res.data:
        student = res.data[0]
        matched = match_jobs_for_student(student, grouped)
        if matched:
            display_jobs = matched
            label = "matched"
        else:
            # Senior/Tech Founder decision: If they have a profile but 0 matches, show a targeted message
            # instead of pulling unrelated random jobs. This builds high trust.
            preferred_roles_str = ", ".join(student.get("preferred_roles", []))
            await update.message.reply_text(
                f"🔍 *No direct matches found today for your roles:* `{preferred_roles_str}`\n\n"
                f"We are scanning 36 product portals every 5 minutes and will notify you "
                f"the second a matching entry-level role is posted! 🚀",
                parse_mode="Markdown"
            )
            return
    else:
        # Unregistered guest user: Show a random sample of fresher-friendly tech roles
        from matching import _filter_fresher_jobs, matches_role, keyword_map
        fresher_only = _filter_fresher_jobs(grouped, 2026, datetime.now().year)
        all_tech_roles = list(keyword_map.keys())
        tech_only_pool = [j for j in fresher_only if matches_role(j["title"], all_tech_roles)]
        
        import random
        sampled = {}
        for job in tech_only_pool:
            sampled.setdefault(job['company'], job)
        pool = list(sampled.values())
        random.shuffle(pool)
        display_jobs = pool[:5]
        label = "latest"

    if not display_jobs:
        await update.message.reply_text("No open roles right now. You'll get an alert the moment something drops!")
        return

    if label == "matched":
        student_data = res.data[0] if res.data else None
        lines = [format_job_card(job, grad_year, score, student_data) for job, score in display_jobs[:5]]
    else:
        lines = [format_job_card(job, grad_year) for job in display_jobs[:5]]

    await update.message.reply_text(
        f"*Your {label} job matches:*\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = count_subscribers()
    await update.message.reply_text(f"🎯 HiringRadar is actively tracking roles for {count} candidates.")

# ── Job 1: Scraper (Producer) ──────────────────────────────────────────────
# Runs every 5 minutes. Only responsibility: fetch jobs from ATS APIs
# and write them to jobs_cache in Supabase. Never touches Telegram.
#
# WHY SEPARATE: Scraping 36 companies takes 15-20s of blocking HTTP.
# If this ran inside the alert delivery loop, students would wait 20s
# before getting their messages. Telegram's JobQueue would time out.

async def scrape_job(context: ContextTypes.DEFAULT_TYPE):
    """Producer: scrape all ATS boards and write results to jobs_cache."""
    print("[scrape_job] Starting scrape...")

    # Run blocking HTTP calls in a thread so the event loop stays free
    all_jobs = await asyncio.to_thread(get_all_jobs)
    print(f"[scrape_job] Scraped {len(all_jobs)} jobs from ATS boards")

    if not all_jobs:
        print("[scrape_job] No jobs returned — skipping cache update")
        return

    # Write to jobs_cache — upsert means same job scraped twice = no duplicate
    await asyncio.to_thread(upsert_jobs_cache, all_jobs)

    # Mark jobs no longer on any ATS as inactive
    live_ids = {f"{j['company']}|{j['title']}|{j['url']}" for j in all_jobs}
    # Use the same hash function as db._job_id
    import hashlib as _hl
    live_hashed = {_hl.md5(raw.encode()).hexdigest() for raw in live_ids}
    await asyncio.to_thread(deactivate_stale_jobs, live_hashed)

    # Track new jobs for channel broadcast (seen_jobs dedup)
    seen_urls = await asyncio.to_thread(load_seen_jobs)
    new_jobs = [job for job in all_jobs if job["url"] not in seen_urls]
    if new_jobs:
        new_urls = [job["url"] for job in new_jobs]
        await asyncio.to_thread(save_seen_jobs, new_urls)

        # Senior/Tech Founder safety limit: If there are more than 15 new jobs (like on cold start / downtime recovery),
        # we treat it as a backfill run and skip posting them to the channel to prevent spam.
        if len(new_jobs) > 15:
            print(f"[scrape_job] Cold start or backfill detected ({len(new_jobs)} jobs). Marking all as seen without posting to channel.")
            return

        # Post new jobs to the Telegram channel (if configured)
        CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
        if CHANNEL_ID:
            bot_username = context.bot.username
            
            # Senior/Tech Founder filter: Only push fresher-friendly & intern positions to the channel.
            # This prevents channel alert fatigue.
            from matching import _filter_fresher_jobs
            # Treat channel audience as current/recent grads (2026/fresher)
            fresher_new_jobs = _filter_fresher_jobs(new_jobs, datetime.now().year, datetime.now().year)
            
            grouped_new = group_jobs(fresher_new_jobs)
            for job in grouped_new:
                try:
                    card = format_job_card(job)
                    text_msg = (
                        f"📢 *New Job Alert!*\n━━━━━━━━━━━━━━━━━━━━━\n\n{card}\n\n"
                        f"🤖 *[Get Personalized Match Alerts](https://t.me/{bot_username})*"
                    )
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=text_msg,
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                    await asyncio.sleep(1)  # Telegram rate limit buffer
                except Exception as e:
                    print(f"[scrape_job] Channel post failed: {e}")

    print(f"[scrape_job] Done. {len(new_jobs)} new jobs found.")


# ── Job 2: Alert Sender (Consumer) ─────────────────────────────────────────
# Runs every 2 minutes. Only responsibility: read from jobs_cache and
# deliver personalised Telegram alerts to each student.
#
# WHY SEPARATE: This job never makes HTTP requests to ATS boards.
# get_cached_jobs() is a single fast DB query — takes <100ms.
# If scraping is slow or fails, students still get alerts from cache.

async def alert_job(context: ContextTypes.DEFAULT_TYPE):
    """Consumer: match cached jobs to students and deliver Telegram alerts."""
    # Get all non-paused students
    students = supabase.table("students").select("*").eq("paused", False).execute().data
    if not students:
        return

    # To optimize, we split students into premium vs free, and fetch jobs accordingly
    premium_student_ids = []
    free_student_ids = []
    
    student_map = {}
    for student in students:
        chat_id = student["chat_id"]
        student_map[chat_id] = student
        is_premium = await asyncio.to_thread(is_student_premium, chat_id)
        if is_premium:
            premium_student_ids.append(chat_id)
        else:
            free_student_ids.append(chat_id)

    # Fetch jobs for both tiers
    instant_jobs = []
    delayed_jobs = []
    
    if premium_student_ids:
        instant_jobs = await asyncio.to_thread(get_cached_jobs, delay_hours=0)
    if free_student_ids:
        delayed_jobs = await asyncio.to_thread(get_cached_jobs, delay_hours=2)

    # Group jobs
    grouped_instant = group_jobs(instant_jobs) if instant_jobs else []
    grouped_delayed = group_jobs(delayed_jobs) if delayed_jobs else []

    print(f"[alert_job] Matching: Premium users count={len(premium_student_ids)}, Free users count={len(free_student_ids)}")

    for chat_id, student in student_map.items():
        is_premium = chat_id in premium_student_ids
        job_pool = grouped_instant if is_premium else grouped_delayed
        
        if not job_pool:
            continue

        matched = match_jobs_for_student(student, job_pool)
        if not matched:
            continue

        # Filter out jobs this student has already seen
        unseen = []
        for job, score in matched:
            seen = await asyncio.to_thread(has_student_seen_job, chat_id, job["url"])
            if not seen:
                unseen.append((job, score))

        if not unseen:
            continue

        # Format and chunk messages (Telegram 4096 char limit per message)
        grad_year = student.get("graduation_year", 2026)
        job_lines = [format_job_card(job, grad_year, score, student) for job, score in unseen]

        TELEGRAM_LIMIT = 4000
        chunks, chunk_pairs = [], []
        current_chunk, current_pairs, current_len = [], [], 0
        for (job, score), line in zip(unseen, job_lines):
            if current_len + len(line) + 2 > TELEGRAM_LIMIT and current_chunk:
                chunks.append(current_chunk)
                chunk_pairs.append(current_pairs)
                current_chunk, current_pairs, current_len = [], [], 0
            current_chunk.append(line)
            current_pairs.append((job, score))
            current_len += len(line) + 2
        if current_chunk:
            chunks.append(current_chunk)
            chunk_pairs.append(current_pairs)

        # Send each chunk with feedback buttons
        try:
            for i, chunk in enumerate(chunks):
                part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                total = len(unseen)
                header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n━━━━━━━━━━━━━━━━━━━━━\n"
                digest = header + "\n\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━"
                buttons = []
                for job, _ in chunk_pairs[i]:
                    url_hash = hashlib.md5(job["url"].encode()).hexdigest()[:10]
                    buttons.append([
                        InlineKeyboardButton("👍 Relevant", callback_data=f"feedback:relevant:{url_hash}"),
                        InlineKeyboardButton("👎 Not for me", callback_data=f"feedback:skip:{url_hash}"),
                    ])
                await context.bot.send_message(
                    chat_id=student['chat_id'],
                    text=digest,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                await asyncio.sleep(0.1)

            # Mark sent — student won't see these again
            sent_urls = [job["url"] for job, _ in unseen]
            await asyncio.to_thread(mark_student_seen_jobs, student["chat_id"], sent_urls)

        except Forbidden:
            # Student blocked the bot — clean up
            supabase.table("students").delete().eq("chat_id", student['chat_id']).execute()
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except (TimedOut, NetworkError) as e:
            # Transient delivery issue — retry once after 5s
            await asyncio.sleep(5)
            try:
                for i, chunk in enumerate(chunks):
                    part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                    total = len(unseen)
                    header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n━━━━━━━━━━━━━━━━━━━━━\n"
                    digest = header + "\n\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━"
                    buttons = []
                    for job, _ in chunk_pairs[i]:
                        url_hash = hashlib.md5(job["url"].encode()).hexdigest()[:10]
                        buttons.append([
                            InlineKeyboardButton("👍 Relevant", callback_data=f"feedback:relevant:{url_hash}"),
                            InlineKeyboardButton("👎 Not for me", callback_data=f"feedback:skip:{url_hash}"),
                        ])
                    await context.bot.send_message(
                        chat_id=student['chat_id'],
                        text=digest,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                    await asyncio.sleep(0.1)
                
                # Successfully sent all chunks on retry: mark these jobs as seen by the student!
                sent_urls = [job["url"] for job, _ in chunk_pairs]
                await asyncio.to_thread(mark_student_seen_jobs, student["chat_id"], sent_urls)

            except Exception as retry_err:
                print(f"Failed to send to {student['chat_id']} after retry: {retry_err}")
        except Exception as e:
            print(f"Failed to send to {student['chat_id']}: {e}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()
    if not res.data:
        await update.message.reply_text("No profile found. Type /start to set one up.")
        return
    s = res.data[0]
    paused_status = "⏸️ Paused" if s.get("paused") else "🟢 Active"
    
    # Check premium status
    premium_active = is_student_premium(chat_id)
    tier_label = "⚡ Premium Tier" if premium_active else "🟢 Free Tier (2hr delay)"
    
    dept_names = {"cse": "CSE/IT", "mba": "MBA/Business", "design": "Design", "other": "Other"}
    dept_label = dept_names.get(s.get("department"), "Other")

    await update.message.reply_text(
        f"👤 *Your Profile*\n\n"
        f"🙋 Name: {s['name']}\n"
        f"🏢 College: {s.get('college') or 'Not set'}\n"
        f"📊 Dept: {dept_label} ({s['branch']})\n"
        f"🎓 Graduating: {s['graduation_year']}\n"
        f"💻 Skills: {', '.join(s['skills'] or [])}\n"
        f"🎯 Roles: {', '.join(s['preferred_roles'] or [])}\n"
        f"💼 Job type: {s['job_type']}\n"
        f"👑 Account: *{tier_label}*\n"
        f"🔔 Alerts: {paused_status}",
        parse_mode="Markdown"
    )

async def share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bot_username = context.bot.username or "Hiringradar_bot"
    stats = await asyncio.to_thread(get_referral_stats, chat_id)
    
    # Get student college to make referral link college-aware
    res = supabase.table("students").select("college").eq("chat_id", chat_id).execute()
    college_name = res.data[0].get("college") if res.data else None
    
    ref_link = f"https://t.me/{bot_username}?start=ref_{stats['code']}"
    premium_status = "⚡ *Premium Active*" if stats['is_premium'] else "🟢 *Free Tier*"
    
    college_context = f" to join your college circle ({college_name})" if college_name else ""

    await update.message.reply_text(
        f"🎁 *HiringRadar Referral Program*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Get friends{college_context} to join and unlock *Premium Alerts* (Instant alerts instead of 2-hour delay)!\n\n"
        f"Invite *3 friends* → Get *7 days of Premium* free.\n\n"
        f"👤 Status: {premium_status}\n"
        f"👥 Successful Invites: *{stats['count']}*\n\n"
        f"🔗 *Your Invite Link:*\n{ref_link}\n\n"
        f"Copy and forward the link above to your college groups! 🚀",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def update_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /skills Python, ML, React")
        return
    skills = [s.strip() for s in " ".join(context.args).split(",")]
    supabase.table("students").update({"skills": skills}).eq("chat_id", chat_id).execute()
    await update.message.reply_text(f"✅ Skills updated: {', '.join(skills)}")

async def update_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("department").eq("chat_id", chat_id).execute()
    dept = res.data[0].get("department", "cse") if res.data else "cse"
    
    # Filter valid options based on department
    if dept == "cse":
        valid = ["backend", "frontend", "ml", "data", "devops", "fullstack", "android", "ios"]
    elif dept == "mba":
        valid = ["pm", "analyst", "consulting", "growth", "finance"]
    elif dept == "design":
        valid = ["design"]
    else:
        valid = list(keyword_map.keys())

    if not context.args:
        await update.message.reply_text(f"Usage: /roles {', '.join(valid[:2])}\nValid options for your department: {', '.join(valid)}")
        return
    roles = [s.strip().lower() for s in " ".join(context.args).split(",")]
    invalid = [r for r in roles if r not in valid]
    if invalid:
        await update.message.reply_text(f"❌ Unknown roles: {', '.join(invalid)}\nValid: {', '.join(valid)}")
        return
    supabase.table("students").update({"preferred_roles": roles}).eq("chat_id", chat_id).execute()
    await update.message.reply_text(f"✅ Roles updated: {', '.join(roles)}")

async def update_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /experience internship\nOptions: internship / fulltime / both")
        return
    job_type = context.args[0].strip().lower()
    if job_type not in ["internship", "fulltime", "both"]:
        await update.message.reply_text("Please send: internship / fulltime / both")
        return
    supabase.table("students").update({"job_type": job_type}).eq("chat_id", chat_id).execute()
    await update.message.reply_text(f"✅ Looking for: {job_type}")


async def pause_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase.table("students").update({"paused": True}).eq("chat_id", chat_id).execute()
    await update.message.reply_text("⏸️ Alerts paused. Send /resume to turn them back on.")

async def resume_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase.table("students").update({"paused": False}).eq("chat_id", chat_id).execute()
    await update.message.reply_text("▶️ Alerts resumed! You'll get the next batch soon.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only broadcast command to update all active students."""
    sender_chat_id = update.effective_chat.id
    admin_id_str = os.getenv("ADMIN_CHAT_ID")
    
    if not admin_id_str or str(sender_chat_id) != admin_id_str.strip():
        await update.message.reply_text("❌ Unauthorized. Admin command only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/broadcast Your message here...`", parse_mode="Markdown")
        return

    message_text = " ".join(context.args)
    # Get all non-paused students
    students = supabase.table("students").select("chat_id").eq("paused", False).execute().data
    if not students:
        await update.message.reply_text("No active users to broadcast to.")
        return

    await update.message.reply_text(f"📣 Starting broadcast to {len(students)} users...")
    
    success_count = 0
    fail_count = 0
    for s in students:
        try:
            await context.bot.send_message(
                chat_id=s["chat_id"],
                text=message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            success_count += 1
            await asyncio.sleep(0.05) # Rate limit buffer
        except Exception as e:
            fail_count += 1
            print(f"[broadcast] Failed to send to {s['chat_id']}: {e}")

    await update.message.reply_text(f"✅ Broadcast finished.\nSent: {success_count}\nFailed: {fail_count}")


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()   # stops the loading spinner on the button
    _, feedback, url_hash = query.data.split(":", 2)
    chat_id = query.from_user.id
    try:
        supabase.table("job_feedback").insert({
            "chat_id": chat_id,
            "job_url_hash": url_hash,
            "feedback": feedback,
        }).execute()
    except Exception as e:
        print(f"Feedback save failed: {e}")
    label = "❤️ Saved!" if feedback == "relevant" else "👍 Got it!"
    await query.edit_message_reply_markup(reply_markup=None)  # remove buttons
    await query.message.reply_text(label)

async def checkin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, status = query.data.split(":", 1)
    chat_id = query.from_user.id
    try:
        if status == "active":
            # Set paused to False to keep alerts on
            supabase.table("students").update({"paused": False}).eq("chat_id", chat_id).execute()
            response_text = "🎯 *Awesome!* We'll keep scanning and sending you the best matches."
        else:
            # Set paused to True to temporarily pause alerts
            supabase.table("students").update({"paused": True}).eq("chat_id", chat_id).execute()
            response_text = "⏸️ *Got it!* Your job alerts are now paused. You can turn them back on anytime by sending /resume."
        
        # Remove buttons from the message and reply with confirmation
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(response_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Check-in callback failed: {e}")
        await query.message.reply_text("⚠️ Something went wrong saving your response. Send /start to update your profile.")


# ── Main ───────────────────────────────────────────────────────────────────

async def on_startup(app):
    """Runs once after the bot initialises — safe place for async setup."""
    await app.bot.set_my_commands([
        BotCommand("jobs",       "See your latest job matches"),
        BotCommand("profile",    "View and update your profile"),
        BotCommand("share",      "Invite friends & get Premium Alerts 🎁"),
        BotCommand("skills",     "Update your skills"),
        BotCommand("roles",      "Update preferred roles"),
        BotCommand("experience", "Update job type preference"),
        BotCommand("pause",      "Pause job alerts"),
        BotCommand("resume",     "Resume job alerts"),
        BotCommand("stats",      "See active user count"),
        BotCommand("start",      "Set up or restart your profile"),
    ])

def create_app(token):
    app = ApplicationBuilder().token(token).post_init(on_startup).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start_onboarding_edit, pattern="^onboard:edit")
        ],
        states={
            NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COLLEGE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_college)],
            DEPARTMENT: [
                CallbackQueryHandler(get_department, pattern="^dept:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_department)
            ],
            BRANCH:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_branch)],
            GRAD_YEAR:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grad_year)],
            SKILLS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_skills)],
            ROLES:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_roles)],
            JOB_TYPE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_job_type)],
            EDIT_COLLEGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_edit_college)],
            EDIT_DEPARTMENT: [
                CallbackQueryHandler(get_edit_department, pattern="^edept:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_edit_department)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("stats", stats),
            CommandHandler("profile", profile),
            CommandHandler("jobs", jobs),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("share", share))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("skills", update_skills))
    app.add_handler(CommandHandler("roles", update_roles))
    app.add_handler(CommandHandler("experience", update_experience))
    app.add_handler(CommandHandler("pause", pause_alerts))
    app.add_handler(CommandHandler("resume", resume_alerts))
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^feedback:"))
    app.add_handler(CallbackQueryHandler(checkin_callback_handler, pattern="^checkin:"))

    # ── Two separate scheduled jobs ─────────────────────────────────────────
    # scrape_job: every 5 min — hits ATS APIs, writes to jobs_cache
    # alert_job:  every 2 min — reads from jobs_cache, sends Telegram messages
    #
    # first=10 means scrape_job fires 10s after bot starts (cache gets populated).
    # first=30 gives scrape_job time to fill the cache before alerts run.
    app.job_queue.run_repeating(scrape_job, interval=300, first=10)
    app.job_queue.run_repeating(alert_job,  interval=120, first=30)

    return app

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Health check endpoint for UptimeRobot monitoring."""
    await update.message.reply_text("🟢 HiringRadar engine is online and scanning.")


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles freeform text messages — pre-agent conversational hook."""
    text = update.message.text or ""
    # Future: Route this through Groq Intent Router
    await update.message.reply_text(
        "👋 I understand commands like /jobs, /profile, /share, /skills, /roles, /experience, /pause, /resume.\n\n"
        "💡 Tip: Type /profile to see your current setup or /jobs to see your latest matches!"
    )


if __name__ == "__main__":
    import asyncio
    from embeddings import get_embeddings_from_hf

    # ── Startup Health Check ────────────────────────────────────────────────
    # Verify HF embeddings are live. If offline, log a clear warning.
    # This prevents silent degradation to keyword-only mode without admin awareness.
    print("[startup] Checking HF embedding API health...")
    test_result = get_embeddings_from_hf(["health check"])
    if test_result:
        print("[startup] ✅ HF embeddings online — semantic matching active.")
    else:
        print("[startup] ⚠️  HF embeddings OFFLINE — running in keyword-only fallback mode. Add HF_TOKEN to .env")

    app = create_app(BOT_TOKEN)

    # Register /ping and freeform message handler
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    print("🚀 HiringRadar backend engine online and scanning...")

    # Python 3.13/3.14 event loop policy fix for daemon runtimes
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app.run_polling()

