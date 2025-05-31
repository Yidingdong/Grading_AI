import streamlit as st
from frontendData import session, User, Course, Enrollment
import pandas as pd
from pymongo import MongoClient, errors as pymongo_errors
from bson.objectid import ObjectId
import bcrypt
import os
from datetime import datetime
import gridfs
from io import BytesIO
import requests

st.set_page_config(
    page_title="Grading AI",
    layout="wide",
    initial_sidebar_state="expanded"
)

MONGO_HOST = os.getenv("MONGO_HOST", "mongodb-server")
MONGO_USER_FRONTEND = os.getenv("MONGO_USER_FRONTEND", "root")
MONGO_PASSWORD_FRONTEND = os.getenv("MONGO_PASSWORD_FRONTEND", "example")
MONGO_DB_NAME_FRONTEND = os.getenv("MONGO_DB_NAME_FRONTEND", "grading_ai_frontend")
MONGO_FILES_COLLECTION_FRONTEND = os.getenv("MONGO_FILES_COLLECTION_FRONTEND", "uploaded_material")
MONGO_EXAMS_DB_NAME = "Exams"
MONGO_PDF_SUBMISSIONS_COLLECTION = "pdf_submissions"
PDF_PROCESSOR_URL_ENV = os.getenv("PDF_PROCESSOR_URL", "http://pdf-processor-service:5003")

MONGO_URI = f"mongodb://{MONGO_USER_FRONTEND}:{MONGO_PASSWORD_FRONTEND}@{MONGO_HOST}:27017/?authSource=admin"

db_frontend = None
fs = None
mongo_client_global = None

try:
    mongo_client_global = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client_global.admin.command('ping')
    db_frontend = mongo_client_global[MONGO_DB_NAME_FRONTEND]
    files_metadata_collection = db_frontend[MONGO_FILES_COLLECTION_FRONTEND]
    fs = gridfs.GridFS(db_frontend)
except Exception as e:
    st.error(f"MongoDB/GridFS Connection Error (Frontend): {e}. Application cannot start.")
    st.stop()

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "role" not in st.session_state: st.session_state.role = None
if "username" not in st.session_state: st.session_state.username = None
if "user_id" not in st.session_state: st.session_state.user_id = None


def signup(username, password, role_selected, full_name):
    user = session.query(User).filter_by(username=username).first()
    if user: st.error("Username already exists."); return
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db_user_type = role_selected.lower()
    if db_user_type not in ['teacher', 'student']: st.error("Invalid role selected."); return
    new_user = User(username=username, password_hash=hashed_password, user_type=db_user_type, name=full_name)
    session.add(new_user)
    try:
        session.commit(); st.success("Account created successfully! Please log in to continue.")
    except Exception as e:
        session.rollback(); st.error(f"Could not create account: {e}")


def login(username, password):
    user = session.query(User).filter_by(username=username).first()
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        st.session_state.logged_in = True
        st.session_state.username = user.username
        st.session_state.user_id = user.id
        st.session_state.role = user.user_type.capitalize()
        st.rerun()
    else:
        st.error("Invalid username or password.")


def logout_action():
    keys_to_delete = [key for key in st.session_state.keys()]
    for key in keys_to_delete: del st.session_state[key]
    st.session_state.logged_in = False
    st.session_state.role = None
    st.success("You have been logged out.")
    st.rerun()


profile_page_nav = st.Page("Profile.py", title="User Profile", icon="👤")
course_allocation_page_nav = st.Page("courses/allocation.py", title="Allocate New Course", icon="➕")
my_courses_page_nav = st.Page("courses/my_courses.py", title="List My Courses Overview", icon="🎒")
grades_page_nav = st.Page("courses/grades.py", title="View My Grades Summary", icon="🗳️")
settings_page_nav = st.Page("settings.py", title="Application Settings", icon="⚙️")


