"""
Class President Super-Bot Platform for EC Money Management.

Features:
- On-demand subject-specific attendance tracking with quick chips and Excel export
- AI-powered KBZPay payment slip auto-reader with OCR and roster matching
- Duplicate screenshot / transaction ID fraud protection
- Teacher announcements with interactive [I'm Interested] RSVP buttons
- Assignment & Lab Project team randomizer with leader assignment
- Multi-class student roster and fund payment status tracking
- Formatted color-coded Excel spreadsheets (.xlsx) delivered directly in chat
- Admin protection (only Class President can record payments/attendance)
- Built-in HTTP health-check server for 24/7 Render cloud deployment
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

# Ensure parent directory is in path
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
from services.attendance_service import (
    list_subjects,
    add_subject,
    get_subject,
    create_attendance_session,
    update_student_attendance,
    get_session_details,
    list_attendance_sessions,
    export_attendance_excel,
)
from services.team_randomizer_service import generate_teams
from services.announcement_service import (
    create_announcement,
    list_active_announcements,
    get_announcement_details,
    rsvp_student,
    withdraw_rsvp,
    close_announcement,
)
from services.kpay_ai_service import (
    analyze_kpay_slip,
    save_verified_kpay_receipt,
    check_duplicate_kpay_transaction,
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ClassPresidentBot")

CONFIG_FILE = BASE_DIR / "class_config.json"
BOT_CONFIG_FILE = BASE_DIR / "bot_config.json"

# Conversation states
ADD_STUDENT_ROLL, ADD_STUDENT_NAME, ADD_STUDENT_CLASS = range(3)
PAY_FEE_SELECT, PAY_STUDENT_SELECT, PAY_AMOUNT_INPUT = range(3, 6)
CREATE_FEE_TITLE, CREATE_FEE_AMOUNT, CREATE_FEE_DUEDATE = range(6, 9)
ATTENDANCE_SELECT_SUBJECT = 9
ANNOUNCE_TITLE, ANNOUNCE_CONTENT, ANNOUNCE_SLOTS = range(10, 13)

def load_config():
    """Loads configuration from class_config.json or bot_config.json."""
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    if BOT_CONFIG_FILE.exists():
        try:
            with open(BOT_CONFIG_FILE, "r", encoding="utf-8") as f:
                b_cfg = json.load(f)
                for k, v in b_cfg.items():
                    if k not in cfg or not cfg[k]:
                        cfg[k] = v
        except Exception:
            pass
    return cfg

def get_bot_token():
    """Reads bot token from env var or config."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip()
    cfg = load_config()
    return cfg.get("telegram_bot_token", "").strip()

def get_admin_ids():
    """Gets list of authorized admin Telegram user IDs."""
    admin_env = os.getenv("ADMIN_USER_IDS")
    admin_list = []
    if admin_env:
        for x in admin_env.split(","):
            if x.strip().isdigit():
                admin_list.append(int(x.strip()))

    cfg = load_config()
    for item in cfg.get("admin_telegram_ids", []):
        if isinstance(item, int):
            admin_list.append(item)
        elif str(item).isdigit():
            admin_list.append(int(item))
    return list(set(admin_list))

def is_admin_user(user_id):
    """Checks if a Telegram user is authorized as Class President / Admin."""
    admins = get_admin_ids()
    if not admins:
        # If no admins configured yet, permit all to facilitate first-time setup
        return True
    return user_id in admins

