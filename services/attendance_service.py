"""
Attendance Service for Subject-Specific Classroom Attendance.

Supports on-demand attendance sessions tagged by subject, period, and date.
Provides quick batch marking, individual roll toggle, and styled Excel exports.
"""

from datetime import datetime
from pathlib import Path
from db.database import get_connection
from services.student_service import list_all_students

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

def add_subject(name, code=None, db_path=None):
    """Adds a new subject to the curriculum."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO subjects (name, code) VALUES (?, ?)",
        (name.strip(), code.strip() if code else None)
    )
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": sub_id, "name": name.strip(), "code": code}

def list_subjects(db_path=None):
    """Returns all available subjects."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, code FROM subjects ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_subject(subject_id, db_path=None):
    """Fetches a subject by ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, code FROM subjects WHERE id = ?", (int(subject_id),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_attendance_session(subject_id, date_str=None, period="Slot 1", created_by=None, class_name=None, db_path=None):
    """
    Creates a new attendance session for a subject and initializes
    all students in the class with default 'PRESENT' status.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO attendance_sessions (subject_id, date, period, created_by) VALUES (?, ?, ?, ?)",
        (int(subject_id), date_str, period, created_by)
    )
    session_id = cursor.lastrowid

    # Initialize all students as PRESENT
    students = list_all_students(class_name=class_name, db_path=db_path)
    records_to_insert = [(session_id, s["id"], "PRESENT", "") for s in students]
    cursor.executemany(
        "INSERT OR REPLACE INTO attendance_records (session_id, student_id, status, remarks) VALUES (?, ?, ?, ?)",
        records_to_insert
    )
    conn.commit()
    conn.close()
    return session_id

def update_student_attendance(session_id, student_id, status, remarks="", db_path=None):
    """Updates attendance status for a single student in a session."""
    valid_statuses = ("PRESENT", "ABSENT", "LEAVE")
    stat = status.upper().strip()
    if stat not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO attendance_records (session_id, student_id, status, remarks)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, student_id) DO UPDATE SET
            status = excluded.status,
            remarks = excluded.remarks
    """, (int(session_id), int(student_id), stat, remarks))
    conn.commit()
    conn.close()
    return {"session_id": session_id, "student_id": student_id, "status": stat}

def mark_absentees(session_id, absent_roll_numbers, db_path=None):
    """Quick helper: marks listed roll numbers as ABSENT, leaving others as PRESENT."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    for sid in absent_roll_numbers:
        cursor.execute("""
            UPDATE attendance_records SET status = 'ABSENT'
            WHERE session_id = ? AND student_id = ?
        """, (int(session_id), int(sid)))
    conn.commit()
    conn.close()

def get_session_details(session_id, db_path=None):
    """Fetches full attendance session info, counts, and student breakdown."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.id, a.date, a.period, a.created_at, s.id AS subject_id, s.name AS subject_name, s.code AS subject_code
        FROM attendance_sessions a
        JOIN subjects s ON a.subject_id = s.id
        WHERE a.id = ?
    """, (int(session_id),))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        return None

    sess = dict(session_row)

    # Get student attendance records
    cursor.execute("""
        SELECT st.id, st.name, COALESCE(st.class_name, 'EC') AS class_name,
               COALESCE(ar.status, 'PRESENT') AS status, COALESCE(ar.remarks, '') AS remarks
        FROM students st
        LEFT JOIN attendance_records ar ON ar.student_id = st.id AND ar.session_id = ?
        ORDER BY st.id ASC
    """, (int(session_id),))
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    present_count = sum(1 for r in records if r["status"] == "PRESENT")
    absent_count = sum(1 for r in records if r["status"] == "ABSENT")
    leave_count = sum(1 for r in records if r["status"] == "LEAVE")
    total = len(records)
    rate = (present_count / total * 100) if total > 0 else 0.0

    return {
        "session": sess,
        "total_students": total,
        "present_count": present_count,
        "absent_count": absent_count,
        "leave_count": leave_count,
        "attendance_rate_percent": round(rate, 1),
        "students": records,
    }

