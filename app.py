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
    # Noise patterns to filter out from topic lists
    noise_patterns = [
        r'L T P C', r'P18PECS\d+', r'Total Contact Hours', r'Prerequisite:', 
        r'Course Designed by', r'OBJECTIVES', r'COURSE OUTCOMES', r'TOTAL NO OF PERIODS'
    ]
    
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

        # Topic detection logic
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
        st.error("Google Sheets Connection Error. Check st.secrets.")
        return None

# --- AI PARSER ---
def generate_questions(topic_list, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        topics_str = ", ".join(topic_list[:50])
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

    with st.expander("📂 1. Syllabus Context", expanded=not st.session_state['syllabus_data']):
        uploaded_file = st.file_uploader("Upload Syllabus (.pdf, .docx)", type=["pdf", "docx"])
        if uploaded_file:
            with st.spinner("Extracting Units & Topics..."):
                text = extract_text_from_file(uploaded_file)
                st.session_state['syllabus_data'] = parse_syllabus_to_structure(text)
                st.success(f"Found {len(st.session_state['syllabus_data'])} distinct units!")

    with st.expander("🎯 2. Quiz Scope & Topics", expanded=True):
        selected_topics = []
        if st.session_state['syllabus_data']:
            mode = st.radio("Selection Method", ["Individual Topics", "Complete Units/Modules", "Whole Syllabus"], horizontal=True)
            data = st.session_state['syllabus_data']
            
            if mode == "Individual Topics":
                # Flat list of all topics across all units
                all_flat_topics = [t for sublist in data.values() for t in sublist]
                selected_topics = st.multiselect("Select specific topics to include:", all_flat_topics)
                
            elif mode == "Complete Units/Modules":
                st.write("### Select Units and Fine-tune Topics:")
                for unit_name, topics in data.items():
                    # Checkbox for the Unit
                    unit_checked = st.checkbox(f"**{unit_name}**", key=f"check_{unit_name}")
                    if unit_checked:
                        # If unit is checked, show nested multiselect for its topics
                        # Default is all topics in that unit selected
                        unit_selected = st.multiselect(
                            f"Topics in {unit_name}:", 
                            options=topics, 
                            default=topics, 
                            key=f"topics_{unit_name}"
                        )
                        selected_topics.extend(unit_selected)
                
            elif mode == "Whole Syllabus":
                selected_topics = [t for sublist in data.values() for t in sublist]
                st.success(f"Selected all units. Total topics: {len(selected_topics)}")
        else:
            manual = st.text_input("Manual Topic Entry")
            if manual: selected_topics = [manual]

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
                with st.spinner("AI is generating questions..."):
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
                            st.success("Quiz successfully published!")
                            st.balloons()

# --- STUDENT VIEW (Simplified for context) ---
def student_dashboard():
    st.header("🎓 Student Portal")
    st.info("Log in to view available quizzes based on your degree and stream.")

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
