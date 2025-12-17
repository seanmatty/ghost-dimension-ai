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
AYRSHARE_KEY = st.secrets["AYRSHARE_KEY"]

# --- TEMPORARY FIX ---
st.divider()
st.subheader("🔧 Repair Tools")
webhook_url = st.text_input("Paste your Make.com Webhook URL here:")

if st.button("🔥 FORCE FIRE TEST SIGNAL"):
    if webhook_url:
        payload = {
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/e/e7/Everest_North_Face_toward_Base_Camp_Tibet_Luca_Galuzzi_2006.jpg",
            "caption": "This is a test from Ghost Dimension AI!"
        }
        requests.post(webhook_url, json=payload)
        st.success("Signal sent! Go check Make.com now!")
    else:
        st.error("https://hook.eu1.make.com/cvuatijp1zs1g8w6hrheudl3saaxmnj3")

# --- HELPER FUNCTIONS ---
def get_best_time_for_day(target_date):
    day_name = target_date.strftime("%A")
    response = supabase.table("strategy").select("best_hour").eq("day", day_name).execute()
    if response.data:
        return time(response.data[0]['best_hour'], 0)
    return time(20, 0)

def scrape_website(url):
    """Downloads text from a website link with smart error handling."""
    if not url.startswith("http"):
        url = "https://" + url
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        text = ' '.join([p.text for p in soup.find_all('p')])
        
        if len(text) < 50:
            return "Could not find much text. Maybe try a specific blog post or episode page?"
            
        return text[:6000] # Increased limit to capture more info
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None

def get_brand_knowledge():
    """Fetches all APPROVED facts about your business."""
    response = supabase.table("brand_knowledge").select("fact_summary").eq("status", "approved").execute()
    if response.data:
        return "\n".join([f"- {item['fact_summary']}" for item in response.data])
    return "No knowledge yet. The show is about paranormal investigations."

st.title("👻 Ghost Dimension AI Manager")

# 3. TEACH & GENERATE SECTION
st.header("🧠 The Brain")

col_teach, col_create = st.columns([1, 1])

# --- LEFT COLUMN: TEACH THE AI ---
with col_teach:
    st.subheader("Teach New Knowledge")
    with st.expander("Add a Website Link", expanded=True):
        st.info("Paste a link. I will extract multiple facts.")
        learn_url = st.text_input("Website URL")
        
        if st.button("Analyze & Learn"):
            if not learn_url:
                st.error("Please paste a URL first.")
            else:
                with st.spinner("Reading and extracting facts..."):
                    raw_text = scrape_website(learn_url)
                    
                    if raw_text and len(raw_text) > 50:
                        # UPDATED PROMPT: Ask for a LIST
                        prompt = f"""
                        Read this text about 'Ghost Dimension'.
                        Extract 3 to 5 distinct, interesting facts or themes.
                        Return them as a plain list separated by newlines.
                        Do not use bullet points or numbers. Just the facts.
                        TEXT: {raw_text}
                        """
                        summary_resp = client.chat.completions.create(
                            model="gpt-4", messages=[{"role": "user", "content": prompt}]
                        )
                        # Split the AI's answer into a list of facts
                        facts_block = summary_resp.choices[0].message.content
                        facts_list = facts_block.split('\n')
                        
                        # Loop through and save each fact separately
                        count = 0
                        for fact in facts_list:
                            clean_fact = fact.strip().replace("- ", "").replace("* ", "")
                            if len(clean_fact) > 10: # Ignore empty lines
                                supabase.table("brand_knowledge").insert({
                                    "source_url": learn_url,
                                    "fact_summary": clean_fact,
                                    "status": "pending"
                                }).execute()
                                count += 1
                                
                        st.success(f"Successfully extracted {count} new facts! Review them below.")
                        st.rerun()
                    else:
                        st.error("Could not read that website. It might be empty or blocking bots.")

    # Show Pending Knowledge for Approval
    pending_knowledge = supabase.table("brand_knowledge").select("*").eq("status", "pending").execute().data
    if pending_knowledge:
        st.warning(f"You have {len(pending_knowledge)} facts waiting for approval:")
        for fact in pending_knowledge:
            with st.container(border=True):
                st.write(f"**AI Learned:** {fact['fact_summary']}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Approve", key=f"app_{fact['id']}"):
                        supabase.table("brand_knowledge").update({"status": "approved"}).eq("id", fact['id']).execute()
                        st.rerun()
                with c2:
                    if st.button("🗑️ Reject", key=f"rej_{fact['id']}"):
                        supabase.table("brand_knowledge").delete().eq("id", fact['id']).execute()
                        st.rerun()

