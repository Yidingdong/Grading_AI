import streamlit as st
import pandas as pd
import os

st.title("⚙️ Application Settings")

st.subheader("Environment Variables Visible to Frontend:")
env_vars = {
    "MYSQL_HOST": os.getenv("MYSQL_HOST"),
    "MYSQL_USER": os.getenv("MYSQL_USER"),
    "MYSQL_DATABASE": os.getenv("MYSQL_DATABASE"),
    "MONGO_HOST": os.getenv("MONGO_HOST"),
    "MONGO_USER_FRONTEND": os.getenv("MONGO_USER_FRONTEND"),
    "MONGO_DB_NAME_FRONTEND": os.getenv("MONGO_DB_NAME_FRONTEND"),
    "MONGO_FILES_COLLECTION_FRONTEND": os.getenv("MONGO_FILES_COLLECTION_FRONTEND"),
    "STREAMLIT_SERVER_ADDRESS": os.getenv("STREAMLIT_SERVER_ADDRESS"),
    "STREAMLIT_SERVER_PORT": os.getenv("STREAMLIT_SERVER_PORT"),
    "PDF_PROCESSOR_URL": os.getenv("PDF_PROCESSOR_URL")
}
st.table(pd.DataFrame(list(env_vars.items()), columns=["Variable", "Value"]))

st.info("These settings are primarily for display and debugging. Database passwords are not shown.")

if st.button("Test Database Connections (from Frontend perspective)",
             key="settings_test_db_conn_btn"):  # Added unique key
    from frontendData import session as new_session_instance_func, User  # Use the sessionmaker

    # It's better to create a new session for such tests
    test_session = new_session_instance_func()

    try:
        user_count = test_session.query(User).count()
        st.success(f"MySQL Connection OK. Found {user_count} users.")
    except Exception as e:
        st.error(f"MySQL Connection Test FAILED: {e}")
    finally:
        test_session.close()

    try:
        MONGO_URI_TEST = f"mongodb://{os.getenv('MONGO_USER_FRONTEND', 'root')}:{os.getenv('MONGO_PASSWORD_FRONTEND', 'example')}@{os.getenv('MONGO_HOST', 'mongodb-server')}:27017/?authSource=admin&serverSelectionTimeoutMS=3000"
        client_test = MongoClient(MONGO_URI_TEST)  # serverSelectionTimeoutMS in URI
        client_test.admin.command('ping')
        st.success(
            f"MongoDB Connection OK (DB: {os.getenv('MONGO_DB_NAME_FRONTEND')}, Collection: {os.getenv('MONGO_FILES_COLLECTION_FRONTEND')}).")
        client_test.close()
    except Exception as e:
        st.error(f"MongoDB Connection Test FAILED: {e}")