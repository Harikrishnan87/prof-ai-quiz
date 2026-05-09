import streamlit as st
import pandas as pd
import json
import datetime
import random
import gspread
import re
import pdfplumber
import time
from docx import Document
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from streamlit.components.v1 import html

# --- CONFIGURATION ---
ADMIN_PASSWORD = "Eliza@123"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1t4JYC-O71X3bV2F0SbNrWXZvLcpNZwn_XXQ-6RGWv64/edit"

# --- HELPER FUNCTIONS ---
def extract_text_from_file(uploaded_file):
    text = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            with pdfplumber.open(uploaded_file) as pdf:
                text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif uploaded_file.name.endswith('.docx'):
            doc = Document(uploaded_file)
            text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return ""

def parse_syllabus_to_structure(text):
    """Identifies Units and topics while filtering administrative noise [cite: 1, 5-21]."""
    noise_patterns = [r'L T P C', r'P18PECS\d+', r'Total Contact Hours', r'Prerequisite:', r'COURSE OUTCOMES', r'TOTAL NO OF PERIODS']
    header_pattern = r'(?im)^(?:Unit|Module|Chapter|Part)\s*(?:[IVX\d]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)[:.-]?\s*(.*)'
    lines = text.split('\n')
    structure = {}
    current_unit = None
    for line in lines:
        line = line.strip()
        if not line or any(re.search(p, line) for p in noise_patterns): continue
        header_match = re.match(header_pattern, line)
        if header_match:
            current_unit = line
            structure[current_unit] = []
            continue
        if current_unit is None:
            current_unit = "General Topics"
            structure[current_unit] = []
        if 5 < len(line) < 150:
            structure[current_unit].append(line)
    return {k: v for k, v in structure.items() if v}

def get_sheet(worksheet_name):
    try:
        creds_dict = dict(st.secrets["gspread_creds"])
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL).worksheet(worksheet_name)
    except Exception:
        return None

