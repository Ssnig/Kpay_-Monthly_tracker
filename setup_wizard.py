"""
Class President Bot-in-a-Box Setup Wizard.

Guides any Class President through a 60-second interactive setup
to customize their bot for their specific class, subjects, and credentials.
"""

import sys
import json
from pathlib import Path
from db.database import init_db
from services.attendance_service import add_subject, list_subjects

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "class_config.json"
BOT_CONFIG_FILE = BASE_DIR / "bot_config.json"

def run_wizard():
    print("=" * 60)
    print("🎓 CLASS PRESIDENT PLATFORM - QUICK SETUP WIZARD")
    print("=" * 60)
    print("This wizard configures your bot for your specific class.\n")

    current_cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                current_cfg = json.load(f)
        except Exception:
            pass

    # 1. Class Name
    def_cname = current_cfg.get("class_name", "EC-Year3")
    cname = input(f"1. Enter Class Code/Batch [Default: '{def_cname}']: ").strip() or def_cname

    # 2. Class Title
    def_title = current_cfg.get("class_title", "Electronics & Communication Engineering")
    title = input(f"2. Enter Class Full Title [Default: '{def_title}']: ").strip() or def_title

    # 3. Admin Telegram IDs
    def_admins = current_cfg.get("admin_telegram_ids", [])
    def_admin_str = ", ".join(str(i) for i in def_admins)
    admin_input = input(f"3. Enter Admin Telegram User ID(s) (comma-separated, get from @userinfobot) [Current: {def_admin_str or 'None'}]: ").strip()
    if admin_input:
        admins = [int(x.strip()) for x in admin_input.split(",") if x.strip().isdigit()]
    else:
        admins = def_admins

    # 4. Telegram Bot Token
    def_tok = current_cfg.get("telegram_bot_token", "")
    mask_tok = (def_tok[:6] + "..." + def_tok[-4:]) if def_tok else "None"
    tok_input = input(f"4. Enter Telegram Bot Token from @BotFather [Current: {mask_tok}]: ").strip()
    bot_token = tok_input or def_tok

    # 5. KPay AI Engine Provider
    cur_provider = current_cfg.get("kpay_ai_provider", "local_ocr")
    print(f"\n5. Select KPay AI Engine Provider [Current: {cur_provider}]:")
    print("   [1] 100% Offline Local Engine (OpenCV + EasyOCR - No API key needed) [Recommended]")
    print("   [2] My Own Custom AI Model Endpoint (FastAPI, Flask, PyTorch, Ollama)")
    print("   [3] Google Gemini API Key")
    ai_choice = input("Enter choice (1, 2, or 3) [Default: 1]: ").strip() or ("2" if cur_provider == "custom_endpoint" else ("3" if cur_provider == "gemini" else "1"))

    custom_endpoint = current_cfg.get("custom_ai_endpoint", "http://localhost:8000/parse_slip")
    custom_token = current_cfg.get("custom_ai_token", "")
    gem_key = current_cfg.get("gemini_api_key", "")

    if ai_choice == "2":
        ai_provider = "custom_endpoint"
        custom_endpoint = input(f"   Enter Custom Model URL [Current: {custom_endpoint}]: ").strip() or custom_endpoint
        custom_token = input("   Enter Bearer Auth Token (if required, or leave blank): ").strip() or custom_token
    elif ai_choice == "3":
        ai_provider = "gemini"
        mask_gem = (gem_key[:6] + "..." + gem_key[-4:]) if gem_key else "None"
        gem_input = input(f"   Enter Gemini API Key [Current: {mask_gem}]: ").strip()
        gem_key = gem_input or gem_key
    else:
        ai_provider = "local_ocr"

    # 6. Save Configuration
    new_cfg = {
        "class_name": cname,
        "class_title": title,
        "admin_telegram_ids": admins,
        "telegram_bot_token": bot_token,
        "kpay_ai_provider": ai_provider,
        "custom_ai_endpoint": custom_endpoint,
        "custom_ai_token": custom_token,
        "gemini_api_key": gem_key,
        "default_subjects": current_cfg.get("default_subjects", [
            "Digital Signal Processing",
            "Microcontrollers & Embedded Systems",
            "Communication Systems",
            "Electronic Circuits"
        ]),
        "google_sheet_url": current_cfg.get("google_sheet_url", "")
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(new_cfg, f, indent=2)

    # Sync bot_config.json
    with open(BOT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "telegram_bot_token": bot_token,
            "kpay_ai_provider": ai_provider,
            "custom_ai_endpoint": custom_endpoint,
            "custom_ai_token": custom_token,
            "gemini_api_key": gem_key,
            "admin_telegram_ids": admins
        }, f, indent=2)
        }, f, indent=2)

    # Initialize Database
    print("\n⚙️ Initializing database tables...")
    init_db()

    print("\n" + "=" * 60)
    print("🎉 SETUP COMPLETE!")
    print(f"Class: {title} ({cname})")
    print(f"Admins: {len(admins)} registered")
    print(f"Bot Token: {'Configured ✅' if bot_token else 'Missing ⚠️'}")
    print(f"Gemini AI Key: {'Configured ✅' if gem_key else 'Missing ⚠️'}")
    print("=" * 60)
    print("To start your bot, run: python telegram_bot.py")

if __name__ == "__main__":
    run_wizard()

