import streamlit as st
import hmac
from openai import OpenAI
from google import genai
from google.genai import types
from supabase import create_client
import requests
from datetime import datetime, time
from bs4 import BeautifulSoup
import random
import urllib.parse
from PIL import Image, ImageOps
import io
from streamlit_cropper import st_cropper 

# 1. PAGE CONFIG & THEME
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- CUSTOM CSS (Updated for visibility) ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    h1, h2, h3 {
        color: #00ff41 !important; 
        font-family: 'Helvetica Neue', sans-serif;
        text-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
    }
    /* Labels and Headers */
    label, .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    /* Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 25px !important; 
        background-color: #121212;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 1px solid #333; 
    }
    /* Input Fields */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div {
        background-color: #1c1c1c !important; color: white !important; border: 1px solid #333 !important; border-radius: 8px;
    }
    /* Standard Buttons (Fixing the Grey-on-White issue) */
    .stButton > button {
        background-color: #1c1c1c !important; 
        color: #00ff41 !important; 
        border: 1px solid #00ff41 !important; 
        border-radius: 8px; 
        transition: all 0.3s ease;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #00ff41 !important; 
        color: #000000 !important; 
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.7);
    }
    /* Primary Buttons (Post Now / Save) */
    button[kind="primary"] {
        background-color: #00ff41 !important; 
        color: black !important; 
        border: none !important; 
        font-weight: bold !important;
    }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #1c1c1c; border-radius: 5px; color: #888; }
    .stTabs [aria-selected="true"] { background-color: #00ff41 !important; color: black !important; }
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
    st.markdown("<h1 style='text-align: center;'>👻 ACCESS RESTRICTED</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.text_input("Enter Clearance Code", type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state: st.error("🚫 Access Denied")
    return False

if not check_password(): st.stop()

# 2. SETUP
openai_client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
google_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        if page.status_code == 200:
            soup = BeautifulSoup(page.content, "html.parser")
            text = ' '.join([p.text for p in soup.find_all('p')])
            return text[:6000] if len(text) > 50 else None
    except: return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    if response.data: return "\n".join([f"- {item['fact_summary']}" for item in response.data])
    return "No knowledge yet."

def save_ai_image_to_storage(image_bytes):
    try:
        filename = f"nano_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        supabase.storage.from_("uploads").upload(filename, image_bytes, {"content-type": "image/png"})
        return supabase.storage.from_("uploads").get_public_url(filename)
    except Exception as e:
        st.error(f"Failed to secure Nano image: {e}")
        return None

def enhance_topic(topic, style):
    prompt = f"""Rewrite this into a technical prompt for a high-end image generator (Imagen 3).
    Topic: {topic}
    Style: {style}
    Instructions:
    - Describe the camera gear (CCTV, 35mm, Daguerreotype).
    - Add paranormal details (shadow person, translucent figure).
    - Add technical artifacts (noise, grain, motion blur).
    - Maintain a realistic 'Evidence' feel.
    - Max 50 words."""
    resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def get_caption_prompt(style, topic_or_desc, context):
    base_prompt = f"Role: Social Media Manager for 'Ghost Dimension'. Context: {context}. Topic: {topic_or_desc}. "
    strategies = {
        "🔥 Viral / Debate (Ask Questions)": "Write a short, punchy caption. Start a fight in the comments. Ask 'Real or Fake?'.",
        "🕵️ Investigator (Analyze Detail)": "Focus on a specific scary detail. Ask the user to zoom in.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence mini horror story. Atmospheric.",
        "😱 Pure Panic (Short & Scary)": "Very short, terrified caption. Use uppercase and emojis like ⚠️👻."
    }
    instruction = strategies.get(style, strategies["🔥 Viral / Debate (Ask Questions)"])
    return f"{base_prompt} \n\nSTRATEGY: {instruction}"

# --- MAIN TITLE ---
st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>👻 GHOST DIMENSION <span style='color: #00ff41; font-size: 20px;'>NANO BANANA ENGINE</span></h1>", unsafe_allow_html=True)

# 3. CONTENT CREATION AREA
tab_gen, tab_upload = st.tabs(["✨ NANO GENERATOR", "📸 EVIDENCE VAULT"])

with tab_gen:
    with st.container(border=True):
        c_head, c_body = st.columns([1, 2])
        with c_head:
            st.info("🧠 **Knowledge Base**")
            l_t1, l_t2 = st.tabs(["🔗 URL", "📝 Paste"])
            with l_t1:
                learn_url = st.text_input("URL", label_visibility="collapsed", placeholder="https://...")
                if st.button("📥 Scrape"):
                    raw_text = scrape_website(learn_url)
                    if raw_text:
                        prompt = f"Extract 3-5 facts about 'Ghost Dimension' from this:\n{raw_text}"
                        resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.success("Facts Pending!"); st.rerun()
            with l_t2:
                m_text = st.text_area("Paste Text", height=100, label_visibility="collapsed")
                if st.button("📥 Learn"):
                    prompt = f"Extract 3-5 facts about 'Ghost Dimension' from this:\n{m_text}"
                    resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                    for fact in resp.choices[0].message.content.split('\n'):
                        clean = fact.strip().replace("- ", "")
                        if len(clean) > 10:
                            supabase.table("brand_knowledge").insert({"source_url": "Manual", "fact_summary": clean, "status": "pending"}).execute()
                    st.success("Facts Pending!"); st.rerun()
            
            st.divider()
            st.write("🔍 **Review Facts**")
            pending_facts = supabase.table("brand_knowledge").select("*").eq("status", "pending").execute().data
            if pending_facts:
                for fact in pending_facts:
                    st.write(f"_{fact['fact_summary']}_")
                    b1, b2 = st.columns(2)
                    with b1: 
                        if st.button("✅", key=f"a_{fact['id']}"):
                            supabase.table("brand_knowledge").update({"status": "approved"}).eq("id", fact['id']).execute(); st.rerun()
                    with b2:
                        if st.button("❌", key=f"r_{fact['id']}"):
                            supabase.table("brand_knowledge").delete().eq("id", fact['id']).execute(); st.rerun()

        with c_body:
            st.subheader("Nano Banana Realism")
            if "enhanced_topic" not in st.session_state: st.session_state.enhanced_topic = ""
            topic = st.text_area("Subject:", value=st.session_state.enhanced_topic if st.session_state.enhanced_topic else "", placeholder="e.g. A shadow figure...", height=100)
            
            c1, c2 = st.columns(2)
            with c1:
                style_choice = st.selectbox("Visual Style", ["🟢 CCTV Night Vision", "🎞️ 35mm Found Footage", "📸 Victorian Spirit Photo", "❄️ Winter Frost Horror"])
            with c2:
                if st.button("🪄 ENHANCE DETAILS"):
                    with st.spinner("Refining..."):
                        st.session_state.enhanced_topic = enhance_topic(topic, style_choice)
                        st.rerun()

            caption_style = st.selectbox("Caption Strategy", ["🔥 Viral / Debate (Ask Questions)", "🕵️ Investigator (Analyze Detail)", "📖 Storyteller (Creepypasta)", "😱 Pure Panic (Short & Scary)"])

            if st.button("🚀 GENERATE WITH NANO", type="primary"):
                with st.spinner("Invoking Imagen 3..."):
                    try:
                        knowledge = get_brand_knowledge()
                        final_cap_prompt = get_caption_prompt(caption_style, topic, knowledge)
                        cap_resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": final_cap_prompt}])
                        caption = cap_resp.choices[0].message.content
                        img_resp = google_client.models.generate_images(model='imagen-3.0-fast-001', prompt=topic, config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1", person_generation="ALLOW_ADULT"))
                        raw_bytes = img_resp.generated_images[0].image.image_bytes
                        perm_url = save_ai_image_to_storage(raw_bytes)
                        if perm_url:
                            supabase.table("social_posts").insert({"caption": caption, "image_url": perm_url, "topic": topic, "status": "draft"}).execute()
                            st.session_state.enhanced_topic = ""
                            st.success("Draft Created!"); st.rerun()
                    except Exception as e: st.error(e)

with tab_upload:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("1. Upload & Crop")
        f = st.file_uploader("Drop Evidence", type=['jpg', 'png', 'jpeg'])
        if f:
            image = ImageOps.exif_transpose(Image.open(f))
            max_size = 1200
            if max(image.size) > max_size: image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            cropped_img = st_cropper(image, aspect_ratio=(1, 1), box_color='#00ff41', should_resize_image=True)
            if st.button("✅ SAVE TO VAULT", type="primary"):
                if cropped_img.mode != "RGB": cropped_img = cropped_img.convert("RGB")
                final_img = cropped_img.resize((1080, 1080))
                buf = io.BytesIO(); final_img.save(buf, format="JPEG", quality=90)
                fname = f"ev_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                supabase.storage.from_("uploads").upload(fname, buf.getvalue(), {"content-type": "image/jpeg"})
                final_url = supabase.storage.from_("uploads").get_public_url(fname)
                supabase.table("uploaded_images").insert({"file_url": final_url, "filename": fname}).execute()
                st.success("Saved!"); st.rerun()

    with c2:
        st.subheader("2. Library")
        library = supabase.table("uploaded_images").select("*").order("created_at", desc=True).limit(4).execute().data
        if library:
            for img in library:
                with st.container(border=True):
                    col_i, col_a = st.columns([1, 2])
                    with col_i: st.image(img['file_url'], use_column_width=True)
                    with col_a:
                        if st.button("✨ DRAFT", key=f"g_{img['id']}", type="primary"):
                            with st.spinner("Analyzing..."):
                                prompt = get_caption_prompt("🔥 Viral / Debate (Ask Questions)", "This spooky image", get_brand_knowledge())
                                response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}], max_tokens=300)
                                supabase.table("social_posts").insert({"caption": response.choices[0].message.content, "image_url": img['file_url'], "topic": "Evidence", "status": "draft"}).execute(); st.success("Draft Created!")
                        if st.button("🗑️", key=f"d_{img['id']}"): supabase.table("uploaded_images").delete().eq("id", img['id']).execute(); st.rerun()

