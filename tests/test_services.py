import os
import tempfile
import pytest
from db.database import init_db, get_connection
from services.student_service import get_student_by_id, list_all_students, search_students
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
from services.export_service import export_fee_report_csv, export_financial_summary_csv

@pytest.fixture
def temp_db():
    """Provides an isolated temporary SQLite database populated with students."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path=path, seed_students=True)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_database_initialization_and_seeding(temp_db):
    """Verify that all 43 students are seeded from rollnum.json."""
    students = list_all_students(db_path=temp_db)
    assert len(students) == 43
    # Check first student
    assert students[0]["id"] == 1
    assert students[0]["name"] == "Htet Oo Wai"
    # Check last student
    assert students[-1]["id"] == 43
    assert students[-1]["name"] == "Zaw Htet Paing"

def test_student_lookup_and_search(temp_db):
    """Verify looking up and searching students."""
    s = get_student_by_id(5, db_path=temp_db)
    assert s is not None
    assert s["name"] == "Cho Lwin Thaw"

    # Invalid ID
    assert get_student_by_id(999, db_path=temp_db) is None
    assert get_student_by_id("abc", db_path=temp_db) is None

    # Search by partial name
    results = search_students("Aung", db_path=temp_db)
    assert len(results) >= 1
    assert all("aung" in r["name"].lower() or "aung" in str(r["id"]).lower() for r in results)

def test_fee_creation_and_payment_tracking(temp_db):
    """Verify creating a fee, recording payments, and verifying collection metrics."""
    fee_id = create_fee("October Dues", 5000.0, "2026-10-31", db_path=temp_db)
    assert fee_id is not None

    fee = get_fee(fee_id, db_path=temp_db)
    assert fee["title"] == "October Dues"
    assert fee["amount_per_student"] == 5000.0

    # Initial status (no payments)
    status_initial = get_fee_status(fee_id, db_path=temp_db)
    assert status_initial["total_students"] == 43
    assert status_initial["total_expected"] == 43 * 5000.0
    assert status_initial["total_collected"] == 0.0
    assert status_initial["paid_count"] == 0
    assert status_initial["unpaid_count"] == 43

    # Student 1 pays in full (5000)
    record_payment(fee_id, 1, 5000.0, "Cash paid", db_path=temp_db)
    # Student 2 pays partial (2000)
    record_payment(fee_id, 2, 2000.0, "Partial payment", db_path=temp_db)

    status_updated = get_fee_status(fee_id, db_path=temp_db)
    assert status_updated["total_collected"] == 7000.0
    assert status_updated["paid_count"] == 1
    assert status_updated["partial_count"] == 1
    assert status_updated["unpaid_count"] == 41

    # Student 2 pays remaining (3000)
    record_payment(fee_id, 2, 3000.0, "Remaining payment", db_path=temp_db)
    status_final = get_fee_status(fee_id, db_path=temp_db)
    assert status_final["total_collected"] == 10000.0
    assert status_final["paid_count"] == 2
    assert status_final["partial_count"] == 0
    assert status_final["unpaid_count"] == 41

def test_expense_and_financial_summary(temp_db):
    """Verify logging expenses and net treasury calculations."""
    fee_id = create_fee("Project Fund", 10000.0, db_path=temp_db)
    record_payment(fee_id, 1, 10000.0, db_path=temp_db)
    record_payment(fee_id, 2, 10000.0, db_path=temp_db)

    # Total collected = 20,000
    add_expense("Whiteboard markers", 3500.0, category="Stationery", spent_by="Treasury Head", notes="Bill #12", db_path=temp_db)
    add_expense("Class snacks", 6500.0, category="Refreshment", spent_by="Vice President", notes="Bill #13", db_path=temp_db)

    summary = get_financial_summary(db_path=temp_db)
    assert summary["total_income"] == 20000.0
    assert summary["total_expenses"] == 10000.0
    assert summary["net_balance"] == 10000.0
    assert summary["expense_count"] == 2
    assert summary["fee_count"] == 1

def test_export_reports(temp_db):
    """Verify CSV export functionality."""
    fee_id = create_fee("Trip Fund", 15000.0, db_path=temp_db)
    record_payment(fee_id, 1, 15000.0, db_path=temp_db)
    add_expense("Bus advance", 5000.0, category="Trip", db_path=temp_db)

    with tempfile.TemporaryDirectory() as tmpdir:
        fee_csv = os.path.join(tmpdir, "fee_report.csv")
        saved_fee_path = export_fee_report_csv(fee_id, fee_csv, db_path=temp_db)
        assert os.path.exists(saved_fee_path)
        with open(saved_fee_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "Trip Fund" in content
            assert "Htet Oo Wai" in content
            assert "PAID" in content

        summary_csv = os.path.join(tmpdir, "summary.csv")
        saved_summary_path = export_financial_summary_csv(summary_csv, db_path=temp_db)
        assert os.path.exists(saved_summary_path)
        with open(saved_summary_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "Bus advance" in content
            assert "Total Income (Collected)" in content