def logout_page_func():
    st.title("Log Out Confirmation")
    if st.button("Confirm Log Out", key="confirm_logout_nav_btn"): logout_action()


logout_nav_page = st.Page(logout_page_func, title="Log Out", icon="🚪")


def delete_file_from_gridfs_and_metadata(metadata_id_to_delete, gridfs_id_to_delete):
    global fs, files_metadata_collection
    if not fs: st.error("GridFS not initialized."); return False
    try:
        actual_metadata_id = ObjectId(metadata_id_to_delete) if isinstance(metadata_id_to_delete,
                                                                           str) else metadata_id_to_delete
        if gridfs_id_to_delete:
            actual_gridfs_id = ObjectId(gridfs_id_to_delete) if isinstance(gridfs_id_to_delete,
                                                                           str) else gridfs_id_to_delete
            fs.delete(actual_gridfs_id)
        result = files_metadata_collection.delete_one({"_id": actual_metadata_id})
        if result.deleted_count > 0:
            st.success("File and its metadata deleted successfully."); return True
        else:
            st.warning("Metadata not found or already deleted. GridFS file (if existed) was targeted."); return True
    except gridfs.errors.NoFile:
        st.warning(
            f"File with GridFS ID {gridfs_id_to_delete} not found (already deleted?). Attempting to delete metadata.");
        try:
            actual_metadata_id = ObjectId(metadata_id_to_delete) if isinstance(metadata_id_to_delete,
                                                                               str) else metadata_id_to_delete
            if files_metadata_collection.delete_one({"_id": actual_metadata_id}).deleted_count > 0:
                st.success("Orphaned metadata deleted.");
                return True
            else:
                st.warning("Orphaned metadata also not found."); return True
        except Exception as e_meta:
            st.error(f"Error deleting orphaned metadata: {e_meta}"); return False
    except Exception as e:
        st.error(f"Error during file deletion: {e}"); return False


