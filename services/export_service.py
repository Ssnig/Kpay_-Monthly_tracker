import csv
from pathlib import Path
from services.treasury_service import get_fee_status, get_financial_summary, list_expenses

def export_fee_report_csv(fee_id, output_path, db_path=None):
    """Exports student payment breakdown for a fee to a CSV file."""
    status = get_fee_status(fee_id, db_path=db_path)
    if not status:
        raise ValueError(f"Fee with ID {fee_id} not found.")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["EC Money Management - Fee Collection Report"])
        writer.writerow(["Fee Title", status["fee"]["title"]])
        writer.writerow(["Target Amount Per Student", status["target_amount_per_student"]])
        writer.writerow(["Total Students", status["total_students"]])
        writer.writerow(["Total Expected", status["total_expected"]])
        writer.writerow(["Total Collected", status["total_collected"]])
        writer.writerow(["Collection Rate", f"{status['collection_rate_percent']}%"])
        writer.writerow(["Paid Students", status["paid_count"]])
        writer.writerow(["Partial Students", status["partial_count"]])
        writer.writerow(["Unpaid Students", status["unpaid_count"]])
        writer.writerow([])
        writer.writerow(["Roll Number", "Student Name", "Amount Paid", "Remaining Due", "Status"])

        for s in status["students"]:
            writer.writerow([s["id"], s["name"], s["amount_paid"], s["remaining"], s["status"]])

    return str(out.resolve())

def export_financial_summary_csv(output_path, db_path=None):
    """Exports high-level financial summary and recent expenses to CSV."""
    summary = get_financial_summary(db_path=db_path)
    expenses = list_expenses(db_path=db_path)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["EC Money Management - Financial Summary"])
        writer.writerow(["Total Students", summary["student_count"]])
        writer.writerow(["Total Income (Collected)", summary["total_income"]])
        writer.writerow(["Total Expenses", summary["total_expenses"]])
        writer.writerow(["Net Cash Balance", summary["net_balance"]])
        writer.writerow([])
        writer.writerow(["--- Expense Log ---"])
        writer.writerow(["ID", "Title", "Amount", "Category", "Spent By", "Date", "Notes"])
        for exp in expenses:
            writer.writerow([exp["id"], exp["title"], exp["amount"], exp["category"], exp["spent_by"], exp["date"], exp["notes"]])

    return str(out.resolve())
