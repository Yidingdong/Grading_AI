import streamlit as st
import pandas as pd
from frontendData import session, User, Course, Enrollment

st.title("Welcome to your Grading AI!")

if 'logged_in' in st.session_state and st.session_state.logged_in:
    st.subheader("👤 Your Profile:")
    username = st.session_state.username
    role = st.session_state.role
    user_id = st.session_state.user_id

    st.write(f"**Username:** {username}")
    st.write(f"**Role:** {role}")

    current_user = session.query(User).filter_by(id=user_id).first()
    if current_user:
        st.write(f"**Name:** {current_user.name}")

    if role == "Teacher":
        teacher_courses_display = []
        if user_id:
            courses = session.query(Course).filter_by(teacher_id=user_id).all()
            for course in courses:
                num_students = session.query(Enrollment).filter_by(course_id=course.course_id).count()
                teacher_courses_display.append({
                    "Course ID": course.course_id,
                    "Course name": course.name,
                    "Number of students": num_students,
                    "Status": "active" if course.is_active else "completed"
                })
        st.subheader("📚 Your Courses")
        if teacher_courses_display:
            df1 = pd.DataFrame(teacher_courses_display)
            df1.index = df1.index + 1
            st.dataframe(df1)
        else:
            st.info("You are not teaching any courses currently.")
else:
    st.warning("Please log in to view your profile.")
    st.page_link("app.py", label="Go to Login", icon="🏠")