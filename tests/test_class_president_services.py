import os
import tempfile
import pytest
from db.database import init_db, get_connection
from services.attendance_service import (
    add_subject,
    list_subjects,
    get_subject,
    create_attendance_session,
    update_student_attendance,
    mark_absentees,
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
    match_payer_to_student,
    check_duplicate_kpay_transaction,
    save_verified_kpay_receipt,
)
from services.google_sync_service import get_google_sync_status

@pytest.fixture
def temp_db():
    """Provides an isolated temporary SQLite database populated with students and subjects."""
    import gc
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path=path, seed_students=True)
    yield path
    gc.collect()
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass

# ----------------- ATTENDANCE TESTS -----------------

def test_attendance_lifecycle(temp_db):
    """Test full attendance flow: create subject, take session, mark absentees, and export."""
    # 1. Add Subject
    sub = add_subject("Digital Communications", "DCOMM", db_path=temp_db)
    assert sub["id"] is not None
    assert sub["name"] == "Digital Communications"

    # 2. Create Attendance Session
    sess_id = create_attendance_session(sub["id"], period="Morning Lecture", db_path=temp_db)
    assert sess_id is not None

    details_init = get_session_details(sess_id, db_path=temp_db)
    assert details_init["total_students"] == 43
    assert details_init["present_count"] == 43
    assert details_init["absent_count"] == 0
    assert details_init["attendance_rate_percent"] == 100.0

    # 3. Mark Roll 5 and Roll 12 as ABSENT
    mark_absentees(sess_id, [5, 12], db_path=temp_db)

    # 4. Mark Roll 20 as LEAVE
    update_student_attendance(sess_id, 20, "LEAVE", "Doctor appointment", db_path=temp_db)

    details_after = get_session_details(sess_id, db_path=temp_db)
    assert details_after["present_count"] == 40
    assert details_after["absent_count"] == 2
    assert details_after["leave_count"] == 1
    assert details_after["attendance_rate_percent"] == round(40 / 43 * 100, 1)

    # 5. Export to Excel
    with tempfile.TemporaryDirectory() as tmpdir:
        excel_path = os.path.join(tmpdir, "attendance_report.xlsx")
        out_f = export_attendance_excel(sess_id, excel_path, db_path=temp_db)
        assert os.path.exists(out_f)

# ----------------- TEAM RANDOMIZER TESTS -----------------

def test_team_randomizer(temp_db):
    """Test randomizing 43 students into teams with designated leaders."""
    # Team size 4 -> 43 students should produce 10 teams (with remainder distributed)
    res = generate_teams(group_size=4, subject_name="DSP Project", db_path=temp_db)
    assert res["total_students"] == 43
    assert res["team_count"] >= 10

    # Ensure every student is assigned to exactly one team
    assigned_ids = []
    for t in res["teams"]:
        assert t["member_count"] >= 3  # balanced sizes
        assert t["leader"] is not None  # leader assigned
        assert any(m["is_leader"] for m in t["members"])
        assigned_ids.extend(m["id"] for m in t["members"])

    assert len(assigned_ids) == 43
    assert len(set(assigned_ids)) == 43  # no duplicate assignments

    # Verify markdown formatting contains headers and team markers
    assert "PROJECT & ASSIGNMENT TEAMS FOR *DSP PROJECT*" in res["formatted_markdown"]
    assert "👑 *Leader:*" in res["formatted_markdown"]

# ----------------- ANNOUNCEMENT & RSVP TESTS -----------------

def test_announcements_and_rsvp_flow(temp_db):
    """Test creating teacher notices, RSVP signup, slot caps, and withdrawals."""
    # Create notice with max 2 spots
    ann_id = create_announcement(
        "Robotics Hackathon",
        "Looking for 2 students to join university robotics team.",
        max_slots=2,
        db_path=temp_db
    )
    assert ann_id is not None

    # Student 1 signs up
    r1 = rsvp_student(ann_id, 1, telegram_user_id=1001, db_path=temp_db)
    assert r1["status"] == "SUCCESS"

    # Duplicate sign up prevented
    r_dup = rsvp_student(ann_id, 1, telegram_user_id=1001, db_path=temp_db)
    assert r_dup["status"] == "ALREADY_REGISTERED"

    # Student 2 signs up -> reaches capacity (2/2)
    r2 = rsvp_student(ann_id, 2, telegram_user_id=1002, db_path=temp_db)
    assert r2["status"] == "SUCCESS"

    details = get_announcement_details(ann_id, db_path=temp_db)
    assert details["rsvp_count"] == 2
    assert details["is_full"] is True

    # Student 3 tries to sign up when full
    with pytest.raises(ValueError, match="slots have been filled"):
        rsvp_student(ann_id, 3, telegram_user_id=1003, db_path=temp_db)

    # Student 1 withdraws
    assert withdraw_rsvp(ann_id, 1, db_path=temp_db) is True
    details_after_withdraw = get_announcement_details(ann_id, db_path=temp_db)
    assert details_after_withdraw["rsvp_count"] == 1
    assert details_after_withdraw["is_full"] is False

