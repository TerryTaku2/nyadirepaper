"""Past papers and announcements (uploads, listing, protected downloads)."""
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import config
from .auth import require_admin, require_member
from .db import get_db

router = APIRouter(prefix="/api", tags=["content"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


# ------------------------------------------------------------------- helpers
def _clean_filename(name: Optional[str], fallback: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)[:150]
    if not name:
        name = fallback
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


async def _read_pdf(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is too large (maximum {limit // (1024 * 1024)} MB).")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Only PDF files can be uploaded.")
    return data


def _save_file(data: bytes) -> str:
    stored = secrets.token_hex(16) + ".pdf"
    (config.UPLOAD_DIR / stored).write_bytes(data)
    return stored


def _delete_file(stored: Optional[str]) -> None:
    if stored:
        try:
            (config.UPLOAD_DIR / Path(stored).name).unlink()
        except FileNotFoundError:
            pass


def _pdf_response(stored: str, filename: str) -> FileResponse:
    path = config.UPLOAD_DIR / Path(stored).name
    if not path.is_file():
        raise HTTPException(404, "The file is missing on the server. Ask the administrator to upload it again.")
    return FileResponse(path, media_type="application/pdf", filename=filename,
                        content_disposition_type="inline", headers=NO_STORE)


# -------------------------------------------------------------------- papers
def _paper_out(r) -> dict:
    return {"id": str(r["id"]), "title": r["module_title"], "moduleTitle": r["module_title"],
            "moduleCode": r["module_code"], "level": r["level"], "semester": r["semester"],
            "programme": r["programme"], "department": r["department"], "subject": r["subject"],
            "year": str(r["exam_year"]), "file": r["filename"], "createdAt": r["created_at"] * 1000}


@router.get("/papers/count")
def paper_count():
    """Public figure for the home page."""
    with get_db() as db:
        return {"count": db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]}


@router.get("/admin/papers")
def admin_list_papers(_: dict = Depends(require_admin)):
    with get_db() as db:
        return [_paper_out(r) for r in db.execute("SELECT * FROM papers ORDER BY id DESC")]


@router.post("/admin/papers", status_code=201)
async def add_paper(
    moduleTitle: str = Form(..., min_length=1, max_length=200),
    moduleCode: str = Form(..., min_length=1, max_length=40),
    level: str = Form(...),
    semester: str = Form(...),
    programme: str = Form("Both"),
    department: str = Form(...),
    subject: str = Form(..., min_length=1, max_length=200),
    year: int = Form(..., ge=1990, le=2100),
    file: UploadFile = File(...),
    _: dict = Depends(require_admin),
):
    for value, allowed, label in ((level, config.LEVELS, "Level"), (semester, config.SEMESTERS, "Semester"),
                                  (programme, config.PROGRAMMES, "Programme"),
                                  (department, config.DEPARTMENTS, "Department")):
        if value not in allowed:
            raise HTTPException(422, f"Invalid {label}.")
    data = await _read_pdf(file, config.MAX_PAPER_BYTES)
    stored = _save_file(data)
    try:
        with get_db() as db:
            cur = db.execute(
                "INSERT INTO papers(module_title, module_code, level, semester, programme, department, subject,"
                " exam_year, filename, stored_name, size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (moduleTitle.strip(), moduleCode.strip(), level, semester, programme, department, subject.strip(),
                 year, _clean_filename(file.filename, "past-paper"), stored, len(data), int(time.time())))
            row = db.execute("SELECT * FROM papers WHERE id = ?", (cur.lastrowid,)).fetchone()
            return _paper_out(row)
    except BaseException:
        _delete_file(stored)
        raise


@router.delete("/admin/papers/{paper_id}")
def delete_paper(paper_id: int, _: dict = Depends(require_admin)):
    with get_db() as db:
        row = db.execute("SELECT stored_name FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Paper not found.")
        db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    _delete_file(row["stored_name"])
    return {"ok": True}


def _visible_to(principal: dict, programme: str) -> bool:
    if principal["kind"] == "admin":
        return True
    return programme == "Both" or programme == principal["type"]


@router.get("/papers")
def list_papers(department: Optional[str] = None, principal: dict = Depends(require_member)):
    """Papers a logged-in student may see (their programme + papers for both programmes)."""
    sql, args = "SELECT * FROM papers", []
    if department:
        sql += " WHERE department = ?"
        args.append(department)
    with get_db() as db:
        rows = db.execute(sql + " ORDER BY exam_year DESC, id DESC", args).fetchall()
    return [_paper_out(r) for r in rows if _visible_to(principal, r["programme"])]


@router.get("/papers/{paper_id}/file")
def paper_file(paper_id: int, principal: dict = Depends(require_member)):
    with get_db() as db:
        r = db.execute("SELECT stored_name, filename, programme FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not r or not _visible_to(principal, r["programme"]):
        raise HTTPException(404, "Paper not found.")
    return _pdf_response(r["stored_name"], r["filename"])


# ------------------------------------------------------------- announcements
def _announcement_out(r) -> dict:
    out = {"id": str(r["id"]), "title": r["title"], "body": r["body"], "createdAt": r["created_at"] * 1000}
    if r["pdf_name"]:
        out["pdfName"] = r["pdf_name"]
    return out


@router.get("/announcements")
def list_announcements():
    with get_db() as db:
        return [_announcement_out(r) for r in db.execute("SELECT * FROM announcements ORDER BY created_at DESC, id DESC")]


@router.post("/admin/announcements", status_code=201)
async def add_announcement(
    title: str = Form(..., min_length=1, max_length=200),
    body: str = Form("", max_length=5000),
    file: Optional[UploadFile] = File(None),
    _: dict = Depends(require_admin),
):
    title, body = title.strip(), body.strip()
    has_file = file is not None and bool(file.filename)
    if not title:
        raise HTTPException(422, "Enter an announcement title.")
    if not body and not has_file:
        raise HTTPException(422, "Enter announcement details or attach a PDF file.")
    stored = pdf_name = None
    if has_file:
        data = await _read_pdf(file, config.MAX_ANNOUNCEMENT_BYTES)
        stored, pdf_name = _save_file(data), _clean_filename(file.filename, "announcement")
    try:
        with get_db() as db:
            cur = db.execute("INSERT INTO announcements(title, body, pdf_name, pdf_stored, created_at) VALUES (?,?,?,?,?)",
                             (title, body, pdf_name, stored, int(time.time())))
            return _announcement_out(db.execute("SELECT * FROM announcements WHERE id = ?", (cur.lastrowid,)).fetchone())
    except BaseException:
        _delete_file(stored)
        raise


@router.delete("/admin/announcements/{announcement_id}")
def delete_announcement(announcement_id: int, _: dict = Depends(require_admin)):
    with get_db() as db:
        row = db.execute("SELECT pdf_stored FROM announcements WHERE id = ?", (announcement_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Announcement not found.")
        db.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
    _delete_file(row["pdf_stored"])
    return {"ok": True}


@router.get("/announcements/{announcement_id}/pdf")
def announcement_pdf(announcement_id: int, _: dict = Depends(require_member)):
    with get_db() as db:
        r = db.execute("SELECT pdf_stored, pdf_name FROM announcements WHERE id = ?", (announcement_id,)).fetchone()
    if not r or not r["pdf_stored"]:
        raise HTTPException(404, "Announcement PDF not found.")
    return _pdf_response(r["pdf_stored"], r["pdf_name"])
