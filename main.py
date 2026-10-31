"""EC Money Management - Main Application.

Provides an interactive CLI for managing class funds, dues, payments,
and expenses for the Electronics & Communication (EC) batch.
"""

import sys
from db.database import init_db
from services.student_service import (
    get_student_by_id,
    list_all_students,
    search_students,
    add_or_update_student,
    list_classes,
)
from services.treasury_service import (
    create_fee,
    list_fees,
    get_fee,
    record_payment,
    get_fee_status,
    add_expense,
    list_expenses,
    get_financial_summary
)
from services.export_service import (
    export_fee_report_csv,
    export_financial_summary_csv,
    export_fee_status_excel,
    export_full_excel_workbook,
)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

def print_table(headers, rows):
    """Renders tabular data cleanly."""
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="grid"))
    else:
        # Fallback simple formatter
        print(" | ".join(str(h) for h in headers))
        print("-" * 50)
        for r in rows:
            print(" | ".join(str(c) for c in r))

def prompt_menu_choice(prompt_text="Enter your choice: "):
    return input(f"\n{prompt_text}").strip()

# --- Feature Handlers ---

def handle_students_menu():
    """Sub-menu for student directory."""
    while True:
        print("\n=== STUDENT DIRECTORY ===")
        print("1. List All Students")
        print("2. Filter Students by Class")
        print("3. Search Student by Roll or Name")
        print("4. Add / Register Student Entry for a Class")
        print("0. Back to Main Menu")

        choice = prompt_menu_choice()
        if choice == "1":
            students = list_all_students()
            rows = [[s["id"], s["name"], s.get("class_name", "EC")] for s in students]
            print(f"\nTotal Students: {len(students)}")
            print_table(["Roll No", "Student Name", "Class"], rows)
        elif choice == "2":
            classes = list_classes()
            if not classes:
                print("No classes found.")
                continue
            print("\nAvailable Classes:")
            for idx, c in enumerate(classes, 1):
                print(f"{idx}. {c['class_name']} ({c['student_count']} students)")
            c_input = input("Enter class name: ").strip()
            if not c_input:
                continue
            students = list_all_students(class_name=c_input)
            if not students:
                print(f"No students found in class '{c_input}'.")
            else:
                rows = [[s["id"], s["name"], s.get("class_name", "EC")] for s in students]
                print(f"\nStudents in {c_input} ({len(students)} total):")
                print_table(["Roll No", "Student Name", "Class"], rows)
        elif choice == "3":
            q = input("Enter roll number or partial name: ").strip()
            if not q:
                continue
            results = search_students(q)
            if not results:
                print("No students matched your search.")
            else:
                rows = [[s["id"], s["name"], s.get("class_name", "EC")] for s in results]
                print(f"\nFound {len(results)} match(es):")
                print_table(["Roll No", "Student Name", "Class"], rows)
        elif choice == "4":
            print("\n--- Register Student Entry ---")
            r_str = input("Enter Roll Number / ID: ").strip()
            try:
                sid = int(r_str)
            except ValueError:
                print("Invalid roll number.")
                continue
            s_name = input("Enter Student Full Name: ").strip()
            if not s_name:
                print("Name cannot be empty.")
                continue
            c_name = input("Enter Class (e.g. EC-1, EC-2) [Default: EC]: ").strip() or "EC"
            res = add_or_update_student(sid, s_name, c_name)
            print(f"\n[Success] Student saved: Roll #{res['id']} - {res['name']} ({res['class_name']})")
        elif choice == "0":
            break
        else:
            print("Invalid option. Please try again.")

def handle_create_fee():
    """Prompts to create a new fee collection."""
    print("\n--- Create New Fee / Dues Campaign ---")
    title = input("Enter fee title (e.g. 'Oct 2026 Monthly Dues'): ").strip()
    if not title:
        print("Title cannot be empty.")
        return

    amount_str = input("Target amount per student (e.g. 5000): ").strip()
    try:
        amount = float(amount_str)
        if amount <= 0:
            print("Amount must be greater than 0.")
            return
    except ValueError:
        print("Invalid number entered.")
        return

    due_date = input("Due date (YYYY-MM-DD or leave blank): ").strip() or None

    fee_id = create_fee(title, amount, due_date)
    print(f"\n[Success] Fee campaign created with ID: {fee_id} ('{title}', {amount:,.0f} per student)")

