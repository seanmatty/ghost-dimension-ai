import streamlit as st
import hmac
from openai import OpenAI
import pandas as pd
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
import calendar
import tempfile
import dropbox #
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

# --- SECURITY GATE (Crash-Proof Version) ---
def check_password():
    """Returns `True` if the user had the correct password."""

    # 1. Check if we are already logged in (Skip everything if yes)
    if st.session_state.get("password_correct", False):
        return True

    # 2. Define the callback (Runs ONLY when you hit Enter on the password box)
    def password_entered():
        # Check if the "password" key exists to prevent KeyErrors
        if "password" in st.session_state:
            if hmac.compare_digest(st.session_state["password"], st.secrets["ADMIN_PASSWORD"]):
                st.session_state["password_correct"] = True
                del st.session_state["password"]  # Clean up
            else:
                st.session_state["password_correct"] = False
    
    # 3. Show the login box
    st.text_input(
        "Enter Clearance Code", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    # 4. Show error if they got it wrong
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("🚫 Access Denied")
        
    return False

if not check_password(): st.stop()

# 2. SETUP
openai_client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
google_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
MAKE_WEBHOOK_URL = st.secrets["MAKE_WEBHOOK_URL"]

def get_dbx():
    """Handles auto-refreshing tokens for 24/7 operation"""
    return dropbox.Dropbox(
        app_key=st.secrets["DROPBOX_APP_KEY"],
        app_secret=st.secrets["DROPBOX_APP_SECRET"],
        oauth2_refresh_token=st.secrets["DROPBOX_REFRESH_TOKEN"]
    )

def upload_to_social_system(local_path, file_name):
    """Moves any file to Dropbox and returns a direct stream link"""
    try:
        dbx = get_dbx()
        db_path = f"/Social System/{file_name}"
        with open(local_path, "rb") as f:
            dbx.files_upload(f.read(), db_path, mode=dropbox.files.WriteMode.overwrite)
            # Create a shared link and convert it to a direct download link
            shared_link = dbx.sharing_create_shared_link_with_settings(db_path)
            return shared_link.url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "&raw=1")
    except Exception as e:
        st.error(f"Dropbox Fail: {e}"); return None

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
    
def generate_viral_title(caption):
    """Generates a high-CTR YouTube Shorts title under 100 chars."""
    try:
        # SAFE VERSION: No triple quotes to prevent syntax errors
        prompt = "You are a master YouTube strategist. Create a viral, high-CTR title for the horror niche.\n"
        prompt += "Rules:\n1. NO brand names.\n2. Use psychological triggers.\n3. Use ALL CAPS for key scary words.\n"
        prompt += "4. Must be under 100 characters.\n5. No hashtags.\n6. Do not use quotes.\n"
        prompt += f"Transform this caption into a title: '{caption}'"

        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        title = resp.choices[0].message.content.strip().replace('"', '')
        return title[:100] 
    except:
        return "GHOST DIMENSION EVIDENCE caught on camera"
        
def save_ai_image_to_storage(image_bytes):
    try:
        filename = f"nano_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        url = upload_to_social_system(tmp_path, filename) 
        os.remove(tmp_path)
        return url
    except Exception as e:
        st.error(f"Image Save failed: {e}"); return None

# --- MOVED TO LEFT MARGIN (GLOBAL SCOPE) ---
def upload_to_youtube_direct(video_path, title, description, scheduled_time=None):
    """
    Uploads directly to YouTube using local keys. 
    Handles both Immediate and Scheduled uploads.
    """
    try:
        # 1. Rebuild Credentials
        creds = Credentials(
            token=st.secrets["YOUTUBE_TOKEN"],
            refresh_token=st.secrets["YOUTUBE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["YOUTUBE_CLIENT_ID"],
            client_secret=st.secrets["YOUTUBE_CLIENT_SECRET"],
            scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
        )
        youtube = build('youtube', 'v3', credentials=creds)

        # 2. Configure Logic
        if scheduled_time:
            publish_at = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            privacy = "private"
        else:
            publish_at = None
            privacy = "public"

        # 3. Metadata
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': ['Ghost Dimension', 'Paranormal'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False
            }
        }
        if publish_at:
            body['status']['publishAt'] = publish_at

        # 4. Upload
        media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
        
        return f"https://youtu.be/{response['id']}"

    except Exception as e:
        st.error(f"YouTube Upload Failed: {e}")
        return None

