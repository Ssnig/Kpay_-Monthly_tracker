import pytest
import databaseConnect

def test_database_connect_find_student(capsys):
    """Test find_student backward-compatible function."""
    res = databaseConnect.find_student(1)
    captured = capsys.readouterr()
    assert res is not None
    assert res["id"] == 1
    assert res["name"] == "Htet Oo Wai"
    assert "Found Student" in captured.out

def test_database_connect_invalid_roll(capsys):
    """Test find_student with invalid input."""
    res = databaseConnect.find_student("invalid")
    captured = capsys.readouterr()
    assert res is None
    assert "Error: Invalid ID" in captured.out

def test_database_connect_list_all(capsys):
    """Test list_all_student_names backward-compatible function."""
    databaseConnect.list_all_student_names()
    captured = capsys.readouterr()
    assert "All Student Names" in captured.out
    assert "Htet Oo Wai" in captured.out
    assert "Zaw Htet Paing" in captured.out