st.markdown("---")
st.markdown("<h2 style='text-align: center;'>📲 COMMAND CENTER</h2>", unsafe_allow_html=True)
d1, d2, d3 = st.tabs(["📝 DRAFTS", "📅 SCHEDULED", "📜 HISTORY"])

with d1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").order("created_at", desc=True).execute().data
    for post in drafts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1: st.image(post['image_url'], use_column_width=True)
            with col2:
                new_cap = st.text_area("Caption", post['caption'], height=150, key=f"cp_{post['id']}")
                date_in = st.date_input("Date", key=f"dt_{post['id']}")
                time_in = st.time_input("Time", value=get_best_time_for_day(date_in), key=f"tm_{post['id']}")
                if st.button("📅 Schedule", key=f"s_{post['id']}"):
                    supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": f"{date_in} {time_in}", "status": "scheduled"}).eq("id", post['id']).execute(); st.rerun()
                if st.button("🚀 POST NOW", key=f"p_{post['id']}", type="primary"):
                    requests.post(MAKE_WEBHOOK_URL, json={"image_url": post['image_url'], "caption": new_cap})
                    supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute(); st.rerun()

with d2:
    sch = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    for p in sch:
        with st.container(border=True):
            col_img, col_txt = st.columns([1, 3])
            with col_img: st.image(p['image_url'], use_column_width=True)
            with col_txt:
                st.write(f"⏰ **Due:** {p['scheduled_time']} UTC")
                st.markdown(f"> {p['caption']}")
                if st.button("❌ ABORT", key=f"can_{p['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", p['id']).execute(); st.rerun()

with d3:
    hist = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(10).execute().data
    for p in hist:
        with st.container(border=True):
            col_img, col_txt = st.columns([1, 3])
            with col_img: st.image(p['image_url'], use_column_width=True)
            with col_txt:
                st.write(f"✅ **Sent on:** {p['scheduled_time']}")
                st.markdown(f"**Caption:**\n{p['caption']}")



