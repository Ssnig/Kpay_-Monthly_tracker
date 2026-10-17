import sqlite3
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "ec_money.db"
ROLLNUM_JSON_PATH = BASE_DIR / "rollnum.json"

def get_connection(db_path=None):
    """Returns a SQLite connection with row_factory set to sqlite3.Row."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path=None, seed_students=True):
    """Initializes tables and optionally seeds students from rollnum.json."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Students table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """)

    # Fees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        amount_per_student REAL NOT NULL,
        due_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Payments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fee_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        amount_paid REAL NOT NULL,
        paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        remarks TEXT,
        FOREIGN KEY (fee_id) REFERENCES fees (id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
    );
    """)

    # Expenses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT,
        spent_by TEXT,
        date TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()

    if seed_students:
        seed_students_from_json(conn)

    conn.close()

def seed_students_from_json(conn, json_path=None):
    """Seeds the students table from rollnum.json if the table is empty."""
    target_json = json_path if json_path is not None else ROLLNUM_JSON_PATH
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM students")
    count = cursor.fetchone()["count"]

    if count == 0 and os.path.exists(target_json):
        with open(target_json, "r", encoding="utf-8") as f:
            students = json.load(f)
            for student in students:
                cursor.execute(
                    "INSERT OR IGNORE INTO students (id, name) VALUES (?, ?)",
                    (student["id"], student["name"])
                )
        conn.commit()
