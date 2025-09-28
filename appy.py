import os
import sqlite3
import datetime
import re
from flask import Flask, render_template, request, jsonify
import os
import io
import threading
import sqlite3
import datetime
import json
from flask import Flask, render_template, request, jsonify, send_file, abort
from model import train_model_background, extract_embedding_for_image, MODEL_PATH
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import bcrypt
import datetime

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")
DATASET_DIR = os.path.join(APP_DIR, "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)
app = Flask(__name__, static_folder="static", template_folder="templates")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Create students table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll TEXT,
            class TEXT,
            section TEXT,
            reg_no TEXT,
            created_at TEXT
        )
    """)
    # Create attendance table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            name TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()

import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

def write_train_status(status_dict):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(status_dict, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not trained"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)

from flask import Flask
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Set a secure random key here

# Your routes below ...


# ---------- Train status helpers ----------
def write_train_status(status_dict):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(status_dict, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not trained"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)
    
def init_user_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_user_db()

def validate_roll(roll):
    # Validate default format: starts with "T-CSE-", then 3 chars (can be alphanumeric)
    import re
    pattern = r"^T-CSE-[A-Za-z0-9]{3}$"
    return re.fullmatch(pattern, roll)

# Registration Page + POST handler
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        # Pass default roll prefix to form
        default_roll = "T-CSE-___"
        return render_template("register.html", default_roll=default_roll)

    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip().upper()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not roll or not password or not confirm_password:
        return render_template("register.html", error="Please fill all fields.", default_roll=roll)

    if not validate_roll(roll):
        return render_template("register.html", error="Invalid roll format (example: T-CSE-ABC).", default_roll=roll)

    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match.", default_roll=roll)

    # Hash password securely
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (roll, password_hash, name, created_at) VALUES (?, ?, ?, ?)",
                  (roll, password_hash, name, datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return render_template("register.html", error="Roll already registered.", default_roll=roll)

    return redirect(url_for("login"))

# Login Page + POST handler
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    roll = request.form.get("roll", "").strip().upper()
    password = request.form.get("password", "")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, password_hash, name FROM users WHERE roll=?", (roll,))
    row = c.fetchone()
    conn.close()

    if not row:
        return render_template("login.html", error="Invalid roll or password.")

    user_id, password_hash, name = row
    if not bcrypt.checkpw(password.encode("utf-8"), password_hash):
        return render_template("login.html", error="Invalid roll or password.")

    # Login success
    session["user_id"] = user_id
    session["user_name"] = name
    session["user_roll"] = roll

    return redirect(url_for("index"))

# Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Example Homepage - requires login
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", name=session.get("user_name"))

# ensure initial train status file exists
write_train_status({"running": False, "progress": 0, "message": "No training yet."})

# ---------- Routes ----------

# Dashboard simple API for attendance stats (last 30 days)
@app.route("/attendance_stats")
def attendance_stats():
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT timestamp FROM attendance", conn)
    conn.close()
    if df.empty:
        from datetime import date, timedelta
        days = [(date.today() - datetime.timedelta(days=i)).strftime("%d-%b") for i in range(29, -1, -1)]
        return jsonify({"dates": days, "counts": [0]*30})
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    last_30 = [ (datetime.date.today() - datetime.timedelta(days=i)) for i in range(29, -1, -1) ]
    counts = [ int(df[df['date'] == d].shape[0]) for d in last_30 ]
    dates = [ d.strftime("%d-%b") for d in last_30 ]
    return jsonify({"dates": dates, "counts": counts})

# -------- Add student (form) --------
import re
# -------- Add student (form) --------
import re
from flask import jsonify

# -------- Add student (form) --------
# -------- Add student (form) --------
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return render_template("add_student.html")
    # POST: save student metadata and return student_id
    data = request.form
    name = data.get("name","").strip()
    roll = data.get("roll","").strip()
    cls = data.get("class","").strip()
    sec = data.get("sec","").strip()
    reg_no = data.get("reg_no","").strip()
    if not name:
        return jsonify({"error":"name required"}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("INSERT INTO students (name, roll, class, section, reg_no, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (name, roll, cls, sec, reg_no, now))
    sid = c.lastrowid
    conn.commit()
    conn.close()
    # create dataset folder for this student
    os.makedirs(os.path.join(DATASET_DIR, str(sid)), exist_ok=True)
    return jsonify({"student_id": sid})




# -------- Upload face images (after capture) --------
from sklearn.metrics.pairwise import cosine_similarity

# -------- Upload face images (after capture) --------
@app.route("/upload_face", methods=["POST"])
def upload_face():
    student_id = request.form.get("student_id")
    if not student_id:
        return jsonify({"error":"student_id required"}), 400
    files = request.files.getlist("images[]")
    saved = 0
    folder = os.path.join(DATASET_DIR, student_id)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    for f in files:
        try:
            fname = f"{datetime.datetime.utcnow().timestamp():.6f}_{saved}.jpg"
            path = os.path.join(folder, fname)
            f.save(path)
            saved += 1
        except Exception as e:
            app.logger.error("save error: %s", e)
    return jsonify({"saved": saved})


# -------- Train model (start background thread) --------
@app.route("/train_model", methods=["GET"])
def train_model_route():
    # if already running, respond accordingly
    status = read_train_status()
    if status.get("running"):
        return jsonify({"status":"already_running"}), 202
    # reset status
    write_train_status({"running": True, "progress": 0, "message": "Starting training"})
    # start background thread
    t = threading.Thread(target=train_model_background, args=(DATASET_DIR, lambda p,m: write_train_status({"running": True, "progress": p, "message": m})))
    t.daemon = True
    t.start()
    return jsonify({"status":"started"}), 202
# -------- Train progress (polling) --------
@app.route("/train_status", methods=["GET"])
def train_status():
    return jsonify(read_train_status())

# -------- Mark attendance page --------
@app.route("/mark_attendance", methods=["GET"])
def mark_attendance_page():
    return render_template("mark_attendance.html")

@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if "image" not in request.files:
        return jsonify({"recognized": False, "error":"no image"}), 400
    img_file = request.files["image"]
    try:
        emb = extract_embedding_for_image(img_file.stream)
        if emb is None:
            return jsonify({"recognized": False, "error":"no face detected"}), 200
        # attempt prediction
        from model import load_model_if_exists, predict_with_model
        clf = load_model_if_exists()
        if clf is None:
            return jsonify({"recognized": False, "error":"model not trained"}), 200
        pred_label, conf = predict_with_model(clf, emb)
        # threshold confidence
        if conf < 0.5:
            return jsonify({"recognized": False, "confidence": float(conf)}), 200
        # find student name
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM students WHERE id=?", (int(pred_label),))
        row = c.fetchone()
        name = row[0] if row else "Unknown"
        # save attendance record with timestamp
        ts = datetime.datetime.utcnow().isoformat()
        c.execute("INSERT INTO attendance (student_id, name, timestamp) VALUES (?, ?, ?)", (int(pred_label), name, ts))
        conn.commit()
        conn.close()
        return jsonify({"recognized": True, "student_id": int(pred_label), "name": name, "confidence": float(conf)}), 200
    except Exception as e:
        app.logger.exception("recognize error")
        return jsonify({"recognized": False, "error": str(e)}), 500


    
from flask import Flask, render_template, request, jsonify
import os
import io
import datetime
import cv2
import sqlite3
from werkzeug.utils import secure_filename
from model import load_model_if_exists, predict_with_model, extract_embedding_for_image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")

@app.route('/video_attendance', methods=['GET', 'POST'])
def video_attendance():
    if request.method == 'GET':
        return render_template('video.html')

    if "video" not in request.files:
        return jsonify({"error": "No video uploaded."})
    
    video_file = request.files['video']
    if video_file.filename == "":
        return jsonify({"error": "No file selected."})

    filename = secure_filename(video_file.filename)
    temp_dir = os.path.join(APP_DIR, "temp_video_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    video_path = os.path.join(temp_dir, filename)
    video_file.save(video_path)

    clf = load_model_if_exists()
    if clf is None:
        os.remove(video_path)
        return jsonify({"error": "Model has not been trained yet."})

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cap = cv2.VideoCapture(video_path)

    frame_skip = 5
    frame_id = 0
    recognized_students = {}

    def has_recorded_in_period(student_id, ts):
        # Period calculation: 50-minute slots, max 8 periods per day
        midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        diff = (ts - midnight).total_seconds()
        period_length = 50 * 60
        period = int(diff // period_length)
        period = min(period, 7)
        
        day_str = ts.date().isoformat()
        c.execute(
            "SELECT timestamp FROM attendance WHERE student_id=? AND date(timestamp)=?", (student_id, day_str)
        )
        timestamps = c.fetchall()
        for (timestamp_str,) in timestamps:
            att_ts = datetime.datetime.fromisoformat(timestamp_str)
            att_diff = (att_ts - midnight).total_seconds()
            att_period = int(att_diff // period_length)
            att_period = min(att_period, 7)
            if att_period == period:
                return True
        return False

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_id += 1
        if frame_id % frame_skip != 0:
            continue

        ret_encode, jpeg = cv2.imencode('.jpg', frame)
        if not ret_encode:
            continue

        emb = extract_embedding_for_image(io.BytesIO(jpeg.tobytes()))
        if emb is None:
            continue

        pred_label, conf = predict_with_model(clf, emb)
        if conf < 0.5:
            continue

        if pred_label not in recognized_students:
            c.execute("SELECT name FROM students WHERE id=?", (int(pred_label),))
            row = c.fetchone()
            if row:
                now_utc = datetime.datetime.utcnow()
                if not has_recorded_in_period(pred_label, now_utc):
                    recognized_students[pred_label] = row[0]
                    c.execute(
                        "INSERT INTO attendance (student_id, name, timestamp) VALUES (?, ?, ?)",
                        (pred_label, row[0], now_utc.isoformat())
                    )
                    conn.commit()

    cap.release()
    conn.close()
    os.remove(video_path)

    return jsonify({"students": list(recognized_students.values())})


# -------- Attendance records & filters --------


# -------- CSV download --------
@app.route("/download_csv", methods=["GET"])
def download_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, student_id, name, timestamp FROM attendance ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    output.write("id,student_id,name,timestamp\n")
    for r in rows:
        output.write(f'{r[0]},{r[1]},{r[2]},{r[3]}\n')
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="attendance.csv", mimetype="text/csv")

# -------- Students API for listing/editing --------
@app.route("/students", methods=["GET"])
def students_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, roll, class, section, reg_no, created_at FROM students ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    data = [ {"id":r[0],"name":r[1],"roll":r[2],"class":r[3],"section":r[4],"reg_no":r[5],"created_at":r[6]} for r in rows ]
    return jsonify({"students": data})

@app.route("/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM students WHERE id=?", (sid,))
    c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()
    # also delete dataset folder
    folder = os.path.join(DATASET_DIR, str(sid))
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"deleted": True})

# -------- Attendance records & filters --------
# -------- Attendance records & filters --------
@app.route("/attendance_record", methods=["GET"])
def attendance_record():
    period = request.args.get("period", "all")  # all, daily, weekly, monthly
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    q = "SELECT id, student_id, name, timestamp FROM attendance"
    params = ()
    if period == "daily":
        today = datetime.date.today().isoformat()
        q += " WHERE date(timestamp) = ?"
        params = (today,)
    elif period == "weekly":
        start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        q += " WHERE date(timestamp) >= ?"
        params = (start,)
    elif period == "monthly":
        start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        q += " WHERE date(timestamp) >= ?"
        params = (start,)
    q += " ORDER BY timestamp DESC LIMIT 5000"
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    return render_template("attendance_record.html", records=rows, period=period)


def can_record_attendance(student_id):
    """
    Return True if student has not been marked present within the last hour.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp FROM attendance
        WHERE student_id=? ORDER BY timestamp DESC LIMIT 1
    """, (student_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return True  # No previous attendance, allow
    last_attendance = datetime.datetime.fromisoformat(row[0])
    now = datetime.datetime.utcnow()
    # Check one-hour difference
    return (now - last_attendance).total_seconds() > 3600


def get_period_for_timestamp(ts):
    """
    Given a datetime, returns the period number (0 to 7) of the day.
    Each period is 50 minutes, 8 periods cover 6 hours 40 minutes.
    After 8th period, still counts as last period.
    """
    midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    diff = (ts - midnight).total_seconds()
    period_length = 50 * 60  # seconds
    period = int(diff // period_length)
    return min(period, 7)  # max period is 7

def has_recorded_in_period(student_id, ts):
    """
    Check if student has attendance recorded in the period for timestamp ts.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    period = get_period_for_timestamp(ts)
    date_str = ts.date().isoformat()
    # Select any record for student on same date and same period slot
    c.execute("""
        SELECT timestamp FROM attendance WHERE student_id = ? AND date(timestamp) = ?
    """, (student_id, date_str))
    rows = c.fetchall()
    conn.close()
    for (timestamp_str,) in rows:
        t = datetime.datetime.fromisoformat(timestamp_str)
        if get_period_for_timestamp(t) == period:
            return True
    return False