def handle_view_fees():
    """Lists all fees and allows drilling down into collection details."""
    fees = list_fees()
    if not fees:
        print("\nNo fee campaigns found. Create one first!")
        return

    rows = [[f["id"], f["title"], f"{f['amount_per_student']:,.0f}", f["due_date"] or "N/A", f["created_at"]] for f in fees]
    print("\n=== ACTIVE & PAST FEES ===")
    print_table(["Fee ID", "Title", "Amount/Student", "Due Date", "Created At"], rows)

    fee_choice = input("\nEnter Fee ID to view detailed collection status (or Enter to go back): ").strip()
    if not fee_choice:
        return

    try:
        fid = int(fee_choice)
    except ValueError:
        print("Invalid Fee ID.")
        return

    status = get_fee_status(fid)
    if not status:
        print(f"Fee ID {fid} not found.")
        return

    print(f"\n==============================================")
    print(f" Fee Details: {status['fee']['title']} (ID: {fid})")
    print(f" Amount Per Student: {status['target_amount_per_student']:,.0f}")
    print(f" Total Students:     {status['total_students']}")
    print(f" Total Expected:     {status['total_expected']:,.0f}")
    print(f" Total Collected:    {status['total_collected']:,.0f}")
    print(f" Collection Rate:    {status['collection_rate_percent']}%")
    print(f" Paid: {status['paid_count']} | Partial: {status['partial_count']} | Unpaid: {status['unpaid_count']}")
    print(f"==============================================")

    sub_view = input("\nShow student breakdown? [1] Unpaid Only, [2] All Students, [0] Back: ").strip()
    if sub_view == "1":
        unpaid = [s for s in status["students"] if s["status"] != "PAID"]
        rows = [[s["id"], s["name"], f"{s['amount_paid']:,.0f}", f"{s['remaining']:,.0f}", s["status"]] for s in unpaid]
        print(f"\n--- Pending / Unpaid Students ({len(unpaid)}) ---")
        print_table(["Roll", "Name", "Paid", "Remaining", "Status"], rows)
    elif sub_view == "2":
        rows = [[s["id"], s["name"], f"{s['amount_paid']:,.0f}", f"{s['remaining']:,.0f}", s["status"]] for s in status["students"]]
        print(f"\n--- All Student Status ({len(status['students'])}) ---")
        print_table(["Roll", "Name", "Paid", "Remaining", "Status"], rows)

def handle_record_payment():
    """Records a payment from a student for a specific fee."""
    fees = list_fees()
    if not fees:
        print("\nNo fees exist. Please create a fee first.")
        return

    print("\n--- Available Fees ---")
    for f in fees:
        print(f"[{f['id']}] {f['title']} (Due: {f['amount_per_student']:,.0f})")

    fee_input = input("Select Fee ID: ").strip()
    try:
        fid = int(fee_input)
    except ValueError:
        print("Invalid Fee ID.")
        return

    fee = get_fee(fid)
    if not fee:
        print("Fee not found.")
        return

    roll_input = input("Enter Student Roll Number (1 - 43): ").strip()
    try:
        sid = int(roll_input)
    except ValueError:
        print("Invalid roll number.")
        return

    student = get_student_by_id(sid)
    if not student:
        print(f"No student found with Roll {sid}.")
        return

    print(f"Selected Student: Roll {student['id']} - {student['name']}")
    default_amount = fee["amount_per_student"]
    amount_str = input(f"Enter amount paid [Default: {default_amount:,.0f}]: ").strip()
    if not amount_str:
        amount = default_amount
    else:
        try:
            amount = float(amount_str)
        except ValueError:
            print("Invalid amount.")
            return

    notes = input("Remarks / Notes (optional): ").strip()

    try:
        payment_id = record_payment(fid, sid, amount, notes)
        print(f"\n[Success] Recorded payment #{payment_id} for {student['name']} ({amount:,.0f} MMK).")
    except Exception as e:
        print(f"\n[Error] Failed to record payment: {e}")