def generate_questions_ai(topic_list, num_q, level):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        topics_str = ", ".join(topic_list[:30])
        prompt = f"""Create {num_q} MCQ questions at the Bloom's Taxonomy level of '{level}' covering: {topics_str}.
        Return ONLY valid JSON: {{"questions": [{{"id": 1, "question_text": "...", "options": ["A. ..", "B. .."], "correct_option": "A"}}]}}"""
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], temperature=0.7)
        return json.loads(re.search(r'\{.*\}', response.choices[0].message.content, re.DOTALL).group(0))
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    
    if 'syllabus_data' not in st.session_state: st.session_state['syllabus_data'] = None
    if 'staging_quiz' not in st.session_state: st.session_state['staging_quiz'] = None

    with st.expander("📂 1. Upload & Analyze Syllabus", expanded=not st.session_state['syllabus_data']):
        uploaded_file = st.file_uploader("Upload PDF/DOCX", type=["pdf", "docx"])
        if uploaded_file:
            text = extract_text_from_file(uploaded_file)
            st.session_state['syllabus_data'] = parse_syllabus_to_structure(text)
            st.success("Syllabus Analysed.")

    selected_topics = []
    if st.session_state['syllabus_data']:
        with st.expander("🎯 2. Select Scope & Bloom's Level", expanded=True):
            data = st.session_state['syllabus_data']
            mode = st.radio("Selection Method", ["Individual Topics", "Complete Units", "Whole Syllabus"], horizontal=True)
            bloom_level = st.select_slider("Bloom's Taxonomy Level", options=["Recall", "Understanding", "Analysis"])
            
            if mode == "Individual Topics":
                all_flat = [t for sublist in data.values() for t in sublist]
                selected_topics = st.multiselect("Topics:", all_flat)
            elif mode == "Complete Units":
                for u, topics in data.items():
                    if st.checkbox(f"**Include {u}**", key=f"unit_check_{u}"):
                        for t_idx, topic in enumerate(topics):
                            if st.checkbox(topic, value=True, key=f"topic_{u}_{t_idx}"):
                                selected_topics.append(topic)
            elif mode == "Whole Syllabus":
                selected_topics = [t for sublist in data.values() for t in sublist]

            num_q = st.number_input("Number of Questions", 5, 50, 10)
            if st.button("🪄 Stage AI Quiz for Review"):
                if selected_topics:
                    st.session_state['staging_quiz'] = generate_questions_ai(selected_topics, num_q, bloom_level)
                    st.session_state['current_bloom'] = bloom_level
                else:
                    st.warning("Please select topics.")

    if st.session_state['staging_quiz']:
        st.divider()
        st.subheader("📝 Review & Edit Stage")
        edited_questions = []
        for i, q in enumerate(st.session_state['staging_quiz']['questions']):
            with st.container(border=True):
                new_text = st.text_area(f"Question {i+1}", value=q['question_text'], key=f"edit_q_{i}")
                new_opts = [st.text_input(f"Option {chr(65+j)}", value=opt, key=f"edit_o_{i}_{j}") for j, opt in enumerate(q['options'])]
                new_correct = st.selectbox("Correct Option", ["A", "B", "C", "D"], index=["A","B","C","D"].index(q['correct_option']), key=f"edit_c_{i}")
                edited_questions.append({"id": i+1, "question_text": new_text, "options": new_opts, "correct_option": new_correct})

        with st.expander("📅 3. Schedule & Settings", expanded=True):
            col1, col2, col3 = st.columns(3)
            deg, strm, sem = col1.selectbox("Degree", ["UG", "PG"]), col2.text_input("Stream"), col3.number_input("Semester", 1, 8, 1)
            c1, c2 = st.columns(2)
            start_date = c1.date_input("Start Date", datetime.date.today())
            end_date = c2.date_input("End Date", datetime.date.today() + datetime.timedelta(days=7))
            time_limit = st.number_input("Time per Question (Seconds)", 10, 120, 30)

        if st.button("🚀 Confirm & Publish Officially"):
            final_quiz = {"questions": edited_questions, "time_limit": time_limit}
            sheet = get_sheet("Quizzes")
            if sheet:
                sheet.append_row([str(int(time.time())), st.session_state['current_bloom'], deg, strm, sem, str(start_date), str(end_date), json.dumps(final_quiz), "Open", str(datetime.datetime.now())])
                st.success("Quiz Published!")
                st.session_state['staging_quiz'] = None

    st.divider()
    st.subheader("📊 Manage Results & Class Analytics")
    try:
        res_sheet = get_sheet("Results")
        if res_sheet:
            res_data = res_sheet.get_all_records()
            if res_data:
                df = pd.DataFrame(res_data)
                st.dataframe(df, use_container_width=True)
                st.markdown("### 🔍 Knowledge Gap Analysis")
                unit_performance = df.groupby('Topic')['Score'].mean().sort_values()
                if not unit_performance.empty:
                    st.error(f"🚨 **Critical Weakness Identified:** Students are struggling most with **'{unit_performance.index[0]}'**.")
                st.download_button("📥 Export CSV", df.to_csv(index=False), "results.csv", "text/csv")
    except Exception: st.info("Results pending.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    html("<script>window.onblur = function() { alert('Integrity Warning: Tab switching is monitored.'); };</script>", height=0)

    if 'profile' not in st.session_state:
        with st.form("login"):
            name = st.text_input("Full Name")
            deg, strm, sem = st.selectbox("Degree", ["UG", "PG"]), st.text_input("Stream"), st.number_input("Semester", 1, 8)
            if st.form_submit_button("Enter Portal"):
                st.session_state['profile'] = {"name": name, "deg": deg, "strm": strm, "sem": sem}
                st.rerun()
    else:
        profile = st.session_state['profile']
        st.write(f"Logged in: {profile['name']}")
        
        quiz_sheet = get_sheet("Quizzes")
        res_sheet = get_sheet("Results")
        
        if quiz_sheet and res_sheet:
            quizzes = quiz_sheet.get_all_records()
            results = res_sheet.get_all_records()
            today = datetime.date.today()
            
            # FIX: Using 'StudentName' to match your results sheet header and added error safety
            submitted_keys = set()
            for r in results:
                s_name = r.get('StudentName') or r.get('Name') or ""
                q_id = str(r.get('QuizID') or "")
                if s_name and q_id:
                    submitted_keys.add((s_name, q_id))

            for row in quizzes:
                # Filter by profile and Schedule Dates
                match_p = (str(row['Degree']) == profile['deg'] and 
                           str(row['Stream']).strip().lower() == profile['strm'].strip().lower() and 
                           int(row['Semester']) == profile['sem'])
                
                start_dt = datetime.datetime.strptime(str(row['StartTime']), '%Y-%m-%d').date()
                end_dt = datetime.datetime.strptime(str(row['EndTime']), '%Y-%m-%d').date()
                is_active = (start_dt <= today <= end_dt)

                if match_p and is_active:
                    with st.container(border=True):
                        st.write(f"**{row['Topic']}**")
                        if (profile['name'], str(row['QuizID'])) in submitted_keys:
                            st.success("✅ Assessment Submitted")
                        else:
                            if st.button("Start Quiz", key=f"start_{row['QuizID']}"):
                                st.session_state['active_quiz'] = row
                                st.rerun()

    if 'active_quiz' in st.session_state:
        quiz_data = json.loads(st.session_state['active_quiz']['Questions'])
        with st.form("quiz_run"):
            st.subheader(st.session_state['active_quiz']['Topic'])
            answers = {q['id']: st.radio(f"**{q['question_text']}**", q['options'], key=f"run_{q['id']}") for q in quiz_data['questions']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in quiz_data['questions'] if answers[q['id']][0] == q['correct_option'])
                get_sheet("Results").append_row([st.session_state['active_quiz']['QuizID'], profile['name'], profile['deg'], profile['strm'], profile['sem'], st.session_state['active_quiz']['Topic'], score, len(quiz_data['questions']), str(datetime.datetime.now())])
                st.success(f"Final Score: {score}/{len(quiz_data['questions'])}")
                del st.session_state['active_quiz']
                st.rerun()

# --- MAIN ---
st.set_page_config(layout="wide")
role = st.sidebar.selectbox("Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD: professor_dashboard()
else: student_dashboard()