def update_youtube_stats():
    """
    Robust Version: Pulls ALL posted videos and filters valid IDs in Python 
    to avoid SQL NULL errors. (Fixed: Removed 'last_updated' to prevent DB error).
    """
    # 1. Fetch ALL posted items (Don't filter IDs yet)
    response = supabase.table("social_posts").select("id, platform_post_id, caption").eq("status", "posted").execute()
    posts = response.data
    
    if not posts: 
        return "⚠️ No posts found with status='posted'."

    # 2. Filter in Python (Safer than SQL)
    # We only keep rows where platform_post_id exists AND is not empty
    valid_posts = [p for p in posts if p.get('platform_post_id') and len(p['platform_post_id']) > 2]
    
    if not valid_posts:
        # Debugging: Show the user what the first few bad rows look like
        sample = posts[:3] if posts else "None"
        return f"⚠️ Found {len(posts)} posted items, but NONE had valid IDs. Sample data: {sample}"

    # 3. Map IDs
    video_map = {p['platform_post_id']: p['id'] for p in valid_posts}
    video_ids = list(video_map.keys())
    
    st.toast(f"🔎 Found {len(video_ids)} videos to sync...")

    # 4. Auth with Google
    try:
        creds = Credentials(
            token=st.secrets["YOUTUBE_TOKEN"],
            refresh_token=st.secrets["YOUTUBE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["YOUTUBE_CLIENT_ID"],
            client_secret=st.secrets["YOUTUBE_CLIENT_SECRET"],
            scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
        )
        youtube = build('youtube', 'v3', credentials=creds)
    except Exception as e:
        return f"❌ Google Auth Failed: {e}"

    # 5. Batch Process
    count = 0
    total_views_found = 0
    
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            res = youtube.videos().list(part="statistics", id=','.join(batch)).execute()

            for item in res.get("items", []):
                stats = item['statistics']
                vid_id = item['id']
                db_id = video_map.get(vid_id)
                
                views = int(stats.get('viewCount', 0))
                
                if db_id:
                    supabase.table("social_posts").update({
                        "views": views,
                        "likes": int(stats.get('likeCount', 0)),
                        "comments": int(stats.get('commentCount', 0))
                        # REMOVED 'last_updated' to fix your error
                    }).eq("id", db_id).execute()
                    count += 1
                    total_views_found += views
                    
        except Exception as e:
            st.error(f"Batch Error: {e}")

    return f"✅ Success! Synced {count} videos (Total Views: {total_views_found})."

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

# TABS:
tab_gen, tab_upload, tab_dropbox, tab_video_vault, tab_analytics = st.tabs(["✨ NANO GENERATOR", "📸 UPLOAD IMAGE", "📦 DROPBOX LAB", "🎬 VIDEO VAULT", "📊 ANALYTICS"])

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

# --- TAB 2: UPLOAD & CROP (CACHED & FAST) ---
with tab_upload:
    c_up, c_lib = st.columns([1, 1])
    
    # --- COLUMN 1: INPUT SOURCE ---
    with c_up:
        st.subheader("1. Acquire Image")
        
        # Session State Setup
        if "crop_source_img" not in st.session_state: st.session_state.crop_source_img = None
        if "crop_source_name" not in st.session_state: st.session_state.crop_source_name = ""
        if "gallery_files" not in st.session_state: st.session_state.gallery_files = [] 
        if "gallery_page" not in st.session_state: st.session_state.gallery_page = 0
        if "gallery_origin" not in st.session_state: st.session_state.gallery_origin = None 
        # 🚀 NEW: Image Cache to stop reloading
        if "img_cache" not in st.session_state: st.session_state.img_cache = {}

        # Source Options
        source_type = st.radio("Select Source:", ["📂 Upload from Computer", "☁️ Single File Link", "🔎 Browse Dropbox Gallery"], horizontal=True)

        # 🅰️ OPTION A: COMPUTER
        if source_type.startswith("📂"):
            f = st.file_uploader("Choose Image", type=['jpg', 'png', 'jpeg'])
            if f:
                st.session_state.crop_source_img = ImageOps.exif_transpose(Image.open(f))
                st.session_state.crop_source_name = f.name

        # 🅱️ OPTION B: SINGLE FILE LINK
        elif source_type.startswith("☁️"):
            db_link = st.text_input("Paste Direct Image Link", placeholder="https://www.dropbox.com/s/...")
            if st.button("📥 Fetch Image"):
                if db_link:
                    try:
                        with st.spinner("Downloading..."):
                            dl_url = db_link.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "")
                            r = requests.get(dl_url)
                            if r.status_code == 200:
                                st.session_state.crop_source_img = ImageOps.exif_transpose(Image.open(io.BytesIO(r.content)))
                                st.session_state.crop_source_name = f"import_{datetime.now().strftime('%H%M%S')}.jpg"
                                st.success("Loaded!")
                    except Exception as e: st.error(f"Error: {e}")

        # 🅾️ OPTION C: SMART GALLERY (Path OR Link)
        else:
            folder_input = st.text_input("Folder Path OR Shared Link", value="/Social System") 
            
            # Load/Refresh Button
            if st.button("🔄 Load Gallery"):
                try:
                    with st.spinner("Accessing Dropbox..."):
                        dbx = get_dbx()
                        files = []
                        
                        # Reset Cache on new load
                        st.session_state.img_cache = {}

                        # LOGIC: Check if it's a LINK or a PATH
                        if folder_input.startswith("http"):
                            # IT IS A SHARED LINK
                            url = folder_input
                            res = dbx.files_list_folder(path="", shared_link=dropbox.files.SharedLink(url=url))
                            st.session_state.gallery_origin = {"type": "link", "url": url}
                        else:
                            # IT IS A FOLDER PATH
                            res = dbx.files_list_folder(folder_input)
                            st.session_state.gallery_origin = {"type": "path", "root": folder_input}

                        # Filter & Sort
                        files = [e for e in res.entries if isinstance(e, dropbox.files.FileMetadata) and e.name.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        files.sort(key=lambda x: x.client_modified, reverse=True)
                        
                        st.session_state.gallery_files = files
                        st.session_state.gallery_page = 0 # Reset
                        
                except Exception as e:
                    st.error(f"Gallery Error: {e}")

            # Display the Grid
            if st.session_state.gallery_files:
                # 🚀 SMART PAGINATION SIZE
                # Links are slow (download full image), so show fewer. Paths are fast (thumbnails), show more.
                if st.session_state.gallery_origin['type'] == 'link':
                    ITEMS_PER_PAGE = 6
                else:
                    ITEMS_PER_PAGE = 12

                total_files = len(st.session_state.gallery_files)
                start_idx = st.session_state.gallery_page * ITEMS_PER_PAGE
                end_idx = start_idx + ITEMS_PER_PAGE
                current_batch = st.session_state.gallery_files[start_idx:end_idx]
                
                st.write(f"📂 **Viewing {start_idx + 1}-{min(end_idx, total_files)} of {total_files} images**")
                
                g_cols = st.columns(3)
                for i, file_entry in enumerate(current_batch):
                    col = g_cols[i % 3]
                    with col:
                        with st.container(border=True):
                            # --- CACHED IMAGE DISPLAY ---
                            # Check if we already have the bytes in session state
                            if file_entry.id in st.session_state.img_cache:
                                st.image(st.session_state.img_cache[file_entry.id], use_container_width=True)
                            else:
                                # Not in cache? Fetch it!
                                try:
                                    dbx = get_dbx()
                                    img_bytes = None
                                    
                                    if st.session_state.gallery_origin['type'] == 'path':
                                        # FAST: Thumbnail
                                        _, res = dbx.files_get_thumbnail(file_entry.path_lower, format=dropbox.files.ThumbnailFormat.jpeg, size=dropbox.files.ThumbnailSize.w128h128)
                                        img_bytes = res.content
                                    else:
                                        # SLOW: Full Download (for Links)
                                        url = st.session_state.gallery_origin['url']
                                        _, res = dbx.sharing_get_shared_link_file(url=url, path=f"/{file_entry.name}")
                                        img_bytes = res.content
                                    
                                    # Save to Cache & Display
                                    if img_bytes:
                                        st.session_state.img_cache[file_entry.id] = img_bytes
                                        st.image(img_bytes, use_container_width=True)
                                        
                                except: st.markdown("🖼️") # Fail gracefully

                            st.caption(file_entry.name[:15]+"...")
                            
                            # Select Button
                            if st.button("Select", key=f"sel_{file_entry.id}", use_container_width=True):
                                try:
                                    with st.spinner(f"Downloading High-Res..."):
                                        dbx = get_dbx()
                                        
                                        # If we already have the full bytes (Link mode), use them!
                                        if st.session_state.gallery_origin['type'] == 'link' and file_entry.id in st.session_state.img_cache:
                                            high_res_bytes = st.session_state.img_cache[file_entry.id]
                                        
                                        # Otherwise download fresh high-res (Path mode)
                                        elif st.session_state.gallery_origin['type'] == 'path':
                                            _, res = dbx.files_download(file_entry.path_lower)
                                            high_res_bytes = res.content
                                        
                                        # Fallback for Link mode if cache missed
                                        else:
                                            url = st.session_state.gallery_origin['url']
                                            _, res = dbx.sharing_get_shared_link_file(url=url, path=f"/{file_entry.name}")
                                            high_res_bytes = res.content
                                        
                                        st.session_state.crop_source_img = ImageOps.exif_transpose(Image.open(io.BytesIO(high_res_bytes)))
                                        st.session_state.crop_source_name = file_entry.name
                                        st.rerun()
                                except Exception as e: st.error(f"Download Failed: {e}")

                # Pagination Buttons
                c_prev, c_page, c_next = st.columns([1, 2, 1])
                with c_prev:
                    if st.session_state.gallery_page > 0:
                        if st.button("◀ Prev"): st.session_state.gallery_page -= 1; st.rerun()
                with c_next:
                    if end_idx < total_files:
                        if st.button("Next ▶"): st.session_state.gallery_page += 1; st.rerun()

        # --- THE CROPPER ---
        if st.session_state.crop_source_img:
            st.divider()
            st.markdown(f"### ✂️ Cropping: {st.session_state.crop_source_name}")
            
            cropped = st_cropper(
                st.session_state.crop_source_img, 
                aspect_ratio=(1,1), 
                box_color='#00ff41',
                key="uni_cropper"
            )
            
            if st.button("✅ SAVE CROP TO DROPBOX", type="primary"):
                try:
                    with st.spinner("Saving to /Social System..."):
                        buf = io.BytesIO()
                        cropped.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG", quality=90)
                        final_name = f"crop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                            tmp.write(buf.getvalue()); tmp_path = tmp.name
                        
                        url = upload_to_social_system(tmp_path, final_name)
                        os.remove(tmp_path)
                        
                        if url:
                            supabase.table("uploaded_images").insert({
                                "file_url": url, 
                                "filename": final_name, 
                                "media_type": "image"
                            }).execute()
                            st.success("✅ Saved to Dropbox!")
                            st.session_state.crop_source_img = None; st.rerun()
                        else: st.error("Upload failed.")
                except Exception as e: st.error(f"Error: {e}")

    # --- COLUMN 2: LIBRARY (PAGINATED) ---
    with c_lib:
        st.subheader("2. Image Library (Photos Only)")
        
        # 1. Inputs
        u_strategy = st.selectbox("Strategy for Drafts", STRATEGY_OPTIONS, key="lib_strat")
        u_context = st.text_input("Optional: What is this?", placeholder="e.g. Liverpool Castle ruins...", key="lib_ctx")

        # 2. Pagination State
        if 'lib_page' not in st.session_state: st.session_state.lib_page = 0
        LIB_PAGE_SIZE = 9

        # 3. Get Total Count (for Next button logic)
        try:
            count_res = supabase.table("uploaded_images").select("id", count="exact").eq("media_type", "image").execute()
            total_lib_imgs = count_res.count if count_res.count else 0
        except: total_lib_imgs = 0

        # 4. Calculate Range
        start_idx = st.session_state.lib_page * LIB_PAGE_SIZE
        end_idx = start_idx + LIB_PAGE_SIZE - 1

        # 5. Fetch Data (Slice)
        lib = supabase.table("uploaded_images").select("*").eq("media_type", "image").order("created_at", desc=True).range(start_idx, end_idx).execute().data
        
        # 6. Pagination Controls
        c_prev, c_info, c_next = st.columns([1, 2, 1])
        with c_prev:
            if st.session_state.lib_page > 0:
                if st.button("◀ Prev", key="lib_prev", use_container_width=True):
                    st.session_state.lib_page -= 1
                    st.rerun()
        with c_info:
            st.markdown(f"<div style='text-align: center; color: #666; font-size: 0.8em; padding-top: 5px;'>{start_idx+1}-{min(end_idx+1, total_lib_imgs)} of {total_lib_imgs}</div>", unsafe_allow_html=True)
        with c_next:
            if total_lib_imgs > (end_idx + 1):
                if st.button("Next ▶", key="lib_next", use_container_width=True):
                    st.session_state.lib_page += 1
                    st.rerun()

        st.divider()

        # 7. Render Grid
        if lib:
            cols = st.columns(3)
            for idx, img in enumerate(lib):
                with cols[idx % 3]: 
                    with st.container(border=True):
                        # Traffic Light Logic
                        last_used_str = img.get('last_used_at')
                        status_icon, status_msg = "🟢", "Fresh"
                        if last_used_str:
                            try:
                                last_used_date = datetime.fromisoformat(last_used_str.replace('Z', '+00:00'))
                                days_ago = (datetime.now(last_used_date.tzinfo) - last_used_date).days
                                if days_ago < 30: status_icon, status_msg = "🔴", f"{days_ago}d ago"
                                else: status_icon, status_msg = "🟢", f"{days_ago}d ago"
                            except: status_msg = "Unknown"

                        st.image(img['file_url'], use_container_width=True)
                        st.markdown(f"**{status_icon} {status_msg}**")

                        # Draft Button (With your 'Mandatory' Fix)
                        if st.button("✨ DRAFT", key=f"g_{img['id']}", type="primary"):
                            with st.spinner("Analyzing..."):
                                # Instruction Strength Logic
                                if u_context:
                                    context_instruction = f"MANDATORY INSTRUCTION: The subject of this image is '{u_context}'. You MUST write the caption about '{u_context}' specifically. Do not write a generic brand post."
                                else:
                                    context_instruction = "Analyze the image details yourself."

                                vision_prompt = f"""
                                You are the Marketing Lead for 'Ghost Dimension'. 
                                BRAND FACTS: {get_brand_knowledge()} 
                                {context_instruction}
                                TASK: Write a scary, engaging social media caption. 
                                STRATEGY: {u_strategy}. 
                                IMPORTANT: Output ONLY the final caption text.
                                """
                                
                                resp = openai_client.chat.completions.create(
                                    model="gpt-4o", 
                                    messages=[{"role": "user", "content": [{"type": "text", "text": vision_prompt}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}], 
                                    max_tokens=400
                                )
                                supabase.table("social_posts").insert({"caption": resp.choices[0].message.content, "image_url": img['file_url'], "topic": u_context if u_context else "Promotional Upload", "status": "draft"}).execute()
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

            # --- MONITOR SECTION ---
            if "preview_reel_path" in st.session_state and os.path.exists(st.session_state.preview_reel_path):
                st.markdown("### 🎬 MONITOR")
                c_vid, c_act = st.columns([1, 1])
                with c_vid: 
                    st.video(st.session_state.preview_reel_path)
                with c_act:
                    if st.button("✅ APPROVE & VAULT", type="primary"):
                        fn = f"reel_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
                        url = upload_to_social_system(st.session_state.preview_reel_path, fn)
                        if url:
                            supabase.table("uploaded_images").insert({"file_url": url, "filename": fn, "media_type": "video"}).execute()
                            st.success("Vaulted to Dropbox!"); os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
                    
                    if st.button("❌ DISCARD PREVIEW"):
                        os.remove(st.session_state.preview_reel_path)
                        del st.session_state.preview_reel_path
                        st.rerun()
                st.divider()

            # --- GRID SECTION ---
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
                            if process_reel(db_url, ts, clip_dur, effect_choice, temp_name): 
                                st.session_state.preview_reel_path = temp_name
                                st.rerun()

# B. PRECISION CUTTER
    elif tool_mode.startswith("⏱️"):
        st.info("Step 1: Watch video to find the time. Step 2: Enter Min/Sec below.")
        
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
            st.subheader("✂️ Cut Settings")
            
            # --- ROW 1: START TIME ---
            st.caption("🟢 Start Point")
            c_s1, c_s2 = st.columns(2)
            with c_s1: s_min = st.number_input("Start Minute", min_value=0, value=0, step=1, key="s_min")
            with c_s2: s_sec = st.number_input("Start Second", min_value=0, max_value=59, value=0, step=1, key="s_sec")
            
            # --- ROW 2: END TIME ---
            st.caption("🔴 End Point")
            c_e1, c_e2 = st.columns(2)
            with c_e1: e_min = st.number_input("End Minute", min_value=0, value=0, step=1, key="e_min")
            with c_e2: e_sec = st.number_input("End Second", min_value=0, max_value=59, value=0, step=1, key="e_sec")

            # --- CALCULATE DURATION AUTOMATICALLY ---
            start_ts = (s_min * 60) + s_sec
            end_ts = (e_min * 60) + e_sec
            duration = end_ts - start_ts

            # Validate
            if duration <= 0:
                st.error("⚠️ End time must be AFTER Start time.")
            else:
                st.info(f"⏱️ Clip Length: **{duration} seconds**")

                # --- ROW 3: EFFECT ---
                st.caption("✨ Filter")
                EFFECTS_LIST = ["None", "🟢 CCTV (Green)", "🔵 Ectoplasm (Blue NV)", "🔴 Demon Mode", "⚫ Noir (B&W)", "🏚️ Old VHS", "⚡ Poltergeist (Static)", "📜 Sepia (1920s)", "📸 Negative (Invert)", "🪞 Mirror World", "🖍️ Edge Detect", "🔥 Deep Fried", "👻 Ghostly Blur", "🔦 Spotlight", "🔮 Purple Haze", "🧊 Frozen", "🩸 Blood Bath", "🌚 Midnight", "📻 Radio Tower", "👽 Alien"]
                man_effect = st.selectbox("Select Visual Effect", EFFECTS_LIST, key="man_fx")

                if st.button("🎬 RENDER PRECISION CLIP", type="primary"):
                    temp_name = "temp_precision_reel.mp4"
                    with st.spinner(f"Cutting from {s_min}:{s_sec:02d} to {e_min}:{e_sec:02d}..."):
                        # We pass the calculated 'duration' to the processor
                        if process_reel(db_url, start_ts, duration, man_effect, temp_name): 
                            st.session_state.preview_reel_path = temp_name; st.rerun()

        # --- UPDATED APPROVAL LOGIC (NOW USES DROPBOX) ---
        if "preview_reel_path" in st.session_state and os.path.exists(st.session_state.preview_reel_path):
            st.markdown("### 🎬 MONITOR")
            c_vid, c_act = st.columns([1, 1])
            with c_vid: st.video(st.session_state.preview_reel_path)
            with c_act:
                if st.button("✅ APPROVE & VAULT", key="man_save", type="primary"):
                    fn = f"reel_prec_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
                    url = upload_to_social_system(st.session_state.preview_reel_path, fn)
                    if url:
                        supabase.table("uploaded_images").insert({"file_url": url, "filename": fn, "media_type": "video"}).execute()
                        st.success("Vaulted to Dropbox!"); os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
                
                if st.button("❌ DISCARD PREVIEW", key="man_del"):
                    os.remove(st.session_state.preview_reel_path); del st.session_state.preview_reel_path; st.rerun()
# --- TAB 4: VIDEO VAULT (SPACED & SAFE) ---
with tab_video_vault:
    # 1. Header & Global Strategy
    c_title, c_strat = st.columns([2, 1])
    with c_title:
        st.subheader("📼 Video Reel Library")
    with c_strat:
        v_strategy = st.selectbox("Global Strategy", STRATEGY_OPTIONS, label_visibility="collapsed")

    # 2. Pagination State
    if 'vid_page' not in st.session_state: st.session_state.vid_page = 0
    VID_PAGE_SIZE = 8 

    # 3. Get Total Count
    try:
        count_res = supabase.table("uploaded_images").select("id", count="exact").eq("media_type", "video").execute()
        total_vids = count_res.count if count_res.count else 0
    except: total_vids = 0

    # 4. Calculate Range
    start_idx = st.session_state.vid_page * VID_PAGE_SIZE
    end_idx = start_idx + VID_PAGE_SIZE - 1

    # 5. Fetch Data
    videos = supabase.table("uploaded_images").select("*").eq("media_type", "video").order("created_at", desc=True).range(start_idx, end_idx).execute().data
    
    # 6. Pagination Controls
    c_prev, c_info, c_next = st.columns([1, 2, 1])
    with c_prev:
        if st.session_state.vid_page > 0:
            if st.button("◀ Prev", key="vid_prev", use_container_width=True):
                st.session_state.vid_page -= 1
                st.rerun()
    with c_info:
        st.markdown(f"<div style='text-align: center; color: #666; font-size: 0.8em; padding-top: 5px;'>{start_idx+1}-{min(end_idx+1, total_vids)} of {total_vids} reels</div>", unsafe_allow_html=True)
    with c_next:
        if total_vids > (end_idx + 1):
            if st.button("Next ▶", key="vid_next", use_container_width=True):
                st.session_state.vid_page += 1
                st.rerun()

    st.divider()

    # 7. Render Grid
    if videos:
        cols = st.columns(4)
        for idx, vid in enumerate(videos):
            with cols[idx % 4]: 
                with st.container(border=True):
                    # 1. Video Player
                    st.video(vid['file_url'])
                    
                    # 2. Safety Spacer (Forces gap so video doesn't cover text)
                    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

                    # 3. Traffic Light Logic
                    last_used_str = vid.get('last_used_at')
                    status_icon, status_msg = "🟢", "Fresh"
                    if last_used_str:
                        try:
                            last_used_date = datetime.fromisoformat(last_used_str.replace('Z', '+00:00'))
                            days_ago = (datetime.now(last_used_date.tzinfo) - last_used_date).days
                            if days_ago < 30: status_icon, status_msg = "🔴", f"{days_ago}d"
                            else: status_icon, status_msg = "🟢", f"{days_ago}d"
                        except: status_msg = "?"
                    
                    # Display Status
                    st.markdown(f"**{status_icon} {status_msg}**")

                    # 4. Context Input
                    v_context = st.text_input("Context", placeholder="e.g. EVP...", key=f"vctx_{vid['id']}", label_visibility="collapsed")

                    # 5. Actions
                    if st.button("✨ CAPTION", key=f"vcap_{vid['id']}", use_container_width=True):
                        # Instruction Logic
                        if v_context:
                            context_instruction = f"MANDATORY INSTRUCTION: The subject is '{v_context}'. You MUST write the caption about '{v_context}'."
                        else:
                            context_instruction = "Analyze the visual evidence yourself."
                        
                        prompt = f"""
                        You are the Social Media Lead for 'Ghost Dimension'.
                        BRAND FACTS: {get_brand_knowledge()}
                        {context_instruction}
                        TASK: Write a caption for this video.
                        STRATEGY: {v_strategy}
                        IMPORTANT: Output ONLY the final caption text.
                        """
                        
                        cap = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}]).choices[0].message.content
                        supabase.table("social_posts").insert({"caption": cap, "image_url": vid['file_url'], "topic": v_context if v_context else "Reel", "status": "draft"}).execute()
                        st.success("Draft Created!")
                        
                    if st.button("🗑️", key=f"vdel_{vid['id']}", use_container_width=True): 
                        supabase.table("uploaded_images").delete().eq("id", vid['id']).execute(); st.rerun()
    else:
        st.info("Vault empty. Render some Reels in the Dropbox Lab!")