def handle_expenses():
    """Sub-menu for class expenses."""
    while True:
        print("\n=== EXPENSE TRACKER ===")
        print("1. Log New Expense")
        print("2. View Expense Log")
        print("0. Back to Main Menu")

        choice = prompt_menu_choice()
        if choice == "1":
            title = input("Expense title / item name: ").strip()
            if not title:
                print("Title cannot be empty.")
                continue
            amount_str = input("Amount spent: ").strip()
            try:
                amount = float(amount_str)
                if amount <= 0:
                    print("Amount must be greater than 0.")
                    continue
            except ValueError:
                print("Invalid amount.")
                continue
            category = input("Category (e.g. Stationery, Event, Refreshment, Printing): ").strip() or "General"
            spent_by = input("Person who spent / paid: ").strip() or ""
            date_str = input("Date (YYYY-MM-DD or leave blank for today): ").strip() or None
            notes = input("Receipt / Notes: ").strip() or ""

            exp_id = add_expense(title, amount, category, spent_by, date_str, notes)
            print(f"\n[Success] Expense #{exp_id} logged: {title} ({amount:,.0f} MMK)")
        elif choice == "2":
            expenses = list_expenses()
            if not expenses:
                print("\nNo expenses logged yet.")
            else:
                rows = [[e["id"], e["title"], f"{e['amount']:,.0f}", e["category"], e["spent_by"], e["date"], e["notes"]] for e in expenses]
                total = sum(e["amount"] for e in expenses)
                print(f"\n--- Total Expenses: {len(expenses)} | Sum: {total:,.0f} MMK ---")
                print_table(["ID", "Title", "Amount", "Category", "Spent By", "Date", "Notes"], rows)
        elif choice == "0":
            break
        else:
            print("Invalid option.")

def handle_financial_summary():
    """Displays treasury balance overview."""
    summary = get_financial_summary()
    print("\n==============================================")
    print("      EC MONEY MANAGEMENT - TREASURY OVERVIEW  ")
    print("==============================================")
    print(f" Total Registered Students: {summary['student_count']}")
    print(f" Active / Past Fee Drives:  {summary['fee_count']}")
    print(f" Total Logged Expenses:     {summary['expense_count']}")
    print("----------------------------------------------")
    print(f" Total Income (Collected):   {summary['total_income']:>15,.2f} MMK")
    print(f" Total Expenses (Spent):     {summary['total_expenses']:>15,.2f} MMK")
    print("----------------------------------------------")
    net = summary["net_balance"]
    status_tag = "[SURPLUS]" if net >= 0 else "[DEFICIT]"
    print(f" Net Cash on Hand:           {net:>15,.2f} MMK {status_tag}")
    print("==============================================")

