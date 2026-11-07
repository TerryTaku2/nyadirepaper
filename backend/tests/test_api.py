import importlib
import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NYADIRE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NYADIRE_ULTIMATE_PASSWORD", "ultimate-pass-1")
    monkeypatch.setenv("NYADIRE_ADMIN_PASSWORD", "standard-pass-1")
    monkeypatch.setenv("NYADIRE_LOGIN_MAX_FAILURES", "5")
    sys.path.insert(0, str(BACKEND))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    main = importlib.import_module("app.main")
    with TestClient(main.app) as c:
        yield c


def login_admin(c, user="admin", pw="standard-pass-1"):
    return c.post("/api/admin/login", json={"username": user, "password": pw})


def add_student(c, sid="24-31-01", intake=31, type_="Junior", pw="1947", name=""):
    return c.post("/api/admin/students", json={"student_id": sid, "intake": intake, "type": type_,
                                               "password": pw, "name": name})


def upload_paper(c, programme="Both", dept="Humanities", content=PDF, name="exam.pdf"):
    return c.post("/api/admin/papers", data={
        "moduleTitle": "Communication Skills", "moduleCode": "CS101", "level": "Level 1",
        "semester": "Semester 1", "programme": programme, "department": dept,
        "subject": "English", "year": "2025"}, files={"file": (name, content, "application/pdf")})


def register_and_login(c, sid="24-31-01", temp="1947", pw="newpass1"):
    r = c.post("/api/student/register", json={"student_id": sid, "temporary_password": temp,
                                              "full_name": "Test Student", "new_password": pw})
    assert r.status_code == 200, r.text
    return c.post("/api/student/login", json={"student_id": sid, "password": pw})


# ---------------------------------------------------------------- admin auth
def test_admin_login_and_session(client):
    assert client.get("/api/session").json() == {"role": None}
    assert login_admin(client).status_code == 200
    s = client.get("/api/session").json()
    assert s["role"] == "admin" and s["adminRole"] == "standard"
    client.post("/api/logout")
    assert client.get("/api/session").json() == {"role": None}


def test_old_hardcoded_credentials_do_not_work(client):
    assert login_admin(client, "lavmoe794815", "icui4cu2day").status_code == 401
    assert login_admin(client, "admin", "nyadire@2026.com").status_code == 401


def test_admin_routes_require_login(client):
    for method, url in [("get", "/api/admin/students"), ("get", "/api/admin/intakes"),
                        ("get", "/api/admin/papers"), ("post", "/api/admin/intakes")]:
        assert getattr(client, method)(url).status_code == 401


def test_login_throttle(client):
    for _ in range(5):
        assert login_admin(client, pw="wrong").status_code == 401
    r = login_admin(client)                      # even the right password is blocked now
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_passwords_are_hashed(client, tmp_path):
    import sqlite3
    con = sqlite3.connect(tmp_path / "nyadire.db")
    for (h,) in con.execute("SELECT password_hash FROM admins"):
        assert h.startswith("scrypt$") and "standard-pass-1" not in h


def test_ultimate_can_reset_standard_password(client):
    login_admin(client)
    assert client.put("/api/admin/standard-password", json={"new_password": "abcdef"}).status_code == 403
    client.post("/api/logout")
    login_admin(client, "superadmin", "ultimate-pass-1")
    assert client.put("/api/admin/standard-password", json={"new_password": "brand-new-pw"}).status_code == 200
    client.post("/api/logout")
    assert login_admin(client).status_code == 401
    assert login_admin(client, pw="brand-new-pw").status_code == 200


# ------------------------------------------------------------------- intakes
def test_default_intakes_seeded_once(client):
    login_admin(client)
    nums = {i["number"]: i["type"] for i in client.get("/api/admin/intakes").json()}
    assert nums == {"20": "ECD", "31": "Junior"}


def test_create_and_delete_intake_cascades(client):
    login_admin(client)
    assert client.post("/api/admin/intakes", json={"year": 2027, "ecd_number": 21, "junior_number": 32}).status_code == 201
    assert client.post("/api/admin/intakes", json={"year": 2027, "ecd_number": 21, "junior_number": 40}).status_code == 409
    assert client.post("/api/admin/intakes", json={"year": 2027, "ecd_number": 50, "junior_number": 50}).status_code == 422
    add_student(client, "24-32-01", 32)
    r = client.delete("/api/admin/intakes/32").json()
    assert r["studentsRemoved"] == 1
    assert [s for s in client.get("/api/admin/students").json() if s["id"] == "24-32-01"] == []
    # deleting a seeded intake sticks across restarts (not re-seeded)
    client.delete("/api/admin/intakes/20")
    assert "20" not in [i["number"] for i in client.get("/api/admin/intakes").json()]