# --- TAB 5: ANALYTICS & STRATEGY ---
with tab_analytics:
    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.subheader("📈 The Feedback Loop")
    with c_btn:
        if st.button("🔄 SYNC YOUTUBE STATS"):
            with st.spinner("Asking YouTube for latest numbers..."):
                res = update_youtube_stats()
                st.success(res)
                st.rerun()
    
    # 1. FETCH DATA (Increased limit to 100 for better analytics)
    history = supabase.table("social_posts").select("*").eq("status", "posted").not_.is_("likes", "null").order("created_at", desc=True).limit(100).execute().data
    
    if len(history) > 0:
        df = pd.DataFrame(history)
        
        # Convert timestamps to readable days/hours
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['day_name'] = df['created_at'].dt.day_name()
        df['hour'] = df['created_at'].dt.hour
        
        # --- 🛡️ SAFETY PATCH: Handle Missing Columns ---
        # 1. Fill missing columns with 0 to prevent crash
        if 'likes' not in df.columns: df['likes'] = 0
        if 'comments' not in df.columns: df['comments'] = 0
        if 'views' not in df.columns: df['views'] = 0

        # 2. Ensure numbers are numbers (not None/NaN)
        df['likes'] = df['likes'].fillna(0)
        df['comments'] = df['comments'].fillna(0)

        # 3. Calculate Score
        df['score'] = df['likes'] + (df['comments'] * 5)
        # -----------------------------------------------
        
        # 2. SHOW THE WINNERS
        # Define the columns (This was missing in your code!)
        c_win, c_chart = st.columns([1, 2])

        with c_win:
            st.write("🏆 **Top Videos**")
            # Show top 5 videos by score
            st.dataframe(df[['caption', 'score', 'views']].sort_values('score', ascending=False).head(5), hide_index=True)
            
        with c_chart:
            st.write("📊 **Heatmap: Best Times by Day**")
            
            # --- ROBUST HEATMAP LOGIC ---
            try:
                # Pivot the data: Days as rows, Hours as columns, Score as values
                # fill_value=0 prevents crashes on empty cells
                heatmap = df.pivot_table(index='day_name', columns='hour', values='score', aggfunc='mean', fill_value=0)
                
                # Sort rows by day of week order
                days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                # reindex(..., fill_value=0) ensures ALL days appear, even if no data exists for them yet
                heatmap = heatmap.reindex(days_order, fill_value=0)
                
                # Display as a color-coded table (High score = Darker Blue)
                # format("{:.0f}") removes decimals for cleaner look
                st.dataframe(heatmap.style.background_gradient(cmap="Blues", axis=None).format("{:.0f}"), use_container_width=True)
            except Exception as e:
                st.info("Not enough data to build a heatmap yet. Keep posting!")
                # Fallback to simple chart if pivot fails completely
                chart_data = df.groupby('hour')['score'].mean()
                st.bar_chart(chart_data)

        # 3. THE BRAIN UPDATE BUTTON
        st.divider()
        st.info("Click below to teach the Scheduler your new best times.")
        
        if st.button("🧠 UPDATE STRATEGY", type="primary"):
            days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            
            progress_text = "Analyzing data..."
            my_bar = st.progress(0, text=progress_text)
            
            # Find best hour for each day
            for i, day in enumerate(days_order):
                day_data = df[df['day_name'] == day]
                
                if not day_data.empty:
                    # Find hour with max average score
                    best_h = int(day_data.groupby('hour')['score'].mean().idxmax())
                else:
                    # Default to 20:00 (8 PM) if no data for that day yet
                    best_h = 20
                
                # Save to Supabase 'strategy' table
                # This overwrites the old rule for that day
                supabase.table("strategy").upsert({"day": day, "best_hour": best_h}, on_conflict="day").execute()
                
                # Update progress bar
                my_bar.progress((i + 1) / 7, text=f"Updated {day}...")
            
            my_bar.empty()
            st.success("✅ Strategy Updated! New drafts will auto-select these times.")
            st.cache_data.clear()
            
    else:
        st.info("⏳ Waiting for data... Once 'The Spy' scenario runs and grabs YouTube stats, this tab will light up.")
