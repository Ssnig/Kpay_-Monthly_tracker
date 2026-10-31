from db.database import get_connection

def add_or_update_student(student_id, name, class_name="EC", db_path=None):
    """Adds a new student or updates existing student info including class."""
    sid = int(student_id)
    cname = (class_name or "EC").strip()
    sname = name.strip()

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO students (id, name, class_name)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            class_name = excluded.class_name
    """, (sid, sname, cname))
    conn.commit()
    conn.close()
    return {"id": sid, "name": sname, "class_name": cname}

def get_student_by_id(student_id, db_path=None):
    """Fetches a student by their ID/roll number."""
    try:
        sid = int(student_id)
    except (ValueError, TypeError):
        return None

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, COALESCE(class_name, 'EC') AS class_name FROM students WHERE id = ?", (sid,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def list_all_students(class_name=None, db_path=None):
    """Returns a list of students ordered by ID, optionally filtered by class."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if class_name:
        cursor.execute(
            "SELECT id, name, COALESCE(class_name, 'EC') AS class_name FROM students WHERE LOWER(class_name) = LOWER(?) ORDER BY id ASC",
            (class_name.strip(),)
        )
    else:
        cursor.execute("SELECT id, name, COALESCE(class_name, 'EC') AS class_name FROM students ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def list_classes(db_path=None):
    """Returns a list of unique class names with their student counts."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(class_name, 'EC') AS class_name, COUNT(*) AS student_count
        FROM students
        GROUP BY COALESCE(class_name, 'EC')
        ORDER BY class_name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def search_students(query_str, class_name=None, db_path=None):
    """Searches students by name substring or exact ID, optionally in a class."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    like_query = f"%{query_str}%"
    if class_name:
        cursor.execute(
            """SELECT id, name, COALESCE(class_name, 'EC') AS class_name 
               FROM students 
               WHERE (CAST(id AS TEXT) LIKE ? OR name LIKE ?) AND LOWER(class_name) = LOWER(?)
               ORDER BY id ASC""",
            (like_query, like_query, class_name.strip())
        )
    else:
        cursor.execute(
            """SELECT id, name, COALESCE(class_name, 'EC') AS class_name 
               FROM students 
               WHERE CAST(id AS TEXT) LIKE ? OR name LIKE ? 
               ORDER BY id ASC""",
            (like_query, like_query)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
