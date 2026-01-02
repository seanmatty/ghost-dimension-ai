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
import numpy as np
import os
import subprocess
import tempfile

# 1. PAGE CONFIG & THEME
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    h1, h2, h3 { color: #00ff41 !important; text-shadow: 0 0 10px rgba(0, 255, 65, 0.3); }
    .stButton > button {
        background-color: #1c1c1c !important; color: #00ff41 !important; border: 1px solid #00ff41 !important; border-radius: 8px; width: 100%;
    }
    .stButton > button:hover { background-color: #00ff41 !important; color: #000000 !important; }
    button[kind="primary"] { background-color: #00ff41 !important; color: black !important; font-weight: bold !important; }
    .stCheckbox label { color: #00ff41 !important; font-weight: bold; }
    div[data-testid="stExpander"] { border: 1px solid #00ff41; }
    .stTabs [aria-selected="true"] { background-color: #00ff41 !important; color: black !important; }
    /* Force white text on inputs */
    .stTextArea textarea:disabled {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
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

# --- VIDEO PROCESSING ENGINE (V74 SAFE RENDER) ---
def process_reel(video_url, start_time_sec, duration, effect, output_filename):
    if "dropbox.com" in video_url:
        video_url = video_url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("?dl=1", "")

    # BASE: Crop to 9:16 (Vertical) -> Scale to 1080x1920
    base = "crop=ih*(9/16):ih:iw/2-ow/2:0,scale=1080:1920"
    
    # EFFECT LIBRARY
    fx_map = {
        "None": "",
        "🟢 CCTV (Green)": ",curves=all='0/0 0.5/0.5 1/1':g='0/0 0.5/0.8 1/1',noise=alls=20:allf=t+u",
        "🔵 Ectoplasm (Blue NV)": ",curves=all='0/0 0.5/0.5 1/1':b='0/0 0.5/0.8 1/1',noise=alls=10:allf=t+u",
        "🔴 Demon Mode": ",colorbalance=rs=0.5:gs=-0.5:bs=-0.5,vignette",
        "⚫ Noir (B&W)": ",hue=s=0,curves=strong_contrast,noise=alls=10:allf=t+u",
        "🏚️ Old VHS": ",curves=vintage,noise=alls=15:allf=t+u,vignette",
        "⚡ Poltergeist (Static)": ",noise=alls=40:allf=t+u",
        "📜 Sepia (1920s)": ",colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
        "📸 Negative (Invert)": ",negate",
        "🪞 Mirror World": ",hflip",
        "🖍️ Edge Detect": ",edgedetect=low=0.1:high=0.4",
        "🔥 Deep Fried": ",eq=contrast=2:saturation=2",
        "👻 Ghostly Blur": ",boxblur=10:1",
        "🔦 Spotlight": ",vignette=PI/4",
        "🔮 Purple Haze": ",colorbalance=rs=0.2:gs=-0.2:bs=0.4",
        "🧊 Frozen": ",colorbalance=rs=-0.2:gs=0.2:bs=0.6",
        "🩸 Blood Bath": ",colorbalance=rs=0.8:gs=-0.5:bs=-0.5",
        "🌚 Midnight": ",eq=brightness=-0.2:contrast=1.2",
        "📻 Radio Tower": ",hue=s=0,noise=alls=30:allf=t+u",
        "👽 Alien": ",colorbalance=rs=-0.1:gs=0.4:bs=0.1,noise=alls=10:allf=t+u"
    }

    selected_filter = fx_map.get(effect, "")
    final_filter = f"{base}{selected_filter}"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time_sec),
        "-t", str(duration),
        "-i", video_url,
        "-vf", final_filter,
        "-c:v", "libx264", 
        "-preset", "ultrafast", 
        "-crf", "28",
        "-pix_fmt", "yuv420p", # FORCE COMPATIBILITY
        "-c:a", "aac",
        output_filename
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        st.error(f"Render Failed. FFmpeg Error: {err_msg}")
        return False

# --- DROPBOX HELPERS ---
def get_video_duration(video_url):
    if "dropbox.com" in video_url:
        video_url = video_url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("?dl=1", "")
    try:
        cap = cv2.VideoCapture(video_url)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0: return int(frames / fps)
        return 600
    except: return 600

def extract_frames_from_url(video_url, num_frames):
    if "dropbox.com" in video_url:
        video_url = video_url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("?dl=1", "")
    
    try:
        cap = cv2.VideoCapture(video_url)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if total_frames <= 0: return [], 0
        
        indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
        frames = []
        timestamps = []
        
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(Image.fromarray(rgb_frame))
                timestamps.append(idx / fps if fps > 0 else 0)
        cap.release()
        return frames, timestamps
    except Exception as e:
        st.error(f"Scan Error: {e}")
        return [], 0

# --- MAIN TITLE ---
total_ev = supabase.table("social_posts").select("id", count="exact").eq("status", "posted").execute().count
st.markdown(f"<h1 style='text-align: center; margin-bottom: 0px;'>👻 GHOST DIMENSION <span style='color: #00ff41; font-size: 20px;'>STUDIO</span></h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: #888;'>Uploads: {total_ev if total_ev else 0} entries</p>", unsafe_allow_html=True)

# --- TABS ---
tab_gen, tab_upload, tab_dropbox, tab_video_vault = st.tabs(["✨ NANO GENERATOR", "📸 UPLOAD IMAGE", "📦 DROPBOX LAB", "🎬 VIDEO VAULT"])

# --- TAB 1: NANO GENERATOR ---
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
            with c2: post_count = st.slider("Quantity to Generate", 1, 10, 1)
            
            cap_style = st.selectbox("Strategy", STRATEGY_OPTIONS)

            if st.button("🚀 GENERATE DRAFTS", type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                for i in range(post_count):
                    try:
                        status_text.write(f"👻 Summoning entity {i+1} of {post_count}...")
                        iter_topic = topic if (topic and post_count == 1) else generate_random_ghost_topic()
                        caption = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": get_caption_prompt(cap_style, iter_topic, get_brand_knowledge())}]).choices[0].message.content
                        img_resp = google_client.models.generate_images(model='imagen-4.0-ultra-generate-001', prompt=iter_topic, config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1", person_generation="ALLOW_ADULT"))
                        url = save_ai_image_to_storage(img_resp.generated_images[0].image.image_bytes)
                        if url: 
                            supabase.table("social_posts").insert({"caption": caption, "image_url": url, "topic": iter_topic, "status": "draft"}).execute()
                        progress_bar.progress((i + 1) / post_count)
                    except Exception as e: st.error(f"Failed on image {i+1}: {e}")
                status_text.success("Batch Complete!")
                st.session_state.enhanced_topic = ""
                if st.button("🔄 Refresh"): st.rerun()

# --- TAB 2: UPLOAD IMAGE ---
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
                supabase.table("uploaded_images").insert({"file_url": supabase.storage.from_("uploads").get_public_url(fname), "filename": fname, "media_type": "image"}).execute()
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

# --- TAB 3: DROPBOX LAB ---
with tab_dropbox:
    st.subheader("🎥 Source Material Processor")
    
    # Tool Selection
    tool_mode = st.radio("Select Tool:", ["🔍 Auto-Scan Grid (Find Random Moments)", "⏱️ Precision Cutter (Scrub Timeline)"], horizontal=True)
    db_url = st.text_input("Dropbox Video Link", placeholder="Paste share link here...")
    
    # A. GRID SCANNER
    if tool_mode.startswith("🔍"):
        mode = st.radio("Output Type:", ["📸 Photo (Crop)", "🎬 Reel (Video)"], horizontal=True)
        snap_count = st.slider("Snapshot Density", 10, 50, 20)
        
        if "db_frames" not in st.session_state: st.session_state.db_frames = []
        if "db_timestamps" not in st.session_state: st.session_state.db_timestamps = []

        if st.button("🚀 SCAN SOURCE", type="primary"):
            if db_url:
                with st.spinner("Scanning..."):
                    frames, timestamps = extract_frames_from_url(db_url, snap_count)
                    st.session_state.db_frames = frames
                    st.session_state.db_timestamps = timestamps
                    if "preview_reel_path" in st.session_state: del st.session_state.preview_reel_path
            else: st.warning("Need link.")

        # Photo Mode
        if mode.startswith("📸") and st.session_state.db_frames:
            if st.session_state.get("frame_to_crop"):
                st.markdown("---"); st.markdown("### ✂️ CROPPER")
                c1, c2 = st.columns([2, 1])
                with c1: cropped = st_cropper(st.session_state.frame_to_crop, aspect_ratio=(1,1), box_color='#00ff41', key="ph_crop")
                with c2:
                    if st.button("💾 SAVE TO IMG VAULT", type="primary"):
                        buf = io.BytesIO(); cropped.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG", quality=90)
                        fname = f"crop_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        supabase.storage.from_("uploads").upload(fname, buf.getvalue(), {"content-type": "image/jpeg"})
                        supabase.table("uploaded_images").insert({"file_url": supabase.storage.from_("uploads").get_public_url(fname), "filename": fname, "media_type": "image"}).execute()
                        st.success("Saved!"); st.session_state.frame_to_crop = None; st.rerun()
                    if st.button("❌ CANCEL CROP"): st.session_state.frame_to_crop = None; st.rerun()
            else:
                st.divider()
                # HEADER WITH CLEAR BUTTON
                c_head, c_clear = st.columns([3, 1])
                with c_head: st.write("📸 **Select a frame to crop:**")
                with c_clear:
                    if st.button("🗑️ DISCARD SCAN", key="clr_ph"):
                        st.session_state.db_frames = []; st.rerun()
                
                cols = st.columns(5)
                for i, frame in enumerate(st.session_state.db_frames):
                    with cols[i % 5]:
                        st.image(frame, use_container_width=True)
                        if st.button("✂️ CROP", key=f"cr_{i}"): st.session_state.frame_to_crop = frame; st.rerun()

        # Reel Mode
        elif mode.startswith("🎬") and st.session_state.db_frames:
            st.divider()
            EFFECTS_LIST = ["None", "🟢 CCTV (Green)", "🔵 Ectoplasm (Blue NV)", "🔴 Demon Mode", "⚫ Noir (B&W)", "🏚️ Old VHS", "⚡ Poltergeist (Static)", "📜 Sepia (1920s)", "📸 Negative (Invert)", "🪞 Mirror World", "🖍️ Edge Detect", "🔥 Deep Fried", "👻 Ghostly Blur", "🔦 Spotlight", "🔮 Purple Haze", "🧊 Frozen", "🩸 Blood Bath", "🌚 Midnight", "📻 Radio Tower", "👽 Alien"]
            c_eff, c_dur = st.columns(2)
            with c_eff: effect_choice = st.selectbox("Effect:", EFFECTS_LIST)
            with c_dur: clip_dur = st.slider("Duration (s)", 5, 60, 15)

            if "preview_reel_path" in st.session_state and os.path.exists(st.session_state.preview_reel_path):
                st.markdown("### 🎬 MONITOR")
                c_vid, c_act = st.columns([1, 1])
                with c_vid: st.video(st.session_state.preview_reel_path)
                with c_act:
                    if st.button("✅ APPROVE", type="primary"):
                        with open(st.session_state.preview_reel_path, "rb") as f:
                            fn = f"reel_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
                            supabase.storage.from_("uploads").upload(fn, f, {"content-type": "video/mp4"})
                            url = supabase.storage.from_("uploads").get_public_url(fn)
                            supabase.table("uploaded_images").insert({"file_url": url, "filename": fn, "media_type": "video"}).execute()
                        st.success("Vaulted!"); os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
                    if st.button("❌ DISCARD PREVIEW"):
                        os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
                st.divider()

            # HEADER WITH CLEAR BUTTON
            c_head, c_clear = st.columns([3, 1])
            with c_head: st.write("🎬 **Click '▶️ PREVIEW' to render a test clip:**")
            with c_clear:
                if st.button("🗑️ DISCARD SCAN", key="clr_rl"):
                    st.session_state.db_frames = []; st.rerun()

            cols = st.columns(5)
            for i, frame in enumerate(st.session_state.db_frames):
                with cols[i % 5]:
                    st.image(frame, use_container_width=True)
                    ts = st.session_state.db_timestamps[i]
                    if st.button(f"▶️ PREVIEW", key=f"prev_{i}"):
                        temp_name = "temp_preview_reel.mp4"
                        with st.spinner("Rendering..."):
                            if process_reel(db_url, ts, clip_dur, effect_choice, temp_name): st.session_state.preview_reel_path = temp_name; st.rerun()

    # B. PRECISION CUTTER
    elif tool_mode.startswith("⏱️"):
        st.info("Step 1: Watch to find the time. Step 2: Drag slider to that time.")
        
        if "vid_duration" not in st.session_state: st.session_state.vid_duration = 0
        if "display_url" not in st.session_state: st.session_state.display_url = ""

        if st.button("📡 LOAD VIDEO INFO"):
            if db_url:
                st.session_state.vid_duration = get_video_duration(db_url)
                st.session_state.display_url = db_url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("?dl=1", "")
                st.rerun()
        
        if st.session_state.display_url:
            st.video(st.session_state.display_url)
            
            st.divider()
            st.write("✂️ **Cut Settings**")
            
            start_ts = st.slider("Select Start Time (Scrub to cut point)", 0, st.session_state.vid_duration, 0, format="%d s")
            st.caption(f"Selected Start: {int(start_ts // 60)}m {int(start_ts % 60)}s")
            
            c_dur, c_eff = st.columns(2)
            with c_dur:
                man_dur = st.slider("Clip Duration (Seconds)", 5, 60, 15)
            with c_eff:
                EFFECTS_LIST = ["None", "🟢 CCTV (Green)", "🔵 Ectoplasm (Blue NV)", "🔴 Demon Mode", "⚫ Noir (B&W)", "🏚️ Old VHS", "⚡ Poltergeist (Static)", "📜 Sepia (1920s)", "📸 Negative (Invert)", "🪞 Mirror World", "🖍️ Edge Detect", "🔥 Deep Fried", "👻 Ghostly Blur", "🔦 Spotlight", "🔮 Purple Haze", "🧊 Frozen", "🩸 Blood Bath", "🌚 Midnight", "📻 Radio Tower", "👽 Alien"]
                man_effect = st.selectbox("Effect", EFFECTS_LIST, key="man_fx")

            if st.button("🎬 RENDER PRECISION CLIP", type="primary"):
                temp_name = "temp_precision_reel.mp4"
                with st.spinner(f"Slicing at {start_ts}s..."):
                    if process_reel(db_url, start_ts, man_dur, man_effect, temp_name):
                        st.session_state.preview_reel_path = temp_name; st.rerun()

        if "preview_reel_path" in st.session_state and os.path.exists(st.session_state.preview_reel_path):
            st.markdown("### 🎬 MONITOR")
            c_vid, c_act = st.columns([1, 1])
            with c_vid: st.video(st.session_state.preview_reel_path)
            with c_act:
                if st.button("✅ APPROVE & VAULT", key="man_save", type="primary"):
                    with open(st.session_state.preview_reel_path, "rb") as f:
                        fn = f"reel_prec_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
                        supabase.storage.from_("uploads").upload(fn, f, {"content-type": "video/mp4"})
                        url = supabase.storage.from_("uploads").get_public_url(fn)
                        supabase.table("uploaded_images").insert({"file_url": url, "filename": fn, "media_type": "video"}).execute()
                    st.success("Vaulted!"); os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
                if st.button("❌ DISCARD PREVIEW", key="man_del"):
                    os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()

# --- TAB 4: VIDEO VAULT ---
with tab_video_vault:
    st.subheader("📼 Video Reel Library")
    videos = supabase.table("uploaded_images").select("*").eq("media_type", "video").order("created_at", desc=True).execute().data
    
    if videos:
        cols = st.columns(3)
        for idx, vid in enumerate(videos):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.video(vid['file_url'])
                    st.caption(f"📄 {vid['filename']}")
                    c_draft, c_del = st.columns(2)
                    with c_draft:
                        if st.button("✨ CAPTION", key=f"vcap_{vid['id']}"):
                            prompt = "Write a viral, scary Instagram Reel caption for this Ghost Dimension clip. Use trending hashtags."
                            cap = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}]).choices[0].message.content
                            supabase.table("social_posts").insert({"caption": cap, "image_url": vid['file_url'], "topic": "Reel", "status": "draft"}).execute()
                            st.success("Draft Created! Check 'Command Center'.")
                    with c_del:
                        if st.button("🗑️", key=f"vdel_{vid['id']}"):
                            supabase.table("uploaded_images").delete().eq("id", vid['id']).execute(); st.rerun()
    else:
        st.info("Vault empty. Render some Reels in the Dropbox Lab!")

# --- COMMAND CENTER ---
st.markdown("---")
st.markdown("<h2 style='text-align: center;'>📲 COMMAND CENTER (DEBUG MODE)</h2>", unsafe_allow_html=True)
d1, d2, d3 = st.tabs(["📝 DRAFTS", "📅 SCHEDULED", "📜 HISTORY"])

with d1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").order("created_at", desc=True).execute().data
    for p in drafts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1: 
                if ".mp4" in p['image_url']: 
                    st.video(p['image_url'])
                    st.caption("🎥 VIDEO REEL")
                else: 
                    st.image(p['image_url'], use_column_width=True)
            with col2:
                cap = st.text_area("Caption", p['caption'], height=150, key=f"cp_{p['id']}")
                din, tin = st.date_input("Date", key=f"dt_{p['id']}"), st.time_input("Time", value=get_best_time_for_day(datetime.now()), key=f"tm_{p['id']}")
                
                b_col1, b_col2, b_col3 = st.columns(3)
                with b_col1:
                    if st.button("📅 Schedule", key=f"s_{p['id']}"):
                        supabase.table("social_posts").update({"caption": cap, "scheduled_time": f"{din} {tin}", "status": "scheduled"}).eq("id", p['id']).execute(); st.rerun()
                with b_col2:
                    if st.button("🚀 POST NOW", key=f"p_{p['id']}", type="primary"):
                        # 1. DETERMINE TYPE
                        media_type = "video" if ".mp4" in p['image_url'] else "image"
                        
                        # 2. PRINT DEBUG INFO TO SCREEN
                        st.warning(f"📡 Preparing to send data...")
                        st.write(f"**Target URL:** `{MAKE_WEBHOOK_URL}`")
                        st.write(f"**Payload:** Type={media_type} | Link={p['image_url'][:30]}...")
                        
                        try:
                            # 3. SEND REQUEST
                            response = requests.post(
                                MAKE_WEBHOOK_URL, 
                                json={"image_url": p['image_url'], "caption": cap, "media_type": media_type},
                                timeout=10
                            )
                            
                            # 4. REPORT RESULT
                            if response.status_code == 200:
                                st.success(f"✅ SUCCESS! Make.com accepted it (200 OK).")
                                st.write(f"Server response: {response.text}")
                                # Only update DB if successful
                                supabase.table("social_posts").update({"caption": cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", p['id']).execute()
                                st.balloons()
                            else:
                                st.error(f"❌ FAILURE. Make.com rejected it.")
                                st.error(f"Status Code: {response.status_code}")
                                st.error(f"Response: {response.text}")
                                
                        except Exception as e:
                            st.error(f"❌ CRITICAL ERROR: Could not connect to internet/Make.")
                            st.code(e)
                            
                with b_col3:
                    if st.button("🗑️", key=f"del_{p['id']}"):
                        supabase.table("social_posts").delete().eq("id", p['id']).execute(); st.rerun()

with d2:
    sch = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    for p in sch:
        with st.container(border=True):
            ci, ct = st.columns([1, 3])
            with ci: 
                if ".mp4" in p['image_url']: st.video(p['image_url'])
                else: st.image(p['image_url'], use_column_width=True)
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
            with ci: 
                 if ".mp4" in p['image_url']: st.video(p['image_url'])
                 else: st.image(p['image_url'], use_column_width=True)
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



