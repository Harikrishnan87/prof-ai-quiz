import streamlit as st
import pandas as pd
import json
import datetime
from openai import OpenAI
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
ST_PRO_THEME = "professional"
ADMIN_PASSWORD = "admin123"  # CHANGE THIS PASSWORD!

# --- DATABASE CONNECTION ---
def get_db_connection():
    try:
        # This connects to Google Sheets using the secrets we will set up in Step 3
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn
    except Exception as e:
        st.error(f"Database Error: {e}")
        return None

# --- OPENAI QUIZ GENERATION ---
def generate_questions(topic, num_questions):
    # This connects to OpenAI using the key we will set up in Step 3
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        
        prompt = f"""
        Create a difficult multiple choice quiz with exactly {num_questions} questions on the topic: '{topic}'.
        Format the output as a valid JSON object with this exact structure:
        {{
            "questions": [
                {{
                    "id": 1,
                    "question_text": "The question?",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_option": "Option A"
                }}
            ]
        }}
        Ensure strictly valid JSON. Do not include markdown formatting like ```json.
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        # Clean up potential markdown formatting from AI
        content = content.replace("```json", "").replace("```", "")
        return json.loads(content)
    except Exception as e:
        st.error(f"Error generating quiz: {e}")
        return None

# --- PROFESSOR VIEW ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    
    # Create Quiz Section
    with st.expander("Create New Quiz", expanded=True):
        topic = st.text_input("Lecture Topic")
        num_q = st.slider("Number of Questions", 1, 10, 5)
        
        if st.button("Generate & Publish Quiz"):
            with st.spinner("Generating Questions with AI..."):
                quiz_data = generate_questions(topic, num_q)
                if quiz_data:
                    conn = get_db_connection()
                    # Prepare data
                    quiz_id = str(int(datetime.datetime.now().timestamp()))
                    new_quiz = pd.DataFrame([{
                        "QuizID": quiz_id,
                        "Topic": topic,
                        "Questions": json.dumps(quiz_data),
                        "Status": "Open",
                        "Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    }])
                    
                    # Append to Google Sheet (Quizzes tab)
                    try:
                        existing_data = conn.read(worksheet="Quizzes", ttl=0)
                        updated_data = pd.concat([existing_data, new_quiz], ignore_index=True)
                        conn.update(worksheet="Quizzes", data=updated_data)
                        st.success(f"Quiz on '{topic}' Published Successfully!")
                        st.json(quiz_data)
                    except Exception as e:
                        st.error(f"Failed to save quiz. Make sure the Google Sheet is set up. Error: {e}")

    # Manage Quizzes Section
    st.divider()
    st.subheader("Manage Active Quizzes")
    conn = get_db_connection()
    try:
        quizzes = conn.read(worksheet="Quizzes", ttl=0)
        if not quizzes.empty:
            for index, row in quizzes.iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{row['Topic']}** ({row['Status']})")
                with col2:
                    if row['Status'] == 'Open':
                        if st.button("Close Quiz", key=f"close_{row['QuizID']}"):
                            quizzes.at[index, 'Status'] = 'Closed'
                            conn.update(worksheet="Quizzes", data=quizzes)
                            st.rerun()
                    elif row['Status'] == 'Closed':
                         if st.button("Release Results", key=f"open_{row['QuizID']}"):
                            quizzes.at[index, 'Status'] = 'Released'
                            conn.update(worksheet="Quizzes", data=quizzes)
                            st.rerun()
    except:
        st.write("No quizzes found yet.")

    # View Results Section
    st.divider()
    st.subheader("Student Results")
    try:
        results = conn.read(worksheet="Results", ttl=0)
        if not results.empty:
            st.dataframe(results)
    except:
        st.write("No results found yet.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    
    student_name = st.text_input("Enter your Full Name to begin:")
    
    if student_name:
        conn = get_db_connection()
        try:
            quizzes = conn.read(worksheet="Quizzes", ttl=0)
            # Filter for Open quizzes
            open_quizzes = quizzes[quizzes['Status'] == 'Open']
        except:
            st.warning("Could not load quizzes.")
            return

        if not open_quizzes.empty:
            st.subheader("Available Quizzes")
            for index, row in open_quizzes.iterrows():
                with st.expander(f"Take Quiz: {row['Topic']}"):
                    st.write("Once you submit, you cannot change your answers.")
                    if st.button(f"Start {row['Topic']}", key=f"start_{row['QuizID']}"):
                        st.session_state['active_quiz'] = row.to_dict()
                        st.session_state['active_quiz_data'] = json.loads(row['Questions'])
                        st.rerun()
        else:
            st.info("No active quizzes at the moment.")

    # Handle Active Quiz Taking
    if 'active_quiz' in st.session_state:
        st.divider()
        st.subheader(f"Quiz: {st.session_state['active_quiz']['Topic']}")
        q_data = st.session_state['active_quiz_data']
        
        with st.form("quiz_form"):
            user_answers = {}
            for q in q_data['questions']:
                st.write(f"**{q['id']}. {q['question_text']}**")
                user_answers[q['id']] = st.radio("Select an option:", q['options'], key=q['id'])
                st.write("---")
            
            submit = st.form_submit_button("Submit Quiz")
            
            if submit:
                score = 0
                total = len(q_data['questions'])
                for q in q_data['questions']:
                    if user_answers[q['id']] == q['correct_option']:
                        score += 1
                
                # Save Result
                new_result = pd.DataFrame([{
                    "QuizID": st.session_state['active_quiz']['QuizID'],
                    "StudentName": student_name,
                    "Topic": st.session_state['active_quiz']['Topic'],
                    "Score": score,
                    "Total": total,
                    "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                
                try:
                    results_data = conn.read(worksheet="Results", ttl=0)
                    updated_results = pd.concat([results_data, new_result], ignore_index=True)
                    conn.update(worksheet="Results", data=updated_results)
                    st.success(f"Quiz Submitted! You scored {score}/{total}")
                    del st.session_state['active_quiz']
                except Exception as e:
                    st.error(f"Error saving results: {e}")

# --- MAIN APP NAVIGATION ---
st.set_page_config(page_title="Lecture Quiz AI", layout="wide")

st.sidebar.title("Login")
role = st.sidebar.radio("Select Role", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.sidebar.error("Incorrect Password")
else:
    student_dashboard()
