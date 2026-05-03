import streamlit as st
import pandas as pd
import json
import datetime
from openai import OpenAI
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"

# --- HELPER: ROBUST SAVE FUNCTION ---
def save_to_sheet(conn, worksheet_name, new_row, expected_cols):
    try:
        # Read existing data
        existing_data = conn.read(worksheet=worksheet_name, ttl=0)
        
        # Handle empty sheets
        if existing_data is None or existing_data.empty:
            existing_data = pd.DataFrame(columns=expected_cols)
        
        # Prepare new data
        new_df = pd.DataFrame(new_row)
        
        # Combine and sanitize: ensure all data is string type to prevent API errors
        updated_data = pd.concat([existing_data, new_df], ignore_index=True)
        updated_data = updated_data[expected_cols].astype(str)
        
        # Write to sheet
        conn.update(worksheet=worksheet_name, data=updated_data)
        return True
    except Exception as e:
        st.error(f"Save Failed: {e}")
        return False

# --- OPENAI QUIZ GENERATION ---
def generate_questions(topic, num_questions):
    try:
        # Verify secret exists before calling
        if "OPENAI_API_KEY" not in st.secrets:
            st.error("Missing OpenAI API Key in Secrets!")
            return None
            
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"""
        Create a difficult multiple choice quiz with exactly {num_questions} questions on: '{topic}'.
        Return valid JSON only. Structure:
        {{
            "questions": [
                {{"id": 1, "question_text": "...", "options": ["A", "B", "C", "D"], "correct_option": "A"}}
            ]
        }}
        """
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        content = response.choices[0].message.content.replace("```json", "").replace("```", "")
        return json.loads(content)
    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return None

# --- MAIN APP LAYOUT ---
st.set_page_config(page_title="Lecture Quiz AI", layout="wide")
role = st.sidebar.radio("Select Role", ["Student", "Professor"])

# --- PROFESSOR LOGIC ---
if role == "Professor":
    pwd = st.sidebar.text_input("Password", type="password")
    if pwd == ADMIN_PASSWORD:
        st.header("👨‍🏫 Professor Dashboard")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        with st.expander("Create New Quiz"):
            topic = st.text_input("Lecture Topic")
            num_q = st.slider("Questions", 1, 10, 5)
            if st.button("Generate & Publish"):
                data = generate_questions(topic, num_q)
                if data:
                    new_row = [{"QuizID": str(int(datetime.datetime.now().timestamp())), "Topic": topic, "Questions": json.dumps(data), "Status": "Open", "Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}]
                    if save_to_sheet(conn, "Quizzes", new_row, ["QuizID", "Topic", "Questions", "Status", "Created"]):
                        st.success("Quiz Published!")

# --- STUDENT LOGIC ---
else:
    st.header("🎓 Student Portal")
    conn = st.connection("gsheets", type=GSheetsConnection)
    name = st.text_input("Enter your Full Name:")
    if name:
        quizzes = conn.read(worksheet="Quizzes", ttl=0)
        for _, row in quizzes[quizzes['Status'] == 'Open'].iterrows():
            if st.button(f"Take Quiz: {row['Topic']}"):
                st.session_state['active'] = row
                st.rerun()

    if 'active' in st.session_state:
        q_data = json.loads(st.session_state['active']['Questions'])
        with st.form("quiz"):
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in q_data['questions']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in q_data['questions'] if ans[q['id']] == q['correct_option'])
                save_to_sheet(conn, "Results", [{"QuizID": st.session_state['active']['QuizID'], "StudentName": name, "Topic": st.session_state['active']['Topic'], "Score": str(score), "Total": str(len(q_data['questions'])), "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}], ["QuizID", "StudentName", "Topic", "Score", "Total", "Timestamp"])
                st.success(f"Score: {score}")
                del st.session_state['active']
