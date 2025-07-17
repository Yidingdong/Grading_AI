import streamlit as st
from frontendData import session, User, Course, Enrollment
import pandas as pd

st.title("➕ Allocate a New Course")

if not st.session_state.get("logged_in") or st.session_state.get("role") != "Teacher":
    st.error("You must be logged in as a teacher to allocate courses.")
    if st.button("Go to Login", key="alloc_goto_login_btn"):
        st.switch_page("app.py")
    st.stop()

teacher_id = st.session_state.get("user_id")
if not teacher_id:
    st.error("Teacher ID not found in session. Please log in again.")
    st.stop()

st.subheader("Course Details")
course_name = st.text_input("Course Name")
course_duration = st.number_input("Duration (weeks)", min_value=1, max_value=52, value=12)

st.subheader("Student Selection")
all_students = session.query(User).filter_by(user_type="student").all()
if not all_students:
    st.info("No students available to select. Please ensure students are registered with the 'student' role.")
    student_options_display = []
    student_options_map = {}
else:
    student_options_display = [f"{student.name} ({student.username})" for student in all_students]
    student_options_map = {f"{student.name} ({student.username})": student.id for student in all_students}

selected_student_displays = st.multiselect(
    "Select Students",
    options=student_options_display
)

if st.button("Allocate Course"):
    selected_student_ids = [student_options_map[display] for display in selected_student_displays if display in student_options_map]
    if course_name and selected_student_ids:
        existing_course = session.query(Course).filter_by(name=course_name).first()
        if existing_course:
            st.error(f"A course with the name '{course_name}' already exists.")
        else:
            try:
                new_course = Course(
                    name=course_name,
                    teacher_id=teacher_id,
                    duration_weeks=course_duration,
                    is_active=True
                )
                session.add(new_course)
                session.flush()
                for student_id_to_enroll in selected_student_ids:
                    if student_id_to_enroll:
                        enrollment = Enrollment(course_id=new_course.course_id, student_id=student_id_to_enroll)
                        session.add(enrollment)
                session.commit()
                st.success(f"Course '{course_name}' allocated and students enrolled successfully!")
                st.rerun()
            except Exception as e:
                session.rollback()
                st.error(f"Failed to allocate course: {e}")
    else:
        st.error("Please fill all fields before submitting.")

st.markdown("---")
st.subheader("Your Existing Courses")
teacher_courses_list = session.query(Course).filter_by(teacher_id=teacher_id).order_by(Course.course_id.desc()).all()
if not teacher_courses_list:
    st.info("You are not currently teaching any courses.")
else:
    courses_data_display = []
    for course_item in teacher_courses_list:
        num_students = session.query(Enrollment).filter_by(course_id=course_item.course_id).count()
        courses_data_display.append({
            "ID": course_item.course_id,
            "Name": course_item.name,
            "Duration (w)": course_item.duration_weeks,
            "Status": "Active" if course_item.is_active else "Completed",
            "Students": num_students
        })
    st.dataframe(pd.DataFrame(courses_data_display))
