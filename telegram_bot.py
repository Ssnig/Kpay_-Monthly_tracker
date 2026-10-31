"""
Telegram Bot for EC Money Management System.

Features:
- Student entry management per class (Add, List, Filter by Class)
- Fee collection and payment recording
- Real-time Paid / Partial / Unpaid status tracking
- Excel Spreadsheet (.xlsx) generation and delivery directly in Telegram chat
"""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Add parent directory to sys.path if running standalone
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from db.database import init_db
from services.student_service import (
    add_or_update_student,
    get_student_by_id,
    list_all_students,
    list_classes,
    search_students,
)
from services.treasury_service import (
    create_fee,
    list_fees,
    get_fee,
    record_payment,
    get_fee_status,
    get_financial_summary,
)
from services.export_service import export_fee_status_excel, export_full_excel_workbook

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("EC_TelegramBot")

CONFIG_FILE = BASE_DIR / "bot_config.json"

# Conversation States
ADD_STUDENT_ROLL, ADD_STUDENT_NAME, ADD_STUDENT_CLASS = range(3)
PAY_FEE_SELECT, PAY_STUDENT_SELECT, PAY_AMOUNT_INPUT = range(3, 6)
CREATE_FEE_TITLE, CREATE_FEE_AMOUNT, CREATE_FEE_DUEDATE = range(6, 9)

