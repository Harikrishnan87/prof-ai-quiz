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
    Parses text to find Units/Modules and their associated topics.
    Returns: { "Unit 1": ["Topic A", "Topic B"], ... }
    """
    # Regex to find Unit/Module headers
    header_pattern = r'(?im)^(?:Module|Unit|Chapter)\s*[\d\w]*[:.-]?\s*(.*)'
    lines = text.split('\n')
    
    structure = {"General Topics": []}
    current_unit = "General Topics"
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Check if line is a Header (Unit/Module)
        if re.match(header_pattern, line):
            current_unit = line
            structure[current_unit] = []
        # Check if line is a Topic (Bullet points or numbered lists)
        elif re.match(r'^[•\-\*]\s*(.*)|^\d+\.\s+(.*)', line):
            match = re.match(r'^[•\-\*]\s*(.*)|^\d+\.\s+(.*)', line)
            topic = match.group(1) if match.group(1) else match.group(2)
            if topic and len(topic) > 3:
                structure[current_unit].append(topic)
        # Fallback for short descriptive lines that aren't headers
        elif 5 < len(line) < 100 and current_unit:
            structure[current_unit].append(line)
            
    # Clean up empty units
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
        # Format multiple topics into a single string
        topics_str = ", ".join(topic_list) if isinstance(topic_list, list) else topic_list
        
        prompt = f"""
        Create {num_q} MCQ questions covering the following topics: {topics_str}.
        Distribute the questions evenly across the topics provided.
        Return ONLY valid JSON in this exact structure:
        {{
            "questions": [
                {{"id": 1, "question_text": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_option": "A"}}
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

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Control Center")
    
    # Initialize session state for extracted topics
    if 'syllabus_data' not in st.session_state:
        st.session_state['syllabus_data'] = None

    # Step 1: Syllabus Upload
    with st.expander("📂 1. Syllabus Context", expanded=not st.session_state['syllabus_data']):
        uploaded_file = st.file_uploader("Upload Syllabus (.pdf, .docx)", type=["pdf", "docx"])
        if uploaded_file:
            with st.spinner("Processing syllabus architecture..."):
                text = extract_text_from_file(uploaded_file)
                st.session_state['syllabus_data'] = parse_syllabus_to_structure(text)
                st.success("Syllabus parsed successfully!")

    # Step 2: Topic Selection Strategy
    with st.expander("🎯 2. Quiz Scope & Topics", expanded=True):
        selected_topics = []
        
        if st.session_state['syllabus_data']:
            mode = st.radio("Selection Method", ["Individual Topics", "Complete Units/Modules", "Whole Syllabus"], horizontal=True)
            
            data = st.session_state['syllabus_data']
            
            if mode == "Individual Topics":
                all_flat_topics = [t for sublist in data.values() for t in sublist]
                selected_topics = st.multiselect("Select specific topics to cover:", all_flat_topics)
                if not selected_topics:
                    st.info("Select one or more topics from the dropdown.")
                
            elif mode == "Complete Units/Modules":
                units = list(data.keys())
                selected_units = st.multiselect("Select one or more Units:", units)
                # Combine all topics from selected units
                for u in selected_units:
                    selected_topics.extend(data[u])
                st.caption(f"Total topics in selected units: {len(selected_topics)}")
                
            elif mode == "Whole Syllabus":
                selected_topics = [t for sublist in data.values() for t in sublist]
                st.success(f"Selected all {len(selected_topics)} topics from the syllabus.")
        else:
            manual_topic = st.text_input("Manual Topic Entry", placeholder="Enter topic name...")
            if manual_topic:
                selected_topics = [manual_topic]
            st.info("Upload a syllabus above to enable automated topic extraction.")

    # Step 3: Quiz Generation
    with st.expander("🛠️ 3. Generation Settings", expanded=True):
        col1, col2, col3 = st.columns(3)
        deg = col1.selectbox("Degree", ["UG", "PG"])
        strm = col2.text_input("Stream", placeholder="e.g. CS, Physics")
        sem = col3.number_input("Semester", 1, 8, 1)
        
        c_a, c_b = st.columns(2)
        start_d = c_a.date_input("Open From", datetime.date.today())
        end_d = c_b.date_input("Close On", datetime.date.today() + datetime.timedelta(days=7))
        
        num_q = st.slider("Total Questions to Generate", 10, 20, 30, 40, 50)
        
        if st.button("🚀 Generate & Publish Quiz", use_container_width=True):
            if not selected_topics:
                st.warning("No topics selected. Please select topics or a unit.")
            else:
                with st.spinner("AI is synthesizing questions..."):
                    quiz_json = generate_questions(selected_topics, num_q)
                    if quiz_json:
                        sheet = get_sheet("Quizzes")
                        if sheet:
                            sheet.append_row([
                                str(int(datetime.datetime.now().timestamp())), 
                                f"Quiz on {len(selected_topics)} topics", 
                                deg, strm, sem, str(start_d), str(end_d), 
                                json.dumps(quiz_json), "Open", str(datetime.datetime.now())
                            ])
                            st.success("Quiz published to Student Portal!")
                            st.balloons()

    st.divider()
    st.subheader("📊 Analytics & Results")
    try:
        sheet = get_sheet("Results")
        if sheet:
            res_df = pd.DataFrame(sheet.get_all_records())
            if not res_df.empty:
                st.dataframe(res_df, use_container_width=True)
                st.download_button("📥 Export CSV", res_df.to_csv(index=False), "quiz_results.csv", "text/csv")
            else:
                st.info("No students have completed a quiz yet.")
    except:
        st.error("Could not fetch results database.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    
    # Profile Setup
    if 'profile' not in st.session_state:
        with st.form("profile_form"):
            st.subheader("Student Registration")
            st.text_input("Full Name", key="name_in")
            st.selectbox("Degree", ["UG", "PG"], key="deg_in")
            st.text_input("Stream", key="strm_in")
            st.number_input("Semester", 1, 8, key="sem_in")
            st.form_submit_button("Enter Portal", on_click=lambda: st.session_state.update({
                'profile': {
                    "name": st.session_state.name_in,
                    "deg": st.session_state.deg_in,
                    "strm": st.session_state.strm_in,
                    "sem": st.session_state.sem_in
                }
            }))
        return

    st.sidebar.markdown(f"**User:** {st.session_state['profile']['name']}")
    st.sidebar.markdown(f"**Class:** {st.session_state['profile']['deg']} {st.session_state['profile']['strm']} (Sem {st.session_state['profile']['sem']})")

    # Fetch Quizzes
    try:
        sheet = get_sheet("Quizzes")
        if not sheet: return
        quizzes = sheet.get_all_records()
        today = datetime.date.today()
        
        found_quiz = False
        for row in quizzes:
            # Match Student Profile
            if (row['Status'] == 'Open' and 
                row['Degree'] == st.session_state['profile']['deg'] and 
                row['Stream'] == st.session_state['profile']['strm'] and 
                int(row['Semester']) == st.session_state['profile']['sem']):
                
                start_date = datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date()
                end_date = datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date()
                
                if start_date <= today <= end_date:
                    found_quiz = True
                    with st.container(border=True):
                        st.write(f"### 📝 {row['Topic']}")
                        st.caption(f"Valid until: {row['EndTime']}")
                        if st.button(f"Take Quiz", key=f"btn_{row['QuizID']}"):
                            q_data = json.loads(row['Questions'])['questions']
                            random.shuffle(q_data)
                            st.session_state['active'] = {"quiz": row, "qs": q_data}
                            st.rerun()

        if not found_quiz:
            st.info("No active quizzes matching your profile were found.")

    except Exception as e:
        st.error(f"Error loading quizzes: {e}")

    # Active Quiz Form
    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz_form"):
            st.title(quiz['quiz']['Topic'])
            ans_collector = {}
            for i, q in enumerate(quiz['qs']):
                st.markdown(f"**Q{i+1}: {q['question_text']}**")
                ans_collector[q['id']] = st.radio("Choose one:", q['options'], key=f"radio_{q['id']}", label_visibility="collapsed")
                st.write("---")
            
            if st.form_submit_button("Submit Quiz"):
                score = 0
                for q in quiz['qs']:
                    student_raw = str(ans_collector[q['id']])
                    student_letter = student_raw.split('.')[0].strip().upper() 
                    correct_letter = str(q['correct_option']).strip().upper()
                    if student_letter == correct_letter:
                        score += 1
                
                res_sheet = get_sheet("Results")
                if res_sheet:
                    res_sheet.append_row([
                        quiz['quiz']['QuizID'], 
                        st.session_state['profile']['name'], 
                        st.session_state['profile']['deg'], 
                        st.session_state['profile']['strm'], 
                        st.session_state['profile']['sem'], 
                        quiz['quiz']['Topic'], 
                        score, len(quiz['qs']), 
                        str(datetime.datetime.now())
                    ])
                    st.success(f"Quiz Submitted! Final Score: {score}/{len(quiz['qs'])}")
                    del st.session_state['active']
                    st.button("Return to Dashboard")

# --- MAIN ---
st.set_page_config(page_title="Syllabus Quiz AI", layout="wide")
role = st.sidebar.selectbox("Access Level", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.error("Invalid credentials.")
else:
    student_dashboard()
