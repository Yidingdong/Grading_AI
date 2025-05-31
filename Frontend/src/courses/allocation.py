import streamlit as st
from frontendData import session, User, Course, Enrollment
import pandas as pd

if not st.session_state.get("logged_in") or st.session_state.get("role") != "Teacher":
    st.error("You must be logged in as a teacher to allocate courses.")
    if st.button("Go to Login", key="alloc_goto_login_btn"): # Added unique key
        st.switch_page("app.py")
    st.stop()

st.title("📚 Course Allocation")

teacher_id = st.session_state.get("user_id")
if not teacher_id:
    st.error("Teacher ID not found in session. Please log in again.")
    st.stop()

course_name = st.text_input("Enter New Course Name")
course_duration = st.number_input("Course Duration (weeks)", min_value=1, max_value=52, value=12)

all_students = session.query(User).filter_by(user_type="student").all()
if not all_students:
    st.info("No students available to select. Please ensure students are registered with the 'student' role.")
    student_options_display = ["No options to select"]
    student_options_map = {}
else:
    student_options_display = [f"{student.name} ({student.username})" for student in all_students]
    student_options_map = {f"{student.name} ({student.username})": student.id for student in all_students}

selected_student_displays = st.multiselect(
    "Select Students to Enroll",
    options=student_options_display
)

if st.button("Create and Allocate Course"):
    selected_student_ids = [student_options_map[display] for display in selected_student_displays if display in student_options_map]
    if course_name and selected_student_ids:
        existing_course = session.query(Course).filter_by(name=course_name).first()
        if existing_course:
            st.error(f"A course with the name '{course_name}' already exists (ID: {existing_course.course_id}).")
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
                enrolled_count = 0
                for student_id_to_enroll in selected_student_ids: # Renamed loop variable
                    if student_id_to_enroll: # Check if student_id is not None
                        existing_enrollment = session.query(Enrollment).filter_by(
                            course_id=new_course.course_id,
                            student_id=student_id_to_enroll
                        ).first()
                        if not existing_enrollment:
                            enrollment = Enrollment(course_id=new_course.course_id, student_id=student_id_to_enroll)
                            session.add(enrollment)
                            enrolled_count += 1
                session.commit()
                st.success(f"Course '{course_name}' created (ID: {new_course.course_id}) and {enrolled_count} student(s) enrolled successfully!")
                st.rerun()
            except Exception as e:
                session.rollback()
                st.error(f"Failed to allocate course: {e}")
    elif not course_name:
        st.error("Course name is required.")
    else:
        st.error("Please select at least one student to enroll.")

st.markdown("---")
st.subheader("Existing Courses Taught by You")
teacher_courses_list = session.query(Course).filter_by(teacher_id=teacher_id).order_by(Course.course_id.desc()).all() # Renamed variable
if not teacher_courses_list:
    st.info("You are not currently teaching any courses.")
else:
    courses_data_display = [] # Renamed variable
    for course_item in teacher_courses_list: # Renamed loop variable
        num_students = session.query(Enrollment).filter_by(course_id=course_item.course_id).count()
        courses_data_display.append({
            "ID": course_item.course_id,
            "Name": course_item.name,
            "Duration (w)": course_item.duration_weeks,
            "Status": "Active" if course_item.is_active else "Completed",
            "Students": num_students
        })
    st.dataframe(pd.DataFrame(courses_data_display))