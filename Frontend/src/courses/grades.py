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
                course_name = "N/A"
                course_status = "N/A"
                if enrollment.course:  # Check if course object is loaded
                    course_name = enrollment.course.name
                    course_status = "Active" if enrollment.course.is_active else "Completed"

                grades_data.append({
                    "Course Name": course_name,
                    "Course ID": enrollment.course_id,
                    "Grade": enrollment.grade if enrollment.grade else "Not Graded",
                    "Course Status": course_status
                })

            if grades_data:
                df_grades = pd.DataFrame(grades_data)
                st.subheader("Your Enrolled Courses and Grades")
                st.dataframe(df_grades)
            else:
                st.info("No grade data found for your enrollments.")
        else:
            st.warning("You are not enrolled in any courses yet.")
    else:
        st.error("Student ID not found in session. Please log in again.")
else:
    st.warning("You must be logged in as a student to view your grades.")
    if st.button("Go to Login", key="grades_goto_login_btn"):  # Added unique key
        st.switch_page("app.py")