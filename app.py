import streamlit as st
import pandas as pd
import json
import datetime
import random
from openai import OpenAI
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"
# HARDCODED URL: This solves the "Invalid URL" error
SHEET_URL = "https://docs.google.com/spreadsheets/d/14JYC-071X3bV2F0SbNrWXZvLcpNZn_XXQ-6RGWv64/edit"

# --- DATABASE HELPERS ---
def get_conn():
    # Pass the URL directly to the connection
    return st.connection("gsheets", type=GSheetsConnection, spreadsheet=SHEET_URL)

def save_to_sheet(worksheet_name, new_row, expected_cols):
    try:
        conn = get_conn()
        existing = conn.read(worksheet=worksheet_name, ttl=0)
        if existing is None or existing.empty: existing = pd.DataFrame(columns=expected_cols)
        updated = pd.concat([existing, pd.DataFrame(new_row)], ignore_index=True)
        conn.update(worksheet=worksheet_name, data=updated[expected_cols].astype(str))
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        return False

# --- OPENAI GENERATION ---
def generate_questions(topic, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"Create a difficult MCQ quiz with {num_q} questions on {topic}. Return valid JSON: {{'questions': [{{'id': 1, 'question_text': '...', 'options': ['A','B','C','D'], 'correct_option': 'A'}}]}}"
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0.7)
        return json.loads(response.choices[0].message.content.replace("```json", "").replace("```", ""))
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    with st.expander("Create Quiz", expanded=True):
        topic = st.text_input("Lecture Topic")
        col1, col2, col3 = st.columns(3)
        deg = col1.selectbox("Degree", ["UG", "PG"])
        strm = col2.text_input("Stream")
        sem = col3.number_input("Semester", 1, 8, 1)
        start_d = st.date_input("Start Date")
        end_d = st.date_input("End Date")
        num_q = st.slider("Questions", 1, 10, 5)
        
        if st.button("Generate & Publish"):
            data = generate_questions(topic, num_q)
            if data:
                new_quiz = [{
                    "QuizID": str(int(datetime.datetime.now().timestamp())), "Topic": topic,
                    "Degree": deg, "Stream": strm, "Semester": sem,
                    "StartTime": str(start_d), "EndTime": str(end_d),
                    "Questions": json.dumps(data), "Status": "Open", "Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }]
                if save_to_sheet("Quizzes", new_quiz, ["QuizID", "Topic", "Degree", "Stream", "Semester", "StartTime", "EndTime", "Questions", "Status", "Created"]):
                    st.success("Published!")

    st.subheader("Manage Results")
    conn = get_conn()
    res = conn.read(worksheet="Results", ttl=0)
    if not res.empty:
        st.dataframe(res)
        st.download_button("Export to CSV", res.to_csv(index=False), "results.csv", "text/csv")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    if 'profile' not in st.session_state:
        with st.form("profile"):
            name = st.text_input("Full Name")
            deg = st.selectbox("Degree", ["UG", "PG"])
            strm = st.text_input("Stream")
            sem = st.number_input("Semester", 1, 8, 1)
            if st.form_submit_button("Enter"):
                st.session_state['profile'] = {"name": name, "deg": deg, "strm": strm, "sem": sem}
                st.rerun()
    else:
        st.write(f"Student: {st.session_state['profile']['name']}")
        conn = get_conn()
        quizzes = conn.read(worksheet="Quizzes", ttl=0)
        today = datetime.date.today()
        
        for _, row in quizzes.iterrows():
            # Filter by academic details
            if row['Status'] == 'Open' and row['Degree'] == st.session_state['profile']['deg'] and row['Stream'] == st.session_state['profile']['strm'] and int(row['Semester']) == st.session_state['profile']['sem']:
                # Filter by schedule
                if datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date() <= today <= datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date():
                    if st.button(f"Take {row['Topic']}"):
                        q_data = json.loads(row['Questions'])['questions']
                        random.shuffle(q_data) # Randomized sequence
                        st.session_state['active'] = {"quiz": row, "qs": q_data}
                        st.rerun()

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz"):
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in quiz['qs']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in quiz['qs'] if ans[q['id']] == q['correct_option'])
                new_res = [{"QuizID": quiz['quiz']['QuizID'], "StudentName": st.session_state['profile']['name'], "Degree": st.session_state['profile']['deg'], "Stream": st.session_state['profile']['strm'], "Semester": st.session_state['profile']['sem'], "Topic": quiz['quiz']['Topic'], "Score": score, "Total": len(quiz['qs']), "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}]
                save_to_sheet("Results", new_res, ["QuizID", "StudentName", "Degree", "Stream", "Semester", "Topic", "Score", "Total", "Timestamp"])
                st.success("Submitted!")
                del st.session_state['active']
                st.rerun()

# --- MAIN ---
st.set_page_config(layout="wide")
role = st.sidebar.radio("Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD:
        professor_dashboard()
else:
    student_dashboard()
