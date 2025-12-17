import os
import requests
from supabase import create_client
from datetime import datetime

# 1. SETUP
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# REPLACE THIS WITH THE URL YOU COPIED FROM MAKE.COM
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/cvuatijp1zs1g8w6hrheudl3saaxmnj3" 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"🤖 Scheduler waking up at {datetime.now()}...")

# 2. CHECK DB
response = supabase.table("social_posts").select("*").eq("status", "scheduled").execute()
posts = response.data

for post in posts:
    scheduled_time = datetime.strptime(str(post['scheduled_time']), "%Y-%m-%d %H:%M:%S")
    
    if datetime.utcnow() >= scheduled_time:
        print(f"🚀 Sending post {post['id']} to Make.com...")
        
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
                print(f"❌ Error: {r.text}")
                
        except Exception as e:
            print(f"❌ Connection Error: {e}")

    else:
        print(f"⏳ Post {post['id']} is not due yet.")
