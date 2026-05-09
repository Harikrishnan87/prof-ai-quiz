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
    """
    Improved parsing logic to identify Units/Modules more accurately.
    """
    # Patterns for headers: "Unit 1", "UNIT I", "Module One", "Chapter 1"
    header_pattern = r'(?im)^(?:Unit|Module|Chapter|Part)\s*(?:[IVX\d]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)[:.-]?\s*(.*)'
    lines = text.split('\n')
    
    structure = {}
    current_unit = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Detect Header
        header_match = re.match(header_pattern, line)
        if header_match:
            current_unit = line
            structure[current_unit] = []
            continue
            
        # If we haven't found a unit yet, put topics in 'General'
        if current_unit is None:
            current_unit = "General Topics"
            structure[current_unit] = []

        # Detect Topics (Bullet points, numbered lists, or short descriptive lines)
        if re.match(r'^[•\-\*]\s*(.*)|^\d+[\.\)]\s+(.*)', line):
            match = re.match(r'^[•\-\*]\s*(.*)|^\d+[\.\)]\s+(.*)', line)
            topic = match.group(1) if match.group(1) else match.group(2)
            if topic and len(topic) > 3:
                structure[current_unit].append(topic)
        elif 5 < len(line) < 120:
            structure[current_unit].append(line)
            
    # Remove empty units and merge 'General Topics' if it's the only one
    final_struct = {k: v for k, v in structure.items() if v}
    return final_struct

# --- DATABASE CONNECTION ---
def get_sheet(worksheet_name):
    try:
        creds_dict = dict(st.secrets["gspread_creds"])
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL).worksheet(worksheet_name)
    except Exception as e:
        st.error("Google Sheets Connection Error. Check st.secrets.")
        return None

