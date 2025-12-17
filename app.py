import streamlit as st
import hmac
from openai import OpenAI
from supabase import create_client
import requests
from datetime import datetime, time
from bs4 import BeautifulSoup
import random
import urllib.parse
from PIL import Image, ImageOps
import io
from streamlit_cropper import st_cropper 

# 1. PAGE CONFIG
st.set_page_config(page_title="Ghost Dimension AI", layout="wide")

# --- SECURITY GATE ---
def check_password():
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["ADMIN_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False): return True
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state: st.error("😕 Password incorrect")
    return False

if not check_password(): st.stop()

# 2. SETUP
client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
MAKE_WEBHOOK_URL = st.secrets["MAKE_WEBHOOK_URL"]

# --- HELPER FUNCTIONS ---
def get_best_time_for_day(target_date):
    day_name = target_date.strftime("%A")
    response = supabase.table("strategy").select("best_hour").eq("day", day_name).execute()
    if response.data: return time(response.data[0]['best_hour'], 0)
    return time(20, 0)

def scrape_website(url):
    if not url.startswith("http"): url = "https://" + url
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        text = ' '.join([p.text for p in soup.find_all('p')])
        return text[:6000] if len(text) > 50 else None
    except: return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    if response.data: return "\n".join([f"- {item['fact_summary']}" for item in response.data])
    return "No knowledge yet."

st.title("👻 Ghost Dimension AI Manager")

# 3. CONTENT CREATION AREA
tab_gen, tab_upload = st.tabs(["✨ Generate from Scratch", "📸 Upload & Auto-Caption"])

# --- TAB A: GENERATE FROM SCRATCH ---
with tab_gen:
    with st.expander("Teach & Generate", expanded=True):
        col_teach, col_create = st.columns([1, 1])
        
        with col_teach:
            st.subheader("Teach New Knowledge")
            learn_url = st.text_input("Website URL")
            if st.button("Analyze & Learn"):
                with st.spinner("Reading..."):
                    raw_text = scrape_website(learn_url)
                    if raw_text:
                        prompt = f"Extract 3-5 facts about 'Ghost Dimension' from this:\n{raw_text}"
                        resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.success("Facts learned! Approve below.")
                        st.rerun()
                    else: st.error("Could not read site.")

        with col_create:
            st.subheader("Generate Content")
            if st.button("🎲 Suggest Topic"):
                knowledge = get_brand_knowledge()
                prompt = f"Context: {knowledge}. Suggest ONE spooky social media topic."
                resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                st.session_state['suggested_topic'] = resp.choices[0].message.content
                st.rerun()

            topic = st.text_area("Topic:", value=st.session_state.get('suggested_topic', ''), height=100)
            
            if st.button("Generate Post", type="primary"):
                with st.spinner("Creating magic..."):
                    try:
                        knowledge = get_brand_knowledge()
                        p_cap = f"Role: Social Manager for Ghost Dimension. Context: {knowledge}. Write scary caption about: {topic}."
                        cap_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": p_cap}])
                        caption = cap_resp.choices[0].message.content
                        
                        # AI Images are always square, so we use them RAW
                        img_resp = client.images.generate(model="dall-e-3", prompt=f"Paranormal photo of {topic}. Night vision green tint, grainy CCTV style.", size="1024x1024")
                        image_url = img_resp.data[0].url
                        
                        supabase.table("social_posts").insert({"caption": caption, "image_url": image_url, "topic": topic, "status": "draft"}).execute()
                        st.success("Draft Created!")
                    except Exception as e: st.error(f"Error: {e}")

# --- TAB B: UPLOAD & MANUAL CROP ---
with tab_upload:
    c1, c2 = st.columns([1, 1])
    
    with c1:
        st.subheader("1. Upload & Crop")
        
        uploaded_file = st.file_uploader("Choose a photo...", type=['jpg', 'png', 'jpeg'])
        
        if uploaded_file:
            # Load the user's image
            image = Image.open(uploaded_file)
            image = ImageOps.exif_transpose(image) # Fix orientation
            
            st.write("👇 **Drag the box to select your square area:**")
            
            # --- THE CROPPER WIDGET ---
            cropped_img = st_cropper(
                image,
                aspect_ratio=(1, 1),    # Forces a Square
                box_color='#FF0000',    # Red Box
                should_resize_image=True
            )
            
            st.write("Preview:")
            st.image(cropped_img, width=150)
            
            if st.button("✅ Confirm & Save to Library", type="primary"):
                with st.spinner("Saving perfect crop..."):
                    try:
                        if cropped_img.mode != "RGB":
                            cropped_img = cropped_img.convert("RGB")
                        
                        final_img = cropped_img.resize((1080, 1080))
                        
                        buf = io.BytesIO()
                        final_img.save(buf, format="JPEG", quality=95)
                        byte_data = buf.getvalue()
                        
                        filename = f"crop_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        supabase.storage.from_("uploads").upload(f"evidence_{filename}", byte_data, {"content-type": "image/jpeg"})
                        final_url = supabase.storage.from_("uploads").get_public_url(f"evidence_{filename}")
                        
                        supabase.table("uploaded_images").insert({"file_url": final_url, "filename": filename}).execute()
                        
                        st.success("Saved to Library! -> Check the right side.")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Save failed: {e}")

    with c2:
        st.subheader("2. Library & Generate")
        st.write("📂 **Evidence Library (Recent 9)**")
        
        library = supabase.table("uploaded_images").select("*").order("created_at", desc=True).limit(9).execute().data
        
        if library:
            # Display grid of uploaded images WITH BUTTONS
            cols = st.columns(2) # 2 columns is wider/cleaner
            for idx, img in enumerate(library):
                with cols[idx % 2]:
                    with st.container(border=True):
                        st.image(img['file_url'], use_column_width=True)
                        
                        # BUTTON 1: CREATE DRAFT (Specific to this image)
                        if st.button("✨ Create Draft", key=f"gen_{img['id']}", type="primary"):
                            with st.spinner("AI is analyzing this photo..."):
                                try:
                                    raw_url = img['file_url']
                                    knowledge = get_brand_knowledge()
                                    prompt = f"Role: Ghost Dimension social manager. Describe this spooky image. Context: {knowledge}. Write caption."
                                    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": raw_url}}]}], max_tokens=300)
                                    caption = response.choices[0].message.content
                                    
                                    supabase.table("social_posts").insert({
                                        "caption": caption, 
                                        "image_url": raw_url, 
                                        "topic": "Uploaded Evidence Analysis", 
                                        "status": "draft"
                                    }).execute()
                                    st.success("Draft Created! Check Dashboard.")
                                except Exception as e: st.error(f"Error: {e}")

                        # BUTTON 2: DELETE
                        if st.button("🗑️ Delete", key=f"del_{img['id']}"):
                            supabase.table("uploaded_images").delete().eq("id", img['id']).execute()
                            st.rerun()

        else:
            st.info("Upload and crop an image on the left to start.")

# 4. DASHBOARD
st.divider()
st.header("📲 Content Dashboard")
dash_t1, dash_t2, dash_t3 = st.tabs(["📝 Drafts", "📅 Scheduled", "📜 History"])

# --- DASHBOARD LOGIC ---
with dash_t1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").execute().data
    if not drafts: st.info("No drafts pending.")
    for post in drafts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1:
                if post.get('image_url'): st.image(post['image_url'], use_column_width=True)
            with col2:
                new_cap = st.text_area("Caption", post['caption'], height=150, key=f"cap_{post['id']}")
                d_col, t_col = st.columns(2)
                with d_col: d = st.date_input("Date", key=f"d_{post['id']}")
                suggested = get_best_time_for_day(d)
                with t_col: t = st.time_input(f"Time (Rec: {suggested})", value=suggested, key=f"t_{post['id']}")
                final_time = f"{d} {t}"
                
                st.write("---")
                b1, b2, b3 = st.columns([1, 1, 1])
                with b1:
                    if st.button("📅 Schedule", key=f"sch_{post['id']}", type="primary"):
                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": final_time, "status": "scheduled"}).eq("id", post['id']).execute()
                        st.success("Scheduled!")
                        st.rerun()
                with b2:
                    if st.button("🚀 Post NOW", key=f"now_{post['id']}"):
                        if not post.get('image_url'):
                             st.error("❌ Draft has no image!")
                        else:
                            with st.spinner("Posting..."):
                                payload = {"image_url": post['image_url'], "caption": new_cap}
                                try:
                                    r = requests.post(MAKE_WEBHOOK_URL, json=payload)
                                    if r.status_code == 200:
                                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute()
                                        st.success("Posted!")
                                        st.rerun()
                                    else: st.error(f"Make.com Error: {r.text}")
                                except Exception as e: st.error(f"Connection Failed: {e}")
                with b3:
                    if st.button("🗑️ Delete", key=f"del_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute()
                        st.rerun()

with dash_t2:
    scheduled = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    if not scheduled: st.info("Nothing scheduled.")
    for post in scheduled:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1: st.image(post['image_url'], width=100)
            with c2:
                st.subheader(f"Due: {post['scheduled_time']} UTC")
                st.text(post['caption'][:100] + "...")
                if st.button("❌ Cancel", key=f"cancel_{post['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", post['id']).execute()
                    st.rerun()

with dash_t3:
    history = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(20).execute().data
    if not history: st.info("No history yet.")
    for post in history:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1: st.image(post['image_url'], width=100)
            with c2:
                st.write(f"**Posted on:** {post['scheduled_time']}")
                with st.expander("View Caption"): st.write(post['caption'])
