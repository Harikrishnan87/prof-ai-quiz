import streamlit as st
import pandas as pd
import json
import datetime
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1t4JYC-O71X3bV2F0SbNrWXZvLcpNZwn_XXQ-6RGWv64/edit"

# --- DATABASE CONNECTION ---
def get_sheet(worksheet_name):
    # Load credentials from secrets
    creds_dict = dict(st.secrets["gspread_creds"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(worksheet_name)

# --- OPENAI GENERATION ---
def generate_questions(topic, num_q):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"Create {num_q} MCQ questions on {topic}. JSON: {{'questions': [{{'id': 1, 'question_text': '...', 'options': ['A','B','C','D'], 'correct_option': 'A'}}]}}"
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
                sheet = get_sheet("Quizzes")
                sheet.append_row([str(int(datetime.datetime.now().timestamp())), topic, deg, strm, sem, str(start_d), str(end_d), json.dumps(data), "Open", str(datetime.datetime.now())])
                st.success("Published!")

    st.subheader("Manage Results")
    res_df = pd.DataFrame(get_sheet("Results").get_all_records())
    if not res_df.empty:
        st.dataframe(res_df)
        st.download_button("Export Results", res_df.to_csv(index=False), "results.csv", "text/csv")

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
    else:
        st.write(f"Student: {st.session_state['profile']['name']}")
        quizzes = get_sheet("Quizzes").get_all_records()
        today = datetime.date.today()
        
        for row in quizzes:
            if row['Status'] == 'Open' and row['Degree'] == st.session_state['profile']['deg'] and row['Stream'] == st.session_state['profile']['strm'] and int(row['Semester']) == st.session_state['profile']['sem']:
                if datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date() <= today <= datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date():
                    if st.button(f"Take {row['Topic']}"):
                        q_data = json.loads(row['Questions'])['questions']
                        random.shuffle(q_data)
                        st.session_state['active'] = {"quiz": row, "qs": q_data}
                        st.rerun()

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz_form"):
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in quiz['qs']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in quiz['qs'] if ans[q['id']] == q['correct_option'])
                get_sheet("Results").append_row([quiz['quiz']['QuizID'], st.session_state['profile']['name'], st.session_state['profile']['deg'], st.session_state['profile']['strm'], st.session_state['profile']['sem'], quiz['quiz']['Topic'], score, len(quiz['qs']), str(datetime.datetime.now())])
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
