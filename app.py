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

# 3. DASHBOARD WITH TABS
st.header("Content Dashboard")

# Create two tabs for better organization
tab1, tab2 = st.tabs(["📝 Drafts (Needs Review)", "📅 Scheduled (Waiting)"])

# --- TAB 1: DRAFTS ---
with tab1:
    # Fetch drafts
    response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
    drafts = response.data

    if not drafts:
        st.info("No drafts pending. Generate more above!")

    for post in drafts:
        # Placeholder for visual cleanup
        container = st.empty()
        with container.container():
            st.divider()
            col1, col2 = st.columns([1, 2])
            with col1:
                if post.get('image_url'):
                    st.image(post['image_url'], width=300)
            with col2:
                new_cap = st.text_area("Caption", post['caption'], key=f"cap_{post['id']}")
                st.write("📅 **When should this go out?**")
                d = st.date_input("Date", key=f"d_{post['id']}")
                t = st.time_input("Time (UTC)", key=f"t_{post['id']}")
                final_time = f"{d} {t}"
                
                if st.button("Approve & Schedule", key=f"btn_{post['id']}"):
                    supabase.table("social_posts").update({
                        "caption": new_cap,
                        "scheduled_time": final_time,
                        "status": "scheduled"
                    }).eq("id", post['id']).execute()
                    
                    st.success(f"Moved to Schedule!")
                    container.empty() # Remove from view
                    try: st.rerun() 
                    except: st.experimental_rerun()

# --- TAB 2: SCHEDULED ---
with tab2:
    st.write("These posts are queued for the robot.")
    # Fetch scheduled posts
    response = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute()
    scheduled = response.data
    
    if not scheduled:
        st.info("Nothing scheduled yet.")
        
    for post in scheduled:
        container = st.empty()
        with container.container():
            st.divider()
            col1, col2 = st.columns([1, 3])
            with col1:
                if post.get('image_url'):
                    st.image(post['image_url'], width=150)
            with col2:
                st.subheader(f"Due: {post['scheduled_time']} UTC")
                st.text(post['caption'])
                
                # CANCEL BUTTON
                if st.button("❌ Cancel & Edit", key=f"cancel_{post['id']}"):
                    # Move back to draft
                    supabase.table("social_posts").update({
                        "status": "draft"
                    }).eq("id", post['id']).execute()
                    
                    st.warning("Moved back to Drafts tab!")
                    container.empty()
                    try: st.rerun() 
                    except: st.experimental_rerun()

