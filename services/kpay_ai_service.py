"""
Multi-Provider KPay (KBZPay) Payment Slip Auto-Reader and Roster Matcher.

Supports:
1. Local Offline Engine (OpenCV + EasyOCR, 100% free, zero API keys)
2. Custom Model / Endpoint (Connect your own custom AI model, Flask, FastAPI, Ollama)
3. Gemini Multimodal API (Optional fallback)

Includes duplicate receipt protection and fuzzy student roster matching.
"""

import os
import re
import json
import base64
import difflib
import logging
from pathlib import Path
from db.database import get_connection
from services.student_service import list_all_students

logger = logging.getLogger("KPay_AI_Service")
BASE_DIR = Path(__file__).resolve().parent.parent

_EASYOCR_READER = None

def get_ai_config():
    """Reads AI provider configuration from class_config.json or bot_config.json."""
    cfg = {}
    config_paths = [BASE_DIR / "class_config.json", BASE_DIR / "bot_config.json"]
    for cp in config_paths:
        if cp.exists():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k not in cfg or not cfg[k]:
                            cfg[k] = v
            except Exception:
                pass
    return cfg

def check_duplicate_kpay_transaction(transaction_id, db_path=None):
    """Checks if a KBZPay transaction ID was already recorded."""
    if not transaction_id:
        return None

    clean_tx = str(transaction_id).strip()
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT kr.id, kr.transaction_id, kr.student_id, kr.fee_id, kr.amount,
               kr.payer_name, kr.verified_at, s.name AS student_name, f.title AS fee_title
        FROM kpay_receipts kr
        LEFT JOIN students s ON kr.student_id = s.id
        LEFT JOIN fees f ON kr.fee_id = f.id
        WHERE kr.transaction_id = ?
    """, (clean_tx,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_verified_kpay_receipt(transaction_id, student_id, fee_id, payment_id, payer_name, amount, slip_timestamp="", raw_response="", db_path=None):
    """Saves a verified KBZPay slip into the audit log."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO kpay_receipts
        (transaction_id, student_id, fee_id, payment_id, payer_name, amount, slip_timestamp, raw_ai_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(transaction_id).strip(),
        int(student_id) if student_id else None,
        int(fee_id) if fee_id else None,
        int(payment_id) if payment_id else None,
        str(payer_name or ""),
        float(amount),
        str(slip_timestamp or ""),
        str(raw_response or "")
    ))
    rec_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rec_id