# ----------------- KPAY AI & FUZZY MATCHING TESTS -----------------

def test_kpay_payer_matching_and_deduplication(temp_db):
    """Test fuzzy roster matching and duplicate KBZPay slip protection."""
    from services.treasury_service import create_fee, record_payment

    # Student in roster: #05 Cho Lwin Thaw
    st, score, top = match_payer_to_student("Daw Cho Lwin Thaw", db_path=temp_db)
    assert st is not None
    assert st["id"] == 5
    assert st["name"] == "Cho Lwin Thaw"
    assert score >= 75.0

    # Student in roster: #43 Zaw Htet Paing
    st2, score2, _ = match_payer_to_student("U Zaw Htet Paing", db_path=temp_db)
    assert st2 is not None
    assert st2["id"] == 43

    # Duplicate slip check
    tx_id = "0100458921849204"
    assert check_duplicate_kpay_transaction(tx_id, db_path=temp_db) is None

    # Create fee and payment to satisfy foreign keys
    fee_id = create_fee("Test November Dues", 5000.0, db_path=temp_db)
    pay_id = record_payment(fee_id, 5, 5000.0, "KPay Test", db_path=temp_db)

    # Save slip
    save_verified_kpay_receipt(
        transaction_id=tx_id,
        student_id=5,
        fee_id=fee_id,
        payment_id=pay_id,
        payer_name="Daw Cho Lwin Thaw",
        amount=5000.0,
        slip_timestamp="2026-10-31 10:00:00",
        db_path=temp_db
    )

    # Duplicate check now flags it!
    dup = check_duplicate_kpay_transaction(tx_id, db_path=temp_db)
    assert dup is not None
    assert dup["transaction_id"] == tx_id
    assert dup["student_id"] == 5
    assert dup["amount"] == 5000.0

def test_custom_endpoint_parsing_and_mock(monkeypatch, temp_db):
    """Test routing to user's custom AI model endpoint."""
    from services.kpay_ai_service import parse_with_custom_endpoint, analyze_kpay_slip

    class MockResponse:
        status_code = 200
        text = '{"transaction_id": "0100998877665544", "amount": 10000.0, "payer_name": "Cho Lwin Thaw", "date_time": "2026-10-31 18:00:00"}'
        def json(self):
            return {
                "transaction_id": "0100998877665544",
                "amount": 10000.0,
                "payer_name": "Cho Lwin Thaw",
                "date_time": "2026-10-31 18:00:00",
                "is_successful": True
            }

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MockResponse())

    # Call custom endpoint parser directly
    res = parse_with_custom_endpoint(b"fake_image_bytes", "http://localhost:8000/parse_slip")
    assert res["success"] is True
    assert res["data"]["transaction_id"] == "0100998877665544"
    assert res["data"]["amount"] == 10000.0
    assert res["data"]["payer_name"] == "Cho Lwin Thaw"

    # Test orchestration via analyze_kpay_slip with mock config
    from services import kpay_ai_service
    monkeypatch.setattr(kpay_ai_service, "get_ai_config", lambda: {
        "kpay_ai_provider": "custom_endpoint",
        "custom_ai_endpoint": "http://localhost:8000/parse_slip"
    })

    analysis = analyze_kpay_slip(b"fake_image_bytes", db_path=temp_db)
    assert analysis["success"] is True
    assert analysis["provider_used"] == "custom_endpoint"
    assert analysis["transaction_id"] == "0100998877665544"
    assert analysis["matched_student"]["id"] == 5  # Cho Lwin Thaw matches student 5!
    assert analysis["matched_student"]["name"] == "Cho Lwin Thaw"

# ----------------- GOOGLE SYNC STATUS TESTS -----------------

def test_google_sync_status():
    """Verify non-blocking Google status reporting."""
    status = get_google_sync_status()
    assert "enabled" in status
    assert "message" in status
