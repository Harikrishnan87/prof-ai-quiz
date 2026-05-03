import streamlit as st
import json
import datetime
from openai import OpenAI

# --- INITIALIZE IN-MEMORY DATA ---
# This initializes your "database" within the app's memory
if 'quizzes' not in st.session_state:
    st.session_state['quizzes'] = []
if 'results' not in st.session_state:
    st.session_state['results'] = []

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"

# --- OPENAI QUIZ GENERATION ---
def generate_questions(topic, num_questions):
    try:
        # We still use secrets for the API key to keep your OpenAI account safe
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"Create a difficult multiple choice quiz with exactly {num_questions} questions on: '{topic}'. Return valid JSON only."
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

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    
    with st.expander("Create New Quiz", expanded=True):
        topic = st.text_input("Lecture Topic")
        num_q = st.slider("Questions", 1, 10, 5)
        if st.button("Generate & Publish"):
            data = generate_questions(topic, num_q)
            if data:
                new_quiz = {
                    "QuizID": str(int(datetime.datetime.now().timestamp())),
                    "Topic": topic,
                    "Questions": data,
                    "Status": "Open",
                    "Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state['quizzes'].append(new_quiz)
                st.success("Quiz Published!")

    st.divider()
    st.subheader("Manage Active Quizzes")
    for quiz in st.session_state['quizzes']:
        col1, col2 = st.columns([3, 1])
        with col1: st.write(f"**{quiz['Topic']}** ({quiz['Status']})")
        with col2:
            btn_text = "Close" if quiz['Status'] == 'Open' else "Open"
            if st.button(btn_text, key=f"btn_{quiz['QuizID']}"):
                quiz['Status'] = 'Closed' if quiz['Status'] == 'Open' else 'Open'
                st.rerun()

    st.divider()
    st.subheader("Student Results")
    st.write(st.session_state['results'])

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    name = st.text_input("Enter your Full Name:")
    
    if name:
        open_quizzes = [q for q in st.session_state['quizzes'] if q['Status'] == 'Open']
        for quiz in open_quizzes:
            if st.button(f"Take Quiz: {quiz['Topic']}", key=f"take_{quiz['QuizID']}"):
                st.session_state['active'] = quiz
                st.rerun()

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        with st.form("quiz_form"):
            q_data = quiz['Questions']['questions']
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in q_data}
            if st.form_submit_button("Submit"):
                score = sum(1 for q in q_data if ans[q['id']] == q['correct_option'])
                st.session_state['results'].append({
                    "QuizID": quiz['QuizID'], "StudentName": name, 
                    "Score": score, "Total": len(q_data)
                })
                st.success(f"Submitted! Score: {score}/{len(q_data)}")
                del st.session_state['active']

# --- MAIN APP ---
st.set_page_config(page_title="Lecture Quiz AI", layout="wide")
role = st.sidebar.radio("Select Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD:
        professor_dashboard()
else:
    student_dashboard()
