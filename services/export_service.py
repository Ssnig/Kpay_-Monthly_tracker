import csv
from pathlib import Path
from db.database import get_connection
from services.treasury_service import get_fee_status, get_financial_summary, list_expenses, list_fees
from services.student_service import list_all_students

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

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
        writer.writerow(["Roll Number", "Student Name", "Class", "Amount Paid", "Remaining Due", "Status"])

        for s in status["students"]:
            writer.writerow([s["id"], s["name"], s.get("class_name", "EC"), s["amount_paid"], s["remaining"], s["status"]])

    return str(out.resolve())

def export_fee_status_excel(fee_id, output_path, class_name=None, db_path=None):
    """
    Exports a beautifully formatted Excel spreadsheet (.xlsx) showing
    who has paid funds and who has not for a specific fee.
    """
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required to generate Excel spreadsheets. Run 'pip install openpyxl'.")

    status = get_fee_status(fee_id, class_name=class_name, db_path=db_path)
    if not status:
        raise ValueError(f"Fee with ID {fee_id} not found.")

    fee = status["fee"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Fee #{fee['id']} Status"
    ws.views.sheetView[0].showGridLines = True

    # Palette
    title_font = Font(name="Calibri", size=16, bold=True, color="1F4E78")
    subtitle_font = Font(name="Calibri", size=11, italic=True, color="595959")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)
    
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    summary_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    
    # Status Fills & Fonts
    paid_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    paid_font = Font(name="Calibri", size=11, bold=True, color="006100")

    partial_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    partial_font = Font(name="Calibri", size=11, bold=True, color="9C6500")

    unpaid_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    unpaid_font = Font(name="Calibri", size=11, bold=True, color="9C0006")

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # 1. Main Title
    ws["A1"] = "EC MONEY MANAGEMENT - FUND PAYMENT STATUS"
    ws["A1"].font = title_font
    ws["A2"] = f"Fee: {fee['title']} | Target: {status['target_amount_per_student']:,.0f} MMK | Due: {fee['due_date'] or 'N/A'}"
    if class_name:
        ws["A2"].value += f" | Class Filter: {class_name}"
    ws["A2"].font = subtitle_font

    # 2. Metric Summary Box
    summary_rows = [
        ("Total Students", status["total_students"], "Collection Rate", f"{status['collection_rate_percent']}%"),
        ("Total Expected", f"{status['total_expected']:,.0f} MMK", "Paid Count", f"{status['paid_count']} students"),
        ("Total Collected", f"{status['total_collected']:,.0f} MMK", "Partial Count", f"{status['partial_count']} students"),
        ("Remaining Due", f"{(status['total_expected'] - status['total_collected']):,.0f} MMK", "Unpaid Count", f"{status['unpaid_count']} students"),
    ]

    start_r = 4
    for idx, (lbl1, val1, lbl2, val2) in enumerate(summary_rows):
        r = start_r + idx
        ws[f"A{r}"] = lbl1
        ws[f"B{r}"] = val1
        ws[f"D{r}"] = lbl2
        ws[f"E{r}"] = val2

        ws[f"A{r}"].font = bold_font
        ws[f"A{r}"].fill = summary_fill
        ws[f"B{r}"].font = regular_font
        ws[f"D{r}"].font = bold_font
        ws[f"D{r}"].fill = summary_fill
        ws[f"E{r}"].font = regular_font

    # 3. Table Headers
    table_header_row = 9
    headers = ["Roll No", "Student Name", "Class", "Target (MMK)", "Amount Paid (MMK)", "Remaining (MMK)", "Fund Status"]
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=table_header_row, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 3, 7] else "left", vertical="center")

    # 4. Table Rows
    curr_row = 10
    for s in status["students"]:
        ws.cell(row=curr_row, column=1, value=s["id"]).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=2, value=s["name"])
        ws.cell(row=curr_row, column=3, value=s.get("class_name", "EC")).alignment = Alignment(horizontal="center")
        
        target_cell = ws.cell(row=curr_row, column=4, value=status["target_amount_per_student"])
        target_cell.number_format = "#,##0"
        
        paid_cell = ws.cell(row=curr_row, column=5, value=s["amount_paid"])
        paid_cell.number_format = "#,##0"
        
        rem_cell = ws.cell(row=curr_row, column=6, value=s["remaining"])
        rem_cell.number_format = "#,##0"

        stat_cell = ws.cell(row=curr_row, column=7, value=s["status"])
        stat_cell.alignment = Alignment(horizontal="center")

        # Color highlight
        if s["status"] == "PAID":
            stat_cell.fill = paid_fill
            stat_cell.font = paid_font
        elif s["status"] == "PARTIAL":
            stat_cell.fill = partial_fill
            stat_cell.font = partial_font
        else:
            stat_cell.fill = unpaid_fill
            stat_cell.font = unpaid_font

        # Apply borders
        for col_idx in range(1, 8):
            ws.cell(row=curr_row, column=col_idx).border = thin_border
            if col_idx != 7:
                ws.cell(row=curr_row, column=col_idx).font = regular_font

        curr_row += 1

    # Freeze header rows
    ws.freeze_panes = f"A{table_header_row + 1}"

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val = cell.value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return str(out.resolve())

