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
from scraper import get_new_jobs, get_all_jobs, count_subscribers
from datetime import datetime
from supabase import create_client
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
model = SentenceTransformer('all-MiniLM-L6-v2')

# Conversation states
NAME, BRANCH, GRAD_YEAR, SKILLS, ROLES, JOB_TYPE = range(6)

# ── Helpers ──────────────────────────────────────────

def group_jobs(jobs):
    seen = {}
    for job in jobs:
        key = (job['company'], job['title'].strip(), job['location'])
        if key not in seen:
            seen[key] = {**job, 'count': 1}
        else:
            seen[key]['count'] += 1
    return list(seen.values())

def get_experience_tag(title):
    t = title.lower()
    if any(k in t for k in ["intern", "internship", "trainee", "campus", "fresher", "new grad"]):
        return "🌱 Fresher / Intern"
    if any(k in t for k in ["director", "vp ", "vice president", "head of", "chief"]):
        return "👑 Director / VP"
    if any(k in t for k in ["engineering manager", "tech lead", "team lead"]):
        return "🏆 Manager / Lead"
    if any(k in t for k in ["principal", "staff", "architect", "sde-3", "sde iii"]):
        return "⚡ Staff / Principal"
    if any(k in t for k in ["senior", "sr.", "sde-2", "sde ii"]):
        return "🚀 Senior (5+ yrs)"
    if any(k in t for k in ["junior", "jr.", "sde-1", "sde i", "associate engineer"]):
        return "🔵 Junior (0-2 yrs)"
    return "💼 Mid-level (2-5 yrs)"

def get_graduation_tag(title: str, grad_year: int) -> str:
    current_year = datetime.now().year
    years_to_grad = grad_year - current_year
    exp_tag = get_experience_tag(title)

    if years_to_grad <= 0:
        if any(x in exp_tag for x in ["Fresher", "Intern", "Junior"]):
            return "✅ Good for you"
        return "⚠️ May need experience"
    elif years_to_grad == 1:
        if any(x in exp_tag for x in ["Fresher", "Intern"]):
            return "✅ Good for you"
        return "⚠️ May need experience"
    else:
        if "Intern" in exp_tag:
            return "✅ Good for you"
        return "⚠️ Check requirements"

# ── Matching ───────────────────────────────────────────────────────────────

keyword_map = {
    "backend":   ["backend", "server", "api", "django", "node", "golang", "java", "spring"],
    "frontend":  ["frontend", "react", "vue", "angular", "ui", "javascript", "css"],
    "ml":        ["machine learning", "ml", "ai", "deep learning", "nlp", "data science"],
    "data":      ["data engineer", "data analyst", "analytics", "sql", "etl"],
    "devops":    ["devops", "sre", "cloud", "kubernetes", "docker", "infrastructure"],
    "fullstack": ["fullstack", "full stack", "full-stack"],
    "android":   ["android", "kotlin"],
    "ios":       ["ios", "swift"],
}

import re

def matches_role(title: str, roles: list) -> bool:
    if not roles:
        return True
    title_lower = title.lower()
    for role in roles:
        keywords = keyword_map.get(role, [role])
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", title_lower):
                return True
    return False


def is_internship(job: dict) -> bool:
    return any(k in job['title'].lower() for k in ["intern", "internship", "trainee"])

def filter_by_job_type(jobs: list, job_type: str) -> list:
    if job_type == "both" or not job_type:
        return jobs
    return [j for j in jobs if (job_type == "internship") == is_internship(j)]

# Common abbreviations to expand before embedding so the model understands them
_ABBREV = {
    "engg": "engineering", "eng": "engineering", "swe": "software engineer",
    "sde": "software development engineer", "dev": "developer",
    "ai": "artificial intelligence", "ml": "machine learning",
    "nlp": "natural language processing", "cv": "computer vision",
    "fe": "frontend", "be": "backend", "fs": "fullstack",
    "ios": "iOS mobile", "infra": "infrastructure",
    "intern": "internship", "jr": "junior", "sr": "senior",
}

def _expand_title(title: str) -> str:
    """Expand abbreviations in job titles before embedding."""
    words = title.lower().split()
    return " ".join(_ABBREV.get(w.strip(".,/-"), w) for w in words)