# --- AI PARSER ---
def generate_questions(topic_list, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        topics_str = ", ".join(topic_list[:50]) # Limit context length
        prompt = f"""
        Create {num_q} MCQ questions covering: {topics_str}.
        Return ONLY valid JSON:
        {{
            "questions": [
                {{"id": 1, "question_text": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_option": "A"}}
            ]
        }}
        """
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        content = response.choices[0].message.content
        match = re.search(r'\{.*\}', content, re.DOTALL)
        return json.loads(match.group(0))
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Control Center")
    
    if 'syllabus_data' not in st.session_state:
        st.session_state['syllabus_data'] = None

    # Step 1: Upload
    with st.expander("📂 1. Syllabus Context", expanded=not st.session_state['syllabus_data']):
        uploaded_file = st.file_uploader("Upload Syllabus (.pdf, .docx)", type=["pdf", "docx"])
        if uploaded_file:
            with st.spinner("Extracting Units & Topics..."):
                text = extract_text_from_file(uploaded_file)
                st.session_state['syllabus_data'] = parse_syllabus_to_structure(text)
                st.success(f"Found {len(st.session_state['syllabus_data'])} distinct units/sections!")

    # Step 2: Selection
    with st.expander("🎯 2. Quiz Scope & Topics", expanded=True):
        selected_topics = []
        if st.session_state['syllabus_data']:
            mode = st.radio("Selection Method", ["Individual Topics", "Complete Units/Modules", "Whole Syllabus"], horizontal=True)
            data = st.session_state['syllabus_data']
            
            if mode == "Individual Topics":
                all_flat_topics = [t for sublist in data.values() for t in sublist]
                selected_topics = st.multiselect("Select topics:", all_flat_topics)
                
            elif mode == "Complete Units/Modules":
                st.write("### Select Units to Include:")
                cols = st.columns(2)
                for i, unit_name in enumerate(data.keys()):
                    with cols[i % 2]:
                        if st.checkbox(unit_name, key=f"unit_{i}"):
                            selected_topics.extend(data[unit_name])
                st.info(f"Selected {len(selected_topics)} topics from the units checked above.")
                
            elif mode == "Whole Syllabus":
                selected_topics = [t for sublist in data.values() for t in sublist]
                st.success(f"Selected all units. Total topics: {len(selected_topics)}")
        else:
            manual = st.text_input("Manual Topic Entry (if no syllabus uploaded)")
            if manual: selected_topics = [manual]

    # Step 3: Settings
    with st.expander("🛠️ 3. Generation Settings", expanded=True):
        col1, col2, col3 = st.columns(3)
        deg = col1.selectbox("Degree", ["UG", "PG"])
        strm = col2.text_input("Stream", placeholder="e.g., Computer Science")
        sem = col3.number_input("Semester", 1, 8, 1)
        
        c_a, c_b = st.columns(2)
        start_d = c_a.date_input("Start Date", datetime.date.today())
        end_d = c_b.date_input("End Date", datetime.date.today() + datetime.timedelta(days=7))
        
        num_q = st.select_slider("Total Questions", options=[10, 20, 30, 40, 50], value=10)
        
        if st.button("🚀 Generate & Publish Quiz", use_container_width=True):
            if not selected_topics:
                st.warning("Please select at least one topic or unit.")
            else:
                with st.spinner("AI is analyzing syllabus and generating questions..."):
                    quiz_json = generate_questions(selected_topics, num_q)
                    if quiz_json:
                        sheet = get_sheet("Quizzes")
                        if sheet:
                            sheet.append_row([
                                str(int(datetime.datetime.now().timestamp())), 
                                f"Quiz: {len(selected_topics)} topics selected", 
                                deg, strm, sem, str(start_d), str(end_d), 
                                json.dumps(quiz_json), "Open", str(datetime.datetime.now())
                            ])
                            st.success("Quiz successfully published to Student Portal!")
                            st.balloons()

    st.divider()
    st.subheader("📊 Results Analytics")
    try:
        sheet = get_sheet("Results")
        if sheet:
            res_df = pd.DataFrame(sheet.get_all_records())
            if not res_df.empty:
                st.dataframe(res_df, use_container_width=True)
    except:
        st.error("Results table is currently empty.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    if 'profile' not in st.session_state:
        with st.form("profile_form"):
            st.text_input("Full Name", key="name_in")
            st.selectbox("Degree", ["UG", "PG"], key="deg_in")
            st.text_input("Stream", key="strm_in")
            st.number_input("Semester", 1, 8, key="sem_in")
            if st.form_submit_button("Enter Portal"):
                st.session_state['profile'] = {
                    "name": st.session_state.name_in, "deg": st.session_state.deg_in,
                    "strm": st.session_state.strm_in, "sem": st.session_state.sem_in
                }
                st.rerun()
        return

    try:
        sheet = get_sheet("Quizzes")
        quizzes = sheet.get_all_records()
        today = datetime.date.today()
        for row in quizzes:
            if (row['Status'] == 'Open' and row['Degree'] == st.session_state['profile']['deg'] and 
                row['Stream'] == st.session_state['profile']['strm'] and int(row['Semester']) == st.session_state['profile']['sem']):
                
                start = datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date()
                end = datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date()
                
                if start <= today <= end:
                    with st.container(border=True):
                        st.write(f"### {row['Topic']}")
                        if st.button(f"Take Quiz", key=f"btn_{row['QuizID']}"):
                            q_data = json.loads(row['Questions'])['questions']
                            random.shuffle(q_data)
                            st.session_state['active'] = {"quiz": row, "qs": q_data}
                            st.rerun()
    except Exception as e:
        st.error("Error loading available quizzes.")

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz_form"):
            st.title(quiz['quiz']['Topic'])
            ans = {}
            for q in quiz['qs']:
                st.write(f"**{q['question_text']}**")
                ans[q['id']] = st.radio("Select:", q['options'], key=f"q_{q['id']}", label_visibility="collapsed")
            
            if st.form_submit_button("Submit"):
                score = sum(1 for q in quiz['qs'] if str(ans[q['id']])[0] == q['correct_option'])
                res_sheet = get_sheet("Results")
                res_sheet.append_row([quiz['quiz']['QuizID'], st.session_state['profile']['name'], st.session_state['profile']['deg'], st.session_state['profile']['strm'], st.session_state['profile']['sem'], quiz['quiz']['Topic'], score, len(quiz['qs']), str(datetime.datetime.now())])
                st.success(f"Submitted! Final Score: {score}/{len(quiz['qs'])}")
                del st.session_state['active']
                st.button("Close Quiz")

# --- MAIN ---
st.set_page_config(page_title="Syllabus Quiz AI", layout="wide")
role = st.sidebar.selectbox("Access Level", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.sidebar.error("Invalid credentials.")
else:
    student_dashboard()
