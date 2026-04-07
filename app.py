from flask import Flask, render_template, request, redirect, session # type: ignore
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import os
from werkzeug.utils import secure_filename # type:ignore

UPLOAD_QUESTIONS = "static/uploads/questions"
UPLOAD_MARKSCHEMES = "static/uploads/markschemes"

os.makedirs(UPLOAD_QUESTIONS, exist_ok=True)
os.makedirs(UPLOAD_MARKSCHEMES, exist_ok=True)

import random
import string

def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

app = Flask(__name__)
app.secret_key = "afeefis"

DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')

    # Classrooms
    c.execute('''
        CREATE TABLE IF NOT EXISTS classrooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            teacher_id INTEGER,
            join_code TEXT UNIQUE
        )
    ''')

    # Student <-> Classroom relationship
    c.execute('''
        CREATE TABLE IF NOT EXISTS classroom_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER,
            student_id INTEGER
        )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        classroom_id INTEGER,
        title TEXT,
        image_path TEXT,
        markscheme_path TEXT,
        comments TEXT
    )
    ''')

    # Tags
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            classroom_id INTEGER
        )
    ''')

    # Question ↔ Tags (many-to-many)
    c.execute('''
        CREATE TABLE IF NOT EXISTS question_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            tag_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        try:
            c.execute(
                "INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                (email, hashed_password, role)
            )
            conn.commit()
        except:
            return render_template("register.html", error="User already exists")

        conn.close()
        return redirect("/login")

    return render_template("register.html")

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = c.fetchone()

        conn.close()

        if user and check_password_hash(user[2], password):
            session["user_id"] = user[0]
            session["role"] = user[3]
            return redirect("/dashboard")

        # stay on login page
        return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if session["role"] == "teacher":
        c.execute("SELECT * FROM classrooms WHERE teacher_id = ?", (session["user_id"],))
    else:
        c.execute('''
            SELECT classrooms.* FROM classrooms
            JOIN classroom_students 
            ON classrooms.id = classroom_students.classroom_id
            WHERE classroom_students.student_id = ?
        ''', (session["user_id"],))

    classrooms = c.fetchall()
    conn.close()

    return render_template("dashboard.html", classrooms=classrooms, role=session["role"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/create_classroom", methods=["GET", "POST"])
def create_classroom():
    if "user_id" not in session or session["role"] != "teacher":
        return redirect("/login")

    if request.method == "POST":
        name = request.form["name"]
        teacher_id = session["user_id"]

        code = generate_code()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute(
            "INSERT INTO classrooms (name, teacher_id, join_code) VALUES (?, ?, ?)",
            (name, teacher_id, code)
        )

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("create_classroom.html")

@app.route("/join_classroom", methods=["GET", "POST"])
def join_classroom():
    if "user_id" not in session or session["role"] != "student":
        return redirect("/login")

    if request.method == "POST":
        code = request.form["code"]
        student_id = session["user_id"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # Find classroom
        c.execute("SELECT id FROM classrooms WHERE join_code = ?", (code,))
        classroom = c.fetchone()

        if classroom:
            classroom_id = classroom[0]

            c.execute('''
                SELECT * FROM classroom_students 
                WHERE classroom_id = ? AND student_id = ?
            ''', (classroom_id, student_id))

            exists = c.fetchone()

            if not exists:
                c.execute(
                    "INSERT INTO classroom_students (classroom_id, student_id) VALUES (?, ?)",
                    (classroom_id, student_id)
                )

            conn.commit()
            conn.close()
            return redirect("/dashboard")

        conn.close()
        return render_template("join_classroom.html", error="Invalid class code")

    return render_template("join_classroom.html")

@app.route("/upload_question/<int:classroom_id>", methods=["GET", "POST"])
def upload_question(classroom_id):
    if "user_id" not in session or session["role"] != "teacher":
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        comments = request.form.get("comments")

        question_file = request.files["question_image"]
        markscheme_file = request.files.get("markscheme_image")

        tags_input = request.form.get("tags", "")
        tags_list = [t.strip().lower() for t in tags_input.split(",") if t.strip()]

        if not question_file:
            return render_template("upload_question.html", error="Question image required", classroom_id=classroom_id)

        # Save question image
        #filename = secure_filename(question_file.filename)
        filename = f"{hash(random.randint(1,100000000))}{hash(random.randint(1,100000000))}{hash(random.randint(1,100000000))}.png"
        q_path = os.path.join(UPLOAD_QUESTIONS, filename)
        question_file.save(q_path)

        # Save markscheme if exists
        m_path = None
        if markscheme_file and markscheme_file.filename != "":
            m_filename = secure_filename(markscheme_file.filename)
            m_path = os.path.join(UPLOAD_MARKSCHEMES, m_filename)
            markscheme_file.save(m_path)

        # Save to DB
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute('''
            INSERT INTO questions (classroom_id, title, image_path, markscheme_path, comments)
            VALUES (?, ?, ?, ?, ?)
        ''', (classroom_id, title, q_path, m_path, comments))

        question_id = c.lastrowid

        for tag_name in tags_list:
            # Check if tag already exists in this classroom
            c.execute(
                "SELECT id FROM tags WHERE name = ? AND classroom_id = ?",
                (tag_name, classroom_id)
            )
            tag = c.fetchone()

            if tag:
                tag_id = tag[0]
            else:
                c.execute(
                    "INSERT INTO tags (name, classroom_id) VALUES (?, ?)",
                    (tag_name, classroom_id)
                )
                tag_id = c.lastrowid

            # Link tag to question
            c.execute(
                "INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)",
                (question_id, tag_id)
            )

        conn.commit()
        conn.close()

        return redirect(f"/classroom/{classroom_id}")

    return render_template("upload_question.html", classroom_id=classroom_id)


@app.route("/classroom/<int:classroom_id>")
def classroom(classroom_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    selected_tags = request.args.getlist("tags")

    if selected_tags:
        placeholders = ",".join("?" * len(selected_tags))

        query = f'''
            SELECT q.id, q.title, GROUP_CONCAT(DISTINCT t.name)
            FROM questions q
            JOIN question_tags qt ON q.id = qt.question_id
            JOIN tags t ON qt.tag_id = t.id
            WHERE q.classroom_id = ?
            AND t.name IN ({placeholders})
            GROUP BY q.id
        '''

        params = [classroom_id] + selected_tags
        c.execute(query, params)

    else:
        # No filter -> show all
        c.execute('''
            SELECT q.id, q.title, GROUP_CONCAT(DISTINCT t.name)
            FROM questions q
            LEFT JOIN question_tags qt ON q.id = qt.question_id
            LEFT JOIN tags t ON qt.tag_id = t.id
            WHERE q.classroom_id = ?
            GROUP BY q.id
        ''', (classroom_id,))

    questions = c.fetchall()

    c.execute("SELECT DISTINCT name FROM tags WHERE classroom_id = ?",(classroom_id,))
    all_tags = [t[0] for t in c.fetchall()]

    conn.close()

    return render_template("classroom.html", questions=questions, classroom_id=classroom_id, role=session["role"], all_tags=all_tags)

@app.route("/question/<int:question_id>")
def view_question(question_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    q = c.fetchone()

    conn.close()

    return render_template("question.html", q=q, classroom_id=q[1])

@app.route("/delete_question/<int:question_id>")
def delete_question(question_id):
    if "user_id" not in session or session.get("role") != "teacher":
        return redirect("/login")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Get classroom_id (for redirect later)
    c.execute("SELECT classroom_id FROM questions WHERE id = ?", (question_id,))
    result = c.fetchone()

    if not result:
        conn.close()
        return redirect("/dashboard")

    classroom_id = result[0]

    # Delete relations first
    c.execute("DELETE FROM question_tags WHERE question_id = ?", (question_id,))
    c.execute("DELETE FROM questions WHERE id = ?", (question_id,))

    conn.commit()
    conn.close()

    return redirect(f"/classroom/{classroom_id}")

if __name__ == "__main__":
    app.run()