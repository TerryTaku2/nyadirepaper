"""Administrator-only routes: intakes and student accounts."""
import re
import sqlite3
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import config
from .auth import require_admin, student_public
from .db import get_db
from .security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$")


# ------------------------------------------------------------------- intakes
class IntakeIn(BaseModel):
    year: int = Field(ge=1990, le=2100)
    ecd_number: int = Field(ge=1, le=9999)
    junior_number: int = Field(ge=1, le=9999)


def _intake_out(r) -> dict:
    return {"number": str(r["number"]), "year": str(r["year"]), "name": str(r["year"]), "type": r["type"]}


@router.get("/intakes")
def list_intakes():
    with get_db() as db:
        return [_intake_out(r) for r in db.execute("SELECT * FROM intakes ORDER BY number")]


@router.post("/intakes", status_code=201)
def create_intakes(body: IntakeIn):
    """Create an ECD intake and a Junior intake for one year."""
    if body.ecd_number == body.junior_number:
        raise HTTPException(422, "ECD and Junior must use different intake numbers.")
    with get_db() as db:
        taken = db.execute("SELECT number FROM intakes WHERE number IN (?, ?)",
                           (body.ecd_number, body.junior_number)).fetchall()
        if taken:
            nums = ", ".join(str(r["number"]) for r in taken)
            raise HTTPException(409, f"Intake number {nums} is already in use. "
                                     "Choose different numbers or remove the existing intake first.")
        db.execute("INSERT INTO intakes(number, year, type) VALUES (?,?,'ECD')", (body.ecd_number, body.year))
        db.execute("INSERT INTO intakes(number, year, type) VALUES (?,?,'Junior')", (body.junior_number, body.year))
        return [_intake_out(r) for r in db.execute("SELECT * FROM intakes ORDER BY number")]


@router.delete("/intakes/{number}")
def delete_intake(number: int):
    """Removes the intake and every student account in it."""
    with get_db() as db:
        if not db.execute("SELECT 1 FROM intakes WHERE number = ?", (number,)).fetchone():
            raise HTTPException(404, "Intake not found.")
        removed = db.execute("SELECT COUNT(*) FROM students WHERE intake_number = ?", (number,)).fetchone()[0]
        db.execute("DELETE FROM intakes WHERE number = ?", (number,))   # cascades to students + sessions
        return {"ok": True, "studentsRemoved": removed}


# ------------------------------------------------------------------ students
class StudentIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=40)
    intake: int
    type: str
    password: str = Field(min_length=1, max_length=128)    # temporary registration password
    name: str = Field(default="", max_length=100)


class BulkRow(BaseModel):
    student_id: str = Field(max_length=40)
    name: str = Field(default="", max_length=100)
    password: str = Field(default="", max_length=128)


class BulkIn(BaseModel):
    intake: int
    type: str
    rows: List[BulkRow] = Field(max_length=2000)


def _check_id_for_type(student_id: str, type_: str) -> str | None:
    """Returns an error message, or None when the ID is acceptable."""
    if not STUDENT_ID_RE.match(student_id):
        return "Student ID may only contain letters, numbers, '-', '_' and '.' (3-40 characters)."
    up = student_id.upper()
    if type_ == "ECD" and not up.startswith("E24"):
        return "ECD Student IDs must start with E24."
    if type_ == "Junior" and not student_id.startswith("24"):
        return "Junior Student IDs must start with 24."
    return None


def _check_intake_type(db: sqlite3.Connection, intake: int, type_: str) -> None:
    if type_ not in config.STUDENT_TYPES:
        raise HTTPException(422, "Student type must be Junior or ECD.")
    row = db.execute("SELECT type FROM intakes WHERE number = ?", (intake,)).fetchone()
    if not row:
        raise HTTPException(404, f"Intake {intake} does not exist.")
    if row["type"] != type_:
        raise HTTPException(422, f"Intake {intake} is a {row['type']} intake, not {type_}.")


@router.get("/students")
def list_students():
    with get_db() as db:
        rows = db.execute("SELECT * FROM students ORDER BY intake_number, type, student_id").fetchall()
        return [student_public(r) for r in rows]


@router.post("/students", status_code=201)
def add_student(body: StudentIn):
    sid = body.student_id.strip()
    err = _check_id_for_type(sid, body.type)
    if err:
        raise HTTPException(422, err)
    with get_db() as db:
        _check_intake_type(db, body.intake, body.type)
        if db.execute("SELECT 1 FROM students WHERE student_id = ?", (sid,)).fetchone():
            raise HTTPException(409, "That Student ID already exists.")
        db.execute("INSERT INTO students(student_id, full_name, password_hash, registered, intake_number, type, created_at)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (sid, body.name.strip(), hash_password(body.password), 0, body.intake, body.type, int(time.time())))
        s = db.execute("SELECT * FROM students WHERE student_id = ?", (sid,)).fetchone()
        return student_public(s)


@router.post("/students/bulk")
def bulk_add_students(body: BulkIn):
    added, skipped = 0, []
    with get_db() as db:
        _check_intake_type(db, body.intake, body.type)
        seen: set[str] = set()
        for row in body.rows:
            sid = row.student_id.strip()
            reason = None
            if not sid or not row.password:
                reason = "missing ID or password"
            elif _check_id_for_type(sid, body.type):
                reason = _check_id_for_type(sid, body.type)
            elif sid.upper() in seen or db.execute("SELECT 1 FROM students WHERE student_id = ?", (sid,)).fetchone():
                reason = "duplicate ID"
            if reason:
                skipped.append({"id": sid, "reason": reason})
                continue
            seen.add(sid.upper())
            db.execute("INSERT INTO students(student_id, full_name, password_hash, registered, intake_number, type, created_at)"
                       " VALUES (?,?,?,?,?,?,?)",
                       (sid, row.name.strip(), hash_password(row.password), 0, body.intake, body.type, int(time.time())))
            added += 1
    return {"added": added, "skipped": skipped}


@router.post("/students/{student_id}/unregister")
def unregister_student(student_id: str):
    """Reset the account to the temporary password so the student can register again."""
    with get_db() as db:
        s = db.execute("SELECT id FROM students WHERE student_id = ?", (student_id,)).fetchone()
        if not s:
            raise HTTPException(404, "Student not found.")
        db.execute("UPDATE students SET registered = 0, password_hash = ? WHERE id = ?",
                   (hash_password(config.REGISTRATION_PASSWORD), s["id"]))
        db.execute("DELETE FROM sessions WHERE student_id = ?", (s["id"],))
    return {"ok": True, "temporaryPassword": config.REGISTRATION_PASSWORD}


@router.delete("/students/{student_id}")
def delete_student(student_id: str):
    with get_db() as db:
        cur = db.execute("DELETE FROM students WHERE student_id = ?", (student_id,))   # cascades to sessions
        if not cur.rowcount:
            raise HTTPException(404, "Student not found.")
    return {"ok": True}
