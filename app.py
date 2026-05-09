import streamlit as st
import pandas as pd
import json
import datetime
import random
import gspread
import re
import pdfplumber
from docx import Document
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI

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
    """Parses text into units and removes administrative noise[cite: 1, 5, 7, 15, 19]."""
    noise_patterns = [
        r'L T P C', r'P18PECS\d+', r'Total Contact Hours', r'Prerequisite:', 
        r'Course Designed by', r'OBJECTIVES', r'COURSE OUTCOMES', r'TOTAL NO OF PERIODS'
    ]
    # Detects headers like "UNIT 1 ARTIFICIAL NEURAL NETWORKS" [cite: 5]
    header_pattern = r'(?im)^(?:Unit|Module|Chapter|Part)\s*(?:[IVX\d]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)[:.-]?\s*(.*)'
    
    lines = text.split('\n')
    structure = {}
    current_unit = None
    
    for line in lines:
        line = line.strip()
        if not line or any(re.search(p, line) for p in noise_patterns): 
            continue
        
        header_match = re.match(header_pattern, line)
        if header_match:
            current_unit = line
            structure[current_unit] = []
            continue
            
        if current_unit is None:
            current_unit = "General Topics"
            structure[current_unit] = []

        # Topic detection logic for items like "Back propagation networks" [cite: 6]
        if re.match(r'^[•\-\*]\s*(.*)|^\d+[\.\)]\s+(.*)', line):
            match = re.match(r'^[•\-\*]\s*(.*)|^\d+[\.\)]\s+(.*)', line)
            topic = match.group(1) if match.group(1) else match.group(2)
            if topic and len(topic) > 3:
                structure[current_unit].append(topic)
        elif 5 < len(line) < 150:
            structure[current_unit].append(line)
            
    return {k: v for k, v in structure.items() if v}

# --- DATABASE CONNECTION ---
def get_sheet(worksheet_name):
    try:
        creds_dict = dict(st.secrets["gspread_creds"])
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL).worksheet(worksheet_name)
    except Exception as e:
        st.error(f"Database Error: {e}")
        return None

