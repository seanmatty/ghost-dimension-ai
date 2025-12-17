import streamlit as st
import hmac
from openai import OpenAI
from supabase import create_client
import requests
from datetime import datetime, time
from bs4 import BeautifulSoup

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

# 2. SETUP
client = OpenAI(api_key=st.secrets["OPENAI_KEY"])
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
MAKE_WEBHOOK_URL = st.secrets["MAKE_WEBHOOK_URL"] # New Secret for 'Post Now'

# --- HELPER FUNCTIONS ---
def get_best_time_for_day(target_date):
    day_name = target_date.strftime("%A")
    response = supabase.table("strategy").select("best_hour").eq("day", day_name).execute()
    if response.data:
        return time(response.data[0]['best_hour'], 0)
    return time(20, 0)

def scrape_website(url):
    if not url.startswith("http"):
        url = "https://" + url
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        text = ' '.join([p.text for p in soup.find_all('p')])
        if len(text) < 50: return "Not enough text found."
        return text[:6000]
    except Exception as e:
        return None

def get_brand_knowledge():
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    if response.data:
        return "\n".join([f"- {item['fact_summary']}" for item in response.data])
    return "No knowledge yet."

st.title("👻 Ghost Dimension AI Manager")

# 3. TEACH & GENERATE SECTION
with st.expander("🧠 The Brain & Generator", expanded=False):
    col_teach, col_create = st.columns([1, 1])
    
    # Teach AI
    with col_teach:
        st.subheader("Teach New Knowledge")
        learn_url = st.text_input("Website URL to Learn From")
        if st.button("Analyze & Learn"):
            if not learn_url: st.error("Paste a URL first.")
            else:
                with st.spinner("Reading..."):
                    raw_text = scrape_website(learn_url)
                    if raw_text and len(raw_text) > 50:
                        prompt = f"Extract 3-5 distinct facts about 'Ghost Dimension' from this text. Return as list:\n{raw_text}"
                        summary_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                        facts_list = summary_resp.choices[0].message.content.split('\n')
                        for fact in facts_list:
                            clean = fact.strip().replace("- ", "").replace("* ", "")
                            if len(clean) > 10:
                                supabase.table("brand_knowledge").insert({"source_url": learn_url, "fact_summary": clean, "status": "pending"}).execute()
                        st.success("Facts learned! Approve them below.")
                        st.rerun()

    # Generate Content
    with col_create:
        st.subheader("Generate Content")
        if st.button("🎲 Suggest Topic"):
            with st.spinner("Thinking..."):
                knowledge = get_brand_knowledge()
                prompt = f"Based on this knowledge:\n{knowledge}\n\nSuggest ONE spooky social media topic."
                resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                st.session_state['suggested_topic'] = resp.choices[0].message.content
                st.rerun()

        default_topic = st.session_state.get('suggested_topic', '')
        topic = st.text_area("Topic:", value=default_topic, height=100)
        
        if st.button("Generate Post", type="primary"):
            with st.spinner("Creating magic..."):
                try:
                    knowledge = get_brand_knowledge()
                    prompt = f"Role: Social Manager for Ghost Dimension. Context: {knowledge}. Task: Write a scary Instagram caption about: {topic}."
                    gpt_resp = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])
                    caption = gpt_resp.choices[0].message.content
                    
                    img_resp = client.images.generate(model="dall-e-3", prompt=f"Paranormal photo of {topic}. Night vision green tint, grainy CCTV style, Ghost Dimension TV show style.", size="1024x1024")
                    image_url = img_resp.data[0].url
                    
                    supabase.table("social_posts").insert({"caption": caption, "image_url": image_url, "topic": topic, "status": "draft"}).execute()
                    st.success("Draft Created!")
                except Exception as e:
                    st.error(f"Error: {e}")

# 4. DASHBOARD
st.divider()
st.header("📲 Content Dashboard")
tab1, tab2, tab3 = st.tabs(["📝 Drafts", "📅 Scheduled", "📜 History"])

# --- TAB 1: DRAFTS ---
with tab1:
    drafts = supabase.table("social_posts").select("*").eq("status", "draft").execute().data
    if not drafts: st.info("No drafts pending.")
    
    for post in drafts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1:
                if post.get('image_url'): st.image(post['image_url'], use_column_width=True)
            with col2:
                new_cap = st.text_area("Caption", post['caption'], height=150, key=f"cap_{post['id']}")
                
                # Scheduling Inputs
                d_col, t_col = st.columns(2)
                with d_col: d = st.date_input("Date", key=f"d_{post['id']}")
                suggested = get_best_time_for_day(d)
                with t_col: t = st.time_input(f"Time (Rec: {suggested})", value=suggested, key=f"t_{post['id']}")
                final_time = f"{d} {t}"
                
                st.write("---")
                b1, b2, b3 = st.columns([1, 1, 1])
                
                # BUTTON 1: SCHEDULE
                with b1:
                    if st.button("📅 Schedule", key=f"sch_{post['id']}", type="primary"):
                        supabase.table("social_posts").update({"caption": new_cap, "scheduled_time": final_time, "status": "scheduled"}).eq("id", post['id']).execute()
                        st.success("Scheduled!")
                        st.rerun()
                
                # BUTTON 2: POST NOW (NEW!)
                with b2:
                    if st.button("🚀 Post NOW", key=f"now_{post['id']}"):
                        with st.spinner("Posting to Instagram..."):
                            # 1. Send to Make.com immediately
                            payload = {"image_url": post['image_url'], "caption": new_cap}
                            try:
                                r = requests.post(MAKE_WEBHOOK_URL, json=payload)
                                if r.status_code == 200:
                                    # 2. Update DB to 'posted'
                                    now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                    supabase.table("social_posts").update({
                                        "caption": new_cap, 
                                        "scheduled_time": now_utc, 
                                        "status": "posted"
                                    }).eq("id", post['id']).execute()
                                    st.success("Posted successfully!")
                                    st.rerun()
                                else:
                                    st.error(f"Make.com Error: {r.text}")
                            except Exception as e:
                                st.error(f"Connection Error: {e}")

                # BUTTON 3: DELETE
                with b3:
                    if st.button("🗑️ Delete", key=f"del_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute()
                        st.rerun()

# --- TAB 2: SCHEDULED ---
with tab2:
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

# --- TAB 3: HISTORY (NEW!) ---
with tab3:
    st.write("Recent posts sent to Instagram:")
    # Fetch last 20 posted items
    history = supabase.table("social_posts").select("*").eq("status", "posted").order("scheduled_time", desc=True).limit(20).execute().data
    
    if not history:
        st.info("No history yet.")
    
    for post in history:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                if post.get('image_url'): st.image(post['image_url'], width=100)
            with c2:
                # Show date nicely
                date_str = str(post['scheduled_time'])
                st.write(f"**Posted on:** {date_str}")
                with st.expander("View Caption"):
                    st.write(post['caption'])
