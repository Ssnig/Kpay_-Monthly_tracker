"""Database connector module providing student lookup with MongoDB and SQLite fallback."""

import pymongo
from db.database import init_db
from services.student_service import get_student_by_id, list_all_students

# Ensure local SQLite database is ready as fallback
init_db()

def _try_mongo_find(student_id):
    """Attempts to find student in MongoDB, returning None if MongoDB is unreachable."""
    try:
        myclient = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=500)
        mydb = myclient["Roll"]
        mystudents = mydb["RollNum"]
        return mystudents.find_one({"id": student_id})
    except Exception:
        return None

def find_student(roll_to_find):
    """Finds a student's name by their ID, checking MongoDB first with seamless fallback."""
    try:
        student_id = int(roll_to_find)
    except ValueError:
        print(f"\nError: Invalid ID '{roll_to_find}'. Please enter a number.")
        return None

    print("\nSearching for student...")

    # Try MongoDB first
    record = _try_mongo_find(student_id)
    if record:
        student_name = record.get("name", "Name not found in record")
        print(f"Found Student (MongoDB) -> ID: {student_id}, Name: {student_name}")
        return {"id": student_id, "name": student_name}

    # Fallback to SQLite/student_service
    student = get_student_by_id(student_id)
    if student:
        print(f"Found Student -> ID: {student['id']}, Name: {student['name']}")
        return student
    else:
        print(f"No student found with ID: {student_id}")
        return None

def list_all_student_names():
    """Lists the name of every student."""
    print("\n--- All Student Names ---")
    # Try MongoDB first
    try:
        myclient = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=500)
        mydb = myclient["Roll"]
        mystudents = mydb["RollNum"]
        all_students = list(mystudents.find({}))
        if all_students:
            for s in all_students:
                print(s.get("name", "Name not found in record"))
            return
    except Exception:
        pass

    # Fallback to SQLite
    students = list_all_students()
    if not students:
        print("No student records found.")
    else:
        for s in students:
            print(f"Roll {s['id']:2d}: {s['name']}")