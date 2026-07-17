import os
import asyncio
from dotenv import load_dotenv
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
    check_and_deactivate_dead_link,
)
from datetime import datetime

from matching import (
    group_jobs,
    get_experience_tag,
    get_graduation_tag,
    match_jobs_for_student,
    build_match_reason,
    keyword_map,
)
from resume_ingest import extract_resume_text_from_path
from jd_skill_extractor import extract_jd_skills_job
from ai_agent import evaluate_resume_for_job

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Conversation states
NAME, COLLEGE, DEPARTMENT, BRANCH, GRAD_YEAR, EXP_LEVEL, RESUME_UPLOAD, SKILLS, ROLES, JOB_TYPE, EDIT_COLLEGE, EDIT_DEPARTMENT = range(12)
def get_time_ago_string(scraped_at_str: str) -> str:
    """Returns a 'time ago' string for the scraped timestamp."""
    from datetime import datetime, timezone
    from dateutil.parser import parse
    if not scraped_at_str:
        return "new"
    try:
        scraped_at = parse(scraped_at_str)
        now = datetime.now(timezone.utc)
        diff = now - scraped_at
        
        minutes = int(diff.total_seconds() / 60)
        hours = int(minutes / 60)
        days = int(hours / 24)
        
        if minutes < 60:
            return f"{max(1, minutes)}m ago"
        elif hours < 24:
            return f"{hours}h ago"
        else:
            return f"{days}d ago"
    except Exception:
        return "recent"


def format_job_card(job: dict, grad_year: int = 2026, score: float = 0.0, student: dict = None) -> str:
    """Minimal placement card — company, role, location, freshness, fit, apply link."""
    desc = job.get('description', '')
    exp = get_experience_tag(job['title'], desc)
    time_ago = get_time_ago_string(job.get('scraped_at'))

    loc_str = job.get('location', 'Not specified')
    if job.get('remote_class') == 'remote_unclear':
        loc_str = "🌍 Remote (unverified location — check listing before applying)"

    lines = [
        f"🏢 *{job['company']}* — {job['title']}",
        f"📍 {loc_str} · {exp} · {time_ago}",
    ]

    if score > 0:
        pct = round(score * 100)
        reason = build_match_reason(job, student)
        lines.append(f"🎯 {pct}% match — _{reason}_")

    lines.append(f"🔗 [Apply]({job['url']})")
    return "\n".join(lines)

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
            InlineKeyboardButton("📈 Data Science / AI", callback_data="edept:data_science"),
        ],
        [
            InlineKeyboardButton("📊 MBA/Business", callback_data="edept:mba"),
            InlineKeyboardButton("🎨 Design", callback_data="edept:design"),
        ],
        [
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
        
        dept_names = {"cse": "CSE/IT", "data_science": "Data Science / AI", "mba": "MBA/Business", "design": "Design", "other": "Other"}
        dept_label = dept_names.get(dept_val, dept_val)
        
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
            InlineKeyboardButton("📈 Data Science / AI", callback_data="dept:data_science"),
        ],
        [
            InlineKeyboardButton("📊 MBA/Business", callback_data="dept:mba"),
            InlineKeyboardButton("🎨 Design", callback_data="dept:design"),
        ],
        [
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
        dept_names = {"cse": "CSE/IT", "data_science": "Data Science / AI", "mba": "MBA/Business", "design": "Design", "other": "Other"}
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

    # Ask experience level via inline buttons
    keyboard = [
        [
            InlineKeyboardButton("🌱 Fresher / Student (0 yrs)", callback_data="exp:fresher"),
        ],
        [
            InlineKeyboardButton("🔵 Up to 1 year", callback_data="exp:junior1"),
            InlineKeyboardButton("💼 1–3 years", callback_data="exp:mid"),
        ],
        [
            InlineKeyboardButton("🚀 3+ years", callback_data="exp:senior"),
        ],
    ]
    await update.message.reply_text(
        "🎯 *What is your current experience level?*\n\n"
        "This helps us filter out jobs that require more experience than you have.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EXP_LEVEL


async def get_exp_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        exp_val = query.data.replace("exp:", "")
    else:
        exp_val = "fresher"  # safe default

    # Map to years of experience for filtering
    exp_years_map = {
        "fresher": 0,
        "junior1": 1,
        "mid": 2,
        "senior": 4,
    }
    exp_label_map = {
        "fresher": "Fresher / Student",
        "junior1": "Up to 1 year",
        "mid": "1–3 years",
        "senior": "3+ years",
    }
    context.user_data['experience_level'] = exp_val
    context.user_data['years_of_experience'] = exp_years_map.get(exp_val, 0)

    label = exp_label_map.get(exp_val, exp_val)
    upload_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Upload Resume (auto-extract skills)", callback_data="onboard_resume:upload")],
        [InlineKeyboardButton("✏️ Type my skills manually", callback_data="onboard_resume:skip")],
    ])
    await query.message.reply_text(
        f"✅ *{label}* selected.\n\n"
        "📄 *Upload your resume (PDF)* to auto-extract your skills — or type them manually.",
        reply_markup=upload_keyboard,
        parse_mode="Markdown"
    )
    return RESUME_UPLOAD