def _build_profile_text(student: dict) -> str:
    """Build a rich, descriptive profile string for better embedding signal."""
    roles = student.get("preferred_roles") or []
    skills = student.get("skills") or []
    job_type = student.get("job_type", "both")
    grad_year = student.get("graduation_year", datetime.now().year)
    current_year = datetime.now().year
    years_left = grad_year - current_year

    role_descriptions = {
        "backend": "backend server-side API development",
        "frontend": "frontend UI web development React",
        "ml": "machine learning AI deep learning data science NLP",
        "data": "data engineering analytics SQL pipeline ETL",
        "devops": "DevOps cloud infrastructure Kubernetes SRE",
        "fullstack": "fullstack web development frontend backend",
        "android": "Android mobile Kotlin app development",
        "ios": "iOS Swift mobile app development",
    }
    role_desc = " and ".join(role_descriptions.get(r, r) for r in roles)
    exp_level = "internship or entry-level fresher" if years_left >= 0 else "software engineer"

    return (
        f"I am a {exp_level} looking for {job_type} roles in {role_desc}. "
        f"My technical skills include {', '.join(skills)}. "
        f"I am interested in software engineering and technology positions."
    )

def match_jobs_for_student(student: dict, jobs: list, top_n=10, threshold=0.25):
    jobs = filter_by_job_type(jobs, student.get("job_type", "both"))
    roles = student.get("preferred_roles") or []
    jobs = [j for j in jobs if matches_role(j["title"], roles)]

    if not jobs:
        return []

    # Filter out overly senior roles for recent grads
    current_year = datetime.now().year
    grad_year = student.get("graduation_year", current_year)
    if grad_year >= current_year - 1:
        fresher_keywords = ["intern", "internship", "fresher", "junior", "graduate", "new grad", "sde-1", "sde1", "associate", "entry"]
        # Roles that are clearly NOT for fresh grads
        non_fresher_tags = {
            "👑 Director / VP", "🏆 Manager / Lead",
            "⚡ Staff / Principal", "🚀 Senior (5+ yrs)",
            "💼 Mid-level (2-5 yrs)"   # ← also exclude mid-level for fresh grads
        }
        # First pass: prefer explicit fresher/intern titles, ensuring no senior leak
        fresher_jobs = [
            j for j in jobs
            if any(k in j["title"].lower() for k in fresher_keywords)
            and get_experience_tag(j["title"]) not in non_fresher_tags
        ]
        # Second pass: include generic SWE titles (e.g. "Software Engineer") that
        # aren't explicitly senior — but only if no fresher-tagged jobs exist
        generic_ok = [
            j for j in jobs
            if get_experience_tag(j["title"]) not in non_fresher_tags
            and j not in fresher_jobs
        ]
        jobs = fresher_jobs if fresher_jobs else generic_ok
        if not jobs:
            return []


    # Build rich profile text and expand job title abbreviations before embedding
    profile_text = _build_profile_text(student)
    job_texts = [
        f"{_expand_title(j['title'])} at {j['company']} in {j.get('location', '')}".strip()
        for j in jobs
    ]

    profile_emb = model.encode([profile_text])
    job_embs = model.encode(job_texts)
    scores = cosine_similarity(profile_emb, job_embs)[0].tolist()

    # Role-match bonus: if the job clearly matches a preferred role, add +0.15
    for i, job in enumerate(jobs):
        if matches_role(job["title"], roles):
            scores[i] = min(1.0, scores[i] + 0.15)
        # Extra bonus for intern/fresher match when student is a recent grad
        if grad_year >= current_year - 1 and is_internship(job):
            scores[i] = min(1.0, scores[i] + 0.05)

    ranked = sorted(zip(jobs, scores), key=lambda x: x[1], reverse=True)
    results = [(job, score) for job, score in ranked if score >= threshold][:top_n]
    # Rescale raw cosine (realistic range ~0.25-0.75) to a display-friendly 0-100
    DISPLAY_FLOOR, DISPLAY_CEIL = 0.25, 0.75
    rescaled = []
    for job, score in results:
        display_score = (score - DISPLAY_FLOOR) / (DISPLAY_CEIL - DISPLAY_FLOOR)
        display_score = max(0.0, min(1.0, display_score))
        rescaled.append((job, round(display_score, 4)))
    return rescaled


