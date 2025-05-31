# HLRS - Grading AI

HLRS - Grading AI is a web-based application for managing courses, students, and grades. It allows teachers to allocate courses, evaluate students, and manage active/completed courses. Students can view their grades and enrolled courses.

---

## Installation

To set up the application, follow these steps:

### Prerequisites
Ensure you have Python installed on your system. You can download it from [python.org](https://www.python.org/).

### Install Required Libraries
Run the following commands in your terminal to install the necessary Python libraries:
```bash
pip install streamlit
pip install pandas
pip install sqlalchemy
pip install streamlit_authenticator
pip install pymongo
```

---

## Getting Started

### Step 1: Activate the Virtual Environment (Optional)
If you are using a virtual environment, activate it:
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
./webpage/Scripts/activate
```

### Step 2: Run the Application
Start the Streamlit application by running:
```bash
streamlit run src/Start.py
```

---

## How to Use the Application

### 1. **Sign Up**
- On the login page, select "sign up" from the dropdown.
- Enter a username, password, and select a role (`Teacher` or `Student`).
- Click the "Sign up" button.
- A success message will appear, prompting you to log in.

> **Note:** Teachers must ensure that multiple students are signed up before attempting to allocate courses. Without registered students, the "Select Students" dropdown will be empty.

### 2. **Log In**
- On the login page, select "login" from the dropdown.
- Enter your username and password.
- Click the "Log in" button to access your dashboard.

### 3. **Teacher Dashboard**
- **Allocate Courses**:
  - Navigate to the "Course Allocation" page.
  - Enter a course name and select students from the list.
  - Click "Allocate Course" to create the course and enroll the selected students.
- **Manage Courses**:
  - View active and completed courses.
  - Click on a course to manage it (e.g., upload materials, evaluate students, mark as completed).

### 4. **Student Dashboard**
- **View Grades**:
  - Navigate to the "Grades" page to view your grades for enrolled courses.

---

## Features

### For Teachers:
- Allocate courses to students.
- Manage active and completed courses.
- Evaluate students and assign grades.

### For Students:
- View grades for enrolled courses.

---

## Database
The application uses SQLite as the database. The database file (`grading_ai.db`) is automatically created and populated with dummy data when the application starts.

---

## Troubleshooting
- If you encounter issues with missing dependencies, ensure all required libraries are installed using `pip install`.
- If the application does not start, verify that Python is installed and accessible from the terminal.

---

