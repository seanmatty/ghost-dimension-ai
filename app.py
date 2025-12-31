import streamlit as st
import hmac
from openai import OpenAI
from google import genai
from google.genai import types
from supabase import create_client
import requests
from datetime import datetime, time, timedelta
from bs4 import BeautifulSoup
import random
import urllib.parse
from PIL import Image, ImageOps
import io
from streamlit_cropper import st_cropper 
import cv2
import yt_dlp
import numpy as np
import os

# 1. PAGE CONFIG & THEME
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
/* FORCE WHITE TEXT ON DISABLED INPUTS */
.stTextArea textarea:disabled {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
    background-color: #121212 !important;
    border: 1px solid #333 !important;
}
    .stApp { background-color: #050505; color: #e0e0e0; }
    h1, h2, h3 {
        color: #00ff41 !important; 
        font-family: 'Helvetica Neue', sans-serif;
        text-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
    }
    label, .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label, .stSlider label {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    .stExpander {
        background-color: #121212 !important;
        border: 1px solid #333 !important;
        border-radius: 12px !important;
    }
    .stExpander [data-testid="stExpanderHeader"], 
    .stExpander [data-testid="stExpanderHeader"] p,
    .stExpander [data-testid="stExpanderHeader"] span {
        color: #00ff41 !important;
        background-color: #121212 !important;
        font-weight: bold !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 25px !important; 
        background-color: #121212;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 1px solid #333; 
    }
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div {
        background-color: #1c1c1c !important; color: white !important; border: 1px solid #333 !important; border-radius: 8px;
    }
    .stButton > button {
        background-color: #1c1c1c !important; 
        color: #00ff41 !important; 
        border: 1px solid #00ff41 !important; 
        border-radius: 8px; 
        font-weight: 500;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #00ff41 !important; 
        color: #000000 !important; 
    }
    button[kind="primary"] {
        background-color: #00ff41 !important; 
        color: black !important; 
        border: none !important; 
        font-weight: bold !important;
    }
    .stTabs [aria-selected="true"] { background-color: #00ff41 !important; color: black !important; }
</style>
""", unsafe_allow_html=True)

# --- SECURITY GATE ---
def check_password():
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["ADMIN_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else: st.session_state["password_correct"] = False
    if st.session_state.get("password_correct", False): return True
    st.markdown("<h1 style='text-align: center;'>👻 ACCESS RESTRICTED</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.text_input("Enter Clearance Code", type="password", on_change=password_entered, key="password")
    return False

if not check_password(): st.stop()

# 2. SETUP
openai_client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
google_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
MAKE_WEBHOOK_URL = st.secrets["MAKE_WEBHOOK_URL"]

# --- GLOBAL OPTIONS ---
STRATEGY_OPTIONS = ["🎲 AI Choice (Promotional)", "🔥 Viral / Debate (Ask Questions)", "🕵️ Investigator (Analyze Detail)", "📖 Storyteller (Creepypasta)", "😱 Pure Panic (Short & Scary)"]

# --- HELPER FUNCTIONS ---
def get_best_time_for_day(target_date):
    day_name = target_date.strftime("%A")
    response = supabase.table("strategy").select("best_hour").eq("day", day_name).execute()
    return time(response.data[0]['best_hour'], 0) if response.data else time(20, 0)

def scrape_website(url):
    if not url.startswith("http"): url = "https://" + url
    try:
        page = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if page.status_code == 200:
            soup = BeautifulSoup(page.content, "html.parser")
            return ' '.join([p.text for p in soup.find_all('p')])[:6000]
    except: return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    return "\n".join([f"- {i['fact_summary']}" for i in response.data]) if response.data else ""

def save_ai_image_to_storage(image_bytes):
    try:
        filename = f"nano_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        supabase.storage.from_("uploads").upload(filename, image_bytes, {"content-type": "image/png"})
        return supabase.storage.from_("uploads").get_public_url(filename)
    except Exception as e:
        st.error(f"Save failed: {e}"); return None

def generate_random_ghost_topic():
    knowledge = get_brand_knowledge()
    prompt = f"Brainstorm a single paranormal subject for a photography prompt. Context: {knowledge if knowledge else 'British hauntings'}. Result must be one sentence, max 20 words."
    resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def enhance_topic(topic, style):
    prompt = f"Rewrite for Imagen 4 Ultra. Topic: {topic}. Style: {style}. Instructions: Gear: CCTV, 35mm, or Daguerreotype. Realistic artifacts only. Max 50 words."
    resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def get_caption_prompt(style, topic, context):
    strategies = {
        "🎲 AI Choice (Promotional)": "Act as the Official Voice of Ghost Dimension. Link this scene to the show and tell people to head to our channel for the full investigation.",
        "🔥 Viral / Debate (Ask Questions)": "Write a short, debating caption. Ask 'Real or Fake?'. Tag @GhostDimension.",
        "🕵️ Investigator (Analyze Detail)": "Focus on a background anomaly. Tell them to watch the latest Ghost Dimension episode to see how we track this energy.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence horror story that sounds like a Ghost Dimension teaser.",
        "😱 Pure Panic (Short & Scary)": "Short, terrified caption. 'We weren't alone in this episode...' Use ⚠️👻."
    }
    return f"Role: Ghost Dimension Official Social Media Lead. Brand Context: {context}. Topic: {topic}. Strategy: {strategies.get(style, strategies['🔥 Viral / Debate (Ask Questions)'])}. IMPORTANT: Output ONLY the final caption text. Do not include 'Post Copy:' or markdown headers."

# --- UPDATED VIDEO PROCESSING (NO AUDIO) ---
def process_video_and_extract_frames(url, num_frames):
    # FORCE NO AUDIO (This fixes the empty file error)
    ydl_opts = {
        'format': 'bestvideo[height<=480][ext=mp4]', # Video only, 480p max
        'outtmpl': 'temp_video.mp4', 
        'quiet': True,
        'no_warnings': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Verify file exists and has size
        if not os.path.exists('temp_video.mp4') or os.path.getsize('temp_video.mp4') == 0:
            return []

        cap = cv2.VideoCapture('temp_video.mp4')
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0: return []
        
        # Calculate even intervals
        indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
        extracted = []
        
        for i in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                extracted.append(Image.fromarray(rgb_frame))
        
        cap.release()
        if os.path.exists('temp_video.mp4'): os.remove('temp_video.mp4')
        return extracted
    except Exception as e:
        # Check if file exists to delete it even on error
        if os.path.exists('temp_video.mp4'): os.remove('temp_video.mp4')
        st.error(f"Video Scan Failed: {e}")
        return []

# --- MAIN TITLE ---
total_ev = supabase.table("social_posts").select("id", count="exact").eq("status", "posted").execute().count
st.markdown(f"<h1 style='text-align: center; margin-bottom: 0px;'>👻 GHOST DIMENSION <span style='color: #00ff41; font-size: 20px;'>SOCIAL MANAGER</span></h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: #888;'>Uploads: {total_ev if total_ev else 0} entries</p>", unsafe_allow_html=True)

# --- TABS ---
tab_gen, tab_upload, tab_video = st.tabs(["✨ NANO GENERATOR", "📸 UPLOAD IMAGE", "🎥 VIDEO SCANNER"])

with tab_gen:
    with st.container(border=True):
        c_head, c_body = st.columns([1, 2])
        with c_head:
            st.info("🧠 **Knowledge Base**")
            l_t1, l_t2 = st.tabs(["🔗 URL", "📝 Paste"])
            with l_t1:
                learn_url = st.text_input("URL", label_visibility="collapsed", placeholder="https://...")
                if st.button("📥 Scrape"):
                    raw = scrape_website(learn_url)
                    if raw:
                        resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": f"Extract 3-5 facts:\n{raw}"}])
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10: supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.rerun()
            with l_t2:
                m_text = st.text_area("Paste Text", height=100, label_visibility="collapsed")
                if st.button("📥 Learn"):
                    resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": f"Extract 3-5 facts:\n{m_text}"}])
                    for fact in resp.choices[0].message.content.split('\n'):
                        clean = fact.strip().replace("- ", "")
                        if len(clean) > 10: supabase.table("brand_knowledge").insert({"source_url": "Manual", "fact_summary": clean, "status": "pending"}).execute()
                    st.rerun()
            
            st.divider()
            st.write("🔍 **Review Pending Facts**")
            pending = supabase.table("brand_knowledge").select("*").eq("status", "pending").execute().data
            if pending:
                for f in pending:
                    st.write(f"_{f['fact_summary']}_")
                    b1, b2 = st.columns(2)
                    with b1: 
                        if st.button("✅", key=f"ok_{f['id']}"): 
                            supabase.table("brand_knowledge").update({"status": "approved"}).eq("id", f['id']).execute(); st.rerun()
                    with b2:
                        if st.button("❌", key=f"no_{f['id']}"): 
                            supabase.table("brand_knowledge").delete().eq("id", f['id']).execute(); st.rerun()
            else: st.write("✅ No facts to review.")

        with c_body:
            st.subheader("Nano Banana Realism")
            if "enhanced_topic" not in st.session_state: st.session_state.enhanced_topic = ""
            topic = st.text_area("Subject:", value=st.session_state.enhanced_topic, placeholder="e.g. Shadow figure...", height=100)
            
            c_rand, c_enh = st.columns(2)
            with c_rand:
                if st.button("🎲 RANDOMISE FROM FACTS"):
                    st.session_state.enhanced_topic = generate_random_ghost_topic(); st.rerun()
            with c_enh:
                if st.button("🪄 ENHANCE DETAILS"):
                    st.session_state.enhanced_topic = enhance_topic(topic, "Official Ghost Dimension Capture"); st.rerun()

            c1, c2 = st.columns(2)
            with c1: style_choice = st.selectbox("Style", ["🟢 CCTV Night Vision", "🎞️ 35mm Found Footage", "📸 Victorian Spirit Photo", "❄️ Winter Frost Horror"])
            with c2: post_count = st.slider("Quantity to Generate", 1, 5, 1)
            
            cap_style = st.selectbox("Strategy", STRATEGY_OPTIONS)

            if st.button("🚀 GENERATE DRAFTS", type="primary"):
                with st.spinner(f"Manufacturing Ghost Dimension Content..."):
                    try:
                        for i in range(post_count):
                            iter_topic = topic if (topic and post_count == 1) else generate_random_ghost_topic()
                            caption = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": get_caption_prompt(cap_style, iter_topic, get_brand_knowledge())}]).choices[0].message.content
                            img_resp = google_client.models.generate_images(model='imagen-4.0-ultra-generate-001', prompt=iter_topic, config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1", person_generation="ALLOW_ADULT"))
                            url = save_ai_image_to_storage(img_resp.generated_images[0].image.image_bytes)
                            if url: supabase.table("social_posts").insert({"caption": caption, "image_url": url, "topic": iter_topic, "status": "draft"}).execute()
                        st.session_state.enhanced_topic = ""; st.rerun()
                    except Exception as e: st.error(e)

with tab_upload:
    c_up, c_lib = st.columns([1, 1])
    with c_up:
        st.subheader("1. Upload")
        f = st.file_uploader("Evidence", type=['jpg', 'png', 'jpeg'])
        u_strategy = st.selectbox("Caption Strategy", STRATEGY_OPTIONS, key="u_strat")
        if f:
            image = ImageOps.exif_transpose(Image.open(f))
            cropped = st_cropper(image, aspect_ratio=(1,1), box_color='#00ff41')
            if st.button("✅ SAVE TO VAULT", type="primary"):
                buf = io.BytesIO(); cropped.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG", quality=90)
                fname = f"ev_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                supabase.storage.from_("uploads").upload(fname, buf.getvalue(), {"content-type": "image/jpeg"})
                supabase.table("uploaded_images").insert({"file_url": supabase.storage.from_("uploads").get_public_url(fname), "filename": fname}).execute()
                st.success("Saved!"); st.rerun()
    
    with c_lib:
        st.subheader("2. Library (All)")
        lib = supabase.table("uploaded_images").select("*").order("created_at", desc=True).execute().data
        
        if lib:
            cols = st.columns(3)
            for idx, img in enumerate(lib):
                with cols[idx % 3]: 
                    with st.container(border=True):
                        st.image(img['file_url'], use_container_width=True)
                        if st.button("✨ DRAFT", key=f"g_{img['id']}", type="primary"):
                            with st.spinner("Analyzing..."):
                                vision_prompt = f"""You are the Marketing Lead for the show 'Ghost Dimension'.
                                BRAND FACTS: {get_brand_knowledge()}
                                TASK: Write a scary, promotional social media caption for this photo. 
                                Mention specific episodes or history. Strategy: {u_strategy}.
                                IMPORTANT: Output ONLY the final caption text. Do not include 'Post Copy:', 'Here is the caption:', or any headers."""
                                
                                resp = openai_client.chat.completions.create(
                                    model="gpt-4o", 
                                    messages=[{"role": "user", "content": [{"type": "text", "text": vision_prompt}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}], 
                                    max_tokens=400
                                )
                                supabase.table("social_posts").insert({"caption": resp.choices[0].message.content, "image_url": img['file_url'], "topic": "Promotional Upload", "status": "draft"}).execute()
                                st.success("Draft Created!"); st.rerun()
                        if st.button("🗑️", key=f"d_{img['id']}"): 
                            supabase.table("uploaded_images").delete().eq("id", img['id']).execute(); st.rerun()

# --- TAB 3: VIDEO SCANNER (SPEED MODE) ---
with tab_video:
    st.subheader("YouTube Frame Extraction")
    if "extracted_frames" not in st.session_state: st.session_state.extracted_frames = []
    
    col_input, col_action = st.columns([3, 1])
    with col_input:
        yt_url = st.text_input("YouTube URL", placeholder="https://youtube.com/watch?v=...")
        num_frames = st.slider("Frames to Extract", 5, 100, 10)
    
    with col_action:
        st.write("") 
        st.write("") 
        if st.button("🚀 SCAN FOOTAGE", type="primary"):
            if yt_url:
                with st.spinner("Downloading (Speed Mode)..."):
                    st.session_state.extracted_frames = process_video_and_extract_frames(yt_url, num_frames)
            else: st.error("Need URL")

    if st.session_state.extracted_frames:
        st.divider()
        c_head, c_clear = st.columns([4, 1])
        with c_head: st.write("🔍 **Select Evidence to Process**")
        with c_clear:
            if st.button("🗑️ CLEAR SCAN", type="primary"):
                st.session_state.extracted_frames = []
                st.rerun()

        v_cols = st.columns(5)
        for i, frame in enumerate(st.session_state.extracted_frames):
            with v_cols[i % 5]:
                st.image(frame, use_container_width=True)
                if st.button("🔍 INSPECT", key=f"vid_{i}"):
                    st.session_state.selected_video_frame = frame
        
        if "selected_video_frame" in st.session_state:
            st.divider()
            st.subheader("✂️ Crop & Save Evidence")
            c_crop, c_save = st.columns([2, 1])
            with c_crop:
                cropped_vid = st_cropper(st.session_state.selected_video_frame, aspect_ratio=(1,1), box_color='#00ff41', key="vid_cropper")
            with c_save:
                st.info("Ready to Vault?")
                if st.button("✅ SAVE TO VAULT", key="save_vid_frame", type="primary"):
                    buf = io.BytesIO()
                    cropped_vid.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG", quality=90)
                    fname = f"yt_ev_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                    supabase.storage.from_("uploads").upload(fname, buf.getvalue(), {"content-type": "image/jpeg"})
                    supabase.table("uploaded_images").insert({"file_url": supabase.storage.from_("uploads").get_public_url(fname), "filename": fname}).execute()
                    st.success("Evidence Secured!"); st.rerun()

# --- COMMAND CENTER ---
st.markdown("---")
st.markdown("<h2 style='text-align: center;'>📲 COMMAND CENTER</h2>", unsafe_allow_html=True)
d1, d2, d3 = st.tabs(["📝 DRAFTS", "📅 SCHEDULED", "📜 HISTORY"])

with d1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").order("created_at", desc=True).execute().data
    for p in drafts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1: st.image(p['image_url'], use_column_width=True)
            with col2:
                cap = st.text_area("Caption", p['caption'], height=150, key=f"cp_{p['id']}")
                din, tin = st.date_input("Date", key=f"dt_{p['id']}"), st.time_input("Time", value=get_best_time_for_day(datetime.now()), key=f"tm_{p['id']}")
                b_col1, b_col2, b_col3 = st.columns(3)
                with b_col1:
                    if st.button("📅 Schedule", key=f"s_{p['id']}"):
                        supabase.table("social_posts").update({"caption": cap, "scheduled_time": f"{din} {tin}", "status": "scheduled"}).eq("id", p['id']).execute(); st.rerun()
                with b_col2:
                    if st.button("🚀 POST NOW", key=f"p_{p['id']}", type="primary"):
                        media_type = "video" if ".mp4" in p['image_url'] else "image"
                        requests.post(MAKE_WEBHOOK_URL, json={"image_url": p['image_url'], "caption": cap, "media_type": media_type})
                        supabase.table("social_posts").update({"caption": cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", p['id']).execute(); st.rerun()
                with b_col3:
                    if st.button("🗑️", key=f"del_{p['id']}"):
                        supabase.table("social_posts").delete().eq("id", p['id']).execute(); st.rerun()

with d2:
    sch = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    for p in sch:
        with st.container(border=True):
            ci, ct = st.columns([1, 3])
            with ci: st.image(p['image_url'], use_column_width=True)
            with ct:
                st.write(f"⏰ **Due:** {p['scheduled_time']} UTC")
                st.text_area("Scheduled Caption", p['caption'], height=100, disabled=True, key=f"view_{p['id']}")
                if st.button("❌ ABORT", key=f"can_{p['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", p['id']).execute(); st.rerun()

with d3:
    hist = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(10).execute().data
    for p in hist:
        with st.container(border=True):
            ci, ct = st.columns([1, 3])
            with ci: st.image(p['image_url'], use_column_width=True)
            with ct: st.write(f"✅ Sent: {p['scheduled_time']}"); st.markdown(f"> {p['caption']}")

st.markdown("---")
with st.expander("🛠️ SYSTEM MAINTENANCE & PURGE", expanded=False):
    sixty_days_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    old_data = supabase.table("social_posts").select("id, image_url").eq("status", "posted").lt("created_at", sixty_days_ago).execute().data
    st.write(f"📂 **Overdue for Purge:** {len(old_data)} files")
    if len(old_data) > 0:
        if st.button("🔥 INCINERATE OLD EVIDENCE"):
            supabase.storage.from_("uploads").remove([u['image_url'].split('/')[-1] for u in old_data])
            supabase.table("social_posts").delete().in_("id", [i['id'] for i in old_data]).execute(); st.rerun()
    else: st.button("✅ VAULT IS CURRENT", disabled=True)