def build_match_reason(job: dict, student: dict) -> str:
    """Build a short human-readable explanation of why a job matched."""
    reasons = []
    title_lower = job["title"].lower()
    skills = student.get("skills") or []
    matched_skills = [s for s in skills if s.lower() in title_lower]
    if matched_skills:
        reasons.append(f"Matches your {', '.join(matched_skills[:2])} skills")
    roles = student.get("preferred_roles") or []
    for role in roles:
        keywords = keyword_map.get(role, [])
        if any(k in title_lower for k in keywords):
            reasons.append(f"{role.capitalize()} role")
            break
    exp_tag = get_experience_tag(job["title"])
    grad_year = student.get("graduation_year", datetime.now().year)
    fit = get_graduation_tag(job["title"], grad_year)
    if "Good" in fit:
        reasons.append("Fresher-friendly")
    if not reasons:
        reasons.append("Matches your profile")
    return " · ".join(reasons)

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
    if res.data:
        student = res.data[0]
        paused_status = "⏸️ Paused" if student.get("paused") else "🟢 Active"
        await update.message.reply_text(
            f"👋 Welcome back, *{student['name']}*!\n\n"
            f"🔔 Alerts: {paused_status}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *What can I do?*\n"
            f"/jobs — see your latest matches\n"
            f"/profile — view \u0026 update your profile\n"
            f"/skills Python, ML — update skills\n"
            f"/roles backend, ml — update roles\n"
            f"/experience internship — update job type\n"
            f"/pause · /resume — toggle alerts\n"
            f"/stats — see active users",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Welcome to *HiringRadar!*\n\n"
        "Get real-time job alerts from top Indian product companies — "
        "Razorpay, CRED, Groww, PhonePe and more.\n\n"
        "Let's set up your profile in 5 quick steps 🚀\n\n"
        "*What's your name?*",
        parse_mode="Markdown"
    )
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text.strip()
    await update.message.reply_text("📚 What's your branch?\n\ne.g. CSE / ECE / IT / Mech / MBA")
    return BRANCH

