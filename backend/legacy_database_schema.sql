-- Nyadire College Past Examination Papers Portal
PRAGMA foreign_keys = ON;

CREATE TABLE admins (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, full_name TEXT, department_id INTEGER, intake TEXT, student_type TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(department_id) REFERENCES departments(id));
CREATE TABLE subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, department_id INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE(department_id,name), FOREIGN KEY(department_id) REFERENCES departments(id) ON DELETE CASCADE);
CREATE TABLE papers (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, department_id INTEGER NOT NULL, subject_id INTEGER NOT NULL, exam_year INTEGER NOT NULL, level TEXT, semester TEXT, filename TEXT NOT NULL, mime_type TEXT NOT NULL DEFAULT 'application/pdf', file_data BLOB, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(department_id) REFERENCES departments(id), FOREIGN KEY(subject_id) REFERENCES subjects(id));
