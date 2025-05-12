from flask import Flask, request, jsonify
from flask_restful import Resource, Api
import mysql.connector
import bcrypt

app = Flask(__name__)
api = Api(app)

db_config = {
    'user': 'user',
    'password': 'password',
    'host': 'mysql-server',
    'database': 'Informations',
    'auth_plugin': 'mysql_native_password'
}

@app.route('/health')
def health_check():
    return jsonify({"status": "ok"}), 200

def create_users_table():
    conn = None
    cursor = None
    try:
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
        print("[Register Service] 'users' table checked/created.")
    except mysql.connector.Error as err:
        print(f"[Register Service] Error creating users table: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
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

        conn = None
        cursor = None
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
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

print("[Register Service] Creating users table...")
create_users_table()
print("[Register Service] Starting Flask app...")

api.add_resource(Registration, '/register')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)