def get_bot_token():
    """Reads bot token from environment variable or bot_config.json."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("telegram_bot_token", "").strip()
        except Exception:
            pass
    return None

def main_keyboard():
    """Persistent reply keyboard for easy mobile navigation."""
    keyboard = [
        [KeyboardButton("📊 Fund Status"), KeyboardButton("📥 Download Spreadsheet")],
        [KeyboardButton("➕ Add Student"), KeyboardButton("🏫 View Classes")],
        [KeyboardButton("💳 Record Payment"), KeyboardButton("💰 View Fees")],
        [KeyboardButton("📋 List Students"), KeyboardButton("ℹ️ Help / Commands")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ----------------- COMMAND HANDLERS -----------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command with an introduction and interactive menu."""
    welcome_text = (
        "👋 *Welcome to EC Money Management Bot!*\n\n"
        "Here you can manage student entries per class, track fund dues, "
        "record payments, and download formatted *Excel Spreadsheets* (.xlsx) "
        "showing who has paid and who has not.\n\n"
        "💡 *Quick Shortcuts:*\n"
        "• Tap *'📊 Fund Status'* to see paid vs unpaid counts\n"
        "• Tap *'📥 Download Spreadsheet'* to get the latest Excel sheet\n"
        "• Tap *'➕ Add Student'* to register a new student for a class\n"
        "• Tap *'💳 Record Payment'* to log a fee payment\n\n"
        "Type /help for full command list."
    )
    await update.message.reply_markdown(welcome_text, reply_markup=main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a list of all commands."""
    help_text = (
        "📖 *Available Bot Commands:*\n\n"
        "*Student & Class Management:*\n"
        "• `/addstudent` - Guided wizard to add a student to a class\n"
        "• `/addstudent <roll> <name> [class]` - Quick add (e.g. `/addstudent 44 Mg Mg EC-A`)\n"
        "• `/students [class]` - View student roster (e.g. `/students` or `/students EC-1`)\n"
        "• `/classes` - List all classes and student counts\n"
        "• `/find <name_or_roll>` - Search student by name or roll\n\n"
        "*Fees & Payment Tracking:*\n"
        "• `/status [fee_id]` - View who has paid and who is unpaid\n"
        "• `/fees` - List all fee collection campaigns\n"
        "• `/createfee` - Start a new fee collection\n"
        "• `/pay` - Guided payment recording\n"
        "• `/pay <fee_id> <roll> <amount>` - Quick record payment\n\n"
        "*Spreadsheets & Reports:*\n"
        "• `/spreadsheet [fee_id]` - Download Excel (.xlsx) fund status sheet\n"
        "• `/master_report` - Download multi-sheet Master Excel Workbook\n"
        "• `/summary` - View financial treasury summary"
    )
    await update.message.reply_markdown(help_text, reply_markup=main_keyboard())

async def list_classes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all classes with student counts."""
    classes = list_classes()
    if not classes:
        await update.message.reply_text("No classes or students registered yet.")
        return

    msg = "🏫 *Registered Classes & Enrollment:*\n\n"
    total = 0
    for c in classes:
        msg += f"• *Class {c['class_name']}*: {c['student_count']} student(s)\n"
        total += c["student_count"]
    msg += f"\n*Total Enrolled:* {total} students\n"
    msg += "\n💡 Tip: Use `/students <class_name>` to see students in a specific class."
    await update.message.reply_markdown(msg)

async def list_students_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists students, optionally filtered by class."""
    args = context.args
    class_filter = " ".join(args).strip() if args else None

    students = list_all_students(class_name=class_filter)
    if not students:
        filter_msg = f" in class '{class_filter}'" if class_filter else ""
        await update.message.reply_text(f"No students found{filter_msg}.")
        return

    title = f"📋 *Student Roster ({class_filter or 'All Classes'} - {len(students)} total):*\n\n"
    lines = []
    for s in students:
        lines.append(f"`#{s['id']:02d}` - {s['name']} (Class: *{s.get('class_name', 'EC')}*)")

    # Chunk into 40 lines per message if long
    chunk_size = 35
    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i:i + chunk_size])
        if i == 0:
            await update.message.reply_markdown(f"{title}{chunk}")
        else:
            await update.message.reply_markdown(chunk)

async def search_students_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Searches for a student by ID or name."""
    if not context.args:
        await update.message.reply_text("Usage: `/find <name_or_roll>`\nExample: `/find Aung` or `/find 5`", parse_mode="Markdown")
        return

    query = " ".join(context.args).strip()
    results = search_students(query)
    if not results:
        await update.message.reply_text(f"No students found matching '{query}'.")
        return

    msg = f"🔍 *Found {len(results)} student(s):*\n\n"
    for s in results:
        msg += f"• `#{s['id']:02d}` - *{s['name']}* (Class: {s.get('class_name', 'EC')})\n"
    await update.message.reply_markdown(msg)

# ----------------- STATUS & SPREADSHEETS -----------------

async def fund_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays payment status breakdown (paid vs unpaid)."""
    fees = list_fees()
    if not fees:
        await update.message.reply_text("No fee campaigns exist yet. Use `/createfee` to create one.")
        return

    target_fee_id = None
    if context.args:
        try:
            target_fee_id = int(context.args[0])
        except ValueError:
            pass

    if not target_fee_id:
        target_fee_id = fees[0]["id"]  # latest fee

    status = get_fee_status(target_fee_id)
    if not status:
        await update.message.reply_text(f"Fee ID {target_fee_id} not found.")
        return

    fee = status["fee"]
    msg = (
        f"📊 *Fund Collection Status*\n"
        f"📌 *Fee #{fee['id']}:* {fee['title']}\n"
        f"🎯 *Target per Student:* {status['target_amount_per_student']:,.0f} MMK\n"
        f"📅 *Due Date:* {fee['due_date'] or 'N/A'}\n"
        f"────────────────────────\n"
        f"👥 *Total Students:* {status['total_students']}\n"
        f"💰 *Expected:* {status['total_expected']:,.0f} MMK\n"
        f"💵 *Collected:* {status['total_collected']:,.0f} MMK\n"
        f"📈 *Collection Rate:* `{status['collection_rate_percent']}%`\n"
        f"────────────────────────\n"
        f"✅ *Fully Paid:* {status['paid_count']} students\n"
        f"⚠️ *Partial:* {status['partial_count']} students\n"
        f"❌ *Unpaid:* {status['unpaid_count']} students\n\n"
    )

    # Show list of unpaid/partial students
    pending = [s for s in status["students"] if s["status"] != "PAID"]
    if pending:
        msg += f"*Pending Students ({len(pending)}):*\n"
        for s in pending[:15]:
            rem = f"{s['remaining']:,.0f} MMK"
            msg += f"• `#{s['id']:02d}` {s['name']} [{s['class_name']}]: *{s['status']}* (Due: {rem})\n"
        if len(pending) > 15:
            msg += f"_...and {len(pending) - 15} more. Download spreadsheet to see all!_\n"
    else:
        msg += "🎉 *All students have completed their payments!*\n"

    # Quick inline action buttons
    inline_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download Excel Sheet", callback_data=f"export_fee_{target_fee_id}"),
            InlineKeyboardButton("💳 Record Payment", callback_data=f"pay_fee_{target_fee_id}"),
        ]
    ])
    await update.message.reply_markdown(msg, reply_markup=inline_kb)

async def spreadsheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates and uploads the formatted Excel spreadsheet (.xlsx)."""
    fees = list_fees()
    if not fees:
        await update.message.reply_text("No fees exist yet to generate a spreadsheet.")
        return

    fee_id = fees[0]["id"]
    if context.args:
        try:
            fee_id = int(context.args[0])
        except ValueError:
            pass

    status = get_fee_status(fee_id)
    if not status:
        await update.message.reply_text(f"Fee ID {fee_id} not found.")
        return

    await update.message.reply_text(f"⏳ Generating styled Excel spreadsheet for *'{status['fee']['title']}'*...", parse_mode="Markdown")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = tmp.name

    try:
        export_fee_status_excel(fee_id, tmp_path)
        filename = f"Fund_Status_Fee_{fee_id}_{status['fee']['title'].replace(' ', '_')}.xlsx"
        caption = (
            f"📊 *Fund Payment Status Spreadsheet*\n"
            f"• Fee: {status['fee']['title']}\n"
            f"• Paid: {status['paid_count']} | Unpaid: {status['unpaid_count']}\n"
            f"• Collection: {status['collection_rate_percent']}%\n\n"
            f"Green = PAID | Yellow = PARTIAL | Red = UNPAID"
        )
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(document=f, filename=filename, caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Spreadsheet error: {e}")
        await update.message.reply_text(f"❌ Failed to generate spreadsheet: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

async def master_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates and uploads the multi-sheet Master Workbook."""
    await update.message.reply_text("⏳ Generating Master Multi-Sheet Excel Workbook...", parse_mode="Markdown")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = tmp.name

    try:
        export_full_excel_workbook(tmp_path)
        caption = (
            "📑 *EC Money Management - Master Workbook*\n"
            "Sheets included:\n"
            "1. Financial Summary & Overview\n"
            "2. Student Funds Matrix (Paid/Unpaid for every fee & class)\n"
            "3. Payment Transactions Log\n"
            "4. Expense Records"
        )
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(document=f, filename="EC_Master_Financial_Workbook.xlsx", caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Master workbook error: {e}")
        await update.message.reply_text(f"❌ Failed to generate master workbook: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays high-level treasury financial health."""
    s = get_financial_summary()
    msg = (
        "💼 *Treasury Financial Summary:*\n"
        f"• Total Students Enrolled: *{s['student_count']}*\n"
        f"• Total Income (Collected): *{s['total_income']:,.0f} MMK*\n"
        f"• Total Expenses Logged: *{s['total_expenses']:,.0f} MMK*\n"
        f"────────────────────────\n"
        f"💰 *Net Cash Balance:* `{s['net_balance']:,.0f} MMK`"
    )
    await update.message.reply_markdown(msg)

async def backup_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a copy of the SQLite database directly to the user in Telegram."""
    from datetime import datetime
    db_file = BASE_DIR / "ec_money.db"
    if not db_file.exists():
        await update.message.reply_text("Database file not found.")
        return

    with open(db_file, "rb") as f:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        await update.message.reply_document(
            document=f,
            filename=f"ec_money_backup_{timestamp}.db",
            caption="📦 *EC Money Database Backup*\nKeep this file safe! You can restore it anytime if needed.",
            parse_mode="Markdown"
        )

async def list_fees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all fee campaigns."""
    fees = list_fees()
    if not fees:
        await update.message.reply_text("No fee campaigns found. Use `/createfee` to create one.")
        return

    msg = "💰 *Fee Collection Campaigns:*\n\n"
    for f in fees:
        msg += (
            f"• *[ID: {f['id']}]* {f['title']}\n"
            f"  Target: `{f['amount_per_student']:,.0f} MMK` | Due: {f['due_date'] or 'N/A'}\n"
            f"  Check: `/status {f['id']}` | Excel: `/spreadsheet {f['id']}`\n\n"
        )
    await update.message.reply_markdown(msg)

# ----------------- CONVERSATIONS: ADD STUDENT -----------------

async def add_student_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /addstudent command (direct args or conversation start)."""
    args = context.args
    # If arguments provided: /addstudent <roll> <name> [class]
    if args and len(args) >= 2:
        try:
            roll = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Roll number must be a valid integer.")
            return ConversationHandler.END

        # Last arg might be class if it starts with 'EC' or similar, else default
        if len(args) >= 3 and (args[-1].startswith("EC") or "-" in args[-1] or args[-1].isalnum()):
            class_name = args[-1]
            name = " ".join(args[1:-1])
        else:
            class_name = "EC"
            name = " ".join(args[1:])

        res = add_or_update_student(roll, name, class_name)
        await update.message.reply_markdown(
            f"✅ *Student Registered Successfully!*\n"
            f"• Roll No: `#{res['id']:02d}`\n"
            f"• Name: *{res['name']}*\n"
            f"• Class: *{res['class_name']}*",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END

    # Start guided conversation
    await update.message.reply_text(
        "📝 *Add Student Entry*\n\nPlease enter the *Student Roll Number / ID* (e.g. `44`):",
        parse_mode="Markdown"
    )
    return ADD_STUDENT_ROLL

async def add_student_roll_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        roll = int(text)
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric roll number (or /cancel):")
        return ADD_STUDENT_ROLL

    context.user_data["add_roll"] = roll
    existing = get_student_by_id(roll)
    exist_note = f"\n_(Note: Roll #{roll} is currently '{existing['name']}' in {existing.get('class_name', 'EC')}, this will update them)_" if existing else ""

    await update.message.reply_text(
        f"Roll Number: `#{roll}`{exist_note}\n\nNow enter the *Student's Full Name*:",
        parse_mode="Markdown"
    )
    return ADD_STUDENT_NAME

async def add_student_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Name cannot be empty. Please enter the student's name:")
        return ADD_STUDENT_NAME

    context.user_data["add_name"] = name
    
    # Suggest existing classes
    classes = list_classes()
    class_names = [c["class_name"] for c in classes] if classes else ["EC-1", "EC-2", "EC"]
    suggest_btns = [[KeyboardButton(c)] for c in class_names[:4]]

    await update.message.reply_text(
        f"Student Name: *{name}*\n\n"
        "Now enter or select the *Class / Batch* for this student (e.g. `EC-1`, `EC-2`, `Batch-2026`):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(suggest_btns, resize_keyboard=True, one_time_keyboard=True)
    )
    return ADD_STUDENT_CLASS

async def add_student_class_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cname = update.message.text.strip() or "EC"
    roll = context.user_data["add_roll"]
    name = context.user_data["add_name"]

    res = add_or_update_student(roll, name, cname)
    await update.message.reply_markdown(
        f"🎉 *Student Successfully Saved!*\n\n"
        f"• Roll No: `#{res['id']:02d}`\n"
        f"• Name: *{res['name']}*\n"
        f"• Class: *{res['class_name']}*\n\n"
        f"You can view the updated class roster with `/students {cname}`.",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ----------------- CONVERSATIONS: RECORD PAYMENT -----------------

async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts payment recording flow."""
    args = context.args
    # Quick form: /pay <fee_id> <roll> <amount>
    if args and len(args) >= 3:
        try:
            fid = int(args[0])
            sid = int(args[1])
            amt = float(args[2])
            student = get_student_by_id(sid)
            fee = get_fee(fid)
            if not student or not fee:
                await update.message.reply_text("❌ Invalid Fee ID or Student Roll number.")
                return ConversationHandler.END

            pid = record_payment(fid, sid, amt, "Telegram Bot quick pay")
            await update.message.reply_markdown(
                f"✅ *Payment Recorded Successfully!* (Receipt #{pid})\n"
                f"• Student: `#{student['id']:02d}` - *{student['name']}* ({student.get('class_name', 'EC')})\n"
                f"• Fee: *{fee['title']}*\n"
                f"• Amount Paid: `{amt:,.0f} MMK`",
                reply_markup=main_keyboard()
            )
            return ConversationHandler.END
        except ValueError:
            pass

    fees = list_fees()
    if not fees:
        await update.message.reply_text("No fees exist yet. Create a fee campaign first with `/createfee`.")
        return ConversationHandler.END

    fee_buttons = [[KeyboardButton(f"[{f['id']}] {f['title']} ({f['amount_per_student']:,.0f} MMK)")] for f in fees[:5]]
    await update.message.reply_text(
        "💳 *Record Student Payment*\n\nPlease select or enter the *Fee ID*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(fee_buttons, resize_keyboard=True, one_time_keyboard=True)
    )
    return PAY_FEE_SELECT

async def pay_fee_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    fee_id = None
    if text.startswith("["):
        try:
            fee_id = int(text.split("]")[0].replace("[", "").strip())
        except ValueError:
            pass
    else:
        try:
            fee_id = int(text)
        except ValueError:
            pass

    fee = get_fee(fee_id) if fee_id else None
    if not fee:
        await update.message.reply_text("❌ Invalid Fee. Please enter a valid Fee ID (or /cancel):")
        return PAY_FEE_SELECT

    context.user_data["pay_fee_id"] = fee["id"]
    context.user_data["pay_fee_title"] = fee["title"]
    context.user_data["pay_target_amount"] = fee["amount_per_student"]

    await update.message.reply_text(
        f"Fee Selected: *{fee['title']}* (Target: {fee['amount_per_student']:,.0f} MMK)\n\n"
        "Now enter the student's *Roll Number / ID* (e.g. `1` or `15`):",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return PAY_STUDENT_SELECT

async def pay_student_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        sid = int(text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a numeric student roll number:")
        return PAY_STUDENT_SELECT

    student = get_student_by_id(sid)
    if not student:
        await update.message.reply_text(f"❌ Student #{sid} not found. Try again or /cancel:")
        return PAY_STUDENT_SELECT

    context.user_data["pay_student_id"] = sid
    context.user_data["pay_student_name"] = student["name"]
    context.user_data["pay_student_class"] = student.get("class_name", "EC")

    target = context.user_data["pay_target_amount"]
    quick_amt_btns = [[KeyboardButton(f"{target:,.0f}"), KeyboardButton(f"{target / 2:,.0f}")]]

    await update.message.reply_text(
        f"Student: `#{sid:02d}` - *{student['name']}* (Class: {student.get('class_name', 'EC')})\n\n"
        f"Enter the *amount paid* in MMK (Target: {target:,.0f}):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(quick_amt_btns, resize_keyboard=True, one_time_keyboard=True)
    )
    return PAY_AMOUNT_INPUT

async def pay_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(",", "").strip()
    try:
        amt = float(text)
        if amt <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a positive number:")
        return PAY_AMOUNT_INPUT

    fid = context.user_data["pay_fee_id"]
    sid = context.user_data["pay_student_id"]
    sname = context.user_data["pay_student_name"]
    cname = context.user_data["pay_student_class"]
    ftitle = context.user_data["pay_fee_title"]

    pid = record_payment(fid, sid, amt, "Paid via Telegram Bot")
    await update.message.reply_markdown(
        f"🎉 *Payment Logged Successfully!*\n\n"
        f"• Receipt No: `#{pid}`\n"
        f"• Student: `#{sid:02d}` - *{sname}* ({cname})\n"
        f"• Fee: *{ftitle}*\n"
        f"• Amount: `{amt:,.0f} MMK`\n\n"
        f"💡 Check updated status with `/status {fid}` or download `/spreadsheet {fid}`.",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ----------------- CONVERSATIONS: CREATE FEE -----------------

async def create_fee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts fee creation."""
    args = context.args
    if args and len(args) >= 2:
        try:
            amt = float(args[-1].replace(",", ""))
            title = " ".join(args[:-1])
            fid = create_fee(title, amt)
            await update.message.reply_markdown(
                f"✅ *Fee Campaign Created!*\n"
                f"• Fee ID: `#{fid}`\n"
                f"• Title: *{title}*\n"
                f"• Target per Student: `{amt:,.0f} MMK`",
                reply_markup=main_keyboard()
            )
            return ConversationHandler.END
        except ValueError:
            pass

    await update.message.reply_text(
        "💰 *Create New Fee / Dues Campaign*\n\n"
        "Enter the title for this fee (e.g. `Nov 2026 Monthly Dues` or `Class Trip Fund`):",
        parse_mode="Markdown"
    )
    return CREATE_FEE_TITLE

async def create_fee_title_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Title cannot be empty. Please enter title:")
        return CREATE_FEE_TITLE

    context.user_data["fee_title"] = title
    await update.message.reply_text(
        f"Title: *{title}*\n\nNow enter the *target amount per student* in MMK (e.g. `5000`):",
        parse_mode="Markdown"
    )
    return CREATE_FEE_AMOUNT

async def create_fee_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(",", "").strip()
    try:
        amt = float(text)
        if amt <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive number for amount:")
        return CREATE_FEE_AMOUNT

    context.user_data["fee_amount"] = amt
    await update.message.reply_text(
        f"Amount: `{amt:,.0f} MMK`\n\nEnter the *due date* (e.g. `2026-11-30`) or type `skip`:",
        parse_mode="Markdown"
    )
    return CREATE_FEE_DUEDATE

async def create_fee_duedate_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    due = update.message.text.strip()
    due_date = None if due.lower() in ["skip", "none", "-"] else due
    title = context.user_data["fee_title"]
    amt = context.user_data["fee_amount"]

    fid = create_fee(title, amt, due_date)
    await update.message.reply_markdown(
        f"🎉 *Fee Campaign Launched Successfully!*\n\n"
        f"• Fee ID: `#{fid}`\n"
        f"• Title: *{title}*\n"
        f"• Amount / Student: `{amt:,.0f} MMK`\n"
        f"• Due Date: {due_date or 'N/A'}\n\n"
        f"Students can now make payments with `/pay`.",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ----------------- BUTTON CALLBACKS & FALLBACKS -----------------

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button clicks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("export_fee_"):
        fid = int(data.split("_")[-1])
        status = get_fee_status(fid)
        if not status:
            await query.edit_message_text("Fee not found.")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp_path = tmp.name

        try:
            export_fee_status_excel(fid, tmp_path)
            fname = f"Fund_Status_Fee_{fid}.xlsx"
            caption = f"📊 Excel Fund Status for: *{status['fee']['title']}*"
            with open(tmp_path, "rb") as f:
                await context.bot.send_document(chat_id=query.message.chat_id, document=f, filename=fname, caption=caption, parse_mode="Markdown")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    elif data.startswith("pay_fee_"):
        fid = int(data.split("_")[-1])
        fee = get_fee(fid)
        if fee:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"To record payment for *{fee['title']}*, type:\n`/pay {fid} <roll_no> <amount>`\nExample: `/pay {fid} 1 5000`",
                parse_mode="Markdown"
            )

async def text_menu_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes persistent reply keyboard text buttons."""
    text = update.message.text.strip()
    if text == "📊 Fund Status":
        await fund_status_command(update, context)
    elif text == "📥 Download Spreadsheet":
        await spreadsheet_command(update, context)
    elif text == "➕ Add Student":
        await update.message.reply_text("To register a student, send `/addstudent`.", parse_mode="Markdown")
    elif text == "🏫 View Classes":
        await list_classes_command(update, context)
    elif text == "💳 Record Payment":
        await update.message.reply_text("To record payment, send `/pay`.", parse_mode="Markdown")
    elif text == "💰 View Fees":
        await list_fees_command(update, context)
    elif text == "📋 List Students":
        await list_students_command(update, context)
    elif text == "ℹ️ Help / Commands":
        await help_command(update, context)
    else:
        # Default fallback
        await update.message.reply_text(
            f"Command not recognized: '{text}'. Use /help to see all commands.",
            reply_markup=main_keyboard()
        )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels any ongoing conversation."""
    context.user_data.clear()
    await update.message.reply_text("Action cancelled.", reply_markup=main_keyboard())
    return ConversationHandler.END

# ----------------- APP BUILDER -----------------

def build_application(token: str):
    """Builds and wires up the Telegram Application."""
    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("students", list_students_command))
    app.add_handler(CommandHandler("classes", list_classes_command))
    app.add_handler(CommandHandler("find", search_students_command))
    app.add_handler(CommandHandler("status", fund_status_command))
    app.add_handler(CommandHandler("spreadsheet", spreadsheet_command))
    app.add_handler(CommandHandler("excel", spreadsheet_command))
    app.add_handler(CommandHandler("master_report", master_report_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("backup_db", backup_db_command))
    app.add_handler(CommandHandler("fees", list_fees_command))

    # Add Student Conversation
    add_student_conv = ConversationHandler(
        entry_points=[CommandHandler("addstudent", add_student_entry)],
        states={
            ADD_STUDENT_ROLL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_student_roll_step)],
            ADD_STUDENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_student_name_step)],
            ADD_STUDENT_CLASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_student_class_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    app.add_handler(add_student_conv)

    # Payment Recording Conversation
    pay_conv = ConversationHandler(
        entry_points=[CommandHandler("pay", pay_start)],
        states={
            PAY_FEE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_fee_step)],
            PAY_STUDENT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_student_step)],
            PAY_AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_amount_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    app.add_handler(pay_conv)

    # Create Fee Conversation
    create_fee_conv = ConversationHandler(
        entry_points=[CommandHandler("createfee", create_fee_start)],
        states={
            CREATE_FEE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_fee_title_step)],
            CREATE_FEE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_fee_amount_step)],
            CREATE_FEE_DUEDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_fee_duedate_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    app.add_handler(create_fee_conv)

    # Callback Query Handler
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    # Persistent keyboard dispatcher
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_menu_dispatcher))

    return app

def start_health_check_server(port: int):
    """Starts a minimal HTTP server on a daemon thread so Render Web Services detect an open port."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"EC Money Management Telegram Bot is running!")

        def log_message(self, format, *args):
            return  # silence access logs to keep console clean

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start health check HTTP server on port {port}: {e}")

def run_bot():
    """Main execution entry point."""
    init_db()  # ensure tables and migrations are ready
    
    # Start health check server if PORT is provided (e.g. on Render)
    port_env = os.getenv("PORT")
    if port_env:
        try:
            start_health_check_server(int(port_env))
        except ValueError:
            pass

    token = get_bot_token()
    if not token:
        print("\n" + "=" * 60)
        print("⚠️  TELEGRAM BOT TOKEN REQUIRED")
        print("=" * 60)
        print("To run the bot, you need a Telegram Bot Token from @BotFather.")
        print("\nYou can either:")
        print("1. Set the TELEGRAM_BOT_TOKEN environment variable:")
        print("   $env:TELEGRAM_BOT_TOKEN = 'your_token_here'")
        print("2. Or enter your token now to save it in bot_config.json:")
        try:
            user_token = input("\nEnter Bot Token (or press Enter to exit): ").strip()
            if user_token:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"telegram_bot_token": user_token}, f, indent=2)
                token = user_token
                print("✅ Token saved to bot_config.json.")
            else:
                print("Exiting.")
                return
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return

    print("🤖 Starting EC Money Management Telegram Bot...")
    print("Press Ctrl+C in terminal to stop.")
    app = build_application(token)
    app.run_polling()

if __name__ == "__main__":
    run_bot()
