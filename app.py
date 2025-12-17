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

# 1. PAGE CONFIG & THEME
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- UPDATED CUSTOM CSS (Expander Fixes) ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    h1, h2, h3 {
        color: #00ff41 !important; 
        font-family: 'Helvetica Neue', sans-serif;
        text-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
    }
    label, .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    /* Expanders (Maintenance Section Fix) */
    .stExpander {
        background-color: #121212 !important;
        border: 1px solid #333 !important;
        border-radius: 12px !important;
    }
    .stExpander [data-testid="stExpanderHeader"] {
        color: #00ff41 !important;
        background-color: #121212 !important;
    }
    .stExpander [data-testid="stExpanderHeader"]:hover {
        color: #ffffff !important;
    }
    
    /* Input Boxes */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div {
        background-color: #1c1c1c !important; color: white !important; border: 1px solid #333 !important; border-radius: 8px;
    }
    
    /* Standard Buttons */
    .stButton > button {
        background-color: #1c1c1c !important; 
        color: #00ff41 !important; 
        border: 1px solid #00ff41 !important; 
        border-radius: 8px; 
        font-weight: 500;
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
    prompt = f"Rewrite this into a technical prompt for Imagen 4 Ultra. Topic: {topic}. Style: {style}. Instructions: Gear: CCTV, 35mm, or Daguerreotype. Artifacts: noise, grain, motion blur. Max 50 words."
    resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def get_caption_prompt(style, topic_or_desc, context):
    base_prompt = f"Role: Social Media Manager. Context: {context}. Topic: {topic_or_desc}."
    strategies = {
        "🔥 Viral / Debate (Ask Questions)": "Write a punchy caption. Ask 'Real or Fake?'.",
        "🕵️ Investigator (Analyze Detail)": "Focus on a detail. Ask them to zoom in.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence horror story.",
        "😱 Pure Panic (Short & Scary)": "Very short, terrified. Use uppercase and ⚠️👻."
    }
    return f"{base_prompt} \n\nSTRATEGY: {strategies.get(style, strategies['🔥 Viral / Debate (Ask Questions)'])}"

# --- MAIN TITLE & COUNTER ---
total_ev = supabase.table("social_posts").select("id", count="exact").eq("status", "posted").execute().count
st.markdown(f"<h1 style='text-align: center; margin-bottom: 0px;'>👻 GHOST DIMENSION <span style='color: #00ff41; font-size: 20px;'>NANO BANANA</span></h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: #888;'>Captured Evidence: {total_ev if total_ev else 0} entries</p>", unsafe_allow_html=True)

# 3. TAB AREA
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
                        prompt = f"Extract 3-5 facts:\n{raw_text}"
                        resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        for fact in resp.choices[0].message.content.split('\n'):
                            clean = fact.strip().replace("- ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.success("Facts Pending!"); st.rerun()
            with l_t2:
                m_text = st.text_area("Paste Text", height=100, label_visibility="collapsed")
                if st.button("📥 Learn"):
                    prompt = f"Extract 3-5 facts:\n{m_text}"
                    resp = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                    for fact in resp.choices[0].message.content.split('\n'):
                        clean = fact.strip().replace("- ", "")
                        if len(clean) > 10:
                            supabase.table("brand_knowledge").insert({"source_url": "Manual", "fact_summary": clean, "status": "pending"}).execute()
                    st.success("Facts Pending!"); st.rerun()

        with c_body:
            st.subheader("Nano Banana Realism")
            if "enhanced_topic" not in st.session_state: st.session_state.enhanced_topic = ""
            topic = st.text_area("Subject:", value=st.session_state.enhanced_topic, placeholder="e.g. A shadow figure...", height=100)
            c1, c2 = st.columns(2)
            with c1: style_choice = st.selectbox("Style", ["🟢 CCTV Night Vision", "🎞️ 35mm Found Footage", "📸 Victorian Spirit Photo", "❄️ Winter Frost Horror"])
            with c2: 
                if st.button("🪄 ENHANCE DETAILS"):
                    st.session_state.enhanced_topic = enhance_topic(topic, style_choice); st.rerun()
            
            caption_style = st.selectbox("Strategy", ["🔥 Viral / Debate (Ask Questions)", "🕵️ Investigator (Analyze Detail)", "📖 Storyteller (Creepypasta)", "😱 Pure Panic (Short & Scary)"])

            if st.button("🚀 GENERATE WITH NANO", type="primary"):
                with st.spinner("Invoking Imagen 4 Ultra..."):
                    try:
                        final_cap = openai_client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": get_caption_prompt(caption_style, topic, get_brand_knowledge())}]).choices[0].message.content
                        img_resp = google_client.models.generate_images(model='imagen-4.0-ultra-generate-001', prompt=topic, config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1", person_generation="ALLOW_ADULT"))
                        perm_url = save_ai_image_to_storage(img_resp.generated_images[0].image.image_bytes)
                        if perm_url:
                            supabase.table("social_posts").insert({"caption": final_cap, "image_url": perm_url, "topic": topic, "status": "draft"}).execute()
                            st.session_state.enhanced_topic = ""; st.success("Draft Created!"); st.rerun()
                    except Exception as e: st.error(e)

with tab_upload:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("1. Upload")
        f = st.file_uploader("Drop Evidence", type=['jpg', 'png', 'jpeg'])
        if f:
            image = ImageOps.exif_transpose(Image.open(f))
            cropped_img = st_cropper(image, aspect_ratio=(1, 1), box_color='#00ff41', should_resize_image=True)
            if st.button("✅ SAVE TO VAULT", type="primary"):
                buf = io.BytesIO(); cropped_img.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG", quality=90)
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
                col_i, col_a = st.columns([1, 2])
                with col_i: st.image(img['file_url'], use_column_width=True)
                with col_a:
                    if st.button("✨ DRAFT", key=f"g_{img['id']}", type="primary"):
                        prompt = get_caption_prompt("🔥 Viral / Debate (Ask Questions)", "Spooky image", get_brand_knowledge())
                        response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}], max_tokens=300)
                        supabase.table("social_posts").insert({"caption": response.choices[0].message.content, "image_url": img['file_url'], "topic": "Evidence", "status": "draft"}).execute(); st.rerun()
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
                d_in, t_in = st.date_input("Date", key=f"dt_{post['id']}"), st.time_input("Time", value=get_best_time_for_day(datetime.now()), key=f"tm_{post['id']}")
                if st.button("📅 Schedule", key=f"s_{post['id']}"):
                    supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": f"{d_in} {t_in}", "status": "scheduled"}).eq("id", post['id']).execute(); st.rerun()
                if st.button("🚀 POST NOW", key=f"p_{post['id']}", type="primary"):
                    requests.post(MAKE_WEBHOOK_URL, json={"image_url": post['image_url'], "caption": new_cap})
                    supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute(); st.rerun()