def handle_export():
    """Handles exporting data to CSV and Excel."""
    print("\n=== EXPORT REPORTS & SPREADSHEETS ===")
    print("1. Export Fee Status to Formatted Excel Spreadsheet (.xlsx) [Color Coded: Paid/Unpaid]")
    print("2. Export Master Multi-Sheet Workbook (.xlsx) [Summary, Matrix, Transactions, Expenses]")
    print("3. Export Fee Report to CSV")
    print("4. Export Financial Summary to CSV")
    print("0. Cancel")

    choice = prompt_menu_choice()
    if choice == "1":
        fees = list_fees()
        if not fees:
            print("No fees to export.")
            return
        for f in fees:
            print(f"[{f['id']}] {f['title']}")
        fid_str = input("Select Fee ID: ").strip()
        try:
            fid = int(fid_str)
        except ValueError:
            print("Invalid ID.")
            return
        default_file = f"fee_{fid}_fund_status.xlsx"
        filepath = input(f"Enter filename to save [Default: {default_file}]: ").strip() or default_file
        try:
            saved_path = export_fee_status_excel(fid, filepath)
            print(f"\n[Success] Formatted Excel spreadsheet saved to: {saved_path}")
        except Exception as e:
            print(f"\n[Error] Excel export failed: {e}")
    elif choice == "2":
        default_file = "EC_Master_Financial_Workbook.xlsx"
        filepath = input(f"Enter filename to save [Default: {default_file}]: ").strip() or default_file
        try:
            saved_path = export_full_excel_workbook(filepath)
            print(f"\n[Success] Master Workbook exported to: {saved_path}")
        except Exception as e:
            print(f"\n[Error] Master export failed: {e}")
    elif choice == "3":
        fees = list_fees()
        if not fees:
            print("No fees to export.")
            return
        for f in fees:
            print(f"[{f['id']}] {f['title']}")
        fid_str = input("Select Fee ID: ").strip()
        try:
            fid = int(fid_str)
        except ValueError:
            print("Invalid ID.")
            return
        default_file = f"fee_{fid}_report.csv"
        filepath = input(f"Enter filename to save [Default: {default_file}]: ").strip() or default_file
        try:
            saved_path = export_fee_report_csv(fid, filepath)
            print(f"\n[Success] CSV report saved to: {saved_path}")
        except Exception as e:
            print(f"\n[Error] Export failed: {e}")
    elif choice == "4":
        default_file = "financial_summary.csv"
        filepath = input(f"Enter filename to save [Default: {default_file}]: ").strip() or default_file
        try:
            saved_path = export_financial_summary_csv(filepath)
            print(f"\n[Success] Summary exported to: {saved_path}")
        except Exception as e:
            print(f"\n[Error] Export failed: {e}")

def handle_launch_telegram_bot():
    """Starts the Telegram bot directly."""
    import telegram_bot
    telegram_bot.run_bot()

from services.attendance_service import (
    list_subjects,
    add_subject,
    create_attendance_session,
    mark_absentees,
    get_session_details,
    list_attendance_sessions,
    export_attendance_excel,
)
from services.team_randomizer_service import generate_teams

def handle_attendance_menu():
    """CLI handler for classroom attendance."""
    while True:
        print("\n=== CLASSROOM ATTENDANCE ===")
        print("1. Take New Attendance Session")
        print("2. View Past Attendance Sessions")
        print("3. Export Attendance Sheet to Excel")
        print("4. Add New Subject")
        print("0. Back to Main Menu")

        choice = prompt_menu_choice()
        if choice == "1":
            subjects = list_subjects()
            if not subjects:
                print("No subjects found. Add a subject first.")
                continue
            print("\nAvailable Subjects:")
            for idx, s in enumerate(subjects, 1):
                print(f"{idx}. {s['name']} ({s.get('code') or 'No Code'})")
            s_idx_str = input("Select Subject #: ").strip()
            try:
                sub = subjects[int(s_idx_str) - 1]
            except (ValueError, IndexError):
                print("Invalid selection.")
                continue

            period = input("Enter Period / Slot [Default: Slot 1]: ").strip() or "Slot 1"
            sess_id = create_attendance_session(sub["id"], period=period)
            print(f"\n[Created] Attendance session #{sess_id} for {sub['name']} ({period}). All students set to PRESENT.")

            absent_str = input("Enter roll numbers of ABSENT students (comma-separated, e.g. '3, 12, 25') or leave blank: ").strip()
            if absent_str:
                absent_rolls = [int(x.strip()) for x in absent_str.split(",") if x.strip().isdigit()]
                mark_absentees(sess_id, absent_rolls)
                print(f"Marked {len(absent_rolls)} student(s) as ABSENT.")

            det = get_session_details(sess_id)
            print(f"Summary: Present: {det['present_count']} | Absent: {det['absent_count']} | Rate: {det['attendance_rate_percent']}%")
        elif choice == "2":
            sessions = list_attendance_sessions(limit=10)
            if not sessions:
                print("No attendance sessions recorded yet.")
                continue
            rows = [[s["id"], s["date"], s["subject_name"], s["period"], s["present_count"], s["absent_count"]] for s in sessions]
            print("\n=== RECENT ATTENDANCE SESSIONS ===")
            print_table(["ID", "Date", "Subject", "Period", "Present", "Absent"], rows)
        elif choice == "3":
            s_id_str = input("Enter Attendance Session ID: ").strip()
            try:
                sess_id = int(s_id_str)
            except ValueError:
                print("Invalid session ID.")
                continue
            det = get_session_details(sess_id)
            if not det:
                print("Session not found.")
                continue
            default_fn = f"attendance_session_{sess_id}_{det['session']['date']}.xlsx"
            filepath = input(f"Enter filename to save [Default: {default_fn}]: ").strip() or default_fn
            try:
                saved = export_attendance_excel(sess_id, filepath)
                print(f"\n[Success] Attendance sheet exported to: {saved}")
            except Exception as e:
                print(f"\n[Error] Export failed: {e}")
        elif choice == "4":
            s_name = input("Enter Subject Name: ").strip()
            if not s_name:
                continue
            s_code = input("Enter Subject Code (optional, e.g. 'DSP'): ").strip()
            sub = add_subject(s_name, s_code)
            print(f"\n[Success] Subject added: {sub['name']} (#{sub['id']})")
        elif choice == "0":
            break

