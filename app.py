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
    # Disguise as real browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        page = requests.get(url, headers=headers, timeout=10)
        if page.status_code != 200: return None
        soup = BeautifulSoup(page.content, "html.parser")
        
        # Try paragraphs first
        text = ' '.join([p.text for p in soup.find_all('p')])
        # If empty, try all text
        if len(text) < 100: text = soup.get_text(separator=' ', strip=True)
            
        return text[:8000] if len(text) > 50 else None
    except: return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    if response.data: return "\n".join([f"- {item['fact_summary']}" for item in response.data])
    return "No knowledge yet."

def get_caption_prompt(style, topic_or_desc, context):
    base_prompt = f"Role: Social Media Manager for 'Ghost Dimension'. Context: {context}. Topic: {topic_or_desc}. "
    strategies = {
        "🔥 Viral / Debate (Ask Questions)": "Write a short, punchy caption. The goal is to start a fight in the comments. Ask 'Real or Fake?'. Ask 'What would you do?'. End with a question.",
        "🕵️ Investigator (Analyze Detail)": "Write a caption that sounds like a paranormal investigator analyzing evidence. Ask the user to zoom in. Focus on details.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence mini horror story. Be atmospheric. End on a cliffhanger.",
        "😱 Pure Panic (Short & Scary)": "Write a very short, terrified caption. Use uppercase words for emphasis. Use emojis like ⚠️👻."
    }
    instruction = strategies.get(style, strategies["🔥 Viral / Debate (Ask Questions)"])
    return f"{base_prompt} \n\nSTRATEGY: {instruction} \n\nMake it sound human, not AI."

st.title("👻 Ghost Dimension AI Manager")

# 3. CONTENT CREATION AREA
tab_gen, tab_upload = st.tabs(["✨ Generate from Scratch", "📸 Upload & Auto-Caption"])

