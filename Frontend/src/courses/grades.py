import streamlit as st
import pandas as pd
from frontendData import session, User, Course, Enrollment

st.header(f"📊 Grades for {st.session_state.get('username', 'Unknown User')}")

if st.session_state.get("logged_in") and st.session_state.get("role") == "Student":
    student_id = st.session_state.get("user_id")

    if student_id:
        student_enrollments = session.query(Enrollment).filter_by(student_id=student_id).all()
        grades_data = []
        if student_enrollments:
            for enrollment in student_enrollments:
                course_name = enrollment.course.name if enrollment.course else "N/A"
                grades_data.append({
                    "Course Name": course_name,
                    "Grade": enrollment.grade if enrollment.grade else "Not graded"
                })

            if grades_data:
                df_grades = pd.DataFrame(grades_data)
                st.subheader("Your Grades")
                st.table(df_grades)
            else:
                st.info("No grade data found for your enrollments.")
        else:
            st.warning("You are not enrolled in any courses yet.")
    else:
        st.error("Student ID not found in session. Please log in again.")
else:
    st.warning("You must be logged in as a student to view your grades.")
    if st.button("Go to Login", key="grades_goto_login_btn"):
        st.switch_page("app.py")