def handle_teams_menu():
    """CLI handler for team randomizer."""
    print("\n=== ASSIGNMENT & PROJECT TEAM RANDOMIZER ===")
    sub_title = input("Enter Subject / Assignment Name (optional): ").strip()
    size_str = input("Enter Target Members Per Team [Default: 4]: ").strip() or "4"
    try:
        group_size = int(size_str)
    except ValueError:
        print("Invalid number.")
        return

    try:
        res = generate_teams(group_size=group_size, subject_name=sub_title)
        print("\n" + res["formatted_markdown"])
    except Exception as e:
        print(f"Error generating teams: {e}")

def handle_run_setup_wizard():
    """Launches the Setup Wizard."""
    import setup_wizard
    setup_wizard.run_wizard()

def main():
    """Main application loop."""
    # Ensure database and student data are initialized
    init_db()

    while True:
        print("\n==============================================")
        print("          CLASS PRESIDENT SUPER-PLATFORM       ")
        print("==============================================")
        print("1. Student Directory (Search & Manage Classes)")
        print("2. Fees & Dues Management (Create & View Status)")
        print("3. Record Student Payment")
        print("4. Subject Attendance Tracker")
        print("5. Project & Assignment Team Randomizer")
        print("6. Class Expense Tracker")
        print("7. Treasury Financial Overview")
        print("8. Export Spreadsheets & Reports (CSV / Excel)")
        print("9. Launch Telegram Bot (AI KPay, Attendance, RSVP)")
        print("10. Run Setup Wizard (Configure Bot for Any Class)")
        print("0. Exit")
        print("==============================================")

        choice = prompt_menu_choice()

        if choice == "1":
            handle_students_menu()
        elif choice == "2":
            print("\n1. View / Check Fee Status")
            print("2. Create New Fee Campaign")
            print("0. Back")
            sub = prompt_menu_choice()
            if sub == "1":
                handle_view_fees()
            elif sub == "2":
                handle_create_fee()
        elif choice == "3":
            handle_record_payment()
        elif choice == "4":
            handle_attendance_menu()
        elif choice == "5":
            handle_teams_menu()
        elif choice == "6":
            handle_expenses()
        elif choice == "7":
            handle_financial_summary()
        elif choice == "8":
            handle_export()
        elif choice == "9":
            handle_launch_telegram_bot()
        elif choice == "10":
            handle_run_setup_wizard()
        elif choice == "0":
            print("\nThank you for using the Class President Platform. Goodbye!")
            sys.exit(0)
        else:
            print("Invalid choice. Please select an option from 0 to 10.")

if __name__ == "__main__":
    main()