# ------------------------------------------------------------------ students
def test_student_id_rules(client):
    login_admin(client)
    assert add_student(client, "E24-31-01", 31, "Junior").status_code == 422    # wrong prefix
    assert add_student(client, "24-20-01", 20, "ECD").status_code == 422
    assert add_student(client, "24-31-02", 20, "Junior").status_code == 422     # intake 20 is ECD
    assert add_student(client, "E24-20-01", 20, "ECD").status_code == 201
    assert add_student(client, "e24-20-01", 20, "ECD").status_code == 409       # case-insensitive dup
    assert add_student(client, "24-31-01", 99, "Junior").status_code == 404


def test_student_lifecycle(client):
    login_admin(client)
    add_student(client, "24-31-01", pw="temp-pass")
    listed = client.get("/api/admin/students").json()[0]
    assert listed == {"id": "24-31-01", "name": "", "type": "Junior", "intake": "31", "registered": False}
    assert "password" not in str(listed).lower()
    client.post("/api/logout")

    # cannot log in before registering
    r = client.post("/api/student/login", json={"student_id": "24-31-01", "password": "temp-pass"})
    assert r.status_code == 403
    # registration validation
    reg = {"student_id": "24-31-01", "full_name": "Tendai M", "new_password": "secret99"}
    assert client.post("/api/student/register", json={**reg, "temporary_password": "nope"}).status_code == 403
    assert client.post("/api/student/register", json={**reg, "temporary_password": "temp-pass", "new_password": "abc"}).status_code == 422
    assert client.post("/api/student/register", json={"student_id": "24-99-99", "temporary_password": "x",
                                                      "full_name": "X", "new_password": "secret99"}).status_code == 404
    assert client.post("/api/student/register", json={**reg, "temporary_password": "temp-pass"}).status_code == 200
    assert client.post("/api/student/register", json={**reg, "temporary_password": "temp-pass"}).status_code == 409

    ok = client.post("/api/student/login", json={"student_id": "24-31-01", "password": "secret99"})
    assert ok.status_code == 200 and ok.json()["student"]["name"] == "Tendai M"
    assert client.post("/api/student/login", json={"student_id": "24-31-01", "password": "wrong"}).status_code == 401
    # student id login is case-insensitive
    assert client.post("/api/student/login", json={"student_id": "24-31-01".upper(), "password": "secret99"}).status_code == 200
    # a student is not an admin
    assert client.get("/api/admin/students").status_code == 401


def test_unregister_and_delete_kill_sessions(client):
    login_admin(client)
    add_student(client)
    admin_cookie = dict(client.cookies)
    client.post("/api/logout")
    register_and_login(client)
    assert client.get("/api/session").json()["role"] == "student"
    student_cookie = dict(client.cookies)

    client.cookies.clear(); client.cookies.update(admin_cookie)
    login_admin(client)
    assert client.post("/api/admin/students/24-31-01/unregister").json()["temporaryPassword"] == "1947"
    client.cookies.clear(); client.cookies.update(student_cookie)
    assert client.get("/api/session").json() == {"role": None}        # session revoked

    login_admin(client)
    assert client.delete("/api/admin/students/24-31-01").status_code == 200
    assert client.delete("/api/admin/students/24-31-01").status_code == 404


def test_bulk_upload(client):
    login_admin(client)
    rows = [{"student_id": "24-31-10", "name": "A", "password": "1947"},
            {"student_id": "24-31-11", "name": "B", "password": "1947"},
            {"student_id": "24-31-10", "name": "dup", "password": "1947"},
            {"student_id": "E24-31-12", "name": "wrong type", "password": "1947"},
            {"student_id": "24-31-13", "name": "no pw", "password": ""}]
    r = client.post("/api/admin/students/bulk", json={"intake": 31, "type": "Junior", "rows": rows}).json()
    assert r["added"] == 2 and len(r["skipped"]) == 3


