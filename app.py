import streamlit as st
import pandas as pd
import json
import datetime
from openai import OpenAI
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"  # CHANGE THIS PASSWORD!

# --- DATABASE CONNECTION ---
def get_db_connection():
    try:
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

# --- HELPER: ROBUST SAVE FUNCTION ---
def save_to_sheet(conn, worksheet_name, new_row, expected_cols):
    """
    Safely reads existing data, appends new row, and writes back.
    Forces columns to match expected list to prevent 400 Bad Request errors.
    """
    try:
        # Read existing data
        existing_data = conn.read(worksheet=worksheet_name, ttl=0)
        
        # Ensure it's a DataFrame even if empty
        if existing_data is None or existing_data.empty:
            existing_data = pd.DataFrame(columns=expected_cols)
        
        # Prepare the new row
        new_df = pd.DataFrame(new_row)
        
        # Combine
        updated_data = pd.concat([existing_data, new_df], ignore_index=True)
        
        # Ensure only expected columns exist and convert to string to avoid type errors
        updated_data = updated_data[expected_cols].astype(str)
        
        # Update
        conn.update(worksheet=worksheet_name, data=updated_data)
        return True
    except Exception as e:
        st.error(f"Failed to save to '{worksheet_name}': {e}")
        return False

# --- OPENAI QUIZ GENERATION ---
def generate_questions(topic, num_questions):
    try:
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
        st.error(f"Error generating quiz: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    conn = get_db_connection()
    
    with st.expander("Create New Quiz", expanded=True):
        topic = st.text_input("Lecture Topic")
        num_q = st.slider("Number of Questions", 1, 10, 5)
        
        if st.button("Generate & Publish Quiz"):
            with st.spinner("Generating..."):
                quiz_data = generate_questions(topic, num_q)
                if quiz_data:
                    quiz_id = str(int(datetime.datetime.now().timestamp()))
                    new_row = [{
                        "QuizID": quiz_id,
                        "Topic": topic,
                        "Questions": json.dumps(quiz_data),
                        "Status": "Open",
                        "Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    }]
                    
                    if save_to_sheet(conn, "Quizzes", new_row, ["QuizID", "Topic", "Questions", "Status", "Created"]):
                        st.success("Quiz Published!")

    st.divider()
    st.subheader("Manage Active Quizzes")
    quizzes = conn.read(worksheet="Quizzes", ttl=0)
    if not quizzes.empty:
        for index, row in quizzes.iterrows():
            col1, col2 = st.columns([3, 1])
            with col1: st.write(f"**{row['Topic']}** ({row['Status']})")
            with col2:
                if st.button(f"Toggle Status {row['QuizID']}", key=row['QuizID']):
                    quizzes.at[index, 'Status'] = 'Closed' if row['Status'] == 'Open' else 'Open'
                    conn.update(worksheet="Quizzes", data=quizzes)
                    st.rerun()

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    conn = get_db_connection()
    student_name = st.text_input("Enter your Full Name:")
    
    if student_name:
        quizzes = conn.read(worksheet="Quizzes", ttl=0)
        open_quizzes = quizzes[quizzes['Status'] == 'Open']
        
        for _, row in open_quizzes.iterrows():
            with st.expander(f"Take Quiz: {row['Topic']}"):
                if st.button(f"Start {row['Topic']}", key=f"start_{row['QuizID']}"):
                    st.session_state['active_quiz'] = row.to_dict()
                    st.session_state['active_quiz_data'] = json.loads(row['Questions'])
                    st.rerun()

    if 'active_quiz' in st.session_state:
        q_data = st.session_state['active_quiz_data']
        with st.form("quiz_form"):
            user_answers = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in q_data['questions']}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in q_data['questions'] if user_answers[q['id']] == q['correct_option'])
                new_result = [{
                    "QuizID": st.session_state['active_quiz']['QuizID'],
                    "StudentName": student_name,
                    "Topic": st.session_state['active_quiz']['Topic'],
                    "Score": str(score),
                    "Total": str(len(q_data['questions'])),
                    "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }]
                if save_to_sheet(conn, "Results", new_result, ["QuizID", "StudentName", "Topic", "Score", "Total", "Timestamp"]):
                    st.success(f"Submitted! Score: {score}/{len(q_data['questions'])}")
                    del st.session_state['active_quiz']

# --- MAIN ---
st.set_page_config(page_title="Lecture Quiz AI", layout="wide")
role = st.sidebar.radio("Select Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD:
        professor_dashboard()
else:
    student_dashboard()
