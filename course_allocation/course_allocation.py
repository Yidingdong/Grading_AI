from flask import Flask, request
from flask_restful import Resource, Api
import mysql.connector

app = Flask(__name__)
api = Api(app)

db_config = {
    'user': 'user',
    'password': 'password',
    'host': 'mysql-server',
    'database': 'Informations',
    'auth_plugin': 'mysql_native_password'
}


def create_courses_tables():
    """Create courses and student-course mapping tables"""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            course_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            duration_weeks INT,
            teacher_id INT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_course (
            student_id INT,
            course_id INT,
            PRIMARY KEY (student_id, course_id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(course_id)
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()


class CourseCreation(Resource):
    def post(self):
        data = request.get_json()

        required_fields = ['name', 'teacher_id']
        if not all(field in data for field in required_fields):
            return {'message': 'Missing required fields'}, 400

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
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()


class StudentAssignment(Resource):
    def put(self, course_id):
        data = request.get_json()

        if 'student_ids' not in data or not isinstance(data['student_ids'], list):
            return {'message': 'Invalid student_ids format'}, 400

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
            conn.rollback()
            return {'message': f'Database error: {err}'}, 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()


create_courses_tables()
api.add_resource(CourseCreation, '/courses')
api.add_resource(StudentAssignment, '/courses/<int:course_id>/students')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)