# -------------------------------------------------------------------- papers
def test_paper_upload_validation(client):
    login_admin(client)
    assert upload_paper(client).status_code == 201
    assert upload_paper(client, content=b"<html>not a pdf</html>", name="evil.pdf").status_code == 422
    assert upload_paper(client, dept="Nonsense").status_code == 422
    assert upload_paper(client, programme="Everyone").status_code == 422


def test_ultimate_admin_can_upload_paper(client):
    assert login_admin(client, "superadmin", "ultimate-pass-1").status_code == 200
    response = upload_paper(client)
    assert response.status_code == 201, response.text
    assert response.json()["file"] == "exam.pdf"


def test_paper_access_control_and_programme_filter(client, tmp_path):
    login_admin(client)
    both = upload_paper(client, "Both").json()["id"]
    ecd_only = upload_paper(client, "ECD").json()["id"]
    jun_only = upload_paper(client, "Junior").json()["id"]
    add_student(client, "24-31-01", 31, "Junior")
    client.post("/api/logout")

    # anonymous: no listing, no files, but public count
    assert client.get("/api/papers").status_code == 401
    assert client.get(f"/api/papers/{both}/file").status_code == 401
    assert client.get("/api/papers/count").json() == {"count": 3}
    # uploaded files are not reachable as static files
    assert client.get("/uploads/anything.pdf").status_code == 404
    assert client.get("/nyadire.db").status_code == 404

    register_and_login(client)
    ids = {p["id"] for p in client.get("/api/papers?department=Humanities").json()}
    assert ids == {both, jun_only}
    assert client.get("/api/papers?department=Natural Science").json() == []
    ok = client.get(f"/api/papers/{jun_only}/file")
    assert ok.status_code == 200 and ok.content == PDF
    assert ok.headers["content-type"] == "application/pdf"
    assert ok.headers["content-disposition"].startswith("inline")
    assert client.get(f"/api/papers/{ecd_only}/file").status_code == 404     # other programme
    assert client.post("/api/admin/papers").status_code == 401               # students can't upload


def test_delete_paper_removes_file(client, tmp_path):
    login_admin(client)
    pid = upload_paper(client).json()["id"]
    files = list((tmp_path / "uploads").glob("*.pdf"))
    assert len(files) == 1
    assert client.delete(f"/api/admin/papers/{pid}").status_code == 200
    assert list((tmp_path / "uploads").glob("*.pdf")) == []
    assert client.delete(f"/api/admin/papers/{pid}").status_code == 404


def test_filename_is_sanitised(client):
    login_admin(client)
    pid = upload_paper(client, name="../../etc/passwd").json()
    assert pid["file"] == "passwd.pdf"


# ------------------------------------------------------------- announcements
def test_announcements(client):
    assert client.get("/api/announcements").json() == []
    assert client.post("/api/admin/announcements", data={"title": "x", "body": "y"}).status_code == 401
    login_admin(client)
    assert client.post("/api/admin/announcements", data={"title": "Only title"}).status_code == 422
    a = client.post("/api/admin/announcements", data={"title": "Exams", "body": "Start Monday"},
                    files={"file": ("timetable.pdf", PDF, "application/pdf")})
    assert a.status_code == 201 and a.json()["pdfName"] == "timetable.pdf"
    aid = a.json()["id"]
    b = client.post("/api/admin/announcements", data={"title": "Plain", "body": "text"})
    assert b.status_code == 201 and "pdfName" not in b.json()
    client.post("/api/logout")

    public = client.get("/api/announcements").json()           # public, newest first
    assert {x["title"] for x in public} == {"Exams", "Plain"}
    assert client.get(f"/api/announcements/{aid}/pdf").status_code == 401     # PDF needs login
    login_admin(client)
    assert client.get(f"/api/announcements/{aid}/pdf").content == PDF
    assert client.delete(f"/api/admin/announcements/{aid}").status_code == 200
    assert client.get(f"/api/announcements/{aid}/pdf").status_code == 404


# -------------------------------------------------------------------- misc
def test_cross_origin_writes_blocked(client):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "standard-pass-1"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_frontend_served_without_secrets(client):
    assert client.get("/").status_code == 200
    html = client.get("/").text + client.get("/app.js").text
    for secret in ("icui4cu2day", "lavmoe794815", "nyadire@2026.com", "ULTIMATE_ADMIN_PASSWORD"):
        assert secret not in html
    assert client.get("/assets/college-logo-new.png").status_code == 200
    assert client.get("/assets/HEALTH_AND_LIFE_SKILLS_075130.pdf").status_code == 404