def match_payer_to_student(payer_name, class_name=None, threshold=0.55, db_path=None):
    """
    Fuzzy-matches the OCR payer name against the student roster.
    Removes common Burmese honorifics (U, Daw, Ko, Ma) and compares token similarity.
    """
    if not payer_name:
        return None, 0.0, []

    students = list_all_students(class_name=class_name, db_path=db_path)
    if not students:
        return None, 0.0, []

    def normalize(text):
        t = text.lower().strip()
        t = re.sub(r"\b(u|daw|ko|ma|mg|dr)\b", "", t)
        t = re.sub(r"[^a-zA-Z0-9\u1000-\u109F\s]", " ", t)
        return " ".join(t.split())

    clean_payer = normalize(payer_name)
    candidates = []

    for s in students:
        clean_sname = normalize(s["name"])
        ratio = difflib.SequenceMatcher(None, clean_payer, clean_sname).ratio()

        payer_tokens = set(clean_payer.split())
        student_tokens = set(clean_sname.split())
        token_overlap = len(payer_tokens.intersection(student_tokens))
        if token_overlap > 0:
            token_score = token_overlap / max(len(payer_tokens), len(student_tokens))
            combined_score = max(ratio, (ratio * 0.4 + token_score * 0.6))
        else:
            combined_score = ratio

        if clean_sname in clean_payer or clean_payer in clean_sname:
            combined_score = max(combined_score, 0.85)

        candidates.append({
            "student": s,
            "score": round(combined_score * 100, 1)
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    best = candidates[0] if candidates else None
    if best and best["score"] >= (threshold * 100):
        return best["student"], best["score"], candidates[:3]
    return None, (best["score"] if best else 0.0), candidates[:3]

# ----------------- PROVIDER 1: YOUR OWN CUSTOM AI MODEL ENDPOINT -----------------

def parse_with_custom_endpoint(image_bytes, endpoint_url, auth_token=None):
    """
    Calls your own custom AI model endpoint (e.g. FastAPI, Flask, PyTorch, Ollama).
    Sends image as base64 JSON payload and expects standardized slip JSON.
    """
    import requests

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    payload = {
        "image_base64": b64_img,
        "filename": "kpay_slip.jpg"
    }

    try:
        resp = requests.post(endpoint_url, json=payload, headers=headers, timeout=25)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"CUSTOM_ENDPOINT_HTTP_{resp.status_code}",
                "message": f"Custom AI endpoint returned error: {resp.text[:200]}"
            }

        res_json = resp.json()
        return {
            "success": True,
            "data": {
                "transaction_id": str(res_json.get("transaction_id", "")).strip(),
                "amount": float(res_json.get("amount", 0.0) or 0.0),
                "payer_name": str(res_json.get("payer_name", "")).strip(),
                "date_time": str(res_json.get("date_time", "")).strip(),
                "is_successful": bool(res_json.get("is_successful", True))
            },
            "raw": resp.text
        }
    except Exception as e:
        logger.error(f"Error calling custom AI endpoint ({endpoint_url}): {e}")
        return {
            "success": False,
            "error": "CUSTOM_ENDPOINT_EXCEPTION",
            "message": f"Could not reach your custom AI endpoint: {e}"
        }

# ----------------- PROVIDER 2: 100% OFFLINE LOCAL OCR ENGINE -----------------

def get_easyocr_reader():
    """Lazy loader for EasyOCR reader to save startup memory."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception as e:
            logger.warning(f"Could not load EasyOCR: {e}")
            _EASYOCR_READER = False
    return _EASYOCR_READER

def parse_with_local_ocr(image_bytes):
    """
    100% Offline local OCR engine using OpenCV and EasyOCR.
    Requires ZERO API keys and ZERO external network connections.
    """
    import numpy as np
    import cv2
    from PIL import Image
    import io

    # Decode bytes to OpenCV image
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(image)

    extracted_texts = []
    reader = get_easyocr_reader()

    if reader:
        try:
            results = reader.readtext(img_np)
            extracted_texts = [text for (_, text, conf) in results if conf > 0.2]
        except Exception as e:
            logger.warning(f"EasyOCR extraction exception: {e}")

    full_text = "\n".join(extracted_texts)

    # Heuristic Regex Extraction tailored for KBZPay Slips
    # 1. Transaction ID: 16-20 digit number starting with 0100 or 0200
    tx_match = re.search(r"\b(0100\d{12,18}|0200\d{12,18}|\d{16,20})\b", full_text)
    transaction_id = tx_match.group(1) if tx_match else ""

    # 2. Amount: e.g. -50,000.00 Ks or 5,000 MMK
    amt_match = re.search(r"-?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?|[0-9]{3,7}(?:\.[0-9]{2})?)\s*(?:MMK|Ks|Kyat|ks)?", full_text, re.IGNORECASE)
    amount = 0.0
    if amt_match:
        try:
            amount = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # 3. Date & Time: DD/MM/YYYY HH.MM:SS or YYYY-MM-DD HH:MM:SS
    date_match = re.search(r"(\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\s+\d{1,2}[.:]\d{2}(?:[.:]\d{2})?)", full_text)
    date_time = date_match.group(1) if date_match else ""

    # 4. Payer / Recipient Name: Look for name patterns like "Name (******8533)" or following 'From' / 'Payer'
    payer_name = ""
    # Pattern: Name followed by masked phone number in parentheses
    name_with_phone = re.search(r"([A-Za-z\s\n]{3,35})\s*\(\*{2,}\d{2,4}\)", full_text)
    if name_with_phone:
        raw_name = name_with_phone.group(1).strip()
        # Clean any leading 'Transfer', 'From', etc.
        payer_name = re.sub(r"^(Transfer|From|Payer|Sender)[\s\n:]*", "", raw_name, flags=re.IGNORECASE).strip()
    else:
        for idx, line in enumerate(extracted_texts):
            if any(keyword in line.lower() for keyword in ["from", "payer", "sender", "transfer"]):
                if idx + 1 < len(extracted_texts):
                    candidate = extracted_texts[idx + 1].strip()
                    if not any(c in candidate for c in ["0100", "KBZ", "E-Receipt"]):
                        payer_name = candidate
                        break

    # If transaction_id or amount found, consider it a success
    if transaction_id or amount > 0 or payer_name:
        return {
            "success": True,
            "data": {
                "transaction_id": transaction_id or "TXN_MANUAL_VERIFY",
                "amount": amount,
                "payer_name": payer_name or "Detected from Slip",
                "date_time": date_time,
                "is_successful": True
            },
            "raw": full_text
        }

    return {
        "success": False,
        "error": "LOCAL_OCR_NO_MATCH",
        "message": "Local OCR could not find standard KBZPay transaction fields in this image."
    }

# ----------------- PROVIDER 3: OPTIONAL GEMINI FALLBACK -----------------

def parse_with_gemini(image_bytes, api_key):
    """Optional cloud multimodal fallback."""
    import requests

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = """
    Extract KBZPay transfer slip fields in JSON:
    {"transaction_id": "...", "amount": 5000, "payer_name": "...", "date_time": "...", "is_successful": true}
    Output ONLY valid JSON.
    """
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}]}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=25)
        if resp.status_code != 200:
            return {"success": False, "error": f"API_{resp.status_code}", "message": resp.text[:200]}
        res_json = resp.json()
        raw = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        clean = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return {"success": True, "data": json.loads(clean), "raw": raw}
    except Exception as e:
        return {"success": False, "error": "GEMINI_ERROR", "message": str(e)}

# ----------------- HIGH-LEVEL ORCHESTRATOR -----------------

def analyze_kpay_slip(image_path_or_bytes, class_name=None, db_path=None):
    """
    Orchestrates slip analysis using the configured AI engine:
    1. Routes to Local OCR, Custom AI Endpoint, or Gemini based on config.
    2. Runs anti-fraud duplicate transaction ID protection.
    3. Fuzzy-matches payer against the student roster.
    """
    if isinstance(image_path_or_bytes, (str, Path)):
        with open(image_path_or_bytes, "rb") as f:
            image_bytes = f.read()
    else:
        image_bytes = image_path_or_bytes

    cfg = get_ai_config()
    provider = cfg.get("kpay_ai_provider", "local_ocr").lower().strip()

    # Route based on provider
    if provider == "custom_endpoint" and cfg.get("custom_ai_endpoint"):
        parse_result = parse_with_custom_endpoint(
            image_bytes,
            cfg["custom_ai_endpoint"],
            auth_token=cfg.get("custom_ai_token")
        )
    elif provider == "gemini" and cfg.get("gemini_api_key"):
        parse_result = parse_with_gemini(image_bytes, cfg["gemini_api_key"])
    else:
        # Default: 100% Offline Local Engine
        parse_result = parse_with_local_ocr(image_bytes)
        # If local OCR returned no fields, try custom endpoint fallback if configured
        if not parse_result.get("success") and cfg.get("custom_ai_endpoint"):
            parse_result = parse_with_custom_endpoint(image_bytes, cfg["custom_ai_endpoint"], cfg.get("custom_ai_token"))

    if not parse_result.get("success"):
        return parse_result

    data = parse_result["data"]
    tx_id = data.get("transaction_id", "")
    amount = float(data.get("amount", 0.0) or 0.0)
    payer = data.get("payer_name", "")
    timestamp = data.get("date_time", "")

    # Duplicate transaction check
    duplicate = check_duplicate_kpay_transaction(tx_id, db_path=db_path) if tx_id else None

    # Match payer against student roster
    student, score, top_matches = match_payer_to_student(payer, class_name=class_name, db_path=db_path)

    return {
        "success": True,
        "provider_used": provider,
        "is_duplicate": duplicate is not None,
        "duplicate_info": duplicate,
        "transaction_id": tx_id,
        "amount": amount,
        "payer_name": payer,
        "date_time": timestamp,
        "matched_student": student,
        "confidence_score": score,
        "top_matches": top_matches,
        "raw_ai": parse_result.get("raw", "")
    }
