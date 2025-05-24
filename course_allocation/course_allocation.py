from flask import Flask, request, jsonify
from flask_restful import Resource, Api
import mysql.connector
import time
import logging

app = Flask(__name__)
api = Api(app)

db_config = {
    'user': 'user',
    'password': 'password',
    'host': 'mysql-server',
    'database': 'Informations',
    'auth_plugin': 'mysql_native_password'
}

MAX_DB_CONNECTION_ATTEMPTS = 15
DB_RETRY_DELAY_SECONDS = 4


def _consume_results(cursor):
    """Helper to consume any existing results on a cursor."""
    try:
        # Fetch all results from the current executed statement
        if cursor.description:  # Check if there's a description (i.e., it was a query)
            cursor.fetchall()

            # Check for and consume more result sets if any
        while cursor.nextset():
            if cursor.description:
                cursor.fetchall()
    except mysql.connector.Error as e:
        # Log error during consumption, but don't let it break the main flow
        app.logger.debug(f"Error while consuming results: {e}")


@app.route('/health')
def health_check():
    for attempt in range(MAX_DB_CONNECTION_ATTEMPTS):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            # Just before executing, see if consuming helps (though less likely for a new conn)
            # _consume_results(cursor) # Probably not needed here for a fresh connection

            cursor.execute("SELECT 1")
            _consume_results(cursor)  # Consume results of SELECT 1

            cursor.close()
            cursor = None  # Mark as closed
            conn.close()
            conn = None  # Mark as closed
            return jsonify({"status": "ok", "message": "Course Allocation service is healthy"}), 200
        except mysql.connector.Error as err:
            app.logger.warning(
                f"Health check DB connection attempt {attempt + 1}/{MAX_DB_CONNECTION_ATTEMPTS} failed: {err}")
            if cursor:
                try:
                    cursor.close()
                except Exception as e_cur:
                    app.logger.debug(f"Error closing cursor in health_check exception: {e_cur}")
            if conn:
                try:
                    conn.close()
                except Exception as e_conn:
                    app.logger.debug(f"Error closing connection in health_check exception: {e_conn}")

            if attempt < MAX_DB_CONNECTION_ATTEMPTS - 1:
                time.sleep(DB_RETRY_DELAY_SECONDS)
            else:
                app.logger.error(f"Health check failed after {MAX_DB_CONNECTION_ATTEMPTS} attempts. Last error: {err}")
                return jsonify({"status": "error",
                                "message": f"Course Allocation service database error after retries: {err}"}), 503
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass  # Already tried
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass  # Already tried

    return jsonify({"status": "error", "message": "Health check exhausted attempts unexpectedly."}), 503


def create_courses_tables():
    for attempt in range(MAX_DB_CONNECTION_ATTEMPTS):
        conn = None
        cursor = None
        try:
            app.logger.info(
                f"Attempting to connect to DB for table creation (attempt {attempt + 1}/{MAX_DB_CONNECTION_ATTEMPTS})")
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            ddl_statements = [
                '''
                CREATE TABLE IF NOT EXISTS courses (
                    course_id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    duration_weeks INT,
                    teacher_id INT NOT NULL,
                    FOREIGN KEY (teacher_id) REFERENCES users(id)
                )
                ''',
                '''
                CREATE TABLE IF NOT EXISTS student_course (
                    student_id INT,
                    course_id INT,
                    PRIMARY KEY (student_id, course_id),
                    FOREIGN KEY (student_id) REFERENCES users(id),
                    FOREIGN KEY (course_id) REFERENCES courses(course_id)
                )
                '''
            ]

            for stmt in ddl_statements:
                cursor.execute(stmt)
                _consume_results(cursor)  # Consume any results/status from DDL

            conn.commit()

            cursor.close()
            cursor = None
            conn.close()
            conn = None
            app.logger.info("Database tables checked/created successfully.")
            return
        except mysql.connector.Error as err:
            app.logger.warning(
                f"Table creation DB connection attempt {attempt + 1}/{MAX_DB_CONNECTION_ATTEMPTS} failed: {err}")
            if cursor:
                try:
                    cursor.close()
                except Exception as e_cur:
                    app.logger.debug(f"Error closing cursor in create_courses_tables exception: {e_cur}")
            if conn:
                try:
                    conn.close()
                except Exception as e_conn:
                    app.logger.debug(f"Error closing connection in create_courses_tables exception: {e_conn}")

            if attempt < MAX_DB_CONNECTION_ATTEMPTS - 1:
                time.sleep(DB_RETRY_DELAY_SECONDS)
            else:
                app.logger.error(
                    f"Failed to create tables after {MAX_DB_CONNECTION_ATTEMPTS} attempts. Last error: {err}")
                raise RuntimeError(f"Could not connect to database for table creation after multiple retries: {err}")
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# ... (Rest of the file: CourseCreation, StudentAssignment classes, api.add_resource calls, logging setup, and __main__)
# is the same as before. I'll include it for completeness.

class CourseCreation(Resource):
    def post(self):
        data = request.get_json()
        required_fields = ['name', 'teacher_id']
        if not all(field in data for field in required_fields):
            return {'message': 'Missing required fields'}, 400
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO courses (name, duration_weeks, teacher_id)
                VALUES (%s, %s, %s)
            ''', (data['name'], data.get('duration_weeks', 12), data['teacher_id']))
            course_id = cursor.lastrowid
            conn.commit()
            return {'message': 'Course created', 'course_id': course_id}, 201
        except mysql.connector.Error as err:
            return {'message': f'Database error: {err}'}, 500
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()


class StudentAssignment(Resource):
    def put(self, course_id):
        data = request.get_json()
        if 'student_ids' not in data or not isinstance(data['student_ids'], list):
            return {'message': 'Invalid student_ids format'}, 400
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM student_course 
                WHERE course_id = %s
            ''', (course_id,))
            for student_id in data['student_ids']:
                cursor.execute('''
                    INSERT INTO student_course (student_id, course_id)
                    VALUES (%s, %s)
                ''', (student_id, course_id))
            conn.commit()
            return {'message': 'Students assigned successfully'}, 200
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            return {'message': f'Database error: {err}'}, 500
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()


if not app.debug and not app.testing:
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

create_courses_tables()
api.add_resource(CourseCreation, '/courses')
api.add_resource(StudentAssignment, '/courses/<int:course_id>/students')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)