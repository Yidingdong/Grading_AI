from flask import Flask, request
from flask_restful import Resource, Api
import mysql.connector
import bcrypt
import time

def create_users_table():
    max_retries = 5
    retry_delay = 5  # seconds
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(**db_config)
            # ... rest of code ...
            return  # Exit on success
        except mysql.connector.Error as err:
            print(f"Connection failed (attempt {attempt + 1}/{max_retries}): {err}")
            time.sleep(retry_delay)
    raise RuntimeError("Failed to connect to MySQL after multiple attempts")
app = Flask(__name__)
api = Api(app)

db_config = {
    'user': 'user',
    'password': 'password',
    'host': 'mysql-server',
    'database': 'Informations',
    'auth_plugin': 'mysql_native_password'
}


def create_users_table():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            user_type ENUM('student', 'teacher') NOT NULL
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()



class Registration(Resource):
    def post(self):
        data = request.get_json()

        required_fields = ['username', 'password', 'name', 'user_type']
        if not all(field in data for field in required_fields):
            return {'message': 'Missing required fields'}, 400

        password_hash = bcrypt.hashpw(
            data['password'].encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users 
                (username, password_hash, name, user_type)
                VALUES (%s, %s, %s, %s)
            ''', (data['username'], password_hash,
                  data['name'], data['user_type']))
            conn.commit()
            return {'message': 'Registration successful'}, 201
        except mysql.connector.Error as err:
            return {'message': f'Database error: {err}'}, 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()


create_users_table()
api.add_resource(Registration, '/register')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)