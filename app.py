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

# 1. PAGE CONFIG & THEME SETUP
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- CUSTOM CSS (THE "SLICK" LOOK) ---
st.markdown("""
<style>
    /* MAIN BACKGROUND: Void Black */
    .stApp {
        background-color: #0a0a0a;
        color: #e0e0e0;
    }
    
    /* HEADERS: Glowing Green Text */
    h1, h2, h3 {
        color: #00ff41 !important; /* Night Vision Green */
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
        text-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
    }
    
    /* INPUT FIELDS: Dark Grey with Green Border */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div {
        background-color: #1c1c1c;
        color: white;
        border: 1px solid #333;
        border-radius: 8px;
    }
    
    /* BUTTONS: Ghostly Outline Style */
    .stButton > button {
        background-color: transparent;
        color: #00ff41;
        border: 1px solid #00ff41;
        border-radius: 8px;
        transition: all 0.3s ease;
        width: 100%;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #00ff41;
        color: black;
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.7);
        border-color: #00ff41;
    }
    
    /* PRIMARY BUTTONS (Generate/Save): Filled Green */
    button[kind="primary"] {
        background-color: #00ff41 !important;
        color: black !important;
        border: none;
        box-shadow: 0 0 10px rgba(0, 255, 65, 0.2);
    }
    button[kind="primary"]:hover {
        box-shadow: 0 0 20px rgba(0, 255, 65, 0.6) !important;
    }

    /* EXPANDER & CONTAINERS: Glassmorphism */
    div[data-testid="stExpander"] {
        background-color: #121212;
        border: 1px solid #333;
        border-radius: 10px;
    }
    
    /* TABS */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1c1c1c;
        border-radius: 5px;
        color: #888;
        padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00ff41 !important;
        color: black !important;
    }
    
    /* SUCCESS/ERROR MESSAGES */
    .stAlert {
        background-color: #1c1c1c;
        border: 1px solid #333;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- SECURITY GATE ---
def check_password():
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["ADMIN_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False): return True
    
    # Login Screen Styling
    st.markdown("<h1 style='text-align: center;'>👻 ACCESS RESTRICTED</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.text_input("Enter Clearance Code", type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state: st.error("🚫 Access Denied")
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

def get_caption_prompt(style, topic_or_desc, context):
    base_prompt = f"Role: Social Media Manager for 'Ghost Dimension'. Context: {context}. Topic: {topic_or_desc}. "
    strategies = {
        "🔥 Viral / Debate (Ask Questions)": "Write a short, punchy caption. The goal is to start a fight in the comments. Ask 'Real or Fake?'. Ask 'What would you do?'. End with a question that forces people to comment.",
        "🕵️ Investigator (Analyze Detail)": "Write a caption that sounds like a paranormal investigator analyzing evidence. Ask the user to zoom in. Ask 'Do you see what I see?'. Focus on a specific scary detail.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence mini horror story. Do not be generic. Be atmospheric. End on a cliffhanger that gives chills.",
        "😱 Pure Panic (Short & Scary)": "Write a very short, terrified caption. Use uppercase words for emphasis. Sound like you are currently running away from a ghost. Use emojis like ⚠️👻."
    }
    instruction = strategies.get(style, strategies["🔥 Viral / Debate (Ask Questions)"])
    return f"{base_prompt} \n\nSTRATEGY: {instruction} \n\nMake it sound human, not AI. No cringe hashtags."

# --- MAIN HEADER ---
st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>👻 GHOST DIMENSION <span style='color: white; font-size: 20px;'>AI OPERATING SYSTEM</span></h1>", unsafe_allow_html=True)

# 3. CONTENT CREATION AREA
tab_gen, tab_upload = st.tabs(["✨ GENERATE NEW", "📸 EVIDENCE ANALYSIS"])

# --- TAB A: GENERATE FROM SCRATCH ---
with tab_gen:
    with st.container(border=True):
        c_head, c_body = st.columns([1, 2])
        
        with c_head:
            st.info("🧠 **Knowledge Base**")
            learn_url = st.text_input("Feed New Website URL")
            if st.button("📥 Learn Facts"):
                with st.spinner("Processing Data..."):
                    raw_text = scrape_website(learn_url)
                    if raw_text:
                        prompt = f"Extract 3-5 facts about 'Ghost Dimension' from this:\n{raw_text}"
                        resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.success("Knowledge Updated")
                        st.rerun()
                    else: st.error("Feed Error")

        with c_body:
            st.subheader("Create Content")
            topic = st.text_area("What is the subject?", placeholder="e.g. The hanging dolls of Pluckley Village...", height=100)
            
            c1, c2 = st.columns(2)
            with c1:
                style_choice = st.selectbox(
                    "Visual Style",
                    [
                        "🟢 CCTV / Night Vision",
                        "🎬 Cinematic Horror",
                        "📸 Vintage Photograph",
                        "🎄 Christmas Horror",
                        "🎃 Halloween Vibes",
                        "❄️ Deep Winter",
                        "☀️ Midsummer Nightmare"
                    ]
                )
            with c2:
                caption_style = st.selectbox(
                    "Caption Strategy",
                    [
                        "🔥 Viral / Debate",
                        "🕵️ Investigator Mode",
                        "📖 Storyteller",
                        "😱 Pure Panic"
                    ]
                )
            
            style_prompts = {
                "🟢 CCTV / Night Vision": "Night vision green tint, grainy CCTV security camera footage style, low resolution feel.",
                "🎬 Cinematic Horror": "High budget horror movie screenshot, cinematic lighting, 4k resolution, sharp focus, hyperrealistic.",
                "📸 Vintage Photograph": "Authentic 1920s spirit photography, sepia tone, dust and scratches, victorian gothic atmosphere.",
                "🎄 Christmas Horror": "Christmas horror style, twisted holiday decorations, falling snow, Krampus atmosphere.",
                "🎃 Halloween Vibes": "Classic Halloween horror style, autumn leaves, pumpkin orange palette, thick fog.",
                "❄️ Deep Winter": "Frozen winter horror, ice and frost, breath visible, bleak blue tones.",
                "☀️ Midsummer Nightmare": "Folk horror style, bright daylight, heat haze, Midsommar movie vibes."
            }

            if st.button("🚀 GENERATE DRAFT", type="primary"):
                if not topic:
                    st.warning("⚠️ Please enter a topic first.")
                else:
                    with st.spinner("Summoning AI Entities..."):
                        try:
                            # 1. Caption
                            knowledge = get_brand_knowledge()
                            final_cap_prompt = get_caption_prompt(caption_style, topic, knowledge)
                            cap_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": final_cap_prompt}])
                            caption = cap_resp.choices[0].message.content
                            
                            # 2. Image
                            style_instr = style_prompts.get(style_choice, style_prompts["🟢 CCTV / Night Vision"])
                            final_img_prompt = f"A scary paranormal image of {topic}. {style_instr} Make it look authentic and terrifying."
                            img_resp = client.images.generate(model="dall-e-3", prompt=final_img_prompt, size="1024x1024", quality="hd")
                            image_url = img_resp.data[0].url
                            
                            supabase.table("social_posts").insert({"caption": caption, "image_url": image_url, "topic": topic, "status": "draft"}).execute()
                            st.success("✅ Draft Materialized in Dashboard")
                        except Exception as e: st.error(f"Generation Failed: {e}")

# --- TAB B: UPLOAD & CROP ---
with tab_upload:
    c1, c2 = st.columns([1, 1])
    
    with c1:
        st.markdown("### 📤 Upload Source")
        uploaded_file = st.file_uploader("Drop Evidence File", type=['jpg', 'png', 'jpeg'])
        
        if uploaded_file:
            image = Image.open(uploaded_file)
            image = ImageOps.exif_transpose(image)
            st.write("👇 **Define Focus Area (Square)**")
            cropped_img = st_cropper(image, aspect_ratio=(1, 1), box_color='#00ff41', should_resize_image=True)
            
            if st.button("✅ PROCESS & SAVE", type="primary"):
                with st.spinner("Processing..."):
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
                        st.success("Evidence Secured"); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    with c2:
        st.markdown("### 🗄️ Evidence Vault")
        
        upload_caption_style = st.selectbox("Caption Strategy for Analysis", ["🔥 Viral / Debate", "🕵️ Investigator Mode", "📖 Storyteller", "😱 Pure Panic"])
        
        library = supabase.table("uploaded_images").select("*").order("created_at", desc=True).limit(4).execute().data
        
        if library:
            for img in library:
                with st.container(border=True):
                    col_img, col_act = st.columns([1, 2])
                    with col_img:
                        st.image(img['file_url'], use_column_width=True)
                    with col_act:
                        st.write(f"**ID:** {str(img['id'])[:8]}...")
                        if st.button("✨ ANALYZE & DRAFT", key=f"gen_{img['id']}", type="primary"):
                            with st.spinner("Analyzing spectral data..."):
                                try:
                                    knowledge = get_brand_knowledge()
                                    final_cap_prompt = get_caption_prompt(upload_caption_style, "This spooky image", knowledge) + " Describe what is in the image specifically."
                                    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": final_cap_prompt}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}], max_tokens=300)
                                    caption = response.choices[0].message.content
                                    supabase.table("social_posts").insert({"caption": caption, "image_url": img['file_url'], "topic": "Uploaded Evidence", "status": "draft"}).execute()
                                    st.success("Draft Created")
                                except Exception as e: st.error(e)
                        if st.button("🗑️ DESTROY", key=f"del_{img['id']}"):
                            supabase.table("uploaded_images").delete().eq("id", img['id']).execute()
                            st.rerun()

# 4. DASHBOARD
st.markdown("---")
st.markdown("<h2 style='text-align: center;'>📲 CONTENT COMMAND CENTER</h2>", unsafe_allow_html=True)
dash_t1, dash_t2, dash_t3 = st.tabs(["📝 DRAFTS", "📅 SCHEDULED", "📜 HISTORY"])

with dash_t1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").order("created_at", desc=True).execute().data
    if not drafts: st.info("No active drafts.")
    for post in drafts:
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                if post.get('image_url'): st.image(post['image_url'], use_column_width=True)
            with c2:
                new_cap = st.text_area("Caption", post['caption'], height=120, key=f"cap_{post['id']}")
                d_col, t_col = st.columns(2)
                with d_col: d = st.date_input("Date", key=f"d_{post['id']}")
                suggested = get_best_time_for_day(d)
                with t_col: t = st.time_input(f"Time (Rec: {suggested})", value=suggested, key=f"t_{post['id']}")
                final_time = f"{d} {t}"
                
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("📅 SCHEDULE", key=f"sch_{post['id']}"):
                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": final_time, "status": "scheduled"}).eq("id", post['id']).execute(); st.rerun()
                with b2:
                    if st.button("🚀 POST NOW", key=f"now_{post['id']}", type="primary"):
                        if not post.get('image_url'): st.error("No Image")
                        else:
                            with st.spinner("Transmitting..."):
                                try:
                                    r = requests.post(MAKE_WEBHOOK_URL, json={"image_url": post['image_url'], "caption": new_cap})
                                    if r.status_code == 200:
                                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute(); st.success("SENT!"); st.rerun()
                                    else: st.error(f"Error: {r.text}")
                                except Exception as e: st.error(e)
                with b3:
                    if st.button("🗑️", key=f"del_d_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute(); st.rerun()

with dash_t2:
    scheduled = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    if not scheduled: st.info("No scheduled transmissions.")
    for post in scheduled:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1: st.image(post['image_url'], width=100)
            with c2:
                st.subheader(f"⏱️ {post['scheduled_time']} UTC")
                st.text(post['caption'][:100] + "...")
                if st.button("❌ ABORT", key=f"cancel_{post['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", post['id']).execute(); st.rerun()

with dash_t3:
    history = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(10).execute().data
    if not history: st.info("No transmission logs.")
    for post in history:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1: st.image(post['image_url'], width=80)
            with c2:
                st.write(f"**Sent:** {post['scheduled_time']}")
                with st.expander("View Payload"): st.write(post['caption'])
