const sqlite3 = require('sqlite3').verbose();

// Open (or create if not exists) a database file
const db = new sqlite3.Database('mydatabase.db', (err) => {
    if (err) {
        console.error('Error opening database:', err.message);
    } else {
        console.log('Connected to SQLite database.');
    }
});

// Create a table (if not exists)
db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT
)`, (err) => {
    if (err) {
        console.error('Error creating table:', err.message);
    } else {
        console.log('Users table is ready.');
    }
});

// Insert a new user
db.run(`INSERT INTO users (name, email) VALUES (?, ?)`, ['John Doe', 'john@example.com'], function(err) {
    if (err) {
        console.error('Error inserting data:', err.message);
    } else {
        console.log(`Inserted user with ID: ${this.lastID}`);
    }
});

// Retrieve all users
db.all(`SELECT * FROM users`, [], (err, rows) => {
    if (err) {
        console.error('Error retrieving users:', err.message);
    } else {
        console.log('Users:', rows);
    }
});

// Close the database connection
db.close((err) => {
    if (err) {
        console.error('Error closing database:', err.message);
    } else {
        console.log('Database connection closed.');
    }
});
