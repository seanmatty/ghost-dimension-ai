import streamlit as st
import hmac
from openai import OpenAI
from supabase import create_client
import requests
from datetime import datetime, time

# 1. PAGE CONFIG
st.set_page_config(page_title="Ghost Dimension AI", layout="wide")

# --- SECURITY GATE ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["ADMIN_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input("Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False

if not check_password():
    st.stop()
# ---------------------

# 2. SETUP
client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
AYRSHARE_KEY = st.secrets["AYRSHARE_KEY"]

# --- HELPER: BRAIN LOGIC ---
def get_best_time_for_day(target_date):
    """
    1. Looks at the date (e.g. 2023-10-31).
    2. Figures out the Day Name (e.g. 'Tuesday').
    3. Asks Database for the best hour.
    """
    day_name = target_date.strftime("%A") # e.g. "Monday"
    
    # Query the Strategy Table
    response = supabase.table("strategy").select("best_hour").eq("day", day_name).execute()
    
    if response.data:
        # If we found a rule (e.g. 19), return that time
        best_hour = response.data[0]['best_hour']
        return time(best_hour, 0) # Returns 19:00:00
    else:
        # Default to 8 PM if no rule found
        return time(20, 0)

st.title("👻 Ghost Dimension AI Manager")

# 3. GENERATE NEW POSTS
with st.expander("Create New Content", expanded=True):
    topic = st.text_input("What is the topic? (e.g. 'Haunted Asylum Episode')")
    if st.button("Generate Magic", type="primary"):
        with st.spinner("AI is writing and painting..."):
            try:
                # A. Write Caption
                prompt = f"Write a scary, viral Instagram caption about {topic}. Use hashtags."
                gpt_resp = client.chat.completions.create(
                    model="gpt-4", 
                    messages=[{"role": "user", "content": prompt}]
                )
                caption_text = gpt_resp.choices[0].message.content
                
                # B. Create Image
                img_resp = client.images.generate(
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

# 4. DASHBOARD
st.header("Content Dashboard")
tab1, tab2 = st.tabs(["📝 Drafts (Needs Review)", "📅 Scheduled (Waiting)"])

# --- TAB 1: DRAFTS ---
with tab1:
    response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
    drafts = response.data

    if not drafts:
        st.info("No drafts pending. Generate more above!")

    for post in drafts:
        container = st.empty()
        with container.container():
            st.divider()
            col1, col2 = st.columns([1, 2])
            
            with col1:
                if post.get('image_url'):
                    st.image(post['image_url'], use_column_width=True)
            
            with col2:
                new_cap = st.text_area("Caption", post['caption'], height=200, key=f"cap_{post['id']}")
                st.write("📅 **Optimization Strategy**")
                
                d_col, t_col = st.columns(2)
                with d_col:
                    # Default to Today
                    d = st.date_input("Date", key=f"d_{post['id']}")
                
                # --- AI TIME SUGGESTION ---
                # We calculate the suggested time based on the date selected above
                suggested_time = get_best_time_for_day(d)
                
                with t_col:
                    t = st.time_input(f"Time (AI suggests {suggested_time})", value=suggested_time, key=f"t_{post['id']}")
                
                final_time = f"{d} {t}"
                
                st.write("---")
                btn_col1, btn_col2 = st.columns(2)
                
                with btn_col1:
                    if st.button("✅ Approve & Schedule", key=f"btn_{post['id']}", type="primary"):
                        supabase.table("social_posts").update({
                            "caption": new_cap, 
                            "scheduled_time": final_time, 
                            "status": "scheduled"
                        }).eq("id", post['id']).execute()
                        st.success("Moved to Schedule!")
                        container.empty()
                        st.rerun()
                
                with btn_col2:
                    if st.button("🗑️ Delete Draft", key=f"del_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute()
                        st.error("Draft Deleted.")
                        container.empty()
                        st.rerun()

# --- TAB 2: SCHEDULED ---
with tab2:
    st.write("These posts are queued for the robot.")
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
                
                if st.button("❌ Cancel & Edit", key=f"cancel_{post['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", post['id']).execute()
                    st.warning("Moved back to Drafts tab!")
                    container.empty()
                    st.rerun()
