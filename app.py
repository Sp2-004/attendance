from flask import Flask, render_template, request, session, redirect, url_for
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from tabulate import tabulate
import time
import re
from datetime import datetime
import os





app = Flask(__name__)
#app.secret_key = 'd3a555c134099aaf6518e8ebde5af63961f84488351346ab2ecc21f95f61a8bc'
app.secret_key = os.urandom(24)

COLLEGE_LOGIN_URL = "https://samvidha.iare.ac.in/"
ATTENDANCE_URL = "https://samvidha.iare.ac.in/home?action=course_content"

def get_attendance_data(username, password):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get(COLLEGE_LOGIN_URL)
        time.sleep(2)

        driver.find_element(By.ID, "txt_uname").send_keys(username)
        driver.find_element(By.ID, "txt_pwd").send_keys(password)
        driver.find_element(By.ID, "but_submit").click()

        # 🔎 Better login check
        time.sleep(3)
        if "home" not in driver.current_url:
            return {"error": "Invalid username or password."}

        # 🔎 Instead of forcing get(), click the menu item for Attendance
        try:
            attendance_link = driver.find_element(By.LINK_TEXT, "Course Content")
            attendance_link.click()
        except:
            driver.get(ATTENDANCE_URL)

        time.sleep(3)
        rows = driver.find_elements(By.TAG_NAME, "tr")

        if not rows:
            return {"error": "No attendance data found (maybe server issue)."}

        return calculate_attendance_percentage(rows)

    except Exception as e:
        # print error for debugging
        print("DEBUG ERROR:", str(e))
        return {"error": f"Exception: {str(e)}"}
    finally:
        driver.quit()