from flask import request, render_template
import datetime

@app.route('/midday_meal', methods=['GET'])
def midday_meal():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get total students count
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]

    # Today's date and weekday
    today = datetime.date.today()
    today_str = today.strftime("%A")
    today_date_str = today.isoformat()

    # Extra date string for Jinja
    today_full_str = datetime.datetime.today().strftime("%B %d, %Y")

    # Attendance count today
    c.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date(timestamp)=?", (today_date_str,))
    present_students = c.fetchone()[0]
    absent_students = total_students - present_students

    # Compute attendance percentage
    attendance_percent = round((present_students / total_students)*100, 1) if total_students > 0 else 0

    # Meal schedule
    meal_schedule = {
        "Monday": {"meal": "Dal, Rice, Mixed Veg Curry, Salad", "tags": ["Protein", "Carbs", "Vitamins"]},
        "Tuesday": {"meal": "Chapati, Paneer Curry, Curd, Fruit", "tags": ["Protein", "Calcium", "Vitamins"]},
        "Wednesday": {"meal": "Khichdi, Curd, Pickle, Seasonal Veg", "tags": ["Carbs", "Protein", "Minerals"]},
        "Thursday": {"meal": "Vegetable Pulao, Raita, Salad", "tags": ["Carbs", "Probiotics", "Vitamin C"]},
        "Friday": {"meal": "Rice, Rajma, Boiled Egg, Salad", "tags": ["Protein", "Carbs"]},
        "Saturday": {"meal": "Chapati, Mixed Dal, Paneer, Fruit", "tags": ["Protein", "Carbs", "Vitamins"]},
        "Sunday": {"meal": "No meal today", "tags": []}
    }
    today_meal = meal_schedule.get(today_str, {"meal": "No meal scheduled", "tags": []})

    # Meal calculation
    dal_needed_kg = round(present_students * 0.06, 2)
    rice_needed_kg = round(present_students * 0.14, 2)

    # Weekly attendance
    c.execute("""
        SELECT date(timestamp), COUNT(DISTINCT student_id) FROM attendance
        WHERE date(timestamp) >= date('now', '-6 days')
        GROUP BY date(timestamp)
        ORDER BY date(timestamp) ASC
    """)
    weekly_data = c.fetchall()
    dates = []
    counts = []
    for date_str, count in weekly_data:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        dates.append(dt.strftime("%a"))
        counts.append(count)

    conn.close()

    return render_template('midday_meal.html',
        total_students=total_students,
        present_students=present_students,
        absent_students=absent_students,
        attendance_percent=attendance_percent,
        dal_needed_kg=dal_needed_kg,
        rice_needed_kg=rice_needed_kg,
        today_meal=today_meal,
        today_str=today_str,
        today_full_str=today_full_str,  # <-- pass here
        dates=dates,
        counts=counts
    )
