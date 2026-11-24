import os
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "Frontend")
DATABASE = os.path.join(BASE_DIR, "academy.db")

app = Flask(
    __name__,
    template_folder=FRONTEND_DIR,
    static_folder=FRONTEND_DIR
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "academy-development-secret-change-before-deployment"
)

ADMIN_LOGIN = "najmiddinovadmin"
ADMIN_PASSWORD = "poiuytrewq"


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            teacher TEXT,
            teacher_id INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, course_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            topic TEXT,
            content TEXT NOT NULL,
            video_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Eski database uchun migration
    user_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "role" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'"
        )

    course_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(courses)").fetchall()
    ]

    if "teacher_id" not in course_columns:
        conn.execute(
            "ALTER TABLE courses ADD COLUMN teacher_id INTEGER"
        )

    conn.commit()
    conn.close()


# =========================
# HELPERS
# =========================

def login_required():
    return "user_id" in session


def teacher_owns_course(conn, teacher_id, course_id):
    course = conn.execute("""
        SELECT id FROM courses
        WHERE id = ? AND teacher_id = ?
    """, (course_id, teacher_id)).fetchone()

    return course is not None


# =========================
# LOGIN
# =========================

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")

        if login_value == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            session.clear()
            session["user_id"] = 0
            session["name"] = "Administrator"
            session["email"] = ADMIN_LOGIN
            session["role"] = "admin"

            return redirect(url_for("dashboard"))

        conn = get_db()

        user = conn.execute("""
            SELECT * FROM users WHERE email = ?
        """, (login_value,)).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["email"] = user["email"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        flash("Login yoki parol noto‘g‘ri!", "error")

    return render_template("login.html")


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()

    role = session["role"]
    user_id = session["user_id"]

    stats = {
        "users": 0,
        "students": 0,
        "teachers": 0,
        "courses": 0
    }

    courses = []
    lessons = []
    assignments = []
    course_students = []
    student_list = []
    teacher_list = []
    recent_users = []

    if role == "admin":

        stats["users"] = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        stats["students"] = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0]

        stats["teachers"] = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='teacher'"
        ).fetchone()[0]

        stats["courses"] = conn.execute(
            "SELECT COUNT(*) FROM courses"
        ).fetchone()[0]

        courses = conn.execute("""
            SELECT courses.*, users.name AS teacher
            FROM courses
            LEFT JOIN users ON courses.teacher_id = users.id
            ORDER BY courses.id DESC
        """).fetchall()

        student_list = conn.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY id DESC
        """).fetchall()

        teacher_list = conn.execute("""
            SELECT * FROM users
            WHERE role='teacher'
            ORDER BY id DESC
        """).fetchall()

        recent_users = conn.execute("""
            SELECT * FROM users
            ORDER BY id DESC LIMIT 10
        """).fetchall()

        lessons = conn.execute("""
            SELECT lessons.*, courses.title AS course_title
            FROM lessons
            JOIN courses ON lessons.course_id = courses.id
            ORDER BY lessons.id DESC
        """).fetchall()

        assignments = conn.execute("""
            SELECT assignments.*, courses.title AS course_title
            FROM assignments
            JOIN courses ON assignments.course_id = courses.id
            ORDER BY assignments.id DESC
        """).fetchall()

    elif role == "teacher":

        courses = conn.execute("""
            SELECT * FROM courses
            WHERE teacher_id = ?
            ORDER BY id DESC
        """, (user_id,)).fetchall()

        lessons = conn.execute("""
            SELECT lessons.*, courses.title AS course_title
            FROM lessons
            JOIN courses ON lessons.course_id = courses.id
            WHERE lessons.teacher_id = ?
            ORDER BY lessons.id DESC
        """, (user_id,)).fetchall()

        assignments = conn.execute("""
            SELECT assignments.*, courses.title AS course_title
            FROM assignments
            JOIN courses ON assignments.course_id = courses.id
            WHERE assignments.teacher_id = ?
            ORDER BY assignments.id DESC
        """, (user_id,)).fetchall()

        course_students = conn.execute("""
            SELECT
                enrollments.course_id,
                users.id AS student_id,
                users.name AS student_name,
                users.email AS student_email,
                courses.title AS course_title
            FROM enrollments
            JOIN users ON enrollments.user_id = users.id
            JOIN courses ON enrollments.course_id = courses.id
            WHERE courses.teacher_id = ?
            ORDER BY users.name
        """, (user_id,)).fetchall()

        stats["courses"] = len(courses)
        stats["students"] = len(course_students)
        stats["users"] = len(course_students)

    elif role == "student":

        courses = conn.execute("""
            SELECT courses.*
            FROM courses
            JOIN enrollments ON courses.id = enrollments.course_id
            WHERE enrollments.user_id = ?
            ORDER BY courses.id DESC
        """, (user_id,)).fetchall()

        lessons = conn.execute("""
            SELECT lessons.*, courses.title AS course_title
            FROM lessons
            JOIN courses ON lessons.course_id = courses.id
            JOIN enrollments ON courses.id = enrollments.course_id
            WHERE enrollments.user_id = ?
            ORDER BY lessons.id DESC
        """, (user_id,)).fetchall()

        assignments = conn.execute("""
            SELECT assignments.*, courses.title AS course_title
            FROM assignments
            JOIN courses ON assignments.course_id = courses.id
            JOIN enrollments ON courses.id = enrollments.course_id
            WHERE enrollments.user_id = ?
            ORDER BY assignments.id DESC
        """, (user_id,)).fetchall()

        stats["courses"] = len(courses)

    conn.close()

    return render_template(
        "dashboard.html",
        stats=stats,
        courses=courses,
        lessons=lessons,
        assignments=assignments,
        course_students=course_students,
        student_list=student_list,
        teacher_list=teacher_list,
        recent_users=recent_users
    )


# =========================
# ADMIN: CREATE USER
# =========================

@app.route("/admin/create-user", methods=["POST"])
def create_user():

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "")

    if not name or not email or not password:
        flash("Barcha maydonlarni to‘ldiring!", "error")
        return redirect(url_for("dashboard"))

    if role not in ["student", "teacher"]:
        flash("Noto‘g‘ri foydalanuvchi turi!", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            generate_password_hash(password),
            role
        ))

        conn.commit()
        flash("Foydalanuvchi yaratildi!", "success")

    except sqlite3.IntegrityError:
        flash("Bu email allaqachon mavjud!", "error")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# =========================
# ADMIN: CREATE COURSE
# =========================

@app.route("/admin/create-course", methods=["POST"])
def create_course():

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    teacher_id = request.form.get("teacher_id", "")

    if not title or not teacher_id:
        flash("Kurs nomi va o‘qituvchini tanlang!", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()

    teacher = conn.execute("""
        SELECT * FROM users
        WHERE id = ? AND role = 'teacher'
    """, (teacher_id,)).fetchone()

    if not teacher:
        conn.close()
        flash("O‘qituvchi topilmadi!", "error")
        return redirect(url_for("dashboard"))

    conn.execute("""
        INSERT INTO courses (title, teacher, teacher_id)
        VALUES (?, ?, ?)
    """, (title, teacher["name"], teacher["id"]))

    conn.commit()
    conn.close()

    flash("Kurs yaratildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# ADMIN: DELETE COURSE
# =========================

@app.route("/admin/delete-course/<int:course_id>", methods=["POST"])
def delete_course(course_id):

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    course = conn.execute("""
        SELECT id FROM courses WHERE id = ?
    """, (course_id,)).fetchone()

    if not course:
        conn.close()
        flash("Kurs topilmadi!", "error")
        return redirect(url_for("dashboard"))

    conn.execute("DELETE FROM lessons WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM assignments WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM enrollments WHERE course_id = ?", (course_id,))
    conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))

    conn.commit()
    conn.close()

    flash("Kurs va unga tegishli ma’lumotlar o‘chirildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# ADMIN: ASSIGN COURSE
# =========================

@app.route("/admin/assign-course", methods=["POST"])
def assign_course():

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    student_id = request.form.get("student_id")
    course_id = request.form.get("course_id")

    conn = get_db()

    student = conn.execute("""
        SELECT id FROM users
        WHERE id = ? AND role = 'student'
    """, (student_id,)).fetchone()

    course = conn.execute("""
        SELECT id FROM courses WHERE id = ?
    """, (course_id,)).fetchone()

    if not student or not course:
        conn.close()
        flash("O‘quvchi yoki kurs topilmadi!", "error")
        return redirect(url_for("dashboard"))

    try:
        conn.execute("""
            INSERT INTO enrollments (user_id, course_id)
            VALUES (?, ?)
        """, (student_id, course_id))

        conn.commit()
        flash("Kurs o‘quvchiga biriktirildi!", "success")

    except sqlite3.IntegrityError:
        flash("Bu kurs o‘quvchiga avval biriktirilgan!", "error")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# =========================
# ADMIN: DELETE STUDENT
# =========================

@app.route("/admin/delete-student/<int:student_id>", methods=["POST"])
def delete_student(student_id):

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute("DELETE FROM enrollments WHERE user_id = ?", (student_id,))
    conn.execute("DELETE FROM users WHERE id = ? AND role = 'student'", (student_id,))

    conn.commit()
    conn.close()

    flash("O‘quvchi o‘chirildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# ADMIN: DELETE TEACHER
# =========================

@app.route("/admin/delete-teacher/<int:teacher_id>", methods=["POST"])
def delete_teacher(teacher_id):

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = get_db()

    teacher = conn.execute("""
        SELECT id FROM users
        WHERE id = ? AND role = 'teacher'
    """, (teacher_id,)).fetchone()

    if not teacher:
        conn.close()
        flash("O‘qituvchi topilmadi!", "error")
        return redirect(url_for("dashboard"))

    teacher_courses = conn.execute("""
        SELECT id FROM courses WHERE teacher_id = ?
    """, (teacher_id,)).fetchall()
    
    course_ids = [c["id"] for c in teacher_courses]

    if course_ids:
        placeholders = ','.join(['?'] * len(course_ids))
        conn.execute(f"DELETE FROM lessons WHERE course_id IN ({placeholders})", course_ids)
        conn.execute(f"DELETE FROM assignments WHERE course_id IN ({placeholders})", course_ids)
        conn.execute(f"DELETE FROM enrollments WHERE course_id IN ({placeholders})", course_ids)
        conn.execute("DELETE FROM courses WHERE teacher_id = ?", (teacher_id,))

    conn.execute("DELETE FROM users WHERE id = ? AND role = 'teacher'", (teacher_id,))

    conn.commit()
    conn.close()

    flash("O‘qituvchi va unga tegishli barcha kurslar o‘chirildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# TEACHER: CREATE LESSON
# =========================

@app.route("/teacher/create-lesson", methods=["POST"])
def create_lesson():

    if session.get("role") != "teacher":
        return redirect(url_for("login"))

    teacher_id = session["user_id"]

    course_id = request.form.get("course_id")
    title = request.form.get("title", "").strip()
    topic = request.form.get("topic", "").strip()
    content = request.form.get("content", "").strip()
    video_url = request.form.get("video_url", "").strip()

    conn = get_db()

    if not teacher_owns_course(conn, teacher_id, course_id):
        conn.close()
        flash("Bu kurs sizga tegishli emas!", "error")
        return redirect(url_for("dashboard"))

    if not title or not content:
        conn.close()
        flash("Dars nomi va matnini kiriting!", "error")
        return redirect(url_for("dashboard"))

    conn.execute("""
        INSERT INTO lessons (
            course_id, teacher_id, title,
            topic, content, video_url
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        course_id,
        teacher_id,
        title,
        topic,
        content,
        video_url
    ))

    conn.commit()
    conn.close()

    flash("Dars muvaffaqiyatli qo‘shildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# TEACHER: CREATE ASSIGNMENT
# =========================

@app.route("/teacher/create-assignment", methods=["POST"])
def create_assignment():

    if session.get("role") != "teacher":
        return redirect(url_for("login"))

    teacher_id = session["user_id"]

    course_id = request.form.get("course_id")
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    deadline = request.form.get("deadline", "").strip()

    conn = get_db()

    if not teacher_owns_course(conn, teacher_id, course_id):
        conn.close()
        flash("Bu kurs sizga tegishli emas!", "error")
        return redirect(url_for("dashboard"))

    if not title or not description:
        conn.close()
        flash("Vazifa nomi va tavsifini kiriting!", "error")
        return redirect(url_for("dashboard"))

    conn.execute("""
        INSERT INTO assignments (
            course_id, teacher_id, title,
            description, deadline
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        course_id,
        teacher_id,
        title,
        description,
        deadline
    ))

    conn.commit()
    conn.close()

    flash("Uy vazifasi qo‘shildi!", "success")
    return redirect(url_for("dashboard"))


# =========================
# PROFILE UPDATE
# =========================

@app.route("/profile/update", methods=["POST"])
def update_profile():

    if session.get("role") not in ["student", "teacher"]:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email:
        flash("Ism va emailni kiriting!", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()

    try:
        if password:
            conn.execute("""
                UPDATE users
                SET name = ?, email = ?, password = ?
                WHERE id = ?
            """, (
                name,
                email,
                generate_password_hash(password),
                user_id
            ))
        else:
            conn.execute("""
                UPDATE users
                SET name = ?, email = ?
                WHERE id = ?
            """, (name, email, user_id))

        if session["role"] == "teacher":
            conn.execute("""
                UPDATE courses
                SET teacher = ?
                WHERE teacher_id = ?
            """, (name, user_id))

        conn.commit()

        session["name"] = name
        session["email"] = email

        flash("Profil yangilandi!", "success")

    except sqlite3.IntegrityError:
        flash("Bu email boshqa foydalanuvchida mavjud!", "error")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================
# RUN
# =========================

if __name__ == "__main__":
    create_table()
    app.run(debug=True, port=5001)