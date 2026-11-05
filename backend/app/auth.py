"""Session handling, FastAPI auth dependencies and the login / register / logout routes."""
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import config
from .db import get_db
from .security import (burn_password_check, hash_password, new_token, throttle,
                       token_hash, verify_password)

router = APIRouter(prefix="/api", tags=["auth"])


# ----------------------------------------------------------------- sessions
def _start_session(db, response: Response, *, admin_id=None, student_id=None, hours: int) -> None:
    token = new_token()
    db.execute("INSERT INTO sessions(token_hash, admin_id, student_id, expires_at) VALUES (?,?,?,?)",
               (token_hash(token), admin_id, student_id, int(time.time()) + hours * 3600))
    response.set_cookie(config.COOKIE_NAME, token, max_age=hours * 3600, httponly=True,
                        samesite="strict", secure=config.COOKIE_SECURE, path="/")


def _end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        with get_db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
    response.delete_cookie(config.COOKIE_NAME, path="/")


def get_principal(request: Request) -> Optional[dict]:
    """The logged-in admin or student for this request, or None."""
    token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        return None
    with get_db() as db:
        row = db.execute("SELECT admin_id, student_id, expires_at FROM sessions WHERE token_hash = ?",
                         (token_hash(token),)).fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
            return None
        if row["admin_id"] is not None:
            a = db.execute("SELECT id, username, role FROM admins WHERE id = ?",
                           (row["admin_id"],)).fetchone()
            return {"kind": "admin", "id": a["id"], "username": a["username"], "role": a["role"]} if a else None
        s = db.execute("SELECT id, student_id, full_name, type, intake_number FROM students WHERE id = ?",
                       (row["student_id"],)).fetchone()
        if not s:
            return None
        return {"kind": "student", "id": s["id"], "student_id": s["student_id"],
                "name": s["full_name"], "type": s["type"], "intake": s["intake_number"]}


def require_admin(request: Request) -> dict:
    p = get_principal(request)
    if not p or p["kind"] != "admin":
        raise HTTPException(401, "Administrator login required.")
    return p


def require_ultimate(p: dict = Depends(require_admin)) -> dict:
    if p["role"] != "ultimate":
        raise HTTPException(403, "Ultimate Admin access is required.")
    return p


def require_member(request: Request) -> dict:
    """A logged-in student or administrator."""
    p = get_principal(request)
    if not p:
        raise HTTPException(401, "Please log in to continue.")
    return p


# ------------------------------------------------------------------ helpers
def client_key(request: Request, username: str) -> tuple[str, str]:
    host = request.client.host if request.client else "unknown"
    return host, username.strip().lower()


def check_throttle(key: tuple[str, str]) -> None:
    wait = throttle.retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).",
                            headers={"Retry-After": str(wait)})


def student_public(s) -> dict:
    return {"id": s["student_id"], "name": s["full_name"], "type": s["type"],
            "intake": str(s["intake_number"]), "registered": bool(s["registered"])}


def validate_new_password(pw: str) -> None:
    if len(pw) < 6:
        raise HTTPException(422, "Password must be at least 6 characters long.")
    if len(pw) > 128:
        raise HTTPException(422, "Password is too long (maximum 128 characters).")


# ------------------------------------------------------------------- schemas
class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class StudentLogin(BaseModel):
    student_id: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class StudentRegister(BaseModel):
    student_id: str = Field(min_length=1, max_length=40)
    temporary_password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)
    new_password: str = Field(min_length=1, max_length=128)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


# -------------------------------------------------------------------- routes
@router.get("/session")
def session_info(request: Request):
    p = get_principal(request)
    if not p:
        return {"role": None}
    if p["kind"] == "admin":
        return {"role": "admin", "adminRole": p["role"], "username": p["username"]}
    return {"role": "student", "student": {"id": p["student_id"], "name": p["name"],
                                           "type": p["type"], "intake": str(p["intake"])}}


