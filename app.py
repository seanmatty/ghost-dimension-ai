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

# 1. PAGE CONFIG & THEME
st.set_page_config(page_title="Ghost Dimension AI", page_icon="👻", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    h1, h2, h3 { color: #00ff41 !important; text-shadow: 0 0 10px rgba(0, 255, 65, 0.3); }
    label { color: #ffffff !important; font-weight: 600 !important; }
    div[data-testid="stVerticalBlockBorderWrapper"] { padding: 25px !important; background-color: #121212; border-radius: 12px; border: 1px solid #333; }
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stSelectbox > div > div > div { background-color: #1c1c1c; color: white; border: 1px solid #333; }
    .stButton > button { color: #00ff41; border: 1px solid #00ff41; border-radius: 8px; }
    button[kind="primary"] { background-color: #00ff41 !important; color: black !important; }
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
    try:
        page = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        return ' '.join([p.text for p in soup.find_all('p')])[:6000]
    except: return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    return "\n".join([f"- {item['fact_summary']}" for item in response.data]) if response.data else "No knowledge."

def save_ai_image_to_storage(image_url):
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            filename = f"ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            supabase.storage.from_("uploads").upload(filename, response.content, {"content-type": "image/png"})
            return supabase.storage.from_("uploads").get_public_url(filename)
    except: pass
    return image_url

def get_caption_prompt(style, topic_or_desc, context):
    strategies = {
        "🔥 Viral / Debate (Ask Questions)": "Start a fight in the comments. Ask 'Real or Fake?'.",
        "🕵️ Investigator (Analyze Detail)": "Focus on a detail. Ask 'Do you see what I see?'.",
        "📖 Storyteller (Creepypasta)": "Write a 3-sentence mini horror story.",
        "😱 Pure Panic (Short & Scary)": "Very short, terrified, uppercase."
    }
    return f"Role: Ghost Dimension Manager. Context: {context}. Topic: {topic_or_desc}. STRATEGY: {strategies.get(style, '')}"

# 3. CONTENT CREATION AREA
st.markdown("<h1 style='text-align: center;'>👻 GHOST DIMENSION AI SYSTEM</h1>", unsafe_allow_html=True)
tab_gen, tab_upload = st.tabs(["✨ GENERATE NEW", "📸 EVIDENCE ANALYSIS"])

with tab_gen:
    with st.container(border=True):
        c_head, c_body = st.columns([1, 2])
        with c_head:
            st.info("🧠 **Knowledge Base**")
            learn_url = st.text_input("URL", placeholder="https://...")
            if st.button("📥 Scrape"):
                raw = scrape_website(learn_url)
                if raw:
                    resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": f"Extract 3 facts: {raw}"}])
                    for f in resp.choices[0].message.content.split('\n'):
                        if len(f) > 10: supabase.table("brand_knowledge").insert({"fact_summary": f.strip(), "status": "pending"}).execute()
                    st.success("Pending!"); st.rerun()
            st.divider()
            pending = supabase.table("brand_knowledge").select("*").eq("status", "pending").execute().data
            if pending:
                for f in pending:
                    st.write(f"_{f['fact_summary']}_")
                    if st.button("✅", key=f"a_{f['id']}"): supabase.table("brand_knowledge").update({"status": "approved"}).eq("id", f['id']).execute(); st.rerun()

        with c_body:
            st.subheader("Create Content")
            topic = st.text_area("Subject:", placeholder="Topic...", height=100)
            c1, c2 = st.columns(2)
            with c1: style_choice = st.selectbox("Visual Style", ["🟢 CCTV / Night Vision", "🎬 Cinematic Horror", "📸 Vintage Photograph", "🎄 Christmas Horror", "🎃 Halloween Vibes", "❄️ Deep Winter", "☀️ Midsummer Nightmare"])
            with c2: caption_style = st.selectbox("Caption Strategy", ["🔥 Viral / Debate (Ask Questions)", "🕵️ Investigator (Analyze Detail)", "📖 Storyteller (Creepypasta)", "😱 Pure Panic (Short & Scary)"])
            
            if st.button("🚀 GENERATE DRAFT", type="primary"):
                with st.spinner("Summoning AI..."):
                    cap_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": get_caption_prompt(caption_style, topic, get_brand_knowledge())}])
                    img_resp = client.images.generate(model="dall-e-3", prompt=f"{topic}. {style_choice}", size="1024x1024", quality="hd")
                    perm_url = save_ai_image_to_storage(img_resp.data[0].url)
                    supabase.table("social_posts").insert({"caption": cap_resp.choices[0].message.content, "image_url": perm_url, "topic": topic, "status": "draft"}).execute()
                    st.success("Draft Created!"); st.rerun()

with tab_upload:
    c1, c2 = st.columns([1, 1])
    with c1:
        f = st.file_uploader("Drop Evidence", type=['jpg', 'png', 'jpeg'])
        if f:
            cropped = st_cropper(ImageOps.exif_transpose(Image.open(f)), aspect_ratio=(1, 1), box_color='#00ff41')
            if st.button("✅ SAVE", type="primary"):
                buf = io.BytesIO(); cropped.convert("RGB").resize((1080, 1080)).save(buf, format="JPEG")
                fname = f"ev_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                supabase.storage.from_("uploads").upload(fname, buf.getvalue(), {"content-type": "image/jpeg"})
                url = supabase.storage.from_("uploads").get_public_url(fname)
                supabase.table("uploaded_images").insert({"file_url": url, "filename": fname}).execute()
                st.success("Saved!"); st.rerun()
    with c2:
        lib = supabase.table("uploaded_images").select("*").order("created_at", desc=True).limit(4).execute().data
        if lib:
            for img in lib:
                with st.container(border=True):
                    st.image(img['file_url'], width=150)
                    if st.button("✨ DRAFT", key=f"g_{img['id']}", type="primary"):
                        resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": "Scary caption for this image."}, {"type": "image_url", "image_url": {"url": img['file_url']}}]}])
                        supabase.table("social_posts").insert({"caption": resp.choices[0].message.content, "image_url": img['file_url'], "topic": "Evidence", "status": "draft"}).execute(); st.rerun()

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
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("📅 Schedule", key=f"s_{post['id']}"):
                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": f"{date_in} {time_in}", "status": "scheduled"}).eq("id", post['id']).execute(); st.rerun()
                with b2:
                    if st.button("🚀 POST NOW", key=f"p_{post['id']}", type="primary"):
                        with st.spinner("Sending..."):
                            requests.post(MAKE_WEBHOOK_URL, json={"image_url": post['image_url'], "caption": new_cap})
                            supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "status": "posted"}).eq("id", post['id']).execute(); st.rerun()
                with b3:
                    if st.button("🗑️", key=f"del_{post['id']}"): supabase.table("social_posts").delete().eq("id", post['id']).execute(); st.rerun()

with d2:
    sch = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute().data
    for p in sch:
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1: st.image(p['image_url'], use_column_width=True)
            with c2:
                st.write(f"⏰ **Due:** {p['scheduled_time']} UTC")
                st.markdown(f"> {p['caption']}")
                if st.button("❌ ABORT", key=f"can_{p['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", p['id']).execute(); st.rerun()

with d3:
    hist = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(10).execute().data
    for p in hist:
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1: st.image(p['image_url'], use_column_width=True)
            with c2:
                st.write(f"✅ Sent: {p['scheduled_time']}")
                st.markdown(f"**Caption:**\n{p['caption']}")
