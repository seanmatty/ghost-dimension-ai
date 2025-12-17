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

# Helper function to handle refreshing the page
def reload_page():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

# Fetch drafts from database
try:
    response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
    posts = response.data

    if not posts:
        st.success("🎉 All caught up! No drafts waiting.")
        st.info("Go to the 'Create New Content' section above to generate more.")

    for post in posts:
        # We create a placeholder. This lets us wipe just this post from the screen later.
        post_container = st.empty()
        
        with post_container.container():
            st.divider()
            col1, col2 = st.columns([1, 2])
            
            with col1:
                if post.get('image_url'):
                    st.image(post['image_url'], width=300)
                else:
                    st.warning("No image generated")
                
            with col2:
                new_cap = st.text_area("Caption", post['caption'], key=f"cap_{post['id']}")
                
                # Scheduling Inputs
                st.write("📅 **Schedule:**")
                d = st.date_input("Date", key=f"d_{post['id']}")
                t = st.time_input("Time (UTC)", key=f"t_{post['id']}")
                iso_date = f"{d}T{t}Z"
                
                if st.button("Approve & Schedule", key=f"btn_{post['id']}"):
                    with st.spinner("Talking to Ayrshare..."):
                        # 1. Prepare Payload
                        payload = {
                            'post': new_cap, 
                            'platforms': ['instagram', 'facebook'], 
                            'mediaUrls': [post['image_url']],
                            'scheduleDate': iso_date
                        }
                        headers = {'Authorization': f'Bearer {AYRSHARE_KEY}'}
                        
                        # 2. Send to API
                        r = requests.post('https://app.ayrshare.com/api/post', json=payload, headers=headers)
                        
                        if r.status_code == 200:
                            # 3. Success! Update Database
                            supabase.table("social_posts").update({"status": "scheduled"}).eq("id", post['id']).execute()
                            
                            # 4. VISUAL CLEANUP
                            st.success("✅ Scheduled successfully!")
                            post_container.empty() # <--- This instantly hides the post UI
                            
                            # 5. Reload the whole page to be sure
                            reload_page()
                            
                        else:
                            st.error(f"❌ Error from Ayrshare: {r.text}")

except Exception as e:
    st.error(f"System Error: {e}")
