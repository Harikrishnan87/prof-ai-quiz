import streamlit as st
import pandas as pd
import datetime
import random
import os
from openai import OpenAI

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"
QUIZ_FILE = "quizzes.csv"
RESULTS_FILE = "results.csv"

# --- FILE HELPERS ---
def load_csv(filename, columns):
    if not os.path.exists(filename):
        return pd.DataFrame(columns=columns)
    return pd.read_csv(filename)

def save_csv(filename, df):
    df.to_csv(filename, index=False)

# --- OPENAI GENERATION ---
def generate_questions(topic, num_q, api_key):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Create {num_q} MCQ questions on {topic}. Return valid JSON: {{'questions': [{{'id': 1, 'question_text': '...', 'options': ['A','B','C','D'], 'correct_option': 'A'}}]}}"}],
            temperature=0.7
        )
        return response.choices[0].message.content.replace("```json", "").replace("```", "")
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard(api_key):
    st.header("👨‍🏫 Professor Dashboard")
    
    with st.expander("Create Quiz"):
        topic = st.text_input("Lecture Topic")
        col1, col2, col3 = st.columns(3)
        deg = col1.selectbox("Degree", ["UG", "PG"])
        strm = col2.text_input("Stream")
        sem = col3.number_input("Semester", 1, 8, 1)
        start_d = st.date_input("Start Date")
        end_d = st.date_input("End Date")
        num_q = st.slider("Questions", 1, 10, 5)
        
        if st.button("Generate & Publish"):
            data = generate_questions(topic, num_q, api_key)
            if data:
                df = load_csv(QUIZ_FILE, ["QuizID", "Topic", "Degree", "Stream", "Semester", "StartTime", "EndTime", "Questions", "Status"])
                new_quiz = pd.DataFrame([{
                    "QuizID": str(int(datetime.datetime.now().timestamp())), "Topic": topic,
                    "Degree": deg, "Stream": strm, "Semester": sem,
                    "StartTime": str(start_d), "EndTime": str(end_d),
                    "Questions": data, "Status": "Open"
                }])
                save_csv(QUIZ_FILE, pd.concat([df, new_quiz], ignore_index=True))
                st.success("Quiz Published!")

    st.subheader("Manage Results")
    res_df = load_csv(RESULTS_FILE, ["QuizID", "StudentName", "Topic", "Score", "Total"])
    if not res_df.empty:
        st.dataframe(res_df)
        st.download_button("Export CSV", res_df.to_csv(index=False), "results.csv", "text/csv")

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
        quizzes = load_csv(QUIZ_FILE, ["QuizID", "Topic", "Degree", "Stream", "Semester", "StartTime", "EndTime", "Questions", "Status"])
        today = datetime.date.today()
        
        for _, row in quizzes.iterrows():
            if row['Status'] == 'Open' and row['Degree'] == st.session_state['profile']['deg'] and row['Stream'] == st.session_state['profile']['strm'] and int(row['Semester']) == st.session_state['profile']['sem']:
                if datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date() <= today <= datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date():
                    if st.button(f"Take {row['Topic']}"):
                        q_data = json.loads(row['Questions'])['questions']
                        random.shuffle(q_data)
                        st.session_state['active'] = {"quiz": row, "qs": q_data}
                        st.rerun()

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz"):
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in quiz['qs']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in quiz['qs'] if ans[q['id']] == q['correct_option'])
                res_df = load_csv(RESULTS_FILE, ["QuizID", "StudentName", "Topic", "Score", "Total"])
                new_res = pd.DataFrame([{"QuizID": quiz['quiz']['QuizID'], "StudentName": st.session_state['profile']['name'], "Topic": quiz['quiz']['Topic'], "Score": score, "Total": len(quiz['qs'])}])
                save_csv(RESULTS_FILE, pd.concat([res_df, new_res], ignore_index=True))
                st.success(f"Submitted! Score: {score}/{len(quiz['qs'])}")
                del st.session_state['active']
                st.rerun()

# --- MAIN ---
st.set_page_config(layout="wide")
api_key = st.sidebar.text_input("OpenAI API Key", type="password")
role = st.sidebar.radio("Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD:
        professor_dashboard(api_key)
else:
    student_dashboard()
