import os
import psycopg2
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# Get DB URLs from environment or prompt the user
railway_url = os.getenv("DATABASE_URL")  # Current Railway URL
supabase_url = os.getenv("SUPABASE_DB_URL")  # New Supabase URI

print("🚀 HiringRadar Database Migrator: Railway -> Supabase")

if not railway_url:
    railway_url = input("Enter your Railway DATABASE_URL: ").strip()

if not supabase_url:
    print("\nTo get your Supabase Connection String:")
    print("1. Go to Supabase Dashboard -> Project Settings -> Database")
    print("2. Copy the Connection String (URI format under Connection Pooling/Direct Connection)")
    print("3. Don't forget to replace [your-password] with your actual Supabase DB password!\n")
    supabase_url = input("Enter your Supabase Connection String (URI): ").strip()

try:
    print("\n⚡ Connecting to Railway database...")
    conn_railway = psycopg2.connect(railway_url)
    cur_railway = conn_railway.cursor()
    print("✅ Connected to Railway!")
except Exception as e:
    print(f"❌ Failed to connect to Railway: {e}")
    exit(1)

try:
    print("\n⚡ Connecting to Supabase database...")
    conn_supabase = psycopg2.connect(supabase_url)
    cur_supabase = conn_supabase.cursor()
    print("✅ Connected to Supabase!")
except Exception as e:
    print(f"❌ Failed to connect to Supabase: {e}")
    conn_railway.close()
    exit(1)

# --- 1. Migrate subscribers table ---
try:
    print("\n📦 Migrating 'subscribers' table...")
    # Fetch from Railway
    cur_railway.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'subscribers');")
    if cur_railway.fetchone()[0]:
        cur_railway.execute("SELECT chat_id FROM subscribers;")
        subscribers = cur_railway.fetchall()
        print(f"  Found {len(subscribers)} subscribers on Railway.")

        # Create table on Supabase
        cur_supabase.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id BIGINT PRIMARY KEY);")
        
        # Insert into Supabase
        inserted = 0
        for row in subscribers:
            cur_supabase.execute(
                "INSERT INTO subscribers (chat_id) VALUES (%s) ON CONFLICT DO NOTHING;",
                (row[0],)
            )
            inserted += cur_supabase.rowcount
        conn_supabase.commit()
        print(f"  ✅ Successfully migrated {inserted} subscribers to Supabase!")
    else:
        print("  ⚠️ 'subscribers' table does not exist on Railway (skipping).")
except Exception as e:
    print(f"  ❌ Error migrating subscribers: {e}")
    conn_supabase.rollback()

# --- 2. Migrate seen_jobs table ---
try:
    print("\n📦 Migrating 'seen_jobs' table...")
    # Fetch from Railway
    cur_railway.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'seen_jobs');")
    if cur_railway.fetchone()[0]:
        cur_railway.execute("SELECT url FROM seen_jobs;")
        seen_jobs = cur_railway.fetchall()
        print(f"  Found {len(seen_jobs)} seen jobs on Railway.")

        # Create table on Supabase
        cur_supabase.execute("CREATE TABLE IF NOT EXISTS seen_jobs (url TEXT PRIMARY KEY);")
        
        # Insert into Supabase
        inserted = 0
        for row in seen_jobs:
            cur_supabase.execute(
                "INSERT INTO seen_jobs (url) VALUES (%s) ON CONFLICT DO NOTHING;",
                (row[0],)
            )
            inserted += cur_supabase.rowcount
        conn_supabase.commit()
        print(f"  ✅ Successfully migrated {inserted} seen jobs to Supabase!")
    else:
        print("  ⚠️ 'seen_jobs' table does not exist on Railway (skipping).")
except Exception as e:
    print(f"  ❌ Error migrating seen_jobs: {e}")
    conn_supabase.rollback()

# Close connections
cur_railway.close()
conn_railway.close()
cur_supabase.close()
conn_supabase.close()

print("\n🎉 Database migration finished successfully!")
