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
        name TEXT NOT NULL,
        class_name TEXT DEFAULT 'EC'
    );
    """)

    # Migration: check if class_name exists in students table
    cursor.execute("PRAGMA table_info(students)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "class_name" not in columns:
        cursor.execute("ALTER TABLE students ADD COLUMN class_name TEXT DEFAULT 'EC';")

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

    # Subjects table (for attendance & assignments)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        code TEXT
    );
    """)

    # Attendance sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        period TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
    );
    """)

    # Attendance records table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_records (
        session_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status TEXT CHECK(status IN ('PRESENT', 'ABSENT', 'LEAVE')) DEFAULT 'PRESENT',
        remarks TEXT,
        PRIMARY KEY (session_id, student_id),
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)

    # Teacher announcements table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        max_slots INTEGER DEFAULT 0,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Announcement RSVPs / Interest signups table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcement_rsvps (
        announcement_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        telegram_user_id INTEGER,
        signed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (announcement_id, student_id),
        FOREIGN KEY (announcement_id) REFERENCES announcements(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)

    # KPay receipt verification table (deduplication & tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpay_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT UNIQUE NOT NULL,
        student_id INTEGER,
        fee_id INTEGER,
        payment_id INTEGER,
        payer_name TEXT,
        amount REAL NOT NULL,
        slip_timestamp TEXT,
        verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        raw_ai_response TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL,
        FOREIGN KEY (fee_id) REFERENCES fees(id) ON DELETE SET NULL,
        FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE SET NULL
    );
    """)

    # Seed default university subjects if empty
    cursor.execute("SELECT COUNT(*) AS count FROM subjects")
    if cursor.fetchone()["count"] == 0:
        default_subs = [
            ("Digital Signal Processing", "DSP"),
            ("Microcontrollers & Embedded Systems", "MCU"),
            ("Communication Systems", "COMM"),
            ("Electronic Circuits", "EC"),
            ("Control Systems", "CS"),
            ("Professional English", "ENG"),
        ]
        cursor.executemany("INSERT OR IGNORE INTO subjects (name, code) VALUES (?, ?)", default_subs)

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