def list_attendance_sessions(subject_id=None, limit=20, db_path=None):
    """Lists recent attendance sessions."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = """
        SELECT a.id, a.date, a.period, a.created_at, s.name AS subject_name, s.code AS subject_code,
               COUNT(ar.student_id) AS total_enrolled,
               SUM(CASE WHEN ar.status = 'PRESENT' THEN 1 ELSE 0 END) AS present_count,
               SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END) AS absent_count,
               SUM(CASE WHEN ar.status = 'LEAVE' THEN 1 ELSE 0 END) AS leave_count
        FROM attendance_sessions a
        JOIN subjects s ON a.subject_id = s.id
        LEFT JOIN attendance_records ar ON a.id = ar.session_id
    """
    params = []
    if subject_id:
        query += " WHERE a.subject_id = ? "
        params.append(int(subject_id))
    query += " GROUP BY a.id ORDER BY a.id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def export_attendance_excel(session_id, output_path, db_path=None):
    """Generates a styled Excel spreadsheet (.xlsx) for an attendance session."""
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required to export attendance sheets.")

    details = get_session_details(session_id, db_path=db_path)
    if not details:
        raise ValueError(f"Attendance session #{session_id} not found.")

    sess = details["session"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Attendance_{sess['date']}"
    ws.views.sheetView[0].showGridLines = True

    # Styling Palette
    title_font = Font(name="Calibri", size=15, bold=True, color="1F4E78")
    subtitle_font = Font(name="Calibri", size=11, italic=True, color="595959")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    summary_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    present_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    present_font = Font(name="Calibri", size=11, bold=True, color="006100")

    absent_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    absent_font = Font(name="Calibri", size=11, bold=True, color="9C0006")

    leave_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    leave_font = Font(name="Calibri", size=11, bold=True, color="9C6500")

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # 1. Title & Header Info
    ws["A1"] = f"CLASSROOM ATTENDANCE RECORD - {sess['subject_name'].upper()}"
    ws["A1"].font = title_font
    ws["A2"] = f"Date: {sess['date']} | Period: {sess['period']} | Code: {sess['subject_code'] or 'N/A'}"
    ws["A2"].font = subtitle_font

    # 2. Metric Summary Box
    summary_items = [
        ("Total Students", details["total_students"], "Attendance Rate", f"{details['attendance_rate_percent']}%"),
        ("Present (Attended)", f"{details['present_count']} students", "Absent", f"{details['absent_count']} students"),
        ("Excused Leave", f"{details['leave_count']} students", "Session ID", f"#{sess['id']}"),
    ]
    for idx, (l1, v1, l2, v2) in enumerate(summary_items, start=4):
        ws[f"A{idx}"] = l1
        ws[f"B{idx}"] = v1
        ws[f"D{idx}"] = l2
        ws[f"E{idx}"] = v2

        ws[f"A{idx}"].font = bold_font
        ws[f"A{idx}"].fill = summary_fill
        ws[f"B{idx}"].font = regular_font
        ws[f"D{idx}"].font = bold_font
        ws[f"D{idx}"].fill = summary_fill
        ws[f"E{idx}"].font = regular_font

    # 3. Table Headers
    t_header_row = 8
    headers = ["Roll No", "Student Name", "Class", "Attendance Status", "Remarks"]
    for col_i, h in enumerate(headers, 1):
        c = ws.cell(row=t_header_row, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center" if col_i in [1, 3, 4] else "left")

    # 4. Table Rows
    curr_r = 9
    for s in details["students"]:
        ws.cell(row=curr_r, column=1, value=s["id"]).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_r, column=2, value=s["name"])
        ws.cell(row=curr_r, column=3, value=s.get("class_name", "EC")).alignment = Alignment(horizontal="center")

        stat_cell = ws.cell(row=curr_r, column=4, value=s["status"])
        stat_cell.alignment = Alignment(horizontal="center")

        if s["status"] == "PRESENT":
            stat_cell.fill = present_fill
            stat_cell.font = present_font
        elif s["status"] == "ABSENT":
            stat_cell.fill = absent_fill
            stat_cell.font = absent_font
        else:
            stat_cell.fill = leave_fill
            stat_cell.font = leave_font

        ws.cell(row=curr_r, column=5, value=s.get("remarks", ""))

        for c_i in range(1, 6):
            ws.cell(row=curr_r, column=c_i).border = thin_border
            if c_i != 4:
                ws.cell(row=curr_r, column=c_i).font = regular_font

        curr_r += 1

    ws.freeze_panes = f"A{t_header_row + 1}"

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return str(out.resolve())

