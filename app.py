import streamlit as st
import json
import datetime
from openai import OpenAI

# --- INITIALIZE IN-MEMORY DATA ---
if 'quizzes' not in st.session_state:
    st.session_state['quizzes'] = []
if 'results' not in st.session_state:
    st.session_state['results'] = []

# --- CONFIGURATION ---
ADMIN_PASSWORD = "admin123"

# --- OPENAI QUIZ GENERATION ---
def generate_questions(topic, num_questions):
    try:
        # Ensure the key is available
        if "OPENAI_API_KEY" not in st.secrets:
            st.error("OpenAI API Key is missing in Secrets!")
            return None
            
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        prompt = f"""
        Create a difficult multiple choice quiz with exactly {num_questions} questions on: '{topic}'. 
        Return valid JSON only in the following format:
        {{
            "questions": [
                {{"id": 1, "question_text": "Sample Question?", "options": ["A", "B", "C", "D"], "correct_option": "A"}}
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
                st.success(f"Quiz '{topic}' Published Successfully!")

    st.divider()
    st.subheader("Manage Active Quizzes")
    if not st.session_state['quizzes']:
        st.write("No quizzes created yet.")
    
    for quiz in st.session_state['quizzes']:
        col1, col2 = st.columns([3, 1])
        with col1: 
            st.write(f"**{quiz['Topic']}** ({quiz['Status']})")
        with col2:
            btn_text = "Close" if quiz['Status'] == 'Open' else "Open"
            if st.button(btn_text, key=f"btn_{quiz['QuizID']}"):
                quiz['Status'] = 'Closed' if quiz['Status'] == 'Open' else 'Open'
                st.rerun()

    st.divider()
    st.subheader("Student Results")
    if st.session_state['results']:
        st.table(st.session_state['results'])
    else:
        st.write("No results yet.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    
    # Hide name input if a quiz is active
    if 'active' not in st.session_state:
        name = st.text_input("Enter your Full Name:")
    else:
        name = "Active User"

    if 'active' not in st.session_state and name:
        open_quizzes = [q for q in st.session_state['quizzes'] if q['Status'] == 'Open']
        if not open_quizzes:
            st.info("No active quizzes available.")
        
        for quiz in open_quizzes:
            if st.button(f"Take Quiz: {quiz['Topic']}", key=f"take_{quiz['QuizID']}"):
                st.session_state['active'] = quiz
                st.session_state['student_name'] = name
                st.rerun()

    if 'active' in st.session_state:
        quiz = st.session_state['active']
        st.subheader(f"Taking Quiz: {quiz['Topic']}")
        
        with st.form("quiz_form"):
            # Use .get() to avoid KeyError if JSON structure varies
            q_data = quiz['Questions'].get('questions', [])
            ans = {q['id']: st.radio(f"{q['id']}. {q['question_text']}", q['options']) for q in q_data}
            
            if st.form_submit_button("Submit"):
                score = sum(1 for q in q_data if ans[q['id']] == q['correct_option'])
                st.session_state['results'].append({
                    "QuizID": quiz['QuizID'], 
                    "StudentName": st.session_state['student_name'], 
                    "Score": score, 
                    "Total": len(q_data)
                })
                st.success(f"Submitted! You scored {score}/{len(q_data)}")
                del st.session_state['active']
                del st.session_state['student_name']
                st.rerun()

# --- MAIN APP ---
st.set_page_config(page_title="Lecture Quiz AI", layout="wide")
role = st.sidebar.radio("Select Role", ["Student", "Professor"])
if role == "Professor":
    if st.sidebar.text_input("Password", type="password") == ADMIN_PASSWORD:
        professor_dashboard()
    elif st.sidebar.text_input("Password"):
        st.error("Incorrect Password")
else:
    student_dashboard()
