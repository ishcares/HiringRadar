from db import supabase

try:
    # 1. Run migration to add remote_class column to jobs_cache (if it doesn't exist)
    # Supabase Python client doesn't support raw SQL runs directly, so we run a RPC call if it exists,
    # or we can simply verify it exists by attempting to update it or read it.
    # In Supabase, if we try to select/update a column that doesn't exist, it throws postgrest error.
    # Let's perform a simple check/update to test. If we need to add the column, we can do it via a simple SQL migration.
    # Actually, let's run a select with it:
    supabase.table("jobs_cache").select("remote_class").limit(1).execute()
    print("Column 'remote_class' already exists in jobs_cache!")
except Exception as e:
    print(f"Error checking/adding column (you might need to run: ALTER TABLE jobs_cache ADD COLUMN remote_class TEXT DEFAULT 'india'; in Supabase SQL editor): {e}")

try:
    # 2. Perform the one-time cleanup to delete DoD SkillBridge listings from jobs_cache
    res = supabase.table("jobs_cache").delete().ilike("title", "%skillbridge%").execute()
    deleted_count = len(res.data) if res.data else 0
    print(f"Cleaned up {deleted_count} DoD SkillBridge listings from jobs_cache!")
except Exception as e:
    print(f"Failed to delete SkillBridge listings: {e}")