def _generate_teacher_course_page_layout(course_obj):
    if f"qp_uploader_key_{course_obj.course_id}" not in st.session_state: st.session_state[
        f"qp_uploader_key_{course_obj.course_id}"] = 0
    if f"ref_uploader_key_{course_obj.course_id}" not in st.session_state: st.session_state[
        f"ref_uploader_key_{course_obj.course_id}"] = 0

    st.title(f"📘 {course_obj.name} (ID: {course_obj.course_id}) - Teacher View")
    is_completed = not course_obj.is_active
    if is_completed: st.info("This course is marked as completed. Uploads and grading might be disabled.")

    st.subheader("❓ Question Paper")
    current_qp_key = f"qp_upload_{course_obj.course_id}_{st.session_state[f'qp_uploader_key_{course_obj.course_id}']}"
    uploaded_qp = st.file_uploader(label="Upload question paper PDF", type=["pdf"], key=current_qp_key,
                                   disabled=is_completed)
    if uploaded_qp and fs:
        try:
            file_id = fs.put(uploaded_qp, filename=uploaded_qp.name, content_type=uploaded_qp.type)
            files_metadata_collection.insert_one(
                {"gridfs_file_id": file_id, "course_id": course_obj.course_id, "course_name": course_obj.name,
                 "file_name": uploaded_qp.name, "file_type": "question_paper", "content_type_orig": uploaded_qp.type,
                 "uploader_username": st.session_state.username, "upload_timestamp": datetime.utcnow()})
            st.success(f"QP '{uploaded_qp.name}' uploaded!", icon="✅");
            st.session_state[f"qp_uploader_key_{course_obj.course_id}"] += 1;
            st.rerun()
        except Exception as e:
            st.error(f"Error uploading QP: {e}")
    qp_docs_meta = list(
        files_metadata_collection.find({"course_id": course_obj.course_id, "file_type": "question_paper"}).sort(
            "upload_timestamp", -1))
    if qp_docs_meta:
        for doc_meta in qp_docs_meta:
            meta_id_str = str(doc_meta['_id']);
            gridfs_id = doc_meta.get('gridfs_file_id')
            cols = st.columns([0.6, 0.2, 0.2]);
            with cols[0]:
                st.write(f"- {doc_meta['file_name']} ({doc_meta['upload_timestamp']:%Y-%m-%d %H:%M})")
            with cols[1]:
                if fs and gridfs_id:
                    try:
                        grid_out = fs.get(gridfs_id); st.download_button("Download", grid_out.read(),
                                                                         doc_meta['file_name'], grid_out.content_type,
                                                                         key=f"dl_qp_{meta_id_str}")
                    except:
                        st.caption("DL Error")
            with cols[2]:
                if st.button("Delete", key=f"del_qp_{meta_id_str}", type="secondary", disabled=is_completed):
                    if delete_file_from_gridfs_and_metadata(doc_meta['_id'], gridfs_id): st.rerun()
    else:
        st.info("No question papers uploaded.")

    st.subheader("📚 Reference Material")
    current_ref_key = f"ref_upload_{course_obj.course_id}_{st.session_state[f'ref_uploader_key_{course_obj.course_id}']}"
    uploaded_ref = st.file_uploader(label="Upload reference material PDF", type=["pdf"], key=current_ref_key,
                                    disabled=is_completed)
    if uploaded_ref and fs:
        try:
            file_id = fs.put(uploaded_ref, filename=uploaded_ref.name, content_type=uploaded_ref.type)
            files_metadata_collection.insert_one(
                {"gridfs_file_id": file_id, "course_id": course_obj.course_id, "course_name": course_obj.name,
                 "file_name": uploaded_ref.name, "file_type": "reference_material",
                 "content_type_orig": uploaded_ref.type, "uploader_username": st.session_state.username,
                 "upload_timestamp": datetime.utcnow()})
            st.success(f"Ref '{uploaded_ref.name}' uploaded!", icon="✅");
            st.session_state[f"ref_uploader_key_{course_obj.course_id}"] += 1;
            st.rerun()
        except Exception as e:
            st.error(f"Error uploading Ref: {e}")
    ref_docs_meta = list(
        files_metadata_collection.find({"course_id": course_obj.course_id, "file_type": "reference_material"}).sort(
            "upload_timestamp", -1))
    if ref_docs_meta:
        for doc_meta in ref_docs_meta:
            meta_id_str = str(doc_meta['_id']);
            gridfs_id = doc_meta.get('gridfs_file_id')
            cols = st.columns([0.6, 0.2, 0.2]);
            with cols[0]:
                st.write(f"- {doc_meta['file_name']} ({doc_meta['upload_timestamp']:%Y-%m-%d %H:%M})")
            with cols[1]:
                if fs and gridfs_id:
                    try:
                        grid_out = fs.get(gridfs_id); st.download_button("Download", grid_out.read(),
                                                                         doc_meta['file_name'], grid_out.content_type,
                                                                         key=f"dl_ref_{meta_id_str}")
                    except:
                        st.caption("DL Error")
            with cols[2]:
                if st.button("Delete", key=f"del_ref_{meta_id_str}", type="secondary", disabled=is_completed):
                    if delete_file_from_gridfs_and_metadata(doc_meta['_id'], gridfs_id): st.rerun()
    else:
        st.info("No reference materials uploaded.")

    st.markdown("---");
    st.subheader("📋 Enrolled Students & Submissions")
    enrollments = session.query(Enrollment).filter_by(course_id=course_obj.course_id).all()
    if not enrollments:
        st.info("No students enrolled in this course.")
    else:
        st.markdown("#### Student Answer Sheets Submitted (via UI):")
        any_ui_submissions_found = False
        for enr_loop in enrollments:
            student_for_submission_view = enr_loop.student
            student_ui_submissions = list(files_metadata_collection.find({
                "course_id": course_obj.course_id,
                "student_id": student_for_submission_view.id,
                "file_type": "student_answer_sheet"
            }).sort("upload_timestamp", -1))

            if student_ui_submissions:
                any_ui_submissions_found = True
                with st.expander(
                        f"{student_for_submission_view.name} ({student_for_submission_view.username}) - {len(student_ui_submissions)} submission(s)"):
                    for sub_meta in student_ui_submissions:
                        meta_id_str = str(sub_meta['_id']);
                        gridfs_id = sub_meta.get('gridfs_file_id')
                        sub_cols = st.columns([0.7, 0.3])
                        with sub_cols[0]:
                            st.write(
                                f"- {sub_meta['file_name']} (Uploaded: {sub_meta['upload_timestamp']:%Y-%m-%d %H:%M})")
                        with sub_cols[1]:
                            if fs and gridfs_id:
                                try:
                                    grid_out_sub = fs.get(gridfs_id)
                                    st.download_button("Download Ans", grid_out_sub.read(), sub_meta['file_name'],
                                                       grid_out_sub.content_type, key=f"dl_ans_{meta_id_str}")
                                except:
                                    st.caption("DL Err")
        if not any_ui_submissions_found:
            st.info("No student answer sheets have been submitted (via UI) for this course yet.")

        st.markdown("---")
        st.subheader("📝 Update Student Grades / Trigger AI Grading")
        selected_enrollment_id = st.selectbox(
            "Select Student to Grade:",
            [enr.enrollment_id for enr in enrollments],
            format_func=lambda x: f"{session.query(Enrollment).get(x).student.name} (Enrollment ID: {x})",
            key=f"sel_stud_for_grade_{course_obj.course_id}",
            disabled=is_completed
        )
        if selected_enrollment_id:
            enrollment_to_grade = session.query(Enrollment).get(selected_enrollment_id)
            st.write(f"**Grading for: {enrollment_to_grade.student.name}**")

            student_ui_submission_meta = files_metadata_collection.find_one({
                "student_id": enrollment_to_grade.student_id,
                "course_id": course_obj.course_id,
                "file_type": "student_answer_sheet"
            })

            ocr_doc_id_for_grading = None
            gridfs_id_of_submission_to_process = None
            original_filename = "N/A"

            if student_ui_submission_meta and student_ui_submission_meta.get('gridfs_file_id'):
                gridfs_id_of_submission_to_process = str(student_ui_submission_meta['gridfs_file_id'])
                original_filename = student_ui_submission_meta.get('file_name', 'unknown_submission.pdf')
                st.write(f"Selected student submission (from UI): {original_filename}")

                ocr_processed_submission = mongo_client_global[MONGO_EXAMS_DB_NAME][
                    MONGO_PDF_SUBMISSIONS_COLLECTION].find_one({
                    "processed_from_gridfs_id": gridfs_id_of_submission_to_process,
                    "category": "answer_sheet"
                })
                if ocr_processed_submission:
                    ocr_doc_id_for_grading = str(ocr_processed_submission['_id'])
                    st.success(f"This submission has been OCR processed. (Exams DB ID: {ocr_doc_id_for_grading})")

            if gridfs_id_of_submission_to_process and not ocr_doc_id_for_grading:
                if st.button(f"⚙️ Process '{original_filename}' for AI Grading",
                             key=f"ocr_proc_btn_{selected_enrollment_id}"):
                    st.info("Sending submission for OCR processing via PDF Processor Service...")
                    try:
                        payload = {
                            "gridfs_file_id": gridfs_id_of_submission_to_process,
                            "student_name": enrollment_to_grade.student.name,
                            "student_id": str(enrollment_to_grade.student_id),
                            "uploader_username": enrollment_to_grade.student.username,
                            "teacher_username": st.session_state.username,
                            "course_name": course_obj.name,
                            "original_filename": original_filename
                        }
                        response = requests.post(f"{PDF_PROCESSOR_URL_ENV}/process_submission", json=payload,
                                                 timeout=180)
                        response.raise_for_status()
                        result_data = response.json()
                        ocr_doc_id_for_grading = result_data.get("exams_db_document_id")
                        st.success(f"Submission OCR processed! New Exams DB ID: {ocr_doc_id_for_grading}")
                        st.rerun()
                    except Exception as e_ocr:
                        st.error(f"Failed to trigger OCR processing: {e_ocr}")
                        if 'response' in locals() and response is not None:
                            st.error(f"PDF Processor Response ({response.status_code}): {response.text[:300]}")
            elif not gridfs_id_of_submission_to_process and enrollment_to_grade:  # Check if enrollment_to_grade is not None
                st.warning(f"No UI submission found for {enrollment_to_grade.student.name} to process for OCR.")

            if st.button("🤖 Grade with AI", key=f"ai_grade_btn_{selected_enrollment_id}",
                         disabled=is_completed or not ocr_doc_id_for_grading):
                if ocr_doc_id_for_grading:
                    st.info(f"Attempting AI Grading for Exams DB document ID: {ocr_doc_id_for_grading}...")
                    try:
                        grading_service_url = "http://grading-service:5002"
                        api_response = requests.post(f"{grading_service_url}/grade_document",
                                                     json={"document_id": ocr_doc_id_for_grading}, timeout=240)
                        api_response.raise_for_status()
                        grading_result = api_response.json()
                        st.success("AI Grading Complete!")

                        evaluation_text = grading_result.get("evaluation_result", "No evaluation text found.")
                        st.text_area("AI Evaluation:", value=evaluation_text, height=200, disabled=True,
                                     help="This is the raw evaluation from the AI.")
                        st.caption(f"Evaluated by: {grading_result.get('evaluation_by_model')}")

                    except Exception as api_e:
                        st.error(f"AI Grading API call failed: {api_e}")
                        if 'api_response' in locals() and api_response is not None:
                            st.error(f"Details: Status {api_response.status_code}, Body: {api_response.text[:300]}")
                        else:
                            st.error("No response from grading service or request failed before response.")
                else:
                    st.warning("Submission needs to be successfully OCR processed first to enable AI grading.")

            manual_grade_input = st.text_input("Manual Grade:", value=enrollment_to_grade.grade or "",
                                               key=f"manual_grade_{selected_enrollment_id}", disabled=is_completed)
            if st.button("Save Manual Grade", key=f"save_manual_grade_{selected_enrollment_id}", disabled=is_completed):
                new_grade_val = manual_grade_input.strip()
                enrollment_to_grade.grade = new_grade_val if new_grade_val else None
                try:
                    session.commit()
                    st.success(f"Manual grade '{new_grade_val if new_grade_val else 'cleared'}' saved.")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"DB Error saving grade: {e}")

    st.markdown("---")
    if st.button("Mark Course Completed", key=f"comp_crs_{course_obj.course_id}",
                 disabled=is_completed): course_obj.is_active = False; session.commit(); st.success(
        "Course marked completed."); st.rerun()
    if st.button("Reactivate Course", key=f"react_crs_{course_obj.course_id}",
                 disabled=not is_completed): course_obj.is_active = True; session.commit(); st.success(
        "Course reactivated."); st.rerun()


