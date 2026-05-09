import streamlit as st
import pandas as pd
import json
import datetime
import random
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI

# --- CONFIGURATION ---
ADMIN_PASSWORD = "Eliza@123" # Updated to match your actual password
SHEET_URL = "https://docs.google.com/spreadsheets/d/1t4JYC-O71X3bV2F0SbNrWXZvLcpNZwn_XXQ-6RGWv64/edit"

# --- DATABASE CONNECTION ---
def get_sheet(worksheet_name):
    try:
        creds_dict = dict(st.secrets["gspread_creds"])
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL).worksheet(worksheet_name)
    except Exception as e:
        st.error(f"Sheet Connection Error: {e}")
        return None

# --- STUDENT LOGIN LOGIC ---
def login_student():
    """Handles student profile saving and state transition."""
    if st.session_state.name_in and st.session_state.strm_in:
        st.session_state['profile'] = {
            "name": st.session_state.name_in,
            "deg": st.session_state.deg_in,
            "strm": st.session_state.strm_in,
            "sem": st.session_state.sem_in
        }
        st.rerun()
    else:
        st.error("Please fill in all details before entering.")

# --- STUDENT VIEW ---
def student_dashboard():
    st.header("🎓 Student Portal")
    
    # Check if student is NOT logged in
    if 'profile' not in st.session_state:
        with st.container(border=True):
            st.info("Enter your academic details to access available quizzes.")
            with st.form("profile_form"):
                st.text_input("Full Name", key="name_in")
                st.selectbox("Degree", ["UG", "PG"], key="deg_in")
                st.text_input("Stream", key="strm_in", placeholder="e.g. Computer Science")
                st.number_input("Semester", 1, 8, key="sem_in")
                
                # Use a direct form submit button with the logic inside or as a callback
                submit = st.form_submit_button("Enter Portal")
                if submit:
                    login_student()
    else:
        # LOGGED IN VIEW
        profile = st.session_state['profile']
        st.sidebar.success(f"Logged in as: {profile['name']}")
        if st.sidebar.button("Logout"):
            del st.session_state['profile']
            st.rerun()

        st.write(f"### Welcome, {profile['name']}!")
        
        try:
            sheet = get_sheet("Quizzes")
            if sheet:
                quizzes = sheet.get_all_records()
                today = datetime.date.today()
                
                available_quizzes = []
                for row in quizzes:
                    # Filter logic
                    if (row['Status'] == 'Open' and 
                        row['Degree'] == profile['deg'] and 
                        row['Stream'] == profile['strm'] and 
                        int(row['Semester']) == profile['sem']):
                        
                        start = datetime.datetime.strptime(row['StartTime'], '%Y-%m-%d').date()
                        end = datetime.datetime.strptime(row['EndTime'], '%Y-%m-%d').date()
                        
                        if start <= today <= end:
                            available_quizzes.append(row)

                if not available_quizzes:
                    st.warning("No quizzes are currently active for your stream/semester.")
                else:
                    for row in available_quizzes:
                        with st.container(border=True):
                            col1, col2 = st.columns([3, 1])
                            col1.write(f"**Topic:** {row['Topic']}")
                            if col2.button(f"Take Quiz", key=f"btn_{row['QuizID']}"):
                                q_data = json.loads(row['Questions'])['questions']
                                random.shuffle(q_data)
                                st.session_state['active'] = {"quiz": row, "qs": q_data}
                                st.rerun()
        except Exception as e:
            st.error(f"Error loading quizzes: {e}")

    # QUIZ INTERFACE
    if 'active' in st.session_state:
        quiz = st.session_state['active']
        st.divider()
        with st.form("quiz_form"):
            st.subheader(f"Quiz: {quiz['quiz']['Topic']}")
            answers = {}
            for i, q in enumerate(quiz['qs'], 1):
                st.write(f"**Q{i}: {q['question_text']}**")
                answers[q['id']] = st.radio("Choose one:", q['options'], key=f"q_{q['id']}", label_visibility="collapsed")
            
            if st.form_submit_button("Submit Final Answers"):
                score = 0
                for q in quiz['qs']:
                    # Extract letter prefix 'A' from 'A. Option text'
                    student_ans = str(answers[q['id']])[0] 
                    if student_ans == q['correct_option']:
                        score += 1
                
                # Save results
                res_sheet = get_sheet("Results")
                if res_sheet:
                    res_sheet.append_row([
                        quiz['quiz']['QuizID'], 
                        profile['name'], 
                        profile['deg'], 
                        profile['strm'], 
                        profile['sem'], 
                        quiz['quiz']['Topic'], 
                        score, 
                        len(quiz['qs']), 
                        str(datetime.datetime.now())
                    ])
                    st.success(f"Quiz Submitted! Your Score: {score}/{len(quiz['qs'])}")
                    del st.session_state['active']
                    # Use a non-form button or link to refresh
                    st.info("Results saved. Refresh to take more quizzes.")

# --- PROFESSOR VIEW (Simplified) ---
def professor_dashboard():
    st.header("👨‍🏫 Professor Dashboard")
    st.write("Authorized Access Granted.")
    # (Rest of your professor logic goes here)

# --- MAIN ---
st.set_page_config(page_title="Syllabus Quiz AI", layout="wide")
role = st.sidebar.selectbox("Access Level", ["Student", "Professor"])

if role == "Professor":
    pwd = st.sidebar.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        professor_dashboard()
    elif pwd:
        st.sidebar.error("Invalid credentials.")
else:
    student_dashboard()