@app.route("/classes", methods=["GET"])
def classes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    classes = [str(i) for i in range(1, 11)]  # Classes 1 to 10
    sections = ['A', 'B', 'C', 'D']           # Sections A to D

    selected_class = request.args.get("class")
    selected_section = request.args.get("section")

    students = []
    class_attendance = 0

    if selected_class and selected_section:
        # Get students matching class and section
        c.execute("""
            SELECT id, name, roll FROM students
            WHERE class=? AND section=?
            ORDER BY roll
        """, (selected_class, selected_section))
        student_rows = c.fetchall()

        # Calculate total attendance days recorded in the system (for % calc)
        c.execute("SELECT COUNT(DISTINCT date(timestamp)) FROM attendance")
        total_days = c.fetchone()[0] or 1  # Avoid zero division

        # Calculate today's attendance count for class group
        c.execute("""
            SELECT COUNT(DISTINCT attendance.student_id)
            FROM attendance
            JOIN students ON attendance.student_id = students.id
            WHERE students.class=? AND students.section=? AND date(attendance.timestamp) = date('now')
        """, (selected_class, selected_section))
        present_today = c.fetchone()[0] or 0

        total_students = len(student_rows)
        class_attendance = round((present_today / total_students) * 100, 1) if total_students > 0 else 0

        # Calculate individual attendance %
        for sid, name, roll in student_rows:
            # Count days present for student
            c.execute("""
                SELECT COUNT(DISTINCT date(timestamp)) FROM attendance WHERE student_id=?
            """, (sid,))
            present_days = c.fetchone()[0] or 0
            attendance_percent = round((present_days / total_days) * 100, 1)
            students.append({'id': sid, 'name': name, 'roll': roll, 'attendance_percent': attendance_percent})

    conn.close()

    return render_template("classes.html",
                           classes=classes,
                           sections=sections,
                           selected_class=selected_class,
                           selected_section=selected_section,
                           students=students,
                           class_attendance=class_attendance)