async def get_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['branch'] = update.message.text.strip().upper()
    await update.message.reply_text("📅 What's your graduation year?\n\ne.g. 2025 / 2026 / 2027")
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
    roles = [r.strip().lower() for r in update.message.text.split(",")]
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

    try:
        supabase.table("students").upsert({
            "chat_id": chat_id,
            "name": data['name'],
            "branch": data['branch'],
            "graduation_year": data['graduation_year'],
            "skills": data['skills'],
            "preferred_roles": data['preferred_roles'],
            "job_type": data['job_type'],
        }).execute()
    except Exception as e:
        print(f"Supabase upsert failed: {e}")
        await update.message.reply_text("⚠️ Couldn't save profile right now. Try /start again.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Profile saved, *{data['name']}*!\n\n"
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

    await update.message.reply_text("🔍 Checking latest roles for you, hold on...")

    all_jobs = await asyncio.to_thread(get_all_jobs)
    grouped = group_jobs(all_jobs)
    # Get grad year for tagging
    grad_year = res.data[0].get("graduation_year", datetime.now().year) if res.data else datetime.now().year

    if res.data:
        matched = match_jobs_for_student(res.data[0], grouped)
        if matched:
            display_jobs = matched          # keep (job, score) pairs
            label = "matched"
        else:
            # Fallback: sample one job per company for variety
            import random
            sampled = {}
            for job in grouped:
                sampled.setdefault(job['company'], job)
            pool = list(sampled.values())
            random.shuffle(pool)
            display_jobs = pool[:5]
            label = "latest"
    else:
        import random
        sampled = {}
        for job in grouped:
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

# ── Alert scheduler ────────────────────────────────────────────────────────

async def send_alerts(context: ContextTypes.DEFAULT_TYPE):
    new_jobs = await asyncio.to_thread(get_new_jobs)
    if not new_jobs:
        return
    grouped_jobs = group_jobs(new_jobs)
    students = supabase.table("students").select("*").execute().data

    for student in students:
        if student.get("paused"):   # skip users who paused alerts
            continue
        matched = match_jobs_for_student(student, grouped_jobs)
        send_pairs = matched if matched else []
        if not send_pairs:
            continue
        grad_year = student.get("graduation_year", 2026)
        job_lines = [format_job_card(job, grad_year, score, student) for job, score in send_pairs]

        TELEGRAM_LIMIT = 4000
        chunks, current_chunk, current_len = [], [], 0
        chunk_pairs = []   # track (job, score) per chunk for buttons
        current_pairs = []
        for (job, score), line in zip(send_pairs, job_lines):
            if current_len + len(line) + 2 > TELEGRAM_LIMIT and current_chunk:
                chunks.append(current_chunk)
                chunk_pairs.append(current_pairs)
                current_chunk, current_len, current_pairs = [], 0, []
            current_chunk.append(line)
            current_pairs.append((job, score))
            current_len += len(line) + 2
        if current_chunk:
            chunks.append(current_chunk)
            chunk_pairs.append(current_pairs)

        try:
            for i, chunk in enumerate(chunks):
                part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                total = len(send_pairs)
                header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n━━━━━━━━━━━━━━━━━━━━━\n"
                digest = header + "\n\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━"
                # Build one feedback button per job in this chunk
                buttons = []
                for job, _ in chunk_pairs[i]:
                    url_hash = hashlib.md5(job["url"].encode()).hexdigest()[:10]
                    buttons.append([
                        InlineKeyboardButton("👍 Relevant", callback_data=f"feedback:relevant:{url_hash}"),
                        InlineKeyboardButton("👎 Not for me", callback_data=f"feedback:skip:{url_hash}"),
                    ])
                keyboard = InlineKeyboardMarkup(buttons)
                await context.bot.send_message(
                    chat_id=student['chat_id'],
                    text=digest,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=keyboard
                )
                await asyncio.sleep(0.1)
        except Forbidden:
            supabase.table("students").delete().eq("chat_id", student['chat_id']).execute()
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except (TimedOut, NetworkError) as e:
            # Transient delivery issue — wait a moment and retry once
            await asyncio.sleep(5)
            try:
                for i, chunk in enumerate(chunks):
                    part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                    total = len(send_pairs)
                    header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n━━━━━━━━━━━━━━━━━━━━━\n"
                    digest = header + "\n\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━"
                    buttons = []
                    for job, _ in chunk_pairs[i]:
                        url_hash = hashlib.md5(job["url"].encode()).hexdigest()[:10]
                        buttons.append([
                            InlineKeyboardButton("👍 Relevant", callback_data=f"feedback:relevant:{url_hash}"),
                            InlineKeyboardButton("👎 Not for me", callback_data=f"feedback:skip:{url_hash}"),
                        ])
                    keyboard = InlineKeyboardMarkup(buttons)
                    await context.bot.send_message(
                        chat_id=student['chat_id'],
                        text=digest,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                        reply_markup=keyboard
                    )
                    await asyncio.sleep(0.1)
            except Exception as retry_err:
                print(f"Failed to send to {student['chat_id']} after retry: {retry_err}")
        except Exception as e:
            print(f"Failed to send to {student['chat_id']}: {e}")

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
    valid = list(keyword_map.keys())  # backend, frontend, ml, data, devops, fullstack, android, ios
    if not context.args:
        await update.message.reply_text(f"Usage: /roles backend, ml\nValid options: {', '.join(valid)}")
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


# ── Main ───────────────────────────────────────────────────────────────────

async def on_startup(app):
    """Runs once after the bot initialises — safe place for async setup."""
    await app.bot.set_my_commands([
        BotCommand("jobs",       "See your latest job matches"),
        BotCommand("profile",    "View and update your profile"),
        BotCommand("skills",     "Update your skills"),
        BotCommand("roles",      "Update preferred roles"),
        BotCommand("experience", "Update job type preference"),
        BotCommand("pause",      "Pause job alerts"),
        BotCommand("resume",     "Resume job alerts"),
        BotCommand("stats",      "See active user count"),
        BotCommand("start",      "Set up or restart your profile"),
    ])

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            BRANCH:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_branch)],
            GRAD_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grad_year)],
            SKILLS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_skills)],
            ROLES:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_roles)],
            JOB_TYPE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_job_type)],
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
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("skills", update_skills))
    app.add_handler(CommandHandler("roles", update_roles))
    app.add_handler(CommandHandler("experience", update_experience))
    app.add_handler(CommandHandler("pause", pause_alerts))
    app.add_handler(CommandHandler("resume", resume_alerts))
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^feedback:"))
    app.job_queue.run_repeating(send_alerts, interval=300, first=10)

    print("🚀 HiringRadar backend engine online and scanning...")
    app.run_polling()
