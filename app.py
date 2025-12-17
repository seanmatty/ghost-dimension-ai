import streamlit as st
import openai
from supabase import create_client
import requests
import pandas as pd

# 1. SETUP: Connect to all your accounts
# We grab these passwords from the cloud settings later
openai.api_key = st.secrets["OPENAI_KEY"]
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
AYRSHARE_KEY = st.secrets["AYRSHARE_KEY"]

st.title("👻 Ghost Dimension AI Manager")

# 2. GENERATE NEW POSTS
with st.expander("Create New Content"):
    topic = st.text_input("What is the topic? (e.g. 'Haunted Asylum Episode')")
    if st.button("Generate Magic"):
        with st.spinner("AI is writing and painting..."):
            # A. Write Caption
            prompt = f"Write a scary, viral Instagram caption about {topic}. Use hashtags."
            gpt_resp = openai.ChatCompletion.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
            caption_text = gpt_resp.choices[0].message.content
            
            # B. Create Image
            img_resp = openai.Image.create(model="dall-e-3", prompt=f"Spooky paranormal photo of {topic}, cinematic", n=1)
            image_url = img_resp.data[0].url
            
            # C. Save to Database
            data = {"caption": caption_text, "image_url": image_url, "topic": topic, "status": "draft"}
            supabase.table("social_posts").insert(data).execute()
            st.success("Draft created! Check the Review tab below.")

# 3. REVIEW DASHBOARD
st.header("Weekly Review Queue")

# Fetch drafts from database
response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
posts = response.data

for post in posts:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(post['image_url'], width=300)
    with col2:
        new_cap = st.text_area("Caption", post['caption'], key=post['id'])
        if st.button("Approve & Post Now", key=f"btn_{post['id']}"):
            # D. Send to Social Media (Ayrshare)
            payload = {'post': new_cap, 'platforms': ['instagram', 'facebook'], 'mediaUrls': [post['image_url']]}
            headers = {'Authorization': f'Bearer {AYRSHARE_KEY}'}
            r = requests.post('https://app.ayrshare.com/api/post', json=payload, headers=headers)
            
            if r.status_code == 200:
                st.success("Posted to Instagram & Facebook!")
                supabase.table("social_posts").update({"status": "posted"}).eq("id", post['id']).execute()
                st.experimental_rerun()
            else:
                st.error("Error posting")