# --- COMMAND CENTER ---
st.markdown("---")
st.markdown("<h2 style='text-align: center;'>📲 COMMAND CENTER (DEBUG MODE)</h2>", unsafe_allow_html=True)
d1, d2, d3 = st.tabs(["📝 DRAFTS", "📅 SCHEDULED", "📜 HISTORY"])

with d1:
    # 1. Fetch Drafts
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").order("created_at", desc=True).execute().data
    
    if not drafts: st.info("No drafts found.")

    for idx, p in enumerate(drafts):
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            
            # --- DETECT MEDIA TYPE ---
            is_video = ".mp4" in p['image_url'] or "youtu" in p['image_url']
            
            # --- LEFT: PREVIEW ---
            with col1: 
                if is_video: 
                    st.video(p['image_url']); st.caption("🎥 VIDEO REEL")
                else: 
                    st.image(p['image_url'], use_container_width=True); st.caption("📸 PHOTO POST")
            
            # --- RIGHT: CONTROLS ---
            with col2:
                cap = st.text_area("Caption", p['caption'], height=150, key=f"cp_{p['id']}_{idx}")
                
                # Smart Clock
                din = st.date_input("Date", key=f"dt_{p['id']}_{idx}")
                best_time = get_best_time_for_day(din)
                tin = st.time_input("Time", value=best_time, key=f"tm_{p['id']}_{idx}_{din}")
                
                b_col1, b_col2, b_col3 = st.columns(3)
                
                # 📅 SCHEDULE BUTTON
                with b_col1:
                    if st.button("📅 Schedule", key=f"s_{p['id']}_{idx}"):
                        target_dt = datetime.combine(din, tin)
                        yt_id = None
                        
                        # --- PATH A: VIDEO (HYBRID HANDOFF) ---
                        if is_video:
                            # 1. Generate Viral Title
                            with st.spinner("🧠 AI generating viral title..."):
                                yt_title = generate_viral_title(cap)
                                st.toast(f"Title: {yt_title}")

                            with st.spinner(f"🚀 Step 2: Uploading to YouTube..."):
                                # 2. Download from Dropbox to Temp
                                dl_link = p['image_url'].replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "")
                                r = requests.get(dl_link)
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_vid:
                                    tmp_vid.write(r.content); local_path = tmp_vid.name

                                # 3. Upload to YouTube (Private Scheduled)
                                yt_link = upload_to_youtube_direct(local_path, yt_title, cap, target_dt)
                                os.remove(local_path)

                                if yt_link:
                                    yt_id = yt_link.split("/")[-1]
                                    st.success(f"✅ YouTube Done! Title: {yt_title}")
                                    
                                    # 4. Update DB for MAKE (Keep Original Caption for FB/Insta!)
                                    supabase.table("social_posts").update({
                                        "status": "scheduled",
                                        "caption": cap,
                                        "platform_post_id": yt_id,
                                        "scheduled_time": str(target_dt)
                                    }).eq("id", p['id']).execute()
                                    
                                    # 🟢 UPDATE TRAFFIC LIGHT (Video)
                                    supabase.table("uploaded_images").update({
                                        "last_used_at": datetime.utcnow().isoformat()
                                    }).eq("file_url", p['image_url']).execute()
                                    
                                    st.toast("🤖 Waking up Make for FB/Insta...")
                                    
                                    # 5. Trigger Make
                                    try:
                                        scenario_id = st.secrets["MAKE_SCENARIO_ID"]
                                        api_token = st.secrets["MAKE_API_TOKEN"]
                                        url = f"https://eu1.make.com/api/v2/scenarios/{scenario_id}/run"
                                        headers = {"Authorization": f"Token {api_token}"}
                                        requests.post(url, headers=headers)
                                    except: pass
                                    st.rerun()
                        
                        # --- PATH B: IMAGE (STANDARD MAKE) ---
                        else:
                            supabase.table("social_posts").update({
                                "caption": cap, "scheduled_time": f"{din} {tin}", "status": "scheduled"
                            }).eq("id", p['id']).execute()

                            # 🟢 UPDATE TRAFFIC LIGHT (Image)
                            supabase.table("uploaded_images").update({
                                "last_used_at": datetime.utcnow().isoformat()
                            }).eq("file_url", p['image_url']).execute()

                            st.toast("✅ Image Scheduled! Make will pick this up.")
                            st.rerun()

                # 🚀 POST NOW BUTTON
                with b_col2:
                    if st.button("🚀 POST NOW", key=f"p_{p['id']}_{idx}", type="primary"):
                        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        yt_id = None
                        
                        # --- PATH A: VIDEO (HYBRID HANDOFF) ---
                        if is_video:
                            # 1. Generate Viral Title
                            with st.spinner("🧠 AI generating viral title..."):
                                yt_title = generate_viral_title(cap)
                                st.toast(f"Title: {yt_title}")

                            with st.spinner("🚀 Step 2: Uploading to YouTube..."):
                                dl_link = p['image_url'].replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "")
                                r = requests.get(dl_link)
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_vid:
                                    tmp_vid.write(r.content); local_path = tmp_vid.name

                                # Upload Immediate
                                yt_link = upload_to_youtube_direct(local_path, yt_title, cap, None)
                                os.remove(local_path)

                                if yt_link:
                                    yt_id = yt_link.split("/")[-1]
                                    st.success(f"✅ YouTube Live! Title: {yt_title}")
                                    
                                    # Update DB for MAKE
                                    supabase.table("social_posts").update({
                                        "status": "scheduled",
                                        "caption": cap,
                                        "platform_post_id": yt_id,
                                        "scheduled_time": now_utc
                                    }).eq("id", p['id']).execute()
                                    
                                    # 🟢 UPDATE TRAFFIC LIGHT (Video)
                                    supabase.table("uploaded_images").update({
                                        "last_used_at": datetime.utcnow().isoformat()
                                    }).eq("file_url", p['image_url']).execute()
                                    
                                    # Wake Make
                                    try:
                                        scenario_id = st.secrets["MAKE_SCENARIO_ID"]
                                        api_token = st.secrets["MAKE_API_TOKEN"]
                                        url = f"https://eu1.make.com/api/v2/scenarios/{scenario_id}/run"
                                        headers = {"Authorization": f"Token {api_token}"}
                                        requests.post(url, headers=headers)
                                    except: pass
                                    st.rerun()

                        # --- PATH B: IMAGE (STANDARD MAKE) ---
                        else:
                            st.spinner("Waking up the Robot...")
                            supabase.table("social_posts").update({
                                "caption": cap, "scheduled_time": now_utc, "status": "scheduled"
                            }).eq("id", p['id']).execute()
                            
                            # 🟢 UPDATE TRAFFIC LIGHT (Image)
                            supabase.table("uploaded_images").update({
                                "last_used_at": datetime.utcnow().isoformat()
                            }).eq("file_url", p['image_url']).execute()
                            
                            try:
                                scenario_id = st.secrets["MAKE_SCENARIO_ID"]
                                api_token = st.secrets["MAKE_API_TOKEN"]
                                url = f"https://eu1.make.com/api/v2/scenarios/{scenario_id}/run"
                                headers = {"Authorization": f"Token {api_token}"}
                                requests.post(url, headers=headers)
                            except: pass
                            st.rerun()

                # 🗑️ DISCARD
                with b_col3:
                    if st.button("🗑️ Discard", key=f"del_{p['id']}_{idx}"):
                        supabase.table("social_posts").delete().eq("id", p['id']).execute(); st.rerun()
                        
