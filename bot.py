import os
import asyncio
from telegram import Update
from telegram.error import Forbidden, RetryAfter
from telegram.ext import (
    ApplicationBuilder, CommandHandler, 
    MessageHandler, ContextTypes, 
    ConversationHandler, filters
)
from scraper import get_new_jobs, get_all_jobs, remove_subscriber, count_subscribers
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
    current_year = 2026
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

def matches_role(title: str, roles: list) -> bool:
    if not roles:
        return True
    title_lower = title.lower()
    for role in roles:
        keywords = keyword_map.get(role, [role])
        if any(k in title_lower for k in keywords):
            return True
    return False

def is_internship(job: dict) -> bool:
    return any(k in job['title'].lower() for k in ["intern", "internship", "trainee"])

def filter_by_job_type(jobs: list, job_type: str) -> list:
    if job_type == "both" or not job_type:
        return jobs
    return [j for j in jobs if (job_type == "internship") == is_internship(j)]

def match_jobs_for_student(student: dict, jobs: list, top_n=10, threshold=0.35):
    jobs = filter_by_job_type(jobs, student.get("job_type", "both"))
    roles = student.get("preferred_roles") or []
    jobs = [j for j in jobs if matches_role(j["title"], roles)]

    if not jobs:
        return []

    skills = ", ".join(student.get("skills") or [])
    role_str = ", ".join(roles)
    profile_text = f"{role_str} developer. Skills: {skills}."

    profile_emb = model.encode([profile_text])
    job_embs = model.encode([f"{j['title']} {j.get('description', '')}" for j in jobs])
    scores = cosine_similarity(profile_emb, job_embs)[0]

    ranked = sorted(zip(jobs, scores), key=lambda x: x[1], reverse=True)
    return [(job, score) for job, score in ranked if score >= threshold][:top_n]

def format_job_card(job: dict, grad_year: int = 2026) -> str:
    """Single place to format a job card — used everywhere"""
    count_label = f" _({job['count']} openings)_" if job.get('count', 1) > 1 else ""
    return (
        f"🏢 *{job['company']}*\n"
        f"💼 {job['title']}{count_label}\n"
        f"🏷️ {get_experience_tag(job['title'])}\n"
        f"🎓 {get_graduation_tag(job['title'], grad_year)}\n"
        f"📍 {job['location']}\n"
        f"[→ Apply Now]({job['url']})"
    )

# ── Onboarding conversation ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()
    if res.data:
        student = res.data[0]
        await update.message.reply_text(
            f"👋 Welcome back, *{student['name']}*!\n\n"
            f"Type /profile to see your profile or /jobs to see latest matches.",
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
    try:
        context.user_data['graduation_year'] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please send a valid year like 2026.")
        return GRAD_YEAR
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

    supabase.table("students").upsert({
        "chat_id": chat_id,
        "name": data['name'],
        "branch": data['branch'],
        "graduation_year": data['graduation_year'],
        "skills": data['skills'],
        "preferred_roles": data['preferred_roles'],
        "job_type": data['job_type'],
    }).execute()

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
    await update.message.reply_text(
        f"👤 *Your Profile*\n\n"
        f"🙋 Name: {s['name']}\n"
        f"🎓 Branch: {s['branch']} | {s['graduation_year']}\n"
        f"💻 Skills: {', '.join(s['skills'] or [])}\n"
        f"🎯 Roles: {', '.join(s['preferred_roles'] or [])}\n"
        f"💼 Job type: {s['job_type']}",
        parse_mode="Markdown"
    )

async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()

    all_jobs = get_all_jobs()
    grouped = group_jobs(all_jobs)

    # Get grad year for tagging
    grad_year = res.data[0].get("graduation_year", 2026) if res.data else 2026

    if res.data:
        matched = match_jobs_for_student(res.data[0], grouped)
        display_jobs = [job for job, score in matched] if matched else grouped[:5]
        label = "matched" if matched else "latest"
    else:
        display_jobs = grouped[:5]
        label = "latest"

    if not display_jobs:
        await update.message.reply_text("No open roles right now. You'll get an alert the moment something drops!")
        return

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
    new_jobs = get_new_jobs()
    if not new_jobs:
        return

    grouped_jobs = group_jobs(new_jobs)
    students = supabase.table("students").select("*").execute().data

    for student in students:
        matched = match_jobs_for_student(student, grouped_jobs)
        send_jobs = [job for job, score in matched] if matched else grouped_jobs

        if not send_jobs:
            continue

        grad_year = student.get("graduation_year", 2026)
        job_lines = [format_job_card(job, grad_year) for job in send_jobs]

        TELEGRAM_LIMIT = 4000
        chunks, current_chunk, current_len = [], [], 0
        for line in job_lines:
            if current_len + len(line) + 2 > TELEGRAM_LIMIT and current_chunk:
                chunks.append(current_chunk)
                current_chunk, current_len = [], 0
            current_chunk.append(line)
            current_len += len(line) + 2
        if current_chunk:
            chunks.append(current_chunk)

        try:
            for i, chunk in enumerate(chunks):
                part_info = f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else ""
                total = len(send_jobs)
                header = f"🔔 *HiringRadar — {total} New {'Opening' if total == 1 else 'Openings'}{part_info}*\n━━━━━━━━━━━━━━━━━━━━━\n"
                digest = header + "\n\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━"
                await context.bot.send_message(
                    chat_id=student['chat_id'],
                    text=digest,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                await asyncio.sleep(0.1)
        except Forbidden:
            supabase.table("students").delete().eq("chat_id", student['chat_id']).execute()
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            print(f"Failed to send to {student['chat_id']}: {e}")

# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("stats", stats))

    app.job_queue.run_repeating(send_alerts, interval=300, first=10)

    print("🚀 HiringRadar backend engine online and scanning...")
    app.run_polling()
