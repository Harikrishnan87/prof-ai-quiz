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
ADMIN_PASSWORD = "admin123"
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

def parse_syllabus_topics(text):
    # Regex to find lines starting with "Module", "Unit", "Chapter" or numbered lists
    # Example: "Module 1: Data Structures" or "1. Introduction"
    pattern = r'(?im)^(?:Module|Unit|Chapter|Topic)\s*[\d\w]*[:.-]?\s*(.*)|^\d+\.\s+(.*)'
    matches = re.findall(pattern, text)
    
    # Flatten matches and clean up
    topics = []
    for match in matches:
        topic = match[0] if match[0] else match[1]
        if topic and len(topic.strip()) > 3:
            topics.append(topic.strip())
    
    # Remove duplicates but keep order
    return list(dict.fromkeys(topics))

# --- DATABASE CONNECTION ---
def get_sheet(worksheet_name):
    creds_dict = dict(st.secrets["gspread_creds"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(worksheet_name)

# --- AI PARSER ---
def generate_questions(topic, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"""
        Create {num_q} MCQ questions on {topic}.
        Return ONLY valid JSON in this exact structure:
        {{
            "questions": [
                {{"id": 1, "question_text": "...", "options": ["A", "B", "C", "D"], "correct_option": "A"}}
            ]
        }}
        IMPORTANT: 'correct_option' must be ONLY the letter (A, B, C, or D).
        """
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0.5)
        content = response.choices[0].message.content
        match = re.search(r'\{.*\}', content, re.DOTALL)
        return json.loads(match.group(0))
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- CALLBACKS ---
def save_profile():
    st.session_state['profile'] = {
        "name": st.session_state.name_in,
        "deg": st.session_state.deg_in,
        "strm": st.session_state.strm_in,
        "sem": st.session_state.sem_in
    }

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    
    # 1. Syllabus Upload Section
    with st.expander("Step 1: Upload Syllabus", expanded=True):
        uploaded_file = st.file_uploader("Upload Syllabus (.pdf, .docx)", type=["pdf", "docx"])
        extracted_topics = []
        
        if uploaded_file:
            with st.spinner("Extracting topics..."):
                raw_text = extract_text_from_file(uploaded_file)
                extracted_topics = parse_syllabus_topics(raw_text)
                
            if extracted_topics:
                st.success(f"Found {len(extracted_topics)} topics!")
            else:
                st.warning("No specific modules found. Using manual entry.")

    # 2. Quiz Configuration
    with st.expander("Step 2: Create Quiz", expanded=True):
        # Dynamic Dropdown vs Manual Input
        if extracted_topics:
            topic = st.selectbox("Select Topic from Syllabus", extracted_topics)
        else:
            topic = st.text_input("Lecture Topic (Manual Entry)", placeholder="e.g. Quantum Physics 101")

        col1, col2, col3 = st.columns(3)
        deg = col1.selectbox("Degree", ["UG", "PG"])
        strm = col2.text_input("Stream")
        sem = col3.number_input("Semester", 1, 8, 1)
        
        col_a, col_b = st.columns(2)
        start_d = col_a.date_input("Start Date")
        end_d = col_b.date_input("End Date")
        
        num_q = st.slider("Number of Questions", 1, 15, 5)
        
        if st.button("Generate & Publish Quiz"):
            if not topic:
                st.error("Please provide or select a topic.")
            else:
                with st.spinner("AI is generating questions..."):
                    data = generate_questions(topic, num_q)
                    if data:
                        sheet = get_sheet("Quizzes")
                        sheet.append_row([
                            str(int(datetime.datetime.now().timestamp())), 
                            topic, deg, strm, sem, str(start_d), str(end_d), 
                            json.dumps(data), "Open", str(datetime.datetime.now())
                        ])
                        st.success(f"Quiz for '{topic}' published successfully!")

    st.divider()
    st.subheader("Manage Results")
    try:
        res_df = pd.DataFrame(get_sheet("Results").get_all_records())
        if not res_df.empty:
            st.dataframe(res_df, use_container_width=True)
            st.download_button("Export Results", res_df.to_csv(index=False), "results.csv", "text/csv")
        else:
            st.info("No results recorded yet.")
    except:
        st.warning("Database empty or connection error.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    if 'profile' not in st.session_state:
        with st.form("profile_form"):
            st.text_input("Full Name", key="name_in")
            st.selectbox("Degree", ["UG", "PG"], key="deg_in")
            st.text_input("Stream", key="strm_in")
            st.number_input("Semester", 1, 8, key="sem_in")
            st.form_submit_button("Enter", on_click=save_profile)
    else:
        st.info(f"Logged in as: {st.session_state['profile']['name']} | {st.session_state['profile']['deg']} {st.session_state['profile']['strm']}")
        
        try:
            quizzes = get_sheet("Quizzes").get_all_records()
            today = datetime.date.today()
            available_quizzes = []

            for row in quizzes:
                # Filtering logic
                if (row['Status'] == 'Open' and 
                    row['Degree'] == st.session_state['profile']['deg'] and 
                    row['Stream'] == st.session_state['profile']['strm'] and 
                    int(row['Semester']) == st.session_state['profile']['sem']):
                    
                    start_date = datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date()
                    end_date = datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date()
                    
                    if start_date <= today <= end_date:
                        available_quizzes.append(row)

            if available_quizzes:
                for row in available_quizzes:
                    if st.button(f"Start Quiz: {row['Topic']}"):
                        q_data = json.loads(row['Questions'])['questions']
                        random.shuffle(q_data)
                        st.session_state['active'] = {"quiz": row, "qs": q_data}
                        st.rerun()
            else:
                st.write("No active quizzes for your department at this time.")
        except Exception as e:
            st.error(f"Error fetching quizzes: {e}")

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz_form"):
            st.subheader(f"Quiz: {quiz['quiz']['Topic']}")
            ans = {}
            for q in quiz['qs']:
                ans[q['id']] = st.radio(f"Q: {q['question_text']}", q['options'], key=f"q_{q['id']}")
            
            if st.form_submit_button("Submit Final Answers"):
                score = 0
                for q in quiz['qs']:
                    student_raw = str(ans[q['id']])
                    student_letter = student_raw.split('.')[0].strip() 
                    correct_letter = str(q['correct_option']).strip()
                    
                    if student_letter.upper() == correct_letter.upper():
                        score += 1
                
                get_sheet("Results").append_row([
                    quiz['quiz']['QuizID'], 
                    st.session_state['profile']['name'], 
                    st.session_state['profile']['deg'], 
                    st.session_state['profile']['strm'], 
                    st.session_state['profile']['sem'], 
                    quiz['quiz']['Topic'], 
                    score, len(quiz['qs']), 
                    str(datetime.datetime.now())
                ])
                st.balloons()
                st.success(f"Submitted! Your Score: {score}/{len(quiz['qs'])}")
                del st.session_state['active']
                # Small delay or user click to reset
                if st.button("Back to Dashboard"):
                    st.rerun()

# --- MAIN ---
st.set_page_config(page_title="Syllabus Quiz AI", layout="wide")
role = st.sidebar.radio("Navigation", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.sidebar.error("Incorrect Password")
else:
    student_dashboard()
