import streamlit as st
from openai import OpenAI # <--- CHANGED THIS
from supabase import create_client
import requests

# 1. SETUP: Connect to all your accounts
# Initialize the OpenAI Client (New v1.0 requirement)
client = OpenAI(api_key=st.secrets["OPENAI_KEY"]) # <--- CHANGED THIS

# Connect Supabase
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
AYRSHARE_KEY = st.secrets["AYRSHARE_KEY"]

st.title("👻 Ghost Dimension AI Manager")

# 2. GENERATE NEW POSTS
with st.expander("Create New Content"):
    topic = st.text_input("What is the topic? (e.g. 'Haunted Asylum Episode')")
    if st.button("Generate Magic"):
        with st.spinner("AI is writing and painting..."):
            try:
                # A. Write Caption (UPDATED CODE)
                prompt = f"Write a scary, viral Instagram caption about {topic}. Use hashtags."
                gpt_resp = client.chat.completions.create( # <--- CHANGED THIS
                    model="gpt-4", 
                    messages=[{"role": "user", "content": prompt}]
                )
                caption_text = gpt_resp.choices[0].message.content
                
                # B. Create Image (UPDATED CODE)
                # Note: We use the client.images.generate method now
                img_resp = client.images.generate( # <--- CHANGED THIS
                    model="dall-e-3", 
                    prompt=f"Realistic paranormal investigation photo of {topic}. Style: Night vision green tint, grainy CCTV footage look, dramatic lighting, shadows, 4k resolution, in the style of the TV show Ghost Dimension.", 
                    n=1,
                    size="1024x1024"
                )
                image_url = img_resp.data[0].url
                
                # C. Save to Database
                data = {"caption": caption_text, "image_url": image_url, "topic": topic, "status": "draft"}
                supabase.table("social_posts").insert(data).execute()
                st.success("Draft created! Check the Review tab below.")
                
            except Exception as e:
                st.error(f"An error occurred: {e}")

# 3. REVIEW DASHBOARD
st.header("Weekly Review Queue")

# Fetch drafts from database
try:
    response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
    posts = response.data

    if not posts:
        st.info("No drafts waiting. Go generate some above!")

    for post in posts:
        st.divider() # Adds a nice line between posts
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(post['image_url'], width=300)
        with col2:
            new_cap = st.text_area("Caption", post['caption'], key=post['id'])
            if st.button("Approve & Post Now", key=f"btn_{post['id']}"):
                # D. Send to Social Media (Ayrshare)
                payload = {
                    'post': new_cap, 
                    'platforms': ['instagram', 'facebook'], 
                    'mediaUrls': [post['image_url']]
                }
                headers = {'Authorization': f'Bearer {AYRSHARE_KEY}'}
                r = requests.post('https://app.ayrshare.com/api/post', json=payload, headers=headers)
                
                if r.status_code == 200:
                    st.success("Posted to Instagram & Facebook!")
                    # Mark as posted so it vanishes from the list
                    supabase.table("social_posts").update({"status": "posted"}).eq("id", post['id']).execute()
                    st.rerun() # Refreshes the page
                else:
                    st.error(f"Error posting: {r.text}")
except Exception as e:
    st.error(f"Database error: {e}")
