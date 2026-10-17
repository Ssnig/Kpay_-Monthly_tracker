from datetime import datetime
from db.database import get_connection

def create_fee(title, amount_per_student, due_date=None, db_path=None):
    """Creates a new fee / dues campaign."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO fees (title, amount_per_student, due_date) VALUES (?, ?, ?)",
        (title.strip(), float(amount_per_student), due_date)
    )
    fee_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return fee_id

def list_fees(db_path=None):
    """Returns all fees ordered by creation time descending."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount_per_student, due_date, created_at FROM fees ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_fee(fee_id, db_path=None):
    """Fetches a single fee by ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount_per_student, due_date, created_at FROM fees WHERE id = ?", (fee_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def record_payment(fee_id, student_id, amount_paid, remarks="", db_path=None):
    """Records a payment by a student for a specific fee."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Validate fee exists
    cursor.execute("SELECT id FROM fees WHERE id = ?", (fee_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"Fee ID {fee_id} does not exist.")

    # Validate student exists
    cursor.execute("SELECT id FROM students WHERE id = ?", (student_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"Student ID {student_id} does not exist.")

    cursor.execute(
        "INSERT INTO payments (fee_id, student_id, amount_paid, remarks) VALUES (?, ?, ?, ?)",
        (fee_id, student_id, float(amount_paid), remarks.strip() if remarks else "")
    )
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return payment_id

def get_fee_status(fee_id, db_path=None):
    """Calculates comprehensive payment tracking status for a specific fee."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, amount_per_student, due_date, created_at FROM fees WHERE id = ?", (fee_id,))
    fee_row = cursor.fetchone()
    if not fee_row:
        conn.close()
        return None

    fee = dict(fee_row)
    target_amount = fee["amount_per_student"]

    # Get all students
    cursor.execute("SELECT id, name FROM students ORDER BY id ASC")
    students = [dict(r) for r in cursor.fetchall()]

    # Aggregate payments per student for this fee
    cursor.execute("""
        SELECT student_id, SUM(amount_paid) AS total_paid
        FROM payments
        WHERE fee_id = ?
        GROUP BY student_id
    """, (fee_id,))
    payments_map = {row["student_id"]: row["total_paid"] for row in cursor.fetchall()}
    conn.close()

    total_expected = target_amount * len(students)
    total_collected = sum(payments_map.values())
    
    student_records = []
    paid_count = 0
    partial_count = 0
    unpaid_count = 0

    for s in students:
        paid = payments_map.get(s["id"], 0.0)
        remaining = max(0.0, target_amount - paid)
        if paid >= target_amount:
            status = "PAID"
            paid_count += 1
        elif paid > 0:
            status = "PARTIAL"
            partial_count += 1
        else:
            status = "UNPAID"
            unpaid_count += 1

        student_records.append({
            "id": s["id"],
            "name": s["name"],
            "amount_paid": paid,
            "remaining": remaining,
            "status": status
        })

    collection_rate = (total_collected / total_expected * 100) if total_expected > 0 else 0.0

    return {
        "fee": fee,
        "total_students": len(students),
        "target_amount_per_student": target_amount,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "collection_rate_percent": round(collection_rate, 2),
        "paid_count": paid_count,
        "partial_count": partial_count,
        "unpaid_count": unpaid_count,
        "students": student_records
    }

def add_expense(title, amount, category="General", spent_by="", date_str=None, notes="", db_path=None):
    """Records an expense in the treasury."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO expenses (title, amount, category, spent_by, date, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (title.strip(), float(amount), category.strip(), spent_by.strip(), date_str, notes.strip())
    )
    expense_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return expense_id

def list_expenses(db_path=None):
    """Returns all expenses ordered by date/ID descending."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount, category, spent_by, date, notes, created_at FROM expenses ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_financial_summary(db_path=None):
    """Calculates overall treasury health: total income, total expenses, net balance."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(SUM(amount_paid), 0) AS total_income FROM payments")
    total_income = cursor.fetchone()["total_income"]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total_expenses FROM expenses")
    total_expenses = cursor.fetchone()["total_expenses"]

    cursor.execute("SELECT COUNT(*) AS fee_count FROM fees")
    fee_count = cursor.fetchone()["fee_count"]

    cursor.execute("SELECT COUNT(*) AS expense_count FROM expenses")
    expense_count = cursor.fetchone()["expense_count"]

    cursor.execute("SELECT COUNT(*) AS student_count FROM students")
    student_count = cursor.fetchone()["student_count"]

    conn.close()

    net_balance = total_income - total_expenses

    return {
        "student_count": student_count,
        "fee_count": fee_count,
        "expense_count": expense_count,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": net_balance
    }