def calculate_attendance_percentage(rows):
    result = {
        "subjects": {},
        "overall": {
            "present": 0,
            "absent": 0,
            "percentage": 0.0,
            "success": False,
            "message": ""
        },
        "date_attendance": {},
        "per_course_date_attendance": {},
        "streak": 0,
        "attended_days": 0,
        "absent_days": 0,
        "safe_bunk_days": 0
    }

    current_course = None
    total_present = 0
    total_absent = 0
    date_attendance = {}
    per_course_date_attendance = {}

    for row in rows:
        text = row.text.strip().upper()
        if not text or text.startswith("S.NO") or "TOPICS COVERED" in text:
            continue

        course_match = re.match(r"^(A[A-Z]+\d+|ACDD05)\s*[-:\s]+\s*(.+)$", text)
        if course_match:
            current_course = course_match.group(1)
            course_name = course_match.group(2).strip()
            result["subjects"][current_course] = {
                "name": course_name,
                "present": 0,
                "absent": 0,
                "percentage": 0.0
            }
            per_course_date_attendance[current_course] = {}
            continue

        if current_course:
            present_count = text.count("PRESENT")
            absent_count = text.count("ABSENT")
            result["subjects"][current_course]["present"] += present_count
            result["subjects"][current_course]["absent"] += absent_count
            total_present += present_count
            total_absent += absent_count

            date_match = re.search(r'(\d{2}\s[A-Za-z]{3},\s\d{4}|\d{2}-\d{2}-\d{4})', text)
            if date_match:
                date_str = date_match.group(1).replace(" ", "-").replace(",", "")
                if not re.match(r'^\d{2}-\d{2}-\d{4}$', date_str):
                    continue
                if date_str not in date_attendance:
                    date_attendance[date_str] = {'present': 0, 'absent': 0}
                date_attendance[date_str]['present'] += present_count
                date_attendance[date_str]['absent'] += absent_count

                if date_str not in per_course_date_attendance[current_course]:
                    per_course_date_attendance[current_course][date_str] = {'present': 0, 'absent': 0}
                per_course_date_attendance[current_course][date_str]['present'] += present_count
                per_course_date_attendance[current_course][date_str]['absent'] += absent_count

    for sub_key, sub in result["subjects"].items():
        total = sub["present"] + sub["absent"]
        if total > 0:
            sub["percentage"] = round((sub["present"] / total) * 100, 2)
        sub["safe_bunk_periods"] = max(0, sub["present"] // 3 - sub["absent"])

        course_dates = per_course_date_attendance.get(sub_key, {})
        sub["attended_days"] = len([d for d in course_dates if course_dates[d]['present'] > 0])
        sub["absent_days"] = len([d for d in course_dates if course_dates[d]['present'] == 0 and course_dates[d]['absent'] > 0])
        sub["safe_bunk_days"] = max(0, sub["attended_days"] // 3 - sub["absent_days"])

    overall_total = total_present + total_absent
    if overall_total > 0:
        overall_percentage = round((total_present / overall_total) * 100, 2)
        result["overall"] = {
            "present": total_present,
            "absent": total_absent,
            "percentage": overall_percentage,
            "success": True,
            "message": f"Overall Attendance: Present = {total_present}, Absent = {total_absent}, Percentage = {overall_percentage}%",
            "safe_bunk_periods": max(0, total_present // 3 - total_absent)
        }

    result["date_attendance"] = date_attendance
    result["per_course_date_attendance"] = per_course_date_attendance

    if date_attendance:
        dates = sorted(date_attendance.keys(), key=lambda x: datetime.strptime(x, "%d-%m-%Y"))
        streak = 0
        for d in reversed(dates):
            if date_attendance[d]['present'] > 0:
                streak += 1
            else:
                break
        result["streak"] = streak
        result["attended_days"] = len([d for d in date_attendance if date_attendance[d]['present'] > 0])
        result["absent_days"] = len([d for d in date_attendance if date_attendance[d]['present'] == 0 and date_attendance[d]['absent'] > 0])
        result["safe_bunk_days"] = max(0, result["attended_days"] // 3 - result["absent_days"])

    return result

@app.route("/", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/dashboard", methods=["POST"])
def dashboard():
    username = request.form["username"]
    password = request.form["password"]

    data = get_attendance_data(username, password)

    if "error" in data:
        return render_template("login.html", error=data["error"])

    session['attendance_data'] = data

    calendar_data = []
    date_attendance = data.get('date_attendance', {})
    for d in date_attendance:
        try:
            dt = datetime.strptime(d, "%d-%m-%Y")
            value = 1 if date_attendance[d]['present'] > 0 else 0
            calendar_data.append({'date': dt.strftime("%Y-%m-%d"), 'value': value})
        except ValueError:
            pass

    table_data = []
    for i, (code, sub) in enumerate(data["subjects"].items(), start=1):
        table_data.append([i, code, sub["name"], sub["present"], sub["absent"], f"{sub['percentage']}%"])

    table_html = tabulate(
        table_data,
        headers=["S.No", "Course Code", "Course Name", "Present", "Absent", "Percentage"],
        tablefmt="html"
    )

    return render_template("dashboard.html", data=data, calendar_data=calendar_data, table_html=table_html)

@app.route("/b_safe", methods=["GET"])
def b_safe():
    data = session.get('attendance_data')
    if not data:
        return redirect("/")
    bunk = request.args.get('bunk', 0, type=int)
    total = data["overall"]["present"] + data["overall"]["absent"] + bunk
    projected = round((data["overall"]["present"] / total * 100) if total > 0 else 0, 2)
    return render_template("b_safe.html", data=data, bunk=bunk, projected=projected)

@app.route("/course/<code>", methods=["GET"])
def course(code):
    data = session.get('attendance_data')
    if not data or code not in data['subjects']:
        return redirect("/dashboard")
    sub = data['subjects'][code]
    bunk = request.args.get('bunk', 0, type=int)
    total = sub["present"] + sub["absent"] + bunk
    projected = round((sub["present"] / total * 100) if total > 0 else 0, 2)
    return render_template("course.html", sub=sub, code=code, bunk=bunk, projected=projected)

@app.route("/lab", methods=["GET"])
def lab():
    return "Lab page coming soon"

@app.route("/profile", methods=["GET"])
def profile():
    return "Profile page"

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

if __name__ == "__main__":
    app.run(debug=True)