with d2:
    # 1. SETUP & STYLE
    if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
    if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month

    # CSS to tighten the layout and force button visibility
    st.markdown("""
    <style>
        div[data-testid="stColumn"] { padding: 0px !important; }
        div[data-testid="stVerticalBlock"] { gap: 0rem; }
        
        .day-box {
            min-height: 120px;
            padding: 5px;
            border-right: 1px solid #222;
            border-bottom: 1px solid #222;
        }
    </style>
    """, unsafe_allow_html=True)

    # 2. NAVIGATION HEADER
    c_prev, c_title, c_next = st.columns([1, 6, 1])
    with c_prev:
        if st.button("◀", key="prev_m", use_container_width=True):
            st.session_state.cal_month -= 1
            if st.session_state.cal_month == 0:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            st.rerun()
    with c_next:
        if st.button("▶", key="next_m", use_container_width=True):
            st.session_state.cal_month += 1
            if st.session_state.cal_month == 13:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            st.rerun()
    with c_title:
        month_name = calendar.month_name[st.session_state.cal_month]
        st.markdown(f"<h3 style='text-align: center; margin: 0; color: #00ff41;'>{month_name} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)
    
    st.divider()

    # 3. GET DATA
    sch = supabase.table("social_posts").select("*").eq("status", "scheduled").execute().data
    posts_by_date = {}
    for p in sch:
        raw_ts = str(p['scheduled_time']).replace('T', ' ').split('+')[0]
        try:
            dt = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S")
            key = f"{dt.year}-{dt.month}-{dt.day}"
            if key not in posts_by_date: posts_by_date[key] = []
            posts_by_date[key].append(p)
        except: pass

    # 4. DRAW CALENDAR
    # Header
    cols = st.columns(7)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i, d in enumerate(days):
        cols[i].markdown(f"<div style='text-align: center; color: #888; font-weight: bold; margin-bottom: 10px;'>{d}</div>", unsafe_allow_html=True)

    # Grid
    cal = calendar.Calendar()
    month_days = cal.monthdayscalendar(st.session_state.cal_year, st.session_state.cal_month)

    for week in month_days:
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            with cols[i]:
                if day_num == 0:
                    st.markdown("<div style='height: 100px; border: 1px solid #111;'></div>", unsafe_allow_html=True) 
                else:
                    # Logic
                    date_key = f"{st.session_state.cal_year}-{st.session_state.cal_month}-{day_num}"
                    day_posts = posts_by_date.get(date_key, [])
                    now = datetime.now()
                    is_today = (day_num == now.day and st.session_state.cal_month == now.month and st.session_state.cal_year == now.year)
                    
                    # Container styling
                    border_style = True
                    
                    with st.container(border=border_style):
                        # Date Number
                        num_color = "#00ff41" if is_today else "#666"
                        st.markdown(f"<div style='text-align: right; color: {num_color}; font-weight: bold; margin-bottom: 5px;'>{day_num}</div>", unsafe_allow_html=True)
                        
                        # Post Buttons (GREEN PRIMARY)
                        if day_posts:
                            for post in day_posts:
                                label = "🎥 Reel" if (".mp4" in post['image_url']) else "📸 Post"
                                # type="primary" forces Green BG + Black Text (High Contrast)
                                if st.button(f"{label}", key=f"cal_{post['id']}", help=post['caption'], use_container_width=True, type="primary"):
                                    st.session_state.selected_post = post
                                    st.rerun()
                        else:
                            st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)

    # 5. EDITOR DRAWER
    if 'selected_post' in st.session_state:
        p = st.session_state.selected_post
        st.markdown("---")
        st.info(f"📝 Editing Post for: {p['scheduled_time']}")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if ".mp4" in p['image_url'] or "youtu" in p['image_url']:
                    st.video(p['image_url'])
                else:
                    st.image(p['image_url'])
            with c2:
                st.text_area("Caption", p['caption'], height=150, disabled=True)
            with c3:
                if st.button("✏️ Edit in Drafts", use_container_width=True):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", p['id']).execute()
                    del st.session_state.selected_post
                    st.rerun()
                if st.button("❌ Delete Post", use_container_width=True):
                    supabase.table("social_posts").delete().eq("id", p['id']).execute()
                    del st.session_state.selected_post
                    st.rerun()
                if st.button("Close", key="cls_btn", use_container_width=True):
                    del st.session_state.selected_post
                    st.rerun()