def _generate_student_course_page_layout(course_obj, enrollment_obj):
    uploader_session_key = f"hw_uploader_key_{course_obj.course_id}_{st.session_state.user_id}"
    if uploader_session_key not in st.session_state:
        st.session_state[uploader_session_key] = 0

    st.title(f"🎒 {course_obj.name} - Student View")
    st.write(f"Teacher: {course_obj.teacher.name if course_obj.teacher else 'N/A'}")
    st.write(f"Your Grade: {enrollment_obj.grade if enrollment_obj.grade else 'Not Graded Yet'}")
    is_course_completed_by_teacher = not course_obj.is_active
    if is_course_completed_by_teacher: st.info("This course is marked as completed by the teacher.")
    st.subheader("❓ Question Papers")
    qps = list(files_metadata_collection.find({"course_id": course_obj.course_id, "file_type": "question_paper"}).sort(
        "upload_timestamp", -1))
    if qps:
        for qp_meta in qps:
            st.markdown(f"- **{qp_meta['file_name']}**")
            if fs and qp_meta.get('gridfs_file_id'):
                try:
                    grid_out = fs.get(qp_meta['gridfs_file_id']); st.download_button("Download QP", grid_out.read(),
                                                                                     qp_meta['file_name'],
                                                                                     grid_out.content_type,
                                                                                     key=f"s_dl_qp_{qp_meta['_id']}")
                except:
                    pass
    else:
        st.info("No question papers available.")
    st.subheader("📚 Reference Materials")
    refs = list(
        files_metadata_collection.find({"course_id": course_obj.course_id, "file_type": "reference_material"}).sort(
            "upload_timestamp", -1))
    if refs:
        for ref_meta in refs:
            st.markdown(f"- **{ref_meta['file_name']}**")
            if fs and ref_meta.get('gridfs_file_id'):
                try:
                    grid_out = fs.get(ref_meta['gridfs_file_id']); st.download_button("Download Ref", grid_out.read(),
                                                                                      ref_meta['file_name'],
                                                                                      grid_out.content_type,
                                                                                      key=f"s_dl_ref_{ref_meta['_id']}")
                except:
                    pass
    else:
        st.info("No reference materials available.")
    st.markdown("---");
    st.subheader("📝 Submit Your Answer Sheet")
    existing_submission = files_metadata_collection.find_one(
        {"course_id": course_obj.course_id, "file_type": "student_answer_sheet",
         "student_id": st.session_state.user_id})
    if existing_submission:
        st.success(
            f"You submitted '{existing_submission['file_name']}' on {existing_submission['upload_timestamp']:%Y-%m-%d %H:%M}.")
        if fs and existing_submission.get('gridfs_file_id'):
            try:
                grid_out_own = fs.get(existing_submission['gridfs_file_id']); st.download_button(
                    "Download Your Submission", grid_out_own.read(), existing_submission['file_name'],
                    grid_out_own.content_type, key=f"s_dl_own_{existing_submission['_id']}")
            except:
                pass
    else:
        if is_course_completed_by_teacher:
            st.warning("Cannot submit homework as the course is completed.")
        else:
            hw_uploader_widget_key = f"hw_upload_{course_obj.course_id}_{st.session_state.user_id}_{st.session_state[uploader_session_key]}"
            uploaded_hw = st.file_uploader("Upload your PDF answer sheet:", type=["pdf"], key=hw_uploader_widget_key)
            if uploaded_hw and fs:
                try:
                    file_id = fs.put(uploaded_hw, filename=uploaded_hw.name, content_type=uploaded_hw.type)
                    hw_metadata = {"gridfs_file_id": file_id, "course_id": course_obj.course_id,
                                   "course_name": course_obj.name, "file_name": uploaded_hw.name,
                                   "file_type": "student_answer_sheet", "content_type_orig": uploaded_hw.type,
                                   "uploader_username": st.session_state.username,
                                   "student_id": st.session_state.user_id, "upload_timestamp": datetime.utcnow()}
                    files_metadata_collection.insert_one(hw_metadata)
                    st.success(f"Answer sheet '{uploaded_hw.name}' submitted successfully!", icon="✅");
                    st.session_state[uploader_session_key] += 1
                    st.info(
                        "Your submission is recorded. It needs to be processed by the OCR system before it can be graded by AI.");
                    st.rerun()
                except Exception as e:
                    st.error(f"Error submitting homework: {e}")