def export_full_excel_workbook(output_path, db_path=None):
    """
    Exports a comprehensive multi-sheet Excel workbook:
    - Sheet 1: Executive Financial Summary & Fee Campaigns
    - Sheet 2: Master Student Ledger (All classes with Paid / Unpaid tracking per fee)
    - Sheet 3: Individual Payment Transactions Log
    - Sheet 4: Expense Records
    """
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required to generate Excel spreadsheets. Run 'pip install openpyxl'.")

    wb = openpyxl.Workbook()
    # Sheet 1: Summary
    ws_summary = wb.active
    ws_summary.title = "Financial Summary"
    ws_summary.views.sheetView[0].showGridLines = True

    title_font = Font(name="Calibri", size=15, bold=True, color="1F4E78")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    regular_font = Font(name="Calibri", size=11)
    bold_font = Font(name="Calibri", size=11, bold=True)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    summary = get_financial_summary(db_path=db_path)
    ws_summary["A1"] = "EC MONEY MANAGEMENT - EXECUTIVE SUMMARY"
    ws_summary["A1"].font = title_font

    ws_summary["A3"] = "Total Students:"
    ws_summary["B3"] = summary["student_count"]
    ws_summary["A4"] = "Total Funds Collected:"
    ws_summary["B4"] = summary["total_income"]
    ws_summary["B4"].number_format = "#,##0.00"
    ws_summary["A5"] = "Total Expenses:"
    ws_summary["B5"] = summary["total_expenses"]
    ws_summary["B5"].number_format = "#,##0.00"
    ws_summary["A6"] = "Net Treasury Cash Balance:"
    ws_summary["B6"] = summary["net_balance"]
    ws_summary["B6"].number_format = "#,##0.00"

    for r in range(3, 7):
        ws_summary[f"A{r}"].font = bold_font

    # Active Fees list on summary sheet
    ws_summary["A9"] = "Fee Campaigns"
    ws_summary["A9"].font = Font(name="Calibri", size=13, bold=True, color="1F4E78")
    
    fee_headers = ["ID", "Title", "Target Amount", "Due Date", "Created At"]
    for idx, h in enumerate(fee_headers, 1):
        cell = ws_summary.cell(row=10, column=idx, value=h)
        cell.font = header_font
        cell.fill = header_fill

    fees = list_fees(db_path=db_path)
    r_idx = 11
    for f in fees:
        ws_summary.cell(row=r_idx, column=1, value=f["id"])
        ws_summary.cell(row=r_idx, column=2, value=f["title"])
        amt_cell = ws_summary.cell(row=r_idx, column=3, value=f["amount_per_student"])
        amt_cell.number_format = "#,##0.00"
        ws_summary.cell(row=r_idx, column=4, value=f["due_date"] or "N/A")
        ws_summary.cell(row=r_idx, column=5, value=str(f["created_at"]))
        r_idx += 1

    # Sheet 2: Master Student Matrix
    ws_students = wb.create_sheet(title="Student Funds Status")
    ws_students.views.sheetView[0].showGridLines = True
    ws_students["A1"] = "STUDENT FUND PAYMENT CHECKLIST"
    ws_students["A1"].font = title_font

    students = list_all_students(db_path=db_path)
    std_headers = ["Roll No", "Student Name", "Class"]
    fee_col_map = {}
    col_ptr = 4

    for f in fees:
        std_headers.append(f"{f['title']} (Due {f['amount_per_student']:,.0f})")
        fee_col_map[f["id"]] = col_ptr
        col_ptr += 1

    for idx, h in enumerate(std_headers, 1):
        c = ws_students.cell(row=3, column=idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center" if idx in [1, 3] else "left")

    # Pre-fetch status for each fee
    fee_statuses = {f["id"]: {s["id"]: s for s in get_fee_status(f["id"], db_path=db_path)["students"]} for f in fees}

    paid_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    partial_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    unpaid_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    row_ptr = 4
    for st in students:
        ws_students.cell(row=row_ptr, column=1, value=st["id"]).alignment = Alignment(horizontal="center")
        ws_students.cell(row=row_ptr, column=2, value=st["name"])
        ws_students.cell(row=row_ptr, column=3, value=st.get("class_name", "EC")).alignment = Alignment(horizontal="center")

        for f in fees:
            f_col = fee_col_map[f["id"]]
            st_status = fee_statuses[f["id"]].get(st["id"])
            if st_status:
                paid = st_status["amount_paid"]
                status_text = st_status["status"]
                val_text = f"{status_text} ({paid:,.0f})"
                cell = ws_students.cell(row=row_ptr, column=f_col, value=val_text)
                cell.alignment = Alignment(horizontal="center")
                if status_text == "PAID":
                    cell.fill = paid_fill
                elif status_text == "PARTIAL":
                    cell.fill = partial_fill
                else:
                    cell.fill = unpaid_fill
            else:
                ws_students.cell(row=row_ptr, column=f_col, value="UNPAID (0)").fill = unpaid_fill

        for c_i in range(1, len(std_headers) + 1):
            ws_students.cell(row=row_ptr, column=c_i).border = thin_border
        row_ptr += 1

    ws_students.freeze_panes = "A4"

    # Sheet 3: Payments Transactions Log
    ws_payments = wb.create_sheet(title="Payment Log")
    ws_payments.views.sheetView[0].showGridLines = True
    ws_payments["A1"] = "INDIVIDUAL PAYMENT TRANSACTIONS"
    ws_payments["A1"].font = title_font

    pay_headers = ["Payment ID", "Paid At", "Fee Title", "Roll No", "Student Name", "Class", "Amount Paid", "Remarks"]
    for idx, h in enumerate(pay_headers, 1):
        c = ws_payments.cell(row=3, column=idx, value=h)
        c.font = header_font
        c.fill = header_fill

    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.paid_at, f.title AS fee_title, s.id AS student_id, s.name AS student_name,
               COALESCE(s.class_name, 'EC') AS class_name, p.amount_paid, p.remarks
        FROM payments p
        JOIN fees f ON p.fee_id = f.id
        JOIN students s ON p.student_id = s.id
        ORDER BY p.id DESC
    """)
    payments = cursor.fetchall()
    conn.close()

    p_row = 4
    for p in payments:
        ws_payments.cell(row=p_row, column=1, value=p["id"])
        ws_payments.cell(row=p_row, column=2, value=str(p["paid_at"]))
        ws_payments.cell(row=p_row, column=3, value=p["fee_title"])
        ws_payments.cell(row=p_row, column=4, value=p["student_id"])
        ws_payments.cell(row=p_row, column=5, value=p["student_name"])
        ws_payments.cell(row=p_row, column=6, value=p["class_name"])
        amt_c = ws_payments.cell(row=p_row, column=7, value=p["amount_paid"])
        amt_c.number_format = "#,##0.00"
        ws_payments.cell(row=p_row, column=8, value=p["remarks"] or "")
        for c_i in range(1, 9):
            ws_payments.cell(row=p_row, column=c_i).border = thin_border
        p_row += 1

    # Sheet 4: Expenses Log
    ws_expenses = wb.create_sheet(title="Expenses")
    ws_expenses.views.sheetView[0].showGridLines = True
    ws_expenses["A1"] = "CLASS EXPENSES LOG"
    ws_expenses["A1"].font = title_font

    exp_headers = ["Expense ID", "Date", "Title", "Amount", "Category", "Spent By", "Notes"]
    for idx, h in enumerate(exp_headers, 1):
        c = ws_expenses.cell(row=3, column=idx, value=h)
        c.font = header_font
        c.fill = header_fill

    expenses = list_expenses(db_path=db_path)
    e_row = 4
    for exp in expenses:
        ws_expenses.cell(row=e_row, column=1, value=exp["id"])
        ws_expenses.cell(row=e_row, column=2, value=exp["date"])
        ws_expenses.cell(row=e_row, column=3, value=exp["title"])
        amt_c = ws_expenses.cell(row=e_row, column=4, value=exp["amount"])
        amt_c.number_format = "#,##0.00"
        ws_expenses.cell(row=e_row, column=5, value=exp["category"])
        ws_expenses.cell(row=e_row, column=6, value=exp["spent_by"])
        ws_expenses.cell(row=e_row, column=7, value=exp["notes"] or "")
        for c_i in range(1, 8):
            ws_expenses.cell(row=e_row, column=c_i).border = thin_border
        e_row += 1

    # Auto-fit columns across all sheets
    for ws in [ws_summary, ws_students, ws_payments, ws_expenses]:
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val = cell.value
                if val is not None:
                    max_len = max(max_len, len(str(val)))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
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