with d3:
    # 1. State Management for Pagination
    if 'hist_page' not in st.session_state: st.session_state.hist_page = 0
    PAGE_SIZE = 10

    # 2. Get Total Count (Fast Query)
    # We need to know the total to decide if "Next" button should be visible
    try:
        count_res = supabase.table("social_posts").select("id", count="exact").eq("status", "posted").execute()
        total_items = count_res.count if count_res.count else 0
    except: 
        total_items = 0

    # 3. Calculate Range for Supabase
    start_idx = st.session_state.hist_page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE - 1

    # 4. Navigation Controls
    c_prev, c_info, c_next = st.columns([1, 4, 1])
    
    with c_prev:
        # Only show Prev if we aren't on page 0
        if st.session_state.hist_page > 0:
            if st.button("◀ Prev", key="h_prev", use_container_width=True):
                st.session_state.hist_page -= 1
                st.rerun()

    with c_next:
        # Only show Next if there are more items ahead
        if total_items > (end_idx + 1):
            if st.button("Next ▶", key="h_next", use_container_width=True):
                st.session_state.hist_page += 1
                st.rerun()

    with c_info:
        st.markdown(f"<div style='text-align: center; color: #666; padding-top: 5px;'>Page {st.session_state.hist_page + 1} • Showing {start_idx + 1}-{min(end_idx + 1, total_items)} of {total_items} posts</div>", unsafe_allow_html=True)

    st.divider()

    # 5. Fetch Data (Only the slice we need)
    # .range() is efficient because it only downloads 10 rows
    hist = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).range(start_idx, end_idx).execute().data

    if hist:
        for p in hist:
            with st.container(border=True):
                ci, ct = st.columns([1, 3])
                
                # Thumbnail
                with ci: 
                     if ".mp4" in p['image_url'] or "youtu" in p['image_url']: 
                         st.video(p['image_url'])
                     else: 
                         st.image(p['image_url'], use_container_width=True)
                
                # Details
                with ct: 
                    st.write(f"✅ **Sent:** {p.get('scheduled_time', 'Unknown')}")
                    
                    # Show stats if available
                    stats = []
                    if p.get('views'): stats.append(f"👁️ {p['views']}")
                    if p.get('likes'): stats.append(f"❤️ {p['likes']}")
                    if stats: st.caption(" | ".join(stats))
                    
                    st.markdown(f"> {p['caption']}")
                    
                    # Debug Info (Hidden in expander)
                    with st.expander("Technical Data"):
                        st.code(f"ID: {p['id']}\nPlatform ID: {p.get('platform_post_id')}")
    else:
        st.info("📭 No history found on this page.")

