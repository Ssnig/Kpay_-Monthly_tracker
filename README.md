# Class President Super-Bot & Management Platform

A modular management platform and Telegram bot tailored for **University Class Presidents** and student treasurers.

Automates classroom funds, subject-specific attendance tracking, AI-powered KBZPay payment slip parsing, teacher announcement RSVPs, assignment team randomizing, and color-coded Excel spreadsheet exports.

---

## 🚀 Core Features

### 1. 🤖 AI-Powered KBZPay Slip Reader (OCR & Deduplication)
- Students send their **KBZPay transfer screenshots** directly into the Telegram chat.
- Uses **Google Gemini Multimodal AI** to automatically extract:
  - **Transaction ID** (guards against duplicate screenshot reuse/fraud)
  - **Amount Transferred (MMK)**
  - **Payer Name & Phone**
  - **Timestamp**
- **Fuzzy Roster Matching**: Matches the payer's name to the student roster (handles Myanmar & English names) and prompts the president with a 1-tap `[✅ Record Payment]` button.

### 2. 📅 On-Demand Subject Attendance Tracker
- Take attendance for lectures, labs, or workshops whenever requested.
- Tagged by **Subject**, **Date**, and **Period/Slot**.
- Quick mobile marking: all students default to **PRESENT**; tap any roll number chip to toggle **ABSENT** or **LEAVE**.
- Exports directly to styled **Excel spreadsheets (.xlsx)** with attendance rates and color tags.

### 3. 📢 Teacher Announcements & Interest RSVP Polls
- Class president broadcasts notices from professors (workshops, hackathons, volunteers).
- Students tap **`[✋ I'm Interested / Sign Up]`** or **`[❌ Withdraw]`** directly under the message.
- Tracks real-time participant limits and exports participant lists for the professor.

### 4. 🎲 Assignment & Lab Project Team Randomizer
- Shuffles students fairly using cryptographic randomness.
- Generates balanced teams based on target members per team (e.g. 4 members/team) or total team count.
- Automatically assigns a **`👑 Team Leader`** for each group.
- Outputs an announcement card ready to share with the class.

### 5. 💰 Treasury Funds & Formatted Spreadsheets
- Create fee collection campaigns with target amounts and due dates.
- Real-time **Paid / Partial / Unpaid** tracking.
- Generates color-coded Excel spreadsheets (.xlsx):
  - 🟢 **PAID** (Green)
  - 🟡 **PARTIAL** (Yellow)
  - 🔴 **UNPAID** (Red)
- Multi-sheet Master Financial Workbook with summary, student matrix, transactions, and expenses.

### 6. 🛡️ Admin Protection & Multi-Class Packaging
- Only authorized Class Presidents (`ADMIN_USER_IDS`) can record payments, take attendance, or post announcements.
- Other students have read-only and self-service access (`/my_status <roll_no>`).
- Includes a 60-second **Setup Wizard** (`python setup_wizard.py`) so other class presidents can easily adopt and run this platform for their own classes.

---

## 📱 Telegram Commands Reference

| Command | Role | Description |
|---|---|---|
| `/start` | Everyone | Open interactive menu with 1-tap keyboard |
| `/help` | Everyone | View command manual and role badge |
| `/status [fee_id]` | Everyone | View fund status breakdown (Paid / Unpaid) |
| `/spreadsheet [fee_id]` | Everyone | Download formatted Excel payment spreadsheet |
| `/master_report` | Everyone | Download 4-sheet Master Excel Workbook |
| `/my_status <roll_no>` | Everyone | Student self-service balance & dues check |
| `/announcements` | Everyone | View active teacher notices and sign-up polls |
| *Send Photo* | Everyone | Send KBZPay slip screenshot for instant AI parsing |
| `/pay` | 👑 Admin | Interactive payment recording wizard |
| `/createfee` | 👑 Admin | Launch a new fee campaign |
| `/attendance` | 👑 Admin | Start on-demand subject attendance session |
| `/attendance_export <id>` | 👑 Admin | Download attendance session Excel sheet |
| `/announce <title> - <text>` | 👑 Admin | Broadcast teacher notice with RSVP buttons |
| `/teams [size] [subject]` | 👑 Admin | Randomize students into groups with leaders |
| `/backup_db` | 👑 Admin | Instant SQLite database snapshot sent to chat |

---

## ⚡ Quick Start & Deployment

### 1. Run the Setup Wizard
```powershell
python setup_wizard.py
```
This configures your Class Name, Admin Telegram IDs, Bot Token, and Gemini API Key.

### 2. Start the Bot Locally
```powershell
python telegram_bot.py
```

### 3. Run the CLI Dashboard
```powershell
python main.py
```

### 4. 24/7 Cloud Deployment (Render)
1. Push this repository to GitHub.
2. In [Render.com](https://render.com), create a new **Web Service** from your repo.
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`: *[Your Bot Token from @BotFather]*
   - `GEMINI_API_KEY`: *[Your Gemini API Key from Google AI Studio]*
   - `ADMIN_USER_IDS`: *[Your Telegram User ID from @userinfobot]*
4. The bot will automatically start its HTTP health-server on `$PORT` and run 24/7!

---

## 🧪 Automated Tests
Run the test suite to verify all services:
```powershell
python -m pytest -v
```
