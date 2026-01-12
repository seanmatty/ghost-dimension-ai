import os
import requests
from supabase import create_client
from datetime import datetime

# 1. SETUP
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/cvuatijp1zs1g8w6hrheudl3saaxmnj3"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"🤖 Scheduler waking up at {datetime.utcnow()} UTC...")

# 2. CHECK DB
response = supabase.table("social_posts").select("*").eq("status", "scheduled").execute()
posts = response.data

if not posts:
    print("💤 No scheduled posts found.")

for post in posts:
    # 🟢 FIX: Handle both "2026-01-12 12:00:00" AND "2026-01-12T12:00:00"
    raw_time = str(post['scheduled_time']).replace('T', ' ')
    # Remove potential timezone info (+00:00) to keep it simple
    if '+' in raw_time:
        raw_time = raw_time.split('+')[0]
    
    try:
        # Now it will always look like "YYYY-MM-DD HH:MM:SS"
        scheduled_time = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
        
        print(f"🔎 Checking post {post['id']} (Due: {scheduled_time})...")
    
        if datetime.utcnow() >= scheduled_time:
            print(f"🚀 IT IS TIME! Sending post {post['id']} to Make.com...")
            
            # 3. SEND TO MAKE.COM
            payload = {
                "image_url": post['image_url'],
                "caption": post['caption']
            }
            
            try:
                r = requests.post(MAKE_WEBHOOK_URL, json=payload)
                
                if r.status_code == 200:
                    print("✅ Sent successfully!")
                    # Mark as posted
                    supabase.table("social_posts").update({"status": "posted"}).eq("id", post['id']).execute()
                else:
                    print(f"❌ Make.com Error: {r.text}")
                    
            except Exception as e:
                print(f"❌ Connection Error: {e}")

        else:
            print(f"⏳ Not due yet (Current UTC: {datetime.utcnow()})")

    except ValueError as e:
        print(f"⚠️ Date Format Error for post {post['id']}: {e}")