def create_teacher_course_page_callable(course_obj):
    def specific_teacher_course_page(): _generate_teacher_course_page_layout(course_obj)

    specific_teacher_course_page.__name__ = f"teacher_course_view_{course_obj.course_id}"
    return specific_teacher_course_page


def create_student_course_page_callable(course_obj, enrollment_obj):
    def specific_student_course_page(): _generate_student_course_page_layout(course_obj, enrollment_obj)

    specific_student_course_page.__name__ = f"student_course_view_{course_obj.course_id}"
    return specific_student_course_page


# --- Main Application Flow ---
if not st.session_state.logged_in:
    with st.container():
        st.title("Grading AI Portal")
        st.subheader("🔐 Sign up / Log in")
        choice = st.selectbox("Choose Action:", ["Login", "Sign Up"], key="main_login_signup_choice")
        form_username = st.text_input("Username", key="main_form_username")
        form_password = st.text_input("Password", type="password", key="main_form_password")
        if choice == "Sign Up":
            form_full_name = st.text_input("Full Name", key="main_form_full_name")
            form_role = st.selectbox("Select Role:", ["Teacher", "Student"], key="main_form_role")
            if st.button("Sign Up", key="main_signup_btn"):
                if form_username and form_password and form_full_name:
                    signup(form_username, form_password, form_role, form_full_name)
                else:
                    st.error("All fields are required for sign up.")
        elif choice == "Login":
            if st.button("Log In", key="main_login_btn"):
                if form_username and form_password:
                    login(form_username, form_password)
                else:
                    st.error("Username and password are required for login.")