@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Fixed classes and sections
    classes = [str(i) for i in range(1, 11)]
    sections = ['A', 'B', 'C', 'D']

    selected_class = request.args.get("class")
    selected_section = request.args.get("section")

    students = []
    class_attendance = 0

    if selected_class and selected_section:
        # Get students matching class/section
        c.execute("""
            SELECT id, name, roll FROM students
            WHERE class=? AND section=?
            ORDER BY roll
        """, (selected_class, selected_section))
        raw = c.fetchall()

        # Total days recorded in attendance table
        c.execute("SELECT COUNT(DISTINCT date(timestamp)) FROM attendance")
        total_days = c.fetchone()[0] or 1

        # Today's attendance count for class and section
        c.execute("""
            SELECT COUNT(DISTINCT attendance.student_id)
            FROM attendance
            JOIN students ON attendance.student_id = students.id
            WHERE students.class=? AND students.section=? AND date(attendance.timestamp) = date('now')
        """, (selected_class, selected_section))
        present_today = c.fetchone()[0] or 0

        total_students = len(raw)
        class_attendance = round((present_today / total_students) * 100, 1) if total_students else 0

        # Fetch streaks and badges from student_progress table
        for sid, name, roll in raw:
            c.execute("SELECT total_days_present, consecutive_days_present, badge FROM student_progress WHERE student_id=?", (sid,))
            prog = c.fetchone()
            if prog:
                total_days_present, consec_days, badge = prog
            else:
                total_days_present, consec_days, badge = 0, 0, ''

            attendance_percent = round((total_days_present / total_days)*100, 1) if total_days > 0 else 0

            # Generate stars for streak (up to 5 stars max for demo)
            stars = "⭐" * min(consec_days, 5)

            students.append({
                "id": sid,
                "name": name,
                "roll": roll,
                "attendance_percent": attendance_percent,
                "consec_days": consec_days,
                "badge": badge or "",
                "stars": stars
            })

        # Sort students by attendance_percent desc, then consecutive_days desc
        students.sort(key=lambda x: (x['attendance_percent'], x['consec_days']), reverse=True)

    conn.close()

    return render_template("leaderboard.html",
                           classes=classes,
                           sections=sections,
                           selected_class=selected_class,
                           selected_section=selected_section,
                           students=students,
                           class_attendance=class_attendance)





# ---------------- run ------------------------
if __name__ == "__main__":
    app.run(debug=True)
    
    
    
    