# --- HISTORY TAB ---
with d3:
    hist = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(10).execute().data
    for p in hist:
        with st.container(border=True):
            ci, ct = st.columns([1, 3])
            with ci: st.image(p['image_url'], use_column_width=True)
            with ct: st.write(f"✅ Sent: {p['scheduled_time']}"); st.markdown(f"> {p['caption']}")

# --- FIXED MAINTENANCE SECTION ---
st.markdown("---")
with st.expander("🛠️ SYSTEM MAINTENANCE & PURGE", expanded=False):
    st.warning("Archive Policy: Delete 'posted' content older than 60 days to save space.")
    
    # 1. Check for old evidence
    sixty_days_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    old_data = supabase.table("social_posts").select("id, image_url").eq("status", "posted").lt("created_at", sixty_days_ago).execute().data
    
    c_stat, c_act = st.columns(2)
    with c_stat:
        st.write(f"📂 **Overdue for Purge:** {len(old_data)} files")
    
    with c_act:
        # TEST BUTTON: Always appears so you can see the color.
        # INCINERATE BUTTON: Only works if there is actual old data.
        if len(old_data) > 0:
            if st.button("🔥 INCINERATE OLD EVIDENCE", help="Permanently delete from vault."):
                filenames = [url['image_url'].split('/')[-1] for url in old_data]
                supabase.storage.from_("uploads").remove(filenames)
                supabase.table("social_posts").delete().in_("id", [i['id'] for i in old_data]).execute()
                st.success("Vault Purged!"); st.rerun()
        else:
            st.button("✅ VAULT IS CURRENT", disabled=True)