# --- AI GENERATOR ---
def generate_questions(topic_list, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        topics_str = ", ".join(topic_list[:50])
        prompt = f"""Create {num_q} MCQ questions covering: {topics_str}. 
        Return ONLY valid JSON with structure: {{"questions": [{{"id": 1, "question_text": "...", "options": ["A. ..", "B. .."], "correct_option": "A"}}]}}"""
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        match = re.search(r'\{.*\}', response.choices[0].message.content, re.DOTALL)
        return json.loads(match.group(0))
    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    
    if 'syllabus_data' not in st.session_state:
        st.session_state['syllabus_data'] = None

    with st.expander("📂 1. Upload Syllabus", expanded=not st.session_state['syllabus_data']):
        uploaded_file = st.file_uploader("Choose a file (.pdf, .docx)", type=["pdf", "docx"])
        if uploaded_file:
            with st.spinner("Processing syllabus..."):
                text = extract_text_from_file(uploaded_file)
                st.session_state['syllabus_data'] = parse_syllabus_to_structure(text)
                st.success(f"Parsed {len(st.session_state['syllabus_data'])} units!")

    selected_topics = []
    if st.session_state['syllabus_data']:
        with st.expander("🎯 2. Select Scope", expanded=True):
            data = st.session_state['syllabus_data']
            mode = st.radio("Selection Method", ["Individual Topics", "Complete Units/Modules", "Whole Syllabus"], horizontal=True)
            
            if mode == "Individual Topics":
                all_flat = [t for sublist in data.values() for t in sublist]
                selected_topics = st.multiselect("Select individual topics (noise removed):", all_flat)
                
            elif mode == "Complete Units/Modules":
                for unit, topics in data.items():
                    if st.checkbox(f"**{unit}**", key=f"cb_{unit}"):
                        # Dynamic display of topics under selected unit
                        unit_sel = st.multiselect(f"Topics in {unit}:", topics, default=topics, key=f"ms_{unit}")
                        selected_topics.extend(unit_sel)
                
            elif mode == "Whole Syllabus":
                selected_topics = [t for sublist in data.values() for t in sublist]
                st.info(f"All units selected ({len(selected_topics)} total topics).")

    if selected_topics:
        with st.expander("🛠️ 3. Quiz Settings", expanded=True):
            col1, col2, col3 = st.columns(3)
            deg = col1.selectbox("Degree", ["UG", "PG"])
            strm = col2.text_input("Stream", placeholder="e.g. CSE")
            sem = col3.number_input("Semester", 1, 8, 1)
            
            c1, c2 = st.columns(2)
            start_d = c1.date_input("Start Date", datetime.date.today())
            end_d = c2.date_input("End Date", datetime.date.today() + datetime.timedelta(days=7))
            
            num_q = st.select_slider("Total Questions", options=[10, 20, 30, 40, 50], value=10)
            
            if st.button("🚀 Publish Quiz to Students", use_container_width=True):
                with st.spinner("Generating quiz with AI..."):
                    quiz_json = generate_questions(selected_topics, num_q)
                    if quiz_json:
                        sheet = get_sheet("Quizzes")
                        if sheet:
                            sheet.append_row([
                                str(int(datetime.datetime.now().timestamp())), 
                                f"Quiz on {len(selected_topics)} topics", deg, strm, sem, 
                                str(start_d), str(end_d), json.dumps(quiz_json), "Open", str(datetime.datetime.now())
                            ])
                            st.success("Quiz Published Successfully!")
                            st.balloons()

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    if 'profile' not in st.session_state:
        with st.form("login_form"):
            st.text_input("Full Name", key="name_in")
            st.selectbox("Degree", ["UG", "PG"], key="deg_in")
            st.text_input("Stream", key="strm_in", placeholder="e.g. CSE")
            st.number_input("Semester", 1, 8, key="sem_in")
            if st.form_submit_button("Enter Portal"):
                if st.session_state.name_in and st.session_state.strm_in:
                    st.session_state['profile'] = {
                        "name": st.session_state.name_in, "deg": st.session_state.deg_in,
                        "strm": st.session_state.strm_in, "sem": st.session_state.sem_in
                    }
                    st.rerun()
                else:
                    st.error("Please fill in all details.")
    else:
        profile = st.session_state['profile']
        st.write(f"### Welcome, {profile['name']}")
        if st.sidebar.button("Logout"):
            del st.session_state['profile']
            st.rerun()
            
        try:
            sheet = get_sheet("Quizzes")
            if sheet:
                quizzes = sheet.get_all_records()
                today = datetime.datetime.now().date()
                available = []
                
                for row in quizzes:
                    # Fuzzy matching for Degree, Stream, and Semester
                    match_deg = str(row['Degree']).strip().lower() == profile['deg'].strip().lower()
                    match_strm = str(row['Stream']).strip().lower() == profile['strm'].strip().lower()
                    match_sem = int(row['Semester']) == int(profile['sem'])
                    
                    if row['Status'] == 'Open' and match_deg and match_strm and match_sem:
                        start = datetime.datetime.strptime(str(row['StartTime']), '%Y-%m-%d').date()
                        end = datetime.datetime.strptime(str(row['EndTime']), '%Y-%m-%d').date()
                        if start <= today <= end:
                            available.append(row)

                if available:
                    for quiz in available:
                        with st.container(border=True):
                            st.write(f"**Quiz Topic:** {quiz['Topic']}")
                            if st.button(f"Take Quiz", key=f"tk_{quiz['QuizID']}"):
                                st.session_state['active_quiz'] = quiz
                                st.rerun()
                else:
                    st.info("No active quizzes found for your profile.")
        except Exception as e:
            st.error(f"Error loading quizzes: {e}")

    # Active Quiz UI
    if 'active_quiz' in st.session_state:
        quiz = st.session_state['active_quiz']
        q_list = json.loads(quiz['Questions'])['questions']
        with st.form("take_quiz"):
            st.subheader(quiz['Topic'])
            user_ans = {}
            for q in q_list:
                st.write(f"**{q['question_text']}**")
                user_ans[q['id']] = st.radio("Options:", q['options'], key=f"ans_{q['id']}", label_visibility="collapsed")
            
            if st.form_submit_button("Submit Quiz"):
                score = sum(1 for q in q_list if user_ans[q['id']][0] == q['correct_option'])
                res_sheet = get_sheet("Results")
                if res_sheet:
                    res_sheet.append_row([quiz['QuizID'], profile['name'], profile['deg'], profile['strm'], profile['sem'], quiz['Topic'], score, len(q_list), str(datetime.datetime.now())])
                    st.success(f"Score: {score}/{len(q_list)}")
                    del st.session_state['active_quiz']
                    st.info("Quiz submitted successfully.")

# --- MAIN ---
st.set_page_config(page_title="Syllabus Quiz AI", layout="wide")
role = st.sidebar.selectbox("Access Level", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.sidebar.error("Invalid Password")
else:
    student_dashboard()