@router.post("/admin/login")
def admin_login(body: AdminLogin, request: Request, response: Response):
    key = client_key(request, "admin:" + body.username)
    check_throttle(key)
    with get_db() as db:
        a = db.execute("SELECT id, password_hash, role FROM admins WHERE username = ?",
                       (body.username.strip(),)).fetchone()
        if not a:
            burn_password_check(body.password)
        if not a or not verify_password(body.password, a["password_hash"]):
            throttle.record_failure(key)
            raise HTTPException(401, "Invalid administrator credentials.")
        throttle.reset(key)
        _end_session(request, response)
        _start_session(db, response, admin_id=a["id"], hours=config.ADMIN_SESSION_HOURS)
        return {"role": "admin", "adminRole": a["role"]}


@router.post("/student/login")
def student_login(body: StudentLogin, request: Request, response: Response):
    key = client_key(request, "student:" + body.student_id)
    check_throttle(key)
    with get_db() as db:
        s = db.execute("SELECT * FROM students WHERE student_id = ?", (body.student_id.strip(),)).fetchone()
        if not s:
            burn_password_check(body.password)
        ok = bool(s) and verify_password(body.password, s["password_hash"])
        if not ok:
            throttle.record_failure(key)
            raise HTTPException(401, "Invalid registered student ID or password. "
                                     "Please register first if you have not created an account.")
        if not s["registered"]:
            # Correct temporary password, but the account must be registered first.
            raise HTTPException(403, "Please create your student account first. "
                                     "The temporary password cannot be used to sign in.")
        throttle.reset(key)
        _end_session(request, response)
        _start_session(db, response, student_id=s["id"], hours=config.STUDENT_SESSION_HOURS)
        return {"role": "student", "student": {"id": s["student_id"], "name": s["full_name"],
                                               "type": s["type"], "intake": str(s["intake_number"])}}


@router.post("/student/register")
def student_register(body: StudentRegister, request: Request):
    """First-time activation: the student proves they hold the admin-issued temporary password."""
    key = client_key(request, "register:" + body.student_id)
    check_throttle(key)
    validate_new_password(body.new_password)
    with get_db() as db:
        s = db.execute("SELECT * FROM students WHERE student_id = ?", (body.student_id.strip(),)).fetchone()
        if not s:
            burn_password_check(body.temporary_password)
            throttle.record_failure(key)
            raise HTTPException(404, "Student ID was not found. Ask the administrator to add you first.")
        if s["registered"]:
            raise HTTPException(409, "This student account is already registered. "
                                     "Please sign in with your registered password.")
        if not verify_password(body.temporary_password, s["password_hash"]):
            throttle.record_failure(key)
            raise HTTPException(403, "Incorrect temporary password. "
                                     "Enter the password provided by the administrator.")
        if body.new_password == body.temporary_password:
            raise HTTPException(422, "Choose a new password that is different from the temporary one.")
        db.execute("UPDATE students SET full_name = ?, password_hash = ?, registered = 1 WHERE id = ?",
                   (body.full_name.strip(), hash_password(body.new_password), s["id"]))
        throttle.reset(key)
        return {"ok": True, "studentId": s["student_id"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    _end_session(request, response)
    return {"ok": True}


@router.post("/admin/change-password")
def change_own_password(body: ChangePassword, p: dict = Depends(require_admin)):
    validate_new_password(body.new_password)
    with get_db() as db:
        a = db.execute("SELECT password_hash FROM admins WHERE id = ?", (p["id"],)).fetchone()
        if not verify_password(body.current_password, a["password_hash"]):
            raise HTTPException(403, "Current password is incorrect.")
        db.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), p["id"]))
        return {"ok": True}


class NewPassword(BaseModel):
    new_password: str = Field(min_length=1, max_length=128)


@router.put("/admin/standard-password")
def set_standard_admin_password(body: NewPassword, _: dict = Depends(require_ultimate)):
    """Ultimate Admin only: reset the standard admin's password (and sign that admin out)."""
    validate_new_password(body.new_password)
    with get_db() as db:
        std = db.execute("SELECT id FROM admins WHERE role = 'standard'").fetchall()
        for a in std:
            db.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), a["id"]))
            db.execute("DELETE FROM sessions WHERE admin_id = ?", (a["id"],))
    return {"ok": True}