# --- MAINTENANCE & TOKEN GEN ---
st.markdown("---")
with st.expander("🛠️ SYSTEM MAINTENANCE & 7-DAY PURGE"):
    # Clear bandwidth by wiping Supabase files older than 7 days
    purge_limit = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    old_files = supabase.table("social_posts").select("image_url").eq("status", "posted").lt("created_at", purge_limit).execute().data
    if st.button("🔥 INCINERATE SUPABASE FILES"):
        supabase.storage.from_("uploads").remove([f['image_url'].split('/')[-1] for f in old_files])
        st.success("Bandwidth cleared!"); st.rerun()

with st.expander("🔑 DROPBOX REFRESH TOKEN GENERATOR"):
    st.write("1. Get App Key/Secret from Dropbox Console.")
    st.write("2. Open this URL in a new tab (replace YOUR_APP_KEY):")
    st.code("https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&token_access_type=offline&response_type=code")
    a_key = st.text_input("App Key", key="db_k")
    a_secret = st.text_input("App Secret", key="db_s")
    auth_code = st.text_input("Paste Auth Code", key="db_a")
    if st.button("🚀 GENERATE REFRESH TOKEN"):
        res = requests.post('https://api.dropbox.com/oauth2/token', 
                            data={'code': auth_code, 'grant_type': 'authorization_code'}, 
                            auth=(a_key, a_secret))
        st.json(res.json()) # Copy 'refresh_token' to Secrets




























