def main_keyboard():
    """Persistent mobile menu for Class President and students."""
    keyboard = [
        [KeyboardButton("📊 Fund Status"), KeyboardButton("📥 Download Spreadsheet")],
        [KeyboardButton("📅 Attendance"), KeyboardButton("🎲 Project Teams")],
        [KeyboardButton("📢 Announcements"), KeyboardButton("💳 Record Payment")],
        [KeyboardButton("📋 List Students"), KeyboardButton("ℹ️ Help / Commands")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ----------------- BASE COMMANDS -----------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome screen with introduction and main menu."""
    cfg = load_config()
    c_title = cfg.get("class_title", "Electronics & Communication")
    c_name = cfg.get("class_name", "EC")

    welcome_text = (
        f"👋 *Welcome to the {c_title} ({c_name}) Platform!*\n\n"
        "I am your automated **Class President & Treasury Assistant**.\n\n"
        "🌟 *What I can do:*\n"
        "• 💰 *Funds & Dues:* Check paid/unpaid status & get styled Excel sheets\n"
        "• 🧾 *AI KPay Reader:* Send any KBZPay transfer slip screenshot — I will read it automatically!\n"
        "• 📅 *Attendance:* Quick subject attendance recording & Excel export\n"
        "• 📢 *Teacher Announcements:* Post notices with 1-click interest signups\n"
        "• 🎲 *Team Randomizer:* Generate balanced assignment teams with leaders\n\n"
        "💡 *Tip:* You can send any KBZPay transfer screenshot directly into this chat anytime!"
    )
    await update.message.reply_markdown(welcome_text, reply_markup=main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays command manual with admin tags."""
    u_id = update.effective_user.id if update.effective_user else 0
    is_adm = is_admin_user(u_id)
    role_badge = "👑 *Admin (Class President)*" if is_adm else "👨‍🎓 *Student Member*"

    help_text = (
        f"📖 *Class Platform Commands* ({role_badge})\n\n"
        "*💰 Funds & Payments:*\n"
        "• `/status [fee_id]` - View who has paid and who is unpaid\n"
        "• `/spreadsheet [fee_id]` - Download color-coded Excel spreadsheet (.xlsx)\n"
        "• `/master_report` - Download 4-sheet master financial workbook\n"
        "• `/my_status <roll_no>` - Check your personal payment & dues status\n"
        "• `/pay` - 👑 Record student fee payment\n"
        "• `/createfee` - 👑 Launch a new fee collection campaign\n\n"
        "*📅 Classroom Attendance:*\n"
        "• `/attendance` - 👑 Start on-demand attendance session for a subject\n"
        "• `/attendance_export <session_id>` - Download session Excel report\n\n"
        "*📢 Announcements & Sign-ups:*\n"
        "• `/announcements` - View active teacher notices and sign-up polls\n"
        "• `/announce <title> - <content>` - 👑 Broadcast teacher notice with RSVP buttons\n\n"
        "*🎲 Project Teams:*\n"
        "• `/teams [size] [subject]` - Generate random assignment groups with leaders\n\n"
        "*📋 Students & Admin:*\n"
        "• `/students [class]` - View roster\n"
        "• `/classes` - View enrollment counts\n"
        "• `/addstudent` - 👑 Add or update student\n"
        "• `/backup_db` - 👑 Download instant database snapshot"
    )
    await update.message.reply_markdown(help_text, reply_markup=main_keyboard())

# ----------------- AI KPAY SLIP READER -----------------

async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives incoming photos/documents, checks if they are KBZPay transfer receipts,
    and uses Gemini Multimodal Vision to extract transaction details and match students.
    """
    msg = update.message
    user_id = update.effective_user.id if update.effective_user else 0
    is_adm = is_admin_user(user_id)

    # Get the highest resolution photo file
    if msg.photo:
        photo = msg.photo[-1]
        file_obj = await context.bot.get_file(photo.file_id)
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        file_obj = await context.bot.get_file(msg.document.file_id)
    else:
        return

    status_msg = await msg.reply_text("🔍 *Reading payment receipt with AI...*", parse_mode="Markdown")

    # Download image bytes
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp_path = tmp.name

    try:
        await file_obj.download_to_drive(custom_path=tmp_path)
        with open(tmp_path, "rb") as f:
            img_bytes = f.read()

        analysis = analyze_kpay_slip(img_bytes)
        if not analysis.get("success"):
            err_msg = analysis.get("message", "Could not parse transaction fields from image.")
            await status_msg.edit_text(
                f"⚠️ *KPay Slip Note:* {err_msg}\n"
                "💡 *Tip:* You can record this payment manually with `/pay` or plug in your custom AI model in `setup_wizard.py`.",
                parse_mode="Markdown"
            )
            return

        tx_id = analysis.get("transaction_id", "N/A")
        amt = analysis.get("amount", 0.0)
        payer = analysis.get("payer_name", "Unknown")
        dt = analysis.get("date_time", "N/A")
        matched_st = analysis.get("matched_student")
        conf = analysis.get("confidence_score", 0.0)
        is_dup = analysis.get("is_duplicate", False)
        provider_used = analysis.get("provider_used", "local_ocr")
        provider_badge = "🌐 *Custom AI Model*" if provider_used == "custom_endpoint" else "💻 *Offline Local OCR*"

        # 1. Duplicate Slip Alert
        if is_dup:
            dup_info = analysis["duplicate_info"]
            prev_student = dup_info.get("student_name", "Unknown")
            prev_fee = dup_info.get("fee_title", "Unknown Fee")
            dup_alert = (
                f"🚨 *DUPLICATE KBZPAY SLIP DETECTED!*\n"
                f"─────────────────────────────\n"
                f"• *Transaction ID:* `{tx_id}`\n"
                f"• *Amount:* `{amt:,.0f} MMK`\n"
                f"• *Payer:* {payer}\n\n"
                f"⚠️ *Warning:* This exact receipt was ALREADY recorded previously for:\n"
                f"👉 *Student:* {prev_student} (Fee: {prev_fee})\n"
                f"👉 *Recorded At:* {dup_info.get('verified_at')}\n\n"
                f"❌ *Action Blocked:* Screenshot reuse is not allowed."
            )
            await status_msg.edit_text(dup_alert, parse_mode="Markdown")
            return

        # 2. Valid New Slip Detected
        st_info = f"#{matched_st['id']:02d} - *{matched_st['name']}* ({matched_st.get('class_name', 'EC')})" if matched_st else "⚠️ *No clear name match in roster*"
        match_note = f" (Confidence: `{conf}%`)" if matched_st else ""

        fees = list_fees()
        target_fee = fees[0] if fees else None

        slip_card = (
            f"🧾 *KBZPay Slip Verified!* ({provider_badge})\n"
            f"─────────────────────────────\n"
            f"• *Amount Paid:* `{amt:,.0f} MMK`\n"
            f"• *Transaction ID:* `{tx_id}`\n"
            f"• *Payer on Slip:* *{payer}*\n"
            f"• *Timestamp:* {dt}\n\n"
            f"🎯 *Roster Match:* {st_info}{match_note}\n"
        )
        if target_fee:
            slip_card += f"📌 *Target Fee:* {target_fee['title']} (Due: {target_fee['amount_per_student']:,.0f} MMK)\n"

        buttons = []
        if is_adm and matched_st and target_fee:
            # Store temporary transaction package in context
            txn_key = f"kpay_{tx_id[:12]}"
            context.bot_data[txn_key] = {
                "tx_id": tx_id,
                "amount": amt,
                "payer": payer,
                "dt": dt,
                "student_id": matched_st["id"],
                "student_name": matched_st["name"],
                "fee_id": target_fee["id"],
                "fee_title": target_fee["title"],
                "raw_ai": analysis.get("raw_ai", "")
            }
            buttons.append([
                InlineKeyboardButton(f"✅ Record for #{matched_st['id']} ({matched_st['name']})", callback_data=f"appr_{txn_key}")
            ])
            buttons.append([
                InlineKeyboardButton("✏️ Select Different Student", callback_data=f"diff_{txn_key}"),
                InlineKeyboardButton("❌ Dismiss", callback_data=f"dism_{txn_key}")
            ])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await status_msg.edit_text(slip_card, parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error handling photo upload: {e}")
        await status_msg.edit_text(f"❌ Error processing receipt: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# ----------------- ATTENDANCE MANAGEMENT -----------------

async def attendance_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Launches the attendance session wizard."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔ *Admin Restricted:* Only the Class President can take attendance.", parse_mode="Markdown")
        return

    subjects = list_subjects()
    if not subjects:
        await update.message.reply_text("No subjects found. Use `/add_subject <name>` first.")
        return

    buttons = []
    for s in subjects[:8]:
        buttons.append([InlineKeyboardButton(f"📚 {s['name']}", callback_data=f"att_start_{s['id']}")])
    buttons.append([InlineKeyboardButton("📋 View Past Sessions", callback_data="att_history")])

    await update.message.reply_markdown(
        "📅 *Take Classroom Attendance*\n\nPlease select the *Subject* for this lecture/lab session:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def export_attendance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exports an attendance session to an Excel spreadsheet."""
    if not context.args:
        sessions = list_attendance_sessions(limit=5)
        if not sessions:
            await update.message.reply_text("No attendance sessions found.")
            return
        msg = "📅 *Recent Attendance Sessions:*\n\n"
        for s in sessions:
            msg += f"• *Session #{s['id']}*: {s['subject_name']} ({s['date']}) - `/attendance_export {s['id']}`\n"
        await update.message.reply_markdown(msg)
        return

    try:
        sess_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid session ID.")
        return

    details = get_session_details(sess_id)
    if not details:
        await update.message.reply_text(f"Attendance session #{sess_id} not found.")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = tmp.name

    try:
        export_attendance_excel(sess_id, tmp_path)
        fname = f"Attendance_{details['session']['subject_name']}_{details['session']['date']}.xlsx"
        caption = (
            f"📅 *Attendance Record Sheet*\n"
            f"• Subject: *{details['session']['subject_name']}*\n"
            f"• Date: {details['session']['date']} | Rate: `{details['attendance_rate_percent']}%`\n"
            f"• Present: {details['present_count']} | Absent: {details['absent_count']} | Leave: {details['leave_count']}"
        )
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(document=f, filename=fname, caption=caption, parse_mode="Markdown")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# ----------------- TEACHER ANNOUNCEMENTS & RSVP -----------------

async def list_announcements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists active teacher announcements and sign-up polls."""
    anns = list_active_announcements()
    if not anns:
        await update.message.reply_text("📢 No active teacher announcements at the moment.")
        return

    for a in anns:
        d = get_announcement_details(a["id"])
        slots_text = f"Slots: {d['rsvp_count']}/{d['max_slots']}" if d["max_slots"] > 0 else f"Signed up: {d['rsvp_count']} students"
        card = (
            f"📢 *TEACHER NOTICE:* *{a['title']}*\n"
            f"─────────────────────────────\n"
            f"{a['content']}\n\n"
            f"👥 *Status:* {slots_text}\n"
        )
        if d["participants"]:
            card += "*Registered Students:*\n"
            for p in d["participants"][:10]:
                card += f"• `#{p['student_id']:02d}` - {p['name']} ({p['class_name']})\n"
            if len(d["participants"]) > 10:
                card += f"_...and {len(d['participants']) - 10} more_\n"

        buttons = [
            [
                InlineKeyboardButton("✋ I'm Interested / Sign Up", callback_data=f"rsvp_in_{a['id']}"),
                InlineKeyboardButton("❌ Withdraw", callback_data=f"rsvp_out_{a['id']}"),
            ]
        ]
        await update.message.reply_markdown(card, reply_markup=InlineKeyboardMarkup(buttons))

async def create_announcement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creates a teacher notice: /announce Title - Content [MaxSlots]"""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔ *Admin Restricted:* Only the Class President can post teacher notices.", parse_mode="Markdown")
        return

    text = " ".join(context.args).strip()
    if not text or "-" not in text:
        await update.message.reply_markdown(
            "Usage: `/announce <Title> - <Content> [Slots]`\n\n"
            "Example: `/announce Robotics Workshop - Workshop next Monday in Lab 3. Need volunteers. 10`"
        )
        return

    parts = text.split("-")
    title = parts[0].strip()
    rest = "-".join(parts[1:]).strip()

    # Check if last word is a slot number
    slots = 0
    tokens = rest.split()
    if tokens and tokens[-1].isdigit():
        slots = int(tokens[-1])
        content = " ".join(tokens[:-1])
    else:
        content = rest

    ann_id = create_announcement(title, content, max_slots=slots)
    slots_msg = f" (Max: {slots} spots)" if slots > 0 else ""
    await update.message.reply_markdown(
        f"✅ *Teacher Announcement Published!* (#{ann_id}){slots_msg}\n"
        f"Students can now tap to RSVP in `/announcements`."
    )

# ----------------- ASSIGNMENT TEAM RANDOMIZER -----------------

async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Randomly partitions students into balanced project groups with assigned leaders.
    Usage: /teams [group_size] [Subject / Project Title]
    """
    args = context.args
    group_size = 4
    subject_title = None

    if args:
        if args[0].isdigit():
            group_size = int(args[0])
            if len(args) > 1:
                subject_title = " ".join(args[1:])
        else:
            subject_title = " ".join(args)

    try:
        result = generate_teams(group_size=group_size, subject_name=subject_title)
        await update.message.reply_markdown(result["formatted_markdown"], reply_markup=main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Could not form teams: {e}")

# ----------------- STUDENT SELF-SERVICE -----------------

async def my_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows a student to view their own payment and dues status."""
    if not context.args:
        await update.message.reply_text("Usage: `/my_status <your_roll_number>`\nExample: `/my_status 5`", parse_mode="Markdown")
        return

    try:
        sid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Roll number must be a number.")
        return

    student = get_student_by_id(sid)
    if not student:
        await update.message.reply_text(f"Student #{sid} not found in roster.")
        return

    fees = list_fees()
    if not fees:
        await update.message.reply_text("No active fee campaigns right now.")
        return

    msg = f"👤 *Student Record: #{student['id']:02d} - {student['name']}* ({student.get('class_name', 'EC')})\n\n"
    for f in fees:
        stat = get_fee_status(f["id"])
        st_entry = next((s for s in stat["students"] if s["id"] == sid), None)
        if st_entry:
            badge = "🟢 PAID" if st_entry["status"] == "PAID" else ("🟡 PARTIAL" if st_entry["status"] == "PARTIAL" else "🔴 UNPAID")
            msg += (
                f"• *{f['title']}* (Target: {f['amount_per_student']:,.0f} MMK)\n"
                f"  Status: {badge} | Paid: `{st_entry['amount_paid']:,.0f} MMK` | Remaining: `{st_entry['remaining']:,.0f} MMK`\n\n"
            )

    await update.message.reply_markdown(msg)

# ----------------- FUNDS & SPREADSHEETS -----------------

async def fund_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays payment status breakdown (paid vs unpaid)."""
    fees = list_fees()
    if not fees:
        await update.message.reply_text("No fee campaigns exist yet. Use `/createfee` to create one.")
        return

    target_fee_id = fees[0]["id"]
    if context.args:
        try:
            target_fee_id = int(context.args[0])
        except ValueError:
            pass

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
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

async def backup_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a copy of the SQLite database directly to the user in Telegram."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔ *Admin Restricted:* Only the Class President can download database snapshots.", parse_mode="Markdown")
        return

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

# ----------------- CALLBACK BUTTON DISPATCHER -----------------

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline interactive button clicks."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id if update.effective_user else 0
    is_adm = is_admin_user(user_id)

    # 1. Excel Export Button
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

    # 2. Approve KPay Payment
    elif data.startswith("appr_kpay_"):
        if not is_adm:
            await query.message.reply_text("⛔ Only the Class President can approve payments.")
            return
        txn_key = data.replace("appr_", "")
        pkg = context.bot_data.get(txn_key)
        if not pkg:
            await query.edit_message_text("⚠️ This receipt approval session has expired.")
            return

        # Double check duplicate
        if check_duplicate_kpay_transaction(pkg["tx_id"]):
            await query.edit_message_text(f"🚨 This transaction (`{pkg['tx_id']}`) was already recorded!")
            return

        # Record payment
        pid = record_payment(pkg["fee_id"], pkg["student_id"], pkg["amount"], f"KPay Slip Txn: {pkg['tx_id']}")
        save_verified_kpay_receipt(pkg["tx_id"], pkg["student_id"], pkg["fee_id"], pid, pkg["payer"], pkg["amount"], pkg["dt"], pkg["raw_ai"])

        del context.bot_data[txn_key]
        success_card = (
            f"🎉 *Payment Successfully Recorded!*\n\n"
            f"• Receipt No: `#{pid}`\n"
            f"• Student: `#{pkg['student_id']:02d}` - *{pkg['student_name']}*\n"
            f"• Amount: `{pkg['amount']:,.0f} MMK`\n"
            f"• Fee: *{pkg['fee_title']}*\n"
            f"• Txn ID: `{pkg['tx_id']}`\n\n"
            f"✅ *Status updated automatically.* Check with `/status {pkg['fee_id']}`"
        )
        await query.edit_message_text(success_card, parse_mode="Markdown")

    elif data.startswith("dism_kpay_"):
        txn_key = data.replace("dism_", "")
        if txn_key in context.bot_data:
            del context.bot_data[txn_key]
        await query.edit_message_text("Receipt dismissed.")

    # 3. Attendance Session Selection
    elif data.startswith("att_start_"):
        sub_id = int(data.split("_")[-1])
        sub = get_subject(sub_id)
        if not sub:
            await query.edit_message_text("Subject not found.")
            return

        sess_id = create_attendance_session(sub_id, created_by=user_id)
        details = get_session_details(sess_id)

        msg = (
            f"📅 *Attendance Session Active: {sub['name']}*\n"
            f"• Date: {details['session']['date']} | Period: {details['session']['period']}\n"
            f"• Enrolled: {details['total_students']} | Present: {details['present_count']} | Absent: {details['absent_count']}\n\n"
            f"All students initialized as *PRESENT*.\n"
            f"Tap any roll number below to toggle *ABSENT* / *LEAVE*:"
        )

        # Build roll number chips (first 15 students)
        st_buttons = []
        row = []
        for s in details["students"][:15]:
            icon = "🟢" if s["status"] == "PRESENT" else ("🔴" if s["status"] == "ABSENT" else "🟡")
            row.append(InlineKeyboardButton(f"#{s['id']} {icon}", callback_data=f"tgl_{sess_id}_{s['id']}"))
            if len(row) == 5:
                st_buttons.append(row)
                row = []
        if row:
            st_buttons.append(row)

        st_buttons.append([
            InlineKeyboardButton("📥 Download Excel Sheet", callback_data=f"att_dl_{sess_id}"),
            InlineKeyboardButton("✅ Finish Session", callback_data=f"att_done_{sess_id}")
        ])

        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(st_buttons))

    # 4. Toggle Student Attendance
    elif data.startswith("tgl_"):
        parts = data.split("_")
        sess_id = int(parts[1])
        st_id = int(parts[2])

        details = get_session_details(sess_id)
        current_st = next((s for s in details["students"] if s["id"] == st_id), None)
        if current_st:
            # Cycle PRESENT -> ABSENT -> LEAVE -> PRESENT
            next_stat = "ABSENT" if current_st["status"] == "PRESENT" else ("LEAVE" if current_st["status"] == "ABSENT" else "PRESENT")
            update_student_attendance(sess_id, st_id, next_stat)

        # Refresh in-place
        details = get_session_details(sess_id)
        msg = (
            f"📅 *Attendance Session: {details['session']['subject_name']}*\n"
            f"• Date: {details['session']['date']} | Present: {details['present_count']} | Absent: {details['absent_count']} | Leave: {details['leave_count']}\n\n"
            f"Tap any roll number below to toggle *ABSENT* / *LEAVE*:"
        )

        st_buttons = []
        row = []
        for s in details["students"][:15]:
            icon = "🟢" if s["status"] == "PRESENT" else ("🔴" if s["status"] == "ABSENT" else "🟡")
            row.append(InlineKeyboardButton(f"#{s['id']} {icon}", callback_data=f"tgl_{sess_id}_{s['id']}"))
            if len(row) == 5:
                st_buttons.append(row)
                row = []
        if row:
            st_buttons.append(row)

        st_buttons.append([
            InlineKeyboardButton("📥 Download Excel Sheet", callback_data=f"att_dl_{sess_id}"),
            InlineKeyboardButton("✅ Finish Session", callback_data=f"att_done_{sess_id}")
        ])

        try:
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(st_buttons))
        except Exception:
            pass

    # 5. Download Attendance Excel
    elif data.startswith("att_dl_"):
        sess_id = int(data.split("_")[-1])
        details = get_session_details(sess_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp_path = tmp.name
        try:
            export_attendance_excel(sess_id, tmp_path)
            fname = f"Attendance_{details['session']['subject_name']}_{details['session']['date']}.xlsx"
            with open(tmp_path, "rb") as f:
                await context.bot.send_document(chat_id=query.message.chat_id, document=f, filename=fname, caption=f"📅 Attendance for {details['session']['subject_name']}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    elif data.startswith("att_done_"):
        sess_id = int(data.split("_")[-1])
        details = get_session_details(sess_id)
        await query.edit_message_text(
            f"✅ *Attendance Session Saved!*\n"
            f"• Subject: {details['session']['subject_name']}\n"
            f"• Present: {details['present_count']} | Absent: {details['absent_count']} | Rate: `{details['attendance_rate_percent']}%`\n\n"
            f"Download spreadsheet anytime with `/attendance_export {sess_id}`.",
            parse_mode="Markdown"
        )

    # 6. RSVP Sign-Up & Withdraw
    elif data.startswith("rsvp_in_"):
        ann_id = int(data.split("_")[-1])
        # Find which student ID this Telegram user corresponds to, or prompt
        st_list = list_all_students()
        if not st_list:
            await query.message.reply_text("No students found.")
            return

        # Prompt student to confirm roll number
        context.user_data["rsvp_ann_id"] = ann_id
        await query.message.reply_text("Please enter your *Roll Number* to confirm your sign-up (e.g. `5`):", parse_mode="Markdown")

    elif data.startswith("rsvp_out_"):
        ann_id = int(data.split("_")[-1])
        await query.message.reply_text("To withdraw, type `/withdraw_rsvp <announcement_id> <roll_number>`\nExample: `/withdraw_rsvp 1 5`", parse_mode="Markdown")

# ----------------- RSVP CONVERSATION HELPER -----------------

async def handle_rsvp_roll_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text message when user enters their roll number for RSVP."""
    ann_id = context.user_data.get("rsvp_ann_id")
    if not ann_id:
        return False

    text = update.message.text.strip()
    if not text.isdigit():
        return False

    sid = int(text)
    student = get_student_by_id(sid)
    if not student:
        await update.message.reply_text(f"❌ Student #{sid} not found in roster.")
        return True

    del context.user_data["rsvp_ann_id"]
    try:
        res = rsvp_student(ann_id, sid, telegram_user_id=update.effective_user.id)
        if res.get("status") == "ALREADY_REGISTERED":
            await update.message.reply_markdown(f"ℹ️ `#{sid:02d}` *{student['name']}* is already signed up!")
        else:
            await update.message.reply_markdown(
                f"🎉 *Sign-Up Confirmed!*\n\n"
                f"• Student: `#{sid:02d}` - *{student['name']}* ({student.get('class_name', 'EC')})\n"
                f"You are successfully registered for this event."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Sign-up failed: {e}")
    return True

# ----------------- TEXT MENU DISPATCHER -----------------

async def text_menu_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes persistent reply keyboard text buttons."""
    # Check if this is an RSVP roll input
    if await handle_rsvp_roll_input(update, context):
        return

    text = update.message.text.strip()
    if text == "📊 Fund Status":
        await fund_status_command(update, context)
    elif text == "📥 Download Spreadsheet":
        await spreadsheet_command(update, context)
    elif text == "📅 Attendance":
        await attendance_menu_command(update, context)
    elif text == "🎲 Project Teams":
        await teams_command(update, context)
    elif text == "📢 Announcements":
        await list_announcements_command(update, context)
    elif text == "💳 Record Payment":
        user_id = update.effective_user.id if update.effective_user else 0
        if not is_admin_user(user_id):
            await update.message.reply_text("⛔ *Admin Restricted:* Only the Class President can record payments.", parse_mode="Markdown")
        else:
            await update.message.reply_text("Send `/pay` to start the payment wizard, or upload a KBZPay slip image directly!", parse_mode="Markdown")
    elif text == "📋 List Students":
        students = list_all_students()
        msg = f"📋 *Student Roster ({len(students)} total):*\n\n"
        for s in students[:30]:
            msg += f"• `#{s['id']:02d}` - {s['name']} [{s.get('class_name', 'EC')}]\n"
        if len(students) > 30:
            msg += f"_...and {len(students) - 30} more._\n"
        await update.message.reply_markdown(msg)
    elif text == "ℹ️ Help / Commands":
        await help_command(update, context)
    else:
        await update.message.reply_text(f"Command not recognized: '{text}'. Use /help to see all features.", reply_markup=main_keyboard())

# ----------------- PAYMENT RECORDING WIZARD -----------------

async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts payment recording flow."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔ *Admin Restricted:* Only the Class President can record payments.", parse_mode="Markdown")
        return ConversationHandler.END

    args = context.args
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

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels ongoing conversation."""
    context.user_data.clear()
    await update.message.reply_text("Action cancelled.", reply_markup=main_keyboard())
    return ConversationHandler.END

# ----------------- HEALTH CHECK SERVER FOR RENDER -----------------

def start_health_check_server(port: int):
    """Starts a minimal HTTP server on a daemon thread so Render Web Services detect an open port."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Class President Super-Bot is running 24/7!")

        def log_message(self, format, *args):
            return  # silence logs

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start health check HTTP server on port {port}: {e}")

# ----------------- APP BUILDER & RUNNER -----------------

def build_application(token: str):
    """Builds and wires up the Telegram Application."""
    app = ApplicationBuilder().token(token).build()

    # Core Navigation & Info Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("my_status", my_status_command))
    app.add_handler(CommandHandler("status", fund_status_command))
    app.add_handler(CommandHandler("spreadsheet", spreadsheet_command))
    app.add_handler(CommandHandler("excel", spreadsheet_command))
    app.add_handler(CommandHandler("master_report", master_report_command))
    app.add_handler(CommandHandler("backup_db", backup_db_command))

    # Attendance Commands
    app.add_handler(CommandHandler("attendance", attendance_menu_command))
    app.add_handler(CommandHandler("attendance_export", export_attendance_command))

    # Team Randomizer Command
    app.add_handler(CommandHandler("teams", teams_command))

    # Announcements Commands
    app.add_handler(CommandHandler("announcements", list_announcements_command))
    app.add_handler(CommandHandler("announce", create_announcement_command))

    # Photo/Document Receiver for KBZPay Slips
    app.add_handler(MessageHandler(filters.PHOTO | (filters.Document.IMAGE & ~filters.COMMAND), handle_photo_upload))

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

    # Callback Query Handler (Buttons)
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    # Persistent keyboard dispatcher
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_menu_dispatcher))

    return app

def run_bot():
    """Main execution entry point."""
    init_db()

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
        print("Run 'python setup_wizard.py' to configure your bot,")
        print("or set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    print("🤖 Starting Class President Super-Bot...")
    print("Press Ctrl+C in terminal to stop.")
    app = build_application(token)
    app.run_polling()

if __name__ == "__main__":
    run_bot()