# --- RIGHT COLUMN: CREATE CONTENT ---
with col_create:
    st.subheader("Generate Content")
    
    # "Suggest Topic" Feature
    if st.button("🎲 Suggest a Topic from Knowledge"):
        with st.spinner("Thinking..."):
            knowledge = get_brand_knowledge()
            prompt = f"Based on this knowledge about Ghost Dimension:\n{knowledge}\n\nSuggest ONE spooky, engaging social media topic or question for a post."
            suggestion_resp = client.chat.completions.create(
                model="gpt-4", messages=[{"role": "user", "content": prompt}]
            )
            st.session_state['suggested_topic'] = suggestion_resp.choices[0].message.content
            st.rerun()

    # The Topic Input
    default_topic = st.session_state.get('suggested_topic', '')
    topic = st.text_area("Topic to write about:", value=default_topic, height=100)
    
    if st.button("Generate Post", type="primary"):
        with st.spinner("AI is writing and painting..."):
            try:
                knowledge_context = get_brand_knowledge()
                
                # A. Write Caption
                prompt = f"""
                You are the social media manager for 'Ghost Dimension'.
                BRAND KNOWLEDGE: {knowledge_context}
                
                TASK: Write a scary, viral Instagram caption about: {topic}. 
                Use emojis and hashtags. Keep it professional but spooky.
                """
                gpt_resp = client.chat.completions.create(
                    model="gpt-4", messages=[{"role": "user", "content": prompt}]
                )
                caption_text = gpt_resp.choices[0].message.content
                
                # B. Create Image
                img_resp = client.images.generate(
                    model="dall-e-3", 
                    prompt=f"Realistic paranormal investigation photo of {topic}. Style: Night vision green tint, grainy CCTV footage look, dramatic lighting, shadows, 4k resolution, in the style of the TV show Ghost Dimension.", 
                    n=1,
                    size="1024x1024"
                )
                image_url = img_resp.data[0].url
                
                # C. Save to Database
                data = {"caption": caption_text, "image_url": image_url, "topic": topic, "status": "draft"}
                supabase.table("social_posts").insert(data).execute()
                st.success("Draft created! Check the Dashboard below.")
                
            except Exception as e:
                st.error(f"An error occurred: {e}")

# 4. DASHBOARD (Review & Schedule)
st.divider()
st.header("📲 Content Schedule")
tab1, tab2 = st.tabs(["📝 Drafts", "📅 Scheduled"])

# --- TAB 1: DRAFTS ---
with tab1:
    response = supabase.table("social_posts").select("*").eq("status", "draft").execute()
    drafts = response.data

    if not drafts:
        st.info("No drafts pending.")

    for post in drafts:
        container = st.empty()
        with container.container():
            st.divider()
            col1, col2 = st.columns([1, 2])
            with col1:
                if post.get('image_url'):
                    st.image(post['image_url'], use_column_width=True)
            with col2:
                new_cap = st.text_area("Caption", post['caption'], height=150, key=f"cap_{post['id']}")
                d_col, t_col = st.columns(2)
                with d_col:
                    d = st.date_input("Date", key=f"d_{post['id']}")
                
                suggested_time = get_best_time_for_day(d)
                with t_col:
                    t = st.time_input(f"Time (Best: {suggested_time})", value=suggested_time, key=f"t_{post['id']}")
                
                final_time = f"{d} {t}"
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Schedule", key=f"btn_{post['id']}", type="primary"):
                        supabase.table("social_posts").update({
                            "caption": new_cap, "scheduled_time": final_time, "status": "scheduled"
                        }).eq("id", post['id']).execute()
                        st.success("Scheduled!")
                        container.empty()
                        st.rerun()
                with c2:
                    if st.button("🗑️ Delete", key=f"del_{post['id']}"):
                        supabase.table("social_posts").delete().eq("id", post['id']).execute()
                        st.error("Deleted.")
                        container.empty()
                        st.rerun()

# --- TAB 2: SCHEDULED ---
with tab2:
    response = supabase.table("social_posts").select("*").eq("status", "scheduled").order("scheduled_time").execute()
    scheduled = response.data
    
    if not scheduled:
        st.info("Nothing scheduled.")
        
    for post in scheduled:
        with st.container():
            st.divider()
            c1, c2 = st.columns([1, 3])
            with c1:
                if post.get('image_url'):
                    st.image(post['image_url'], width=100)
            with c2:
                st.subheader(f"Due: {post['scheduled_time']} UTC")
                st.text(post['caption'])
                if st.button("❌ Cancel", key=f"cancel_{post['id']}"):
                    supabase.table("social_posts").update({"status": "draft"}).eq("id", post['id']).execute()
                    st.rerun()