async def handle_onboarding_resume_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Upload / Skip choice after experience level selection."""
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("onboard_resume:", "")

    if choice == "upload":
        await query.message.reply_text(
            "📤 *Send your resume as a PDF file now.*\n\n"
            "_Your skills will be automatically extracted from it._",
            parse_mode="Markdown"
        )
        return RESUME_UPLOAD  # wait for document
    else:
        # User chose to type manually
        await query.message.reply_text(
            "💻 What are your top skills?\n\nSend comma separated: *Python, React, SQL, ML*",
            parse_mode="Markdown"
        )
        return SKILLS


async def handle_onboarding_resume_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses uploaded PDF during onboarding and extracts skills into user_data."""
    document = update.message.document
    if not document or not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("⚠️ Please send a PDF file, or type /cancel and enter skills manually.")
        return RESUME_UPLOAD

    await update.message.reply_text("⏳ Reading your resume...")

    import tempfile
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_resumes")
    os.makedirs(local_dir, exist_ok=True)
    chat_id = update.effective_chat.id
    local_path = os.path.join(local_dir, f"{chat_id}_onboard_resume.pdf")

    try:
        new_file = await context.bot.get_file(document.file_id)
        await new_file.download_to_drive(local_path)
        resume_text = await asyncio.to_thread(extract_resume_text_from_path, local_path)
        if os.path.exists(local_path):
            os.remove(local_path)

        if not resume_text:
            await update.message.reply_text(
                "⚠️ Couldn't extract text from this PDF. It may be scanned.\n\n"
                "💻 Please type your skills manually (comma separated):"
            )
            return SKILLS

        # Use ai_agent to parse skills from resume text
        from ai_agent import parse_skills_from_resume
        resume_data = await asyncio.to_thread(parse_skills_from_resume, resume_text)
        skills = resume_data.get("skills", [])
        if not skills:
            await update.message.reply_text(
                "⚠️ Couldn't detect skills from your resume.\n\n"
                "💻 Please type your skills manually (comma separated):"
            )
            return SKILLS

        context.user_data['skills'] = skills
        context.user_data['resume_text'] = resume_text

        await update.message.reply_text(
            f"✅ *Skills extracted from resume:*\n{', '.join(skills[:20])}\n\n"
            "🎯 What roles are you interested in?\n\n"
            "Choose from: backend / frontend / ml / data / devops / fullstack / android / ios\n\n"
            "Send comma separated: *backend, ml*",
            parse_mode="Markdown"
        )
        return ROLES

    except Exception as e:
        print(f"Onboarding resume parse failed: {e}")
        await update.message.reply_text(
            "⚠️ Something went wrong reading your PDF.\n\n"
            "💻 Please type your skills manually (comma separated):"
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
            "experience_level": data.get('experience_level', 'fresher'),
            "years_of_experience": data.get('years_of_experience', 0),
            "skills": data['skills'],
            "preferred_roles": data['preferred_roles'],
            "job_type": data['job_type'],
            "referral_code": referral_code,
            "resume_text": data.get('resume_text'),  # None if they typed skills manually
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

    # Run an immediate match check to give them instant feedback
    from db import get_cached_jobs
    from matching import match_jobs_for_student
    
    student_dict = {
        "skills": data["skills"],
        "preferred_roles": data["preferred_roles"],
        "job_type": data["job_type"],
        "department": data.get("department", "cse")
    }
    
    active_jobs = get_cached_jobs()
    matches = match_jobs_for_student(student_dict, active_jobs)
    
    if matches:
        status_msg = "We found matching jobs for you! Your first alert cards will arrive in your chat in a couple of minutes. 🚀"
    else:
        status_msg = "🔍 *HiringRadar is on the hunt:*\nWe couldn't find an exact skill match for you in today's active placements, but our scrapers are checking new career pages every 5 minutes. We'll alert you the moment a fit goes live! 📡"

    dept_names = {"cse": "CSE/IT", "mba": "MBA/Business", "design": "Design", "other": "Other"}
    dept_label = dept_names.get(data.get('department'), 'Other')
    await update.message.reply_text(
        f"✅ *Profile saved, {data['name']}!*\n\n"
        f"🏢 College: {data.get('college')} ({dept_label})\n"
        f"🎓 Branch: {data['branch']} | Graduating: {data['graduation_year']}\n"
        f"💻 Skills: {', '.join(data['skills'])}\n"
        f"🎯 Roles: {', '.join(data['preferred_roles'])}\n"
        f"💼 Looking for: {data['job_type']}\n\n"
        f"{status_msg}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Setup cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ── Other commands ─────────────────────────────────────────────────────────


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
        for job, score in display_jobs[:5]:
            card = format_job_card(job, grad_year, score, student_data)
            url_hash = hashlib.md5(job["url"].encode()).hexdigest()[:10]
            buttons = [
                [
                    InlineKeyboardButton("👍 Relevant", callback_data=f"feedback:relevant:{url_hash}"),
                    InlineKeyboardButton("👎 Not for me", callback_data=f"feedback:skip:{url_hash}"),
                ]
            ]
            if os.getenv("ENABLE_RESUME_CHECK") == "True":
                buttons.append([
                    InlineKeyboardButton("🤖 Check Resume Match", callback_data=f"feedback:check_match:{url_hash}")
                ])
            await update.message.reply_text(
                card,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        for job in display_jobs[:5]:
            card = format_job_card(job, grad_year)
            await update.message.reply_text(
                card,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if str(update.effective_chat.id) != str(admin_chat_id):
        # Silently ignore or pretend command does not exist
        return
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

    # Filter to staging accounts if whitelist environment variable is set
    staging_ids_str = os.getenv("STAGING_CHAT_IDS", "")
    if staging_ids_str:
        staging_ids = [int(x.strip()) for x in staging_ids_str.split(",") if x.strip()]
        students = [s for s in students if s["chat_id"] in staging_ids]
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
                is_live = await asyncio.to_thread(check_and_deactivate_dead_link, job.get("id"), job["url"])
                if is_live:
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
                    if os.getenv("ENABLE_RESUME_CHECK") == "True":
                        buttons.append([
                            InlineKeyboardButton("🤖 Check Resume Match", callback_data=f"feedback:check_match:{url_hash}")
                        ])

                
                # Send the message
                await context.bot.send_message(
                    chat_id=student['chat_id'],
                    text=digest,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                
                # Mark this chunk's jobs as seen immediately after successful send
                chunk_urls = [job["url"] for job, _ in chunk_pairs[i]]
                await asyncio.to_thread(mark_student_seen_jobs, student["chat_id"], chunk_urls)
                await asyncio.sleep(0.1)

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
                        if os.getenv("ENABLE_RESUME_CHECK") == "True":
                            buttons.append([
                                InlineKeyboardButton("🤖 Check Resume Match", callback_data=f"feedback:check_match:{url_hash}")
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

    import urllib.parse
    bot_username = context.bot.username or "Hiringradar_bot"
    ref_code = s.get("referral_code") or ensure_referral_code(chat_id)
    ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"
    
    share_text = (
        f"Get SDE, MBA, and Design placement/internship matching alerts directly on Telegram! 🚀\n"
        f"Unlock instant notifications and campus drives here:"
    )
    encoded_text = urllib.parse.quote(share_text)
    encoded_url = urllib.parse.quote(ref_link)
    telegram_share_url = f"https://t.me/share/url?url={encoded_url}&text={encoded_text}"

    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit Profile", callback_data="onboard:edit"),
            InlineKeyboardButton("✉️ Share with Friends", url=telegram_share_url)
        ]
    ])

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
        parse_mode="Markdown",
        reply_markup=reply_markup
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

    import urllib.parse
    share_text = (
        f"Get SDE, MBA, and Design placement/internship matching alerts directly on Telegram! 🚀\n"
        f"Unlock instant notifications and campus drives here: {ref_link}"
    )
    encoded_text = urllib.parse.quote(share_text)
    telegram_share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote('Get SDE, MBA, and Design matching alerts! 🚀')}"
    whatsapp_share_url = f"https://api.whatsapp.com/send?text={encoded_text}"

    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✉️ Share on Telegram", url=telegram_share_url),
            InlineKeyboardButton("💬 Share on WhatsApp", url=whatsapp_share_url)
        ]
    ])

    await update.message.reply_text(
        f"🎁 *HiringRadar Referral Program*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Get friends{college_context} to join and unlock *Premium Alerts* (Instant alerts instead of 2-hour delay)!\n\n"
        f"Invite *3 friends* → Get *7 days of Premium* free.\n\n"
        f"👤 Status: {premium_status}\n"
        f"👥 Successful Invites: *{stats['count']}*\n\n"
        f"🔗 *Your Invite Link:*\n"
        f"👉 [HiringRadar Invite Link]({ref_link})\n\n"
        f"Click below to share instantly with classmates! 🚀",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
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


async def update_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lets users update their stored resume PDF without re-doing onboarding."""
    context.user_data["updresume_mode"] = True
    await update.message.reply_text(
        "📄 *Update your resume*\n\n"
        "Send your resume as a PDF and we'll update it on file.\n"
        "All future match analyses will use the new version automatically.",
        parse_mode="Markdown"
    )


async def update_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/locations Pune, Mumbai, Remote`\n"
            "Or type `/locations Any` to clear filters and see jobs from all locations.",
            parse_mode="Markdown"
        )
        return
    locations = [loc.strip().lower() for loc in " ".join(context.args).split(",")]
    supabase.table("students").update({"preferred_locations": locations}).eq("chat_id", chat_id).execute()
    display_locs = ", ".join(locations).title()
    await update.message.reply_text(f"✅ *Preferred locations updated:* `{display_locs}`", parse_mode="Markdown")


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


async def _run_resume_analysis(context, chat_id: int, url_hash: str, resume_text: str, reply_msg):
    """
    Runs resume evaluation against a job using stored resume_text.
    Called directly when user already has a resume on file — skips upload prompt.
    """
    job_title = "Software Engineer"
    job_company = "Tech Firm"
    job_description = "Software engineering duties."
    try:
        res = supabase.table("jobs_cache").select("url, title, company, description").eq("is_active", True).execute()
        for j in (res.data or []):
            h = hashlib.md5(j["url"].encode()).hexdigest()[:10]
            if h == url_hash:
                job_title = j["title"]
                job_company = j["company"]
                job_description = j.get("description") or job_description
                break
    except Exception as e:
        print(f"_run_resume_analysis: job lookup failed: {e}")

    try:
        evaluation_text = await asyncio.to_thread(
            evaluate_resume_for_job, resume_text, job_title, job_company, job_description
        )
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        if admin_chat_id:
            buttons = [[
                InlineKeyboardButton("✅ Approve & Send", callback_data=f"admin:approve:{chat_id}:{url_hash}"),
                InlineKeyboardButton("❌ Reject / Clear", callback_data=f"admin:reject:{chat_id}:{url_hash}")
            ]]
            await context.bot.send_message(
                chat_id=int(admin_chat_id),
                text=(
                    f"📝 *Evaluation (stored resume)*\n\n"
                    f"👤 Candidate ID: `{chat_id}`\n"
                    f"🏢 *Target:* {job_company} — {job_title}\n\n"
                    f"--- REPORT ---\n{evaluation_text}\n--------------\n\n"
                    f"Approve or reject:"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    except Exception as e:
        print(f"_run_resume_analysis failed: {e}")
        await reply_msg.reply_text("⚠️ Error running analysis. Please try again.")


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()   # stops the loading spinner on the button
    _, feedback, url_hash = query.data.split(":", 2)
    chat_id = query.from_user.id
    
    if feedback == "check_match":
        # Check if the student already has a resume stored in their profile
        stored_res = supabase.table("students").select("resume_text").eq("chat_id", chat_id).execute()
        stored_resume = (stored_res.data or [{}])[0].get("resume_text") if stored_res.data else None

        if stored_resume:
            # Resume already on file — trigger analysis directly, no upload needed
            context.user_data["waiting_for_resume_hash"] = url_hash
            await query.message.reply_text(
                "⏳ *Running match analysis using your stored resume...*\n"
                "_(You can update your resume anytime with /updresume)_",
                parse_mode="Markdown"
            )
            # Kick off the Wizard-of-Oz analysis in background using stored resume
            asyncio.create_task(_run_resume_analysis(context, chat_id, url_hash, stored_resume, query.message))
            return

        # No resume on file — ask them to upload
        context.user_data["waiting_for_resume_hash"] = url_hash
        privacy_text = (
            "🔒 *HiringRadar Secure Match:*\n\n"
            "Please upload your resume in PDF format. "
            "_(We’ll save it so you never have to upload again!)_\n\n"
            "You can redact your email and phone number if you wish.\n\n"
            "_(Processing takes 5–10 minutes. We’ll ping you with your score here!)_"
        )
        await query.message.reply_text(privacy_text, parse_mode="Markdown")
        return

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


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles admin actions: approving and forwarding generated resume reports to students."""
    query = update.callback_query
    await query.answer()
    
    # Format: admin:action:chat_id:url_hash
    _, action, student_chat_id_str, url_hash = query.data.split(":", 3)
    student_chat_id = int(student_chat_id_str)
    
    # Fetch report from Supabase matching_queue
    report_text = None
    try:
        q_res = supabase.table("matching_queue").select("generated_report").eq("chat_id", student_chat_id).execute()
        if q_res.data:
            report_text = q_res.data[0].get("generated_report")
    except Exception as db_fetch_err:
        print(f"Failed to fetch report from DB: {db_fetch_err}")
        
    if action == "approve":
        if not report_text:
            await query.edit_message_text("⚠️ Report not found in Supabase matching_queue (may have been cleared).")
            return
            
        try:
            # 1. Forward the report to the student
            student_msg = (
                f"⚡ *HiringRadar SDE Match Score & Gap Analysis:*\n\n"
                f"{report_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _Verify these gaps and upgrade your projects to unlock direct SDE referral portals!_"
            )
            await context.bot.send_message(
                chat_id=student_chat_id,
                text=student_msg,
                parse_mode="Markdown"
            )
            
            # 2. Update queue status in Supabase
            supabase.table("matching_queue").update({"status": "completed"}).eq("chat_id", student_chat_id).execute()
            
            await query.edit_message_text(f"✅ *Report successfully sent to Candidate {student_chat_id}!*", parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to send approved report to candidate: {e}")
            await query.message.reply_text(f"❌ Error sending report: {e}")
            
    elif action == "reject":
        try:
            # Remove from queue
            supabase.table("matching_queue").delete().eq("chat_id", student_chat_id).execute()
            await query.edit_message_text("❌ *Report rejected and cleared from queue.*", parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to clear queue for reject: {e}")


async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forwards any user message to the admin for manual response."""
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
        
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text
    
    # Don't forward messages sent by the admin themselves!
    if str(chat_id) == str(admin_chat_id):
        return
        
    forward_text = (
        f"📬 *New message from {user.first_name} (@{user.username or 'none'})*\n"
        f"Chat ID: `{chat_id}`\n"
        f"Message:\n\n{text}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=int(admin_chat_id),
            text=forward_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to forward message to admin: {e}")


async def handle_wizard_resume_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wizard of Oz handler: parses PDF, runs evaluation, and requests admin approval."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    document = update.message.document
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    
    if not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("❌ Please upload your resume in PDF format.")
        return

    # /updresume mode: just save the resume, no match analysis
    if context.user_data.get("updresume_mode"):
        context.user_data.pop("updresume_mode", None)
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_resumes")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{chat_id}_update_resume.pdf")
        try:
            new_file = await context.bot.get_file(document.file_id)
            await new_file.download_to_drive(local_path)
            resume_text = await asyncio.to_thread(extract_resume_text_from_path, local_path)
            if os.path.exists(local_path):
                os.remove(local_path)
            if resume_text:
                supabase.table("students").update({"resume_text": resume_text}).eq("chat_id", chat_id).execute()
                await update.message.reply_text("✅ *Resume updated!* Your next match analysis will use this version.", parse_mode="Markdown")
            else:
                await update.message.reply_text("⚠️ Couldn't read that PDF. Please try a text-based PDF.")
        except Exception as e:
            print(f"updresume failed: {e}")
            await update.message.reply_text("⚠️ Something went wrong. Please try again.")
        return

    url_hash = context.user_data.get("waiting_for_resume_hash")
    if not url_hash:
        await update.message.reply_text("⚠️ Please click 'Check Resume Match' under a job card first to initiate matching.")
        return
        
    # Get job info from cache to print for admin.
    # WHY NOT select("*").execute(): that pulls the ENTIRE jobs_cache table into
    # memory just to find one row — O(N) on a table that grows every 5 min.
    # Instead we fetch all active jobs' (id, url) pairs and do the hash match
    # server-side by filtering on url. Since url is functionally unique per job
    # and we already have the 10-char hash, we can't filter directly on the DB
    # (the hash is computed client-side). However, we only need 3 columns, and
    # Supabase will use the index on `url` for equality.
    # Correct fix: store url_hash as a generated column in jobs_cache (migration
    # needed). Short-term: select only the 4 columns we need to keep payload small.
    job_info = "Unknown Job"
    job_title = "Software Engineer"
    job_company = "Tech Firm"
    job_description = "Software engineering duties."
    try:
        res = supabase.table("jobs_cache").select("url, title, company, description").eq("is_active", True).execute()
        for j in res.data:
            h = hashlib.md5(j["url"].encode()).hexdigest()[:10]
            if h == url_hash:
                job_info = f"*{j['company']}* — {j['title']}\n🔗 URL: {j['url']}"
                job_title = j["title"]
                job_company = j["company"]
                job_description = j.get("description") or "Software engineering duties."
                break
    except Exception as e:
        print(f"Failed to fetch job info for forward: {e}")

    # 1. Enforce Golden Rule: Check queue capacity
    queue_msg = "Our matching engine is processing your profile. Estimated time: 2-3 minutes. 🚀"
    try:
        # Check active pending queue size
        q_res = supabase.table("matching_queue").select("chat_id").eq("status", "pending").execute()
        pending_count = len(q_res.data or [])
        if pending_count > 0:
            wait_mins = pending_count * 5
            queue_msg = f"🔥 *HiringRadar Match Queue is busy:*\nThere are {pending_count} candidates ahead of you.\nEstimated wait time: {wait_mins} minutes. We will alert you the second your score is ready! ⏳"
    except Exception as q_err:
        print(f"Queue count failed: {q_err}")

    # Reply to student
    await update.message.reply_text(
        f"📥 *Resume received successfully!*\n\n{queue_msg}",
        parse_mode="Markdown"
    )

    # 2. Add to database queue
    try:
        supabase.table("matching_queue").upsert({
            "chat_id": chat_id,
            "job_url_hash": url_hash,
            "status": "pending"
        }, on_conflict="chat_id").execute()
    except Exception as ins_err:
        print(f"Failed to insert queue row: {ins_err}")

    # 3. Parse PDF locally (Zero-Trust download/parse/delete loop)
    # Use a path relative to this file so it works on any machine / deployment
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_resumes")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{chat_id}_wizard_resume.pdf")
    
    try:
        # Download PDF file
        new_file = await context.bot.get_file(document.file_id)
        await new_file.download_to_drive(local_path)
        
        # Read text and delete local file instantly
        resume_text = await asyncio.to_thread(extract_resume_text_from_path, local_path)
        if os.path.exists(local_path):
            os.remove(local_path)
            
        if not resume_text:
            await update.message.reply_text("⚠️ We couldn't extract text from this PDF. Please ensure it is not a scanned image.")
            return

        # Save resume to student profile so they never upload again
        try:
            supabase.table("students").update({"resume_text": resume_text}).eq("chat_id", chat_id).execute()
        except Exception as save_err:
            print(f"Failed to save resume to students table: {save_err}")

        # 4. Generate Strict Evaluation using Gemini
        evaluation_text = await asyncio.to_thread(
            evaluate_resume_for_job, resume_text, job_title, job_company, job_description
        )
        
        # Save generated report directly to Supabase matching_queue
        try:
            supabase.table("matching_queue").update({
                "generated_report": evaluation_text
            }).eq("chat_id", chat_id).execute()
        except Exception as db_report_err:
            print(f"Failed to save report to Supabase matching_queue: {db_report_err}")
        
        # 5. Notify Admin with generated evaluation and action buttons
        if admin_chat_id:
            admin_text = (
                f"📝 *New Evaluation Ready for Approval!*\n\n"
                f"👤 *Candidate:* {user.first_name} (@{user.username or 'none'}) (ID: `{chat_id}`)\n"
                f"🏢 *Target:* {job_company} — {job_title}\n\n"
                f"--- GENERATED REPORT ---\n"
                f"{evaluation_text}\n"
                f"------------------------\n\n"
                f"Click below to approve or reject this report:"
            )
            buttons = [
                [
                    InlineKeyboardButton("✅ Approve & Send", callback_data=f"admin:approve:{chat_id}:{url_hash}"),
                    InlineKeyboardButton("❌ Reject / Clear", callback_data=f"admin:reject:{chat_id}:{url_hash}")
                ]
            ]
            await context.bot.send_message(
                chat_id=int(admin_chat_id),
                text=admin_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
    except Exception as eval_err:
        print(f"Autopilot evaluation failed: {eval_err}")
        if os.path.exists(local_path):
            os.remove(local_path)
        await update.message.reply_text("⚠️ Error running AI grader. Our technical team is reviewing this.")
        
    # Clear waiting state
    context.user_data.pop("waiting_for_resume_hash", None)


# ── Main ───────────────────────────────────────────────────────────────────

async def on_startup(app):
    """Runs once after the bot initialises — safe place for async setup."""
    await app.bot.set_my_commands([
        BotCommand("jobs",       "See your latest job matches"),
        BotCommand("profile",    "View and update your profile"),
        BotCommand("share",      "Invite friends & get Premium Alerts 🎁"),
        BotCommand("skills",     "Update your skills"),
        BotCommand("roles",      "Update preferred roles"),
        BotCommand("locations",  "Update preferred locations"),
        BotCommand("experience", "Update job type preference"),
        BotCommand("updresume",  "Update your stored resume"),
        BotCommand("pause",      "Pause job alerts"),
        BotCommand("resume",     "Resume job alerts"),
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
            EXP_LEVEL:  [CallbackQueryHandler(get_exp_level, pattern="^exp:")],
            RESUME_UPLOAD: [
                CallbackQueryHandler(handle_onboarding_resume_choice, pattern="^onboard_resume:"),
                MessageHandler(filters.Document.PDF, handle_onboarding_resume_pdf),
            ],
            SKILLS:     [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_skills)
            ],
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
            CommandHandler("profile", profile),
            CommandHandler("jobs", jobs),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("share", share))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("skills", update_skills))
    app.add_handler(CommandHandler("roles", update_roles))
    app.add_handler(CommandHandler("locations", update_locations))
    app.add_handler(CommandHandler("experience", update_experience))
    app.add_handler(CommandHandler("updresume",  update_resume))
    app.add_handler(CommandHandler("pause", pause_alerts))
    app.add_handler(CommandHandler("resume", resume_alerts))
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^feedback:"))
    app.add_handler(CallbackQueryHandler(checkin_callback_handler, pattern="^checkin:"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin:"))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_wizard_resume_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin))

    # scrape_job: every 5 min — hits ATS APIs, writes to jobs_cache
    # alert_job:  every 2 min — reads from jobs_cache, sends Telegram messages
    # extract_skills_job: every 30 min — extracts JD technical skills using Gemini
    #
    # first=10 means scrape_job fires 10s after bot starts (cache gets populated).
    # first=30 gives scrape_job time to fill the cache before alerts run.
    app.job_queue.run_repeating(scrape_job,             interval=300,  first=10)
    app.job_queue.run_repeating(alert_job,              interval=120,  first=30)
    app.job_queue.run_repeating(extract_jd_skills_job,  interval=1800, first=60)

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

    # Verify local embeddings model loads correctly.
    # NOTE: embeddings run fully locally via sentence-transformers (BAAI/bge-small-en-v1.5).
    # There is no external API, no HF_TOKEN, no rate limits.
    print("[startup] Loading local embedding model (BAAI/bge-small-en-v1.5)...")
    test_result = get_embeddings_from_hf(["health check"])
    if test_result:
        print("[startup] ✅ Local embeddings online — semantic matching active.")
    else:
        print("[startup] ⚠️  Local embedding model failed to initialise — running in keyword-only fallback mode. Check sentence-transformers install.")

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

