from db.database import get_connection

def get_student_by_id(student_id, db_path=None):
    """Fetches a student by their ID/roll number."""
    try:
        sid = int(student_id)
    except (ValueError, TypeError):
        return None

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students WHERE id = ?", (sid,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def list_all_students(db_path=None):
    """Returns a list of all students ordered by ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def search_students(query_str, db_path=None):
    """Searches students by name substring or exact ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    like_query = f"%{query_str}%"
    cursor.execute(
        "SELECT id, name FROM students WHERE CAST(id AS TEXT) LIKE ? OR name LIKE ? ORDER BY id ASC",
        (like_query, like_query)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
