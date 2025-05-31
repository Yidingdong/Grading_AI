import streamlit as st
from frontendData import session, User, Course, Enrollment
import pandas as pd

if not st.session_state.get("logged_in") or st.session_state.get("role") != "Student":
    st.error("You must be logged in as a student to view your courses.")
    if st.button("Go to Login", key="my_courses_goto_login_btn"):
        st.switch_page("app.py")
    st.stop()

st.title("📚 My Enrolled Courses Overview")
st.write(
    "This page provides a summary of your courses. You can access individual active/completed courses directly from the sidebar.")

student_id = st.session_state.get("user_id")
if not student_id:
    st.error("Student ID not found in session. Please log in again.")
    if st.button("Go to Login", key="my_courses_no_id_goto_login_btn"):
        st.switch_page("app.py")
    st.stop()

try:
    student_enrollments = session.query(Enrollment).filter_by(student_id=student_id).all()

    active_courses_summary = []
    completed_courses_summary = []

    if student_enrollments:
        for enrollment in student_enrollments:
            course = enrollment.course
            teacher_name = "N/A"
            if course and course.teacher:
                teacher_name = course.teacher.name

            course_summary_info = {
                "Course Name": course.name if course else "N/A",
                "Teacher": teacher_name,
                "Your Grade": enrollment.grade if enrollment.grade else "Not Graded yet",
                "Status": ("Active" if course.is_active else "Completed") if course else "N/A"
            }
            if course and course.is_active:
                active_courses_summary.append(course_summary_info)
            elif course:
                completed_courses_summary.append(course_summary_info)

    st.subheader("🚀 Active Courses Summary")
    if active_courses_summary:
        st.dataframe(pd.DataFrame(active_courses_summary))
    else:
        st.info("You are not currently enrolled in any active courses.")

    st.subheader("✔ Completed Courses Summary")
    if completed_courses_summary:
        st.dataframe(pd.DataFrame(completed_courses_summary))
    else:
        st.info("You have no completed courses.")

except Exception as e:
    st.error(f"An error occurred while retrieving your course summary: {e}")
finally:
    pass