else:
    st.sidebar.title(f"Welcome, {st.session_state.username}!")
    st.sidebar.caption(f"Role: {st.session_state.role}")

    navigation_config = {"Account": [profile_page_nav, logout_nav_page]}

    if st.session_state.role == "Teacher":
        user_id = st.session_state.user_id
        try:
            active_courses = session.query(Course).filter_by(teacher_id=user_id, is_active=True).order_by(
                Course.name).all()
            completed_courses = session.query(Course).filter_by(teacher_id=user_id, is_active=False).order_by(
                Course.name).all()
        except Exception as e:
            st.sidebar.error(f"DB error: {e}"); active_courses, completed_courses = [], []

        teacher_active_pages = [
            st.Page(create_teacher_course_page_callable(c), title=f"Active: {c.name} (TC{c.course_id})", icon="📖") for c
            in active_courses]
        teacher_completed_pages = [
            st.Page(create_teacher_course_page_callable(c), title=f"Done: {c.name} (TC{c.course_id})", icon="📘") for c
            in completed_courses]
        navigation_config["Manage Courses"] = [course_allocation_page_nav]
        if teacher_active_pages: navigation_config["Teacher Active Courses"] = teacher_active_pages
        if teacher_completed_pages: navigation_config["Teacher Completed Courses"] = teacher_completed_pages

    elif st.session_state.role == "Student":
        user_id = st.session_state.user_id
        try:
            enrollments = session.query(Enrollment).filter_by(student_id=user_id).all()
            student_active_course_pages = []
            student_completed_course_pages = []
            for enr in enrollments:
                if enr.course:
                    page_callable = create_student_course_page_callable(enr.course, enr)
                    page_title = f"{enr.course.name} (SC{enr.course.course_id})"
                    if enr.course.is_active:
                        student_active_course_pages.append(st.Page(page_callable, title=page_title, icon="📄"))
                    else:
                        student_completed_course_pages.append(st.Page(page_callable, title=page_title, icon="✅"))
        except Exception as e:
            st.sidebar.error(f"DB error loading student courses: {e}")
            student_active_course_pages, student_completed_course_pages = [], []
        navigation_config["My Learning Summary"] = [my_courses_page_nav,
                                                    grades_page_nav]  # Keep my_courses_page_nav for an overview
        if student_active_course_pages: navigation_config["My Active Courses"] = student_active_course_pages
        if student_completed_course_pages: navigation_config["My Completed Courses"] = student_completed_course_pages

    navigation_config["Tools"] = [settings_page_nav]
    pg = st.navigation(navigation_config)
    pg.run()