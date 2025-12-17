import os
import requests
from supabase import create_client
from datetime import datetime

# 1. Setup Connections
# Note: On GitHub, we use os.environ to get secrets
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
AYRSHARE_KEY = os.environ.get("AYRSHARE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"🤖 Scheduler waking up at {datetime.now()}...")

# 2. Find posts that are 'scheduled' AND the time has passed
# We get all scheduled posts, then filter in Python for simplicity
response = supabase.table("social_posts").select("*").eq("status", "scheduled").execute()
posts = response.data

for post in posts:
    # Check if time is due
    # (Assuming stored format is YYYY-MM-DD HH:MM:SS)
    scheduled_time = datetime.strptime(str(post['scheduled_time']), "%Y-%m-%d %H:%M:%S")
    
    if datetime.utcnow() >= scheduled_time:
        print(f"🚀 Posting post {post['id']}...")
        
        # 3. Send to Ayrshare (Post NOW mode)
        payload = {
            'post': post['caption'], 
            'platforms': ['instagram', 'facebook'], 
            'mediaUrls': [post['image_url']]
            # No 'scheduleDate' here, so it posts immediately!
        }
        headers = {'Authorization': f'Bearer {AYRSHARE_KEY}'}
        
        r = requests.post('https://app.ayrshare.com/api/post', json=payload, headers=headers)
        
        if r.status_code == 200:
            print("✅ Success!")
            # Mark as posted
            supabase.table("social_posts").update({"status": "posted"}).eq("id", post['id']).execute()
        else:
            print(f"❌ Failed: {r.text}")
    else:
        print(f"⏳ Post {post['id']} is not due yet (Due: {scheduled_time})")