# --- TAB A: GENERATE FROM SCRATCH ---
with tab_gen:
    col_teach, col_create = st.columns([1, 1])
    
    with col_teach:
        with st.container(border=True):
            st.subheader("1. Teach New Knowledge")
            learn_url = st.text_input("Website URL (News article, Wiki, About Us)")
            if st.button("Analyze & Learn"):
                with st.spinner("Reading Website..."):
                    raw_text = scrape_website(learn_url)
                    if raw_text:
                        prompt = f"Extract 3-5 facts about 'Ghost Dimension' (or the spooky topic) from this text. Keep them short:\n{raw_text}"
                        resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        
                        count = 0
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                                count += 1
                        
                        if count > 0: st.success(f"✅ Learned {count} facts! Review them below ↓")
                        else: st.warning("Found text, but could not extract clear facts.")
                        st.rerun()
                    else: st.error("❌ Could not read site. It might be blocking bots.")

        # --- THE MISSING SECTION: APPROVAL QUEUE ---
        st.write("---")
        st.subheader("📋 Review Pending Knowledge")
        pending_facts = supabase.table("brand_knowledge").select("*").eq("status", "pending").execute().data
        
        if pending_facts:
            for fact in pending_facts:
                with st.expander(f"Pending: {fact['fact_summary'][:50]}...", expanded=True):
                    st.write(fact['fact_summary'])
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Approve", key=f"app_{fact['id']}"):
                            supabase.table("brand_knowledge").update({"status": "approved"}).eq("id", fact['id']).execute()
                            st.rerun()
                    with b2:
                        if st.button("🗑️ Delete", key=f"del_fact_{fact['id']}"):
                            supabase.table("brand_knowledge").delete().eq("id", fact['id']).execute()
                            st.rerun()
        else:
            st.info("No pending facts to review.")

    with col_create:
        with st.container(border=True):
            st.subheader("2. Generate Content")
            if st.button("🎲 Suggest Topic"):
                knowledge = get_brand_knowledge()
                prompt = f"Context: {knowledge}. Suggest ONE spooky social media topic."
                resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                st.session_state['suggested_topic'] = resp.choices[0].message.content
                st.rerun()

            topic = st.text_area("Topic:", value=st.session_state.get('suggested_topic', ''), height=100)
            
            # 1. VISUAL STYLE
            style_choice = st.selectbox(
                "Visual Style:",
                [
                    "🟢 CCTV / Night Vision (Classic)",
                    "🎬 Cinematic Horror (Sharp & Realistic)",
                    "📸 Vintage Photograph (Sepia/Damaged)",
                    "🎨 Digital Concept Art (Clean Text)",
                    "🎄 Christmas / Yule Horror",
                    "🎃 Halloween / Samhain",
                    "❄️ Deep Winter",
                    "☀️ Midsummer Nightmare"
                ]
            )
            
            # 2. CAPTION STYLE
            caption_style = st.selectbox(
                "Caption Strategy:",
                [
                    "🔥 Viral / Debate (Ask Questions)",
                    "🕵️ Investigator (Analyze Detail)",
                    "📖 Storyteller (Creepypasta)",
                    "😱 Pure Panic (Short & Scary)"
                ]
            )
            
            style_prompts = {
                "🟢 CCTV / Night Vision (Classic)": "Night vision green tint, grainy CCTV security camera footage style, low resolution feel.",
                "🎬 Cinematic Horror (Sharp & Realistic)": "High budget horror movie screenshot, cinematic lighting, 4k resolution, sharp focus, hyperrealistic.",
                "📸 Vintage Photograph (Sepia/Damaged)": "Authentic 1920s spirit photography, sepia tone, dust and scratches, victorian gothic atmosphere.",
                "🎨 Digital Concept Art (Clean Text)": "High quality digital horror concept art, clean lines, atmospheric fog, sharp details, artstation style.",
                "🎄 Christmas / Yule Horror": "Christmas horror style, twisted holiday decorations, falling snow, Krampus atmosphere, cold blue and red lighting.",
                "🎃 Halloween / Samhain": "Classic Halloween horror style, autumn leaves, pumpkin orange palette, thick fog, jack-o-lantern atmosphere.",
                "❄️ Deep Winter": "Frozen winter horror, ice and frost, breath visible, desaturated blue tones, bleak atmosphere.",
                "☀️ Midsummer Nightmare": "Folk horror style, bright daylight but scary, heat haze, dried grass, Midsommar movie vibes."
            }
            
            if st.button("Generate Post", type="primary"):
                with st.spinner("Creating magic..."):
                    try:
                        knowledge = get_brand_knowledge()
                        final_cap_prompt = get_caption_prompt(caption_style, topic, knowledge)
                        cap_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": final_cap_prompt}])
                        caption = cap_resp.choices[0].message.content
                        
                        selected_style_instruction = style_prompts.get(style_choice, style_prompts["🎬 Cinematic Horror (Sharp & Realistic)"])
                        final_img_prompt = f"A scary paranormal image of {topic}. {selected_style_instruction} Make it look authentic and terrifying."
                        
                        img_resp = client.images.generate(model="dall-e-3", prompt=final_img_prompt, size="1024x1024", quality="hd")
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
            image = Image.open(uploaded_file)
            image = ImageOps.exif_transpose(image)
            st.write("👇 **Drag the box to select your square area:**")
            cropped_img = st_cropper(image, aspect_ratio=(1, 1), box_color='#FF0000', should_resize_image=True)
            st.write("Preview:")
            st.image(cropped_img, width=150)
            
            if st.button("✅ Confirm & Save to Library", type="primary"):
                with st.spinner("Saving..."):
                    try:
                        if cropped_img.mode != "RGB": cropped_img = cropped_img.convert("RGB")
                        final_img = cropped_img.resize((1080, 1080))
                        buf = io.BytesIO()
                        final_img.save(buf, format="JPEG", quality=95)
                        byte_data = buf.getvalue()
                        filename = f"crop_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        supabase.storage.from_("uploads").upload(f"evidence_{filename}", byte_data, {"content-type": "image/jpeg"})
                        final_url = supabase.storage.from_("uploads").get_public_url(f"evidence_{filename}")
                        supabase.table("uploaded_images").insert({"file_url": final_url, "filename": filename}).execute()
                        st.success("Saved!"); st.rerun()
                    except Exception as e: st.error(f"Save failed: {e}")

    with c2:
        st.subheader("2. Library & Generate")
        upload_caption_style = st.selectbox(
            "Caption Strategy:",
            ["🔥 Viral / Debate (Ask Questions)", "🕵️ Investigator (Analyze Detail)", "📖 Storyteller (Creepypasta)", "😱 Pure Panic (Short & Scary)"],
            key="upload_cap_style"
        )
        st.divider()
        st.write("📂 **Evidence Library (Recent 9)**")
        library = supabase.table("uploaded_images").select("*").order("created_at", desc=True).limit(9).execute().data
        
        if library:
            cols = st.columns(2)
            for idx, img in enumerate(library):
                with cols[idx % 2]:
                    with st.container(border=True):
                        st.image(img['file_url'], use_column_width=True)
                        if st.button("✨ Create Draft", key=f"gen_{img['id']}", type="primary"):
                            with st.spinner("Analyzing..."):
                                try:
                                    raw_url = img['file_url']
                                    knowledge = get_brand_knowledge()
                                    final_cap_prompt = get_caption_prompt(upload_caption_style, "This spooky image", knowledge)
                                    final_cap_prompt += " Describe what is in the image specifically."
                                    
                                    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": final_cap_prompt}, {"type": "image_url", "image_url": {"url": raw_url}}]}], max_tokens=300)
                                    caption = response.choices[0].message.content
                                    supabase.table("social_posts").insert({"caption": caption, "image_url": raw_url, "topic": "Uploaded Evidence", "status": "draft"}).execute()
                                    st.success("Draft Created!")
                                except Exception as e: st.error(f"Error: {e}")

                        if st.button("🗑️ Delete", key=f"del_{img['id']}"):
                            supabase.table("uploaded_images").delete().eq("id", img['id']).execute(); st.rerun()
        else: st.info("Upload and crop an image on the left to start.")

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
                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": final_time, "status": "scheduled"}).eq("id", post['id']).execute(); st.success("Scheduled!"); st.rerun()
                with b2:
                    if st.button("🚀 Post NOW", key=f"now_{post['id']}"):
                        if not post.get('image_url'): st.error("❌ Draft has no image!")
                        else:
                            with st.spinner("Posting..."):
                                try:
                                    r = requests.post(MAKE_WEBHOOK_URL, json={"image_url": post['image_url'], "caption": new_cap})
                                    if r.status_code == 200:
                                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute(); st.success("Posted!"); st.rerun()
                                    else: st.error(f"Make.com Error: {r.text}")
                                except Exception as e: st.error(f"Connection Failed: {e}")
                with b3:
                    if st.button("🗑️ Delete", key=f"del_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute(); st.rerun()

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
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", post['id']).execute(); st.rerun()

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
