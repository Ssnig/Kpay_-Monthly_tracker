"""
Teacher Announcement & Interest RSVP Service.

Handles broadcasting official teacher notices and collecting participant signups/RSVPs.
"""

from db.database import get_connection
from services.student_service import get_student_by_id

def create_announcement(title, content, max_slots=0, db_path=None):
    """Creates a new teacher announcement / signup campaign."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcements (title, content, max_slots, is_active)
        VALUES (?, ?, ?, 1)
    """, (title.strip(), content.strip(), max(0, int(max_slots))))
    ann_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ann_id

def list_active_announcements(limit=10, db_path=None):
    """Returns active announcements with current signup counts."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.title, a.content, a.max_slots, a.is_active, a.created_at,
               COUNT(r.student_id) AS rsvp_count
        FROM announcements a
        LEFT JOIN announcement_rsvps r ON a.id = r.announcement_id
        WHERE a.is_active = 1
        GROUP BY a.id
        ORDER BY a.id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_announcement_details(announcement_id, db_path=None):
    """Fetches full announcement info and the list of signed-up students."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, content, max_slots, is_active, created_at
        FROM announcements WHERE id = ?
    """, (int(announcement_id),))
    ann_row = cursor.fetchone()
    if not ann_row:
        conn.close()
        return None

    ann = dict(ann_row)

    cursor.execute("""
        SELECT r.student_id, r.telegram_user_id, r.signed_up_at, s.name, COALESCE(s.class_name, 'EC') AS class_name
        FROM announcement_rsvps r
        JOIN students s ON r.student_id = s.id
        WHERE r.announcement_id = ?
        ORDER BY r.signed_up_at ASC
    """, (int(announcement_id),))
    rsvps = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_rsvps = len(rsvps)
    max_s = ann["max_slots"]
    is_full = (max_s > 0 and total_rsvps >= max_s)

    return {
        "announcement": ann,
        "rsvp_count": total_rsvps,
        "max_slots": max_s,
        "is_full": is_full,
        "participants": rsvps
    }

def rsvp_student(announcement_id, student_id, telegram_user_id=None, db_path=None):
    """Signs up a student for an announcement."""
    details = get_announcement_details(announcement_id, db_path=db_path)
    if not details:
        raise ValueError(f"Announcement #{announcement_id} does not exist.")

    if not details["announcement"]["is_active"]:
        raise ValueError("This announcement is closed and no longer accepting sign-ups.")

    # Check if already signed up
    existing = any(p["student_id"] == int(student_id) for p in details["participants"])
    if existing:
        return {"status": "ALREADY_REGISTERED", "message": "You are already signed up for this event."}

    # Check slot limit
    if details["is_full"]:
        raise ValueError(f"All {details['max_slots']} available slots have been filled.")

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcement_rsvps (announcement_id, student_id, telegram_user_id)
        VALUES (?, ?, ?)
    """, (int(announcement_id), int(student_id), telegram_user_id))
    conn.commit()
    conn.close()

    student = get_student_by_id(student_id, db_path=db_path)
    return {
        "status": "SUCCESS",
        "student_id": int(student_id),
        "student_name": student["name"] if student else "Unknown",
        "message": "Successfully signed up!"
    }

def withdraw_rsvp(announcement_id, student_id, db_path=None):
    """Removes a student's RSVP."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM announcement_rsvps
        WHERE announcement_id = ? AND student_id = ?
    """, (int(announcement_id), int(student_id)))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def close_announcement(announcement_id, db_path=None):
    """Closes an announcement so no more sign-ups can be added."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE announcements SET is_active = 0 WHERE id = ?", (int(announcement_id),))
    conn.commit()
    conn.close()
    return True

