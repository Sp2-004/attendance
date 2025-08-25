from flask import Flask, render_template, request, session, redirect, url_for
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from tabulate import tabulate
import time
import re
from datetime import datetime
import os
from PIL import Image
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
import tempfile
from werkzeug.utils import secure_filename





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

            # Enhanced date matching for various formats
            date_match = re.search(r'(\d{1,2}\s[A-Za-z]{3},?\s\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s[A-Za-z]{3})', text)
            if date_match:
                date_str = date_match.group(1).strip()
                
                # Convert various date formats to DD-MM-YYYY
                try:
                    if ',' in date_str:
                        # Format: "20 Aug, 2025" or "20 Aug,2025"
                        date_str = date_str.replace(',', '').strip()
                        dt = datetime.strptime(date_str, "%d %b %Y")
                    elif re.match(r'\d{1,2}\s[A-Za-z]{3}\s\d{4}', date_str):
                        # Format: "20 Aug 2025"
                        dt = datetime.strptime(date_str, "%d %b %Y")
                    elif re.match(r'\d{1,2}\s[A-Za-z]{3}', date_str):
                        # Format: "20 Aug" (assume current year)
                        dt = datetime.strptime(f"{date_str} 2025", "%d %b %Y")
                    elif re.match(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}', date_str):
                        # Format: "20-08-2025" or "20/08/2025"
                        date_str = date_str.replace('/', '-')
                        dt = datetime.strptime(date_str, "%d-%m-%Y")
                    else:
                        continue
                    
                    date_key = dt.strftime("%d-%m-%Y")
                except (ValueError, AttributeError):
                    continue
                
                if date_key not in date_attendance:
                    date_attendance[date_key] = {'present': 0, 'absent': 0}
                date_attendance[date_key]['present'] += present_count
                date_attendance[date_key]['absent'] += absent_count

                if date_key not in per_course_date_attendance[current_course]:
                    per_course_date_attendance[current_course][date_key] = {'present': 0, 'absent': 0}
                per_course_date_attendance[current_course][date_key]['present'] += present_count
                per_course_date_attendance[current_course][date_key]['absent'] += absent_count

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

    # Calculate streak and other date-based metrics
    if date_attendance:
        try:
            dates = sorted(date_attendance.keys(), key=lambda x: datetime.strptime(x, "%d-%m-%Y"))
        except ValueError:
            dates = list(date_attendance.keys())
            
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
    if request.method == "GET":
        # Handle GET requests (navigation from other pages)
        data = session.get('attendance_data')
        if not data:
            return redirect("/")
        
        calendar_data = []
        date_attendance = data.get('date_attendance', {})
        
        for date_key in date_attendance:
            try:
                dt = datetime.strptime(date_key, "%d-%m-%Y")
                value = 1 if date_attendance[date_key]['present'] > 0 else 0
                calendar_data.append({'date': dt.strftime("%Y-%m-%d"), 'value': value})
            except ValueError:
                continue
        
        table_data = []
        for i, (code, sub) in enumerate(data["subjects"].items(), start=1):
            table_data.append([i, code, sub["name"], sub["present"], sub["absent"], f"{sub['percentage']}%"])

        table_html = tabulate(
            table_data,
            headers=["S.No", "Course Code", "Course Name", "Present", "Absent", "Percentage"],
            tablefmt="html"
        )
        
        return render_template("dashboard.html", data=data, calendar_data=calendar_data, table_html=table_html)
    
    # Handle POST requests (login)
    username = request.form["username"]
    password = request.form["password"]

    data = get_attendance_data(username, password)

    if "error" in data:
        return render_template("login.html", error=data["error"])

    session['attendance_data'] = data
    session['username'] = username
    session['password'] = password

    calendar_data = []
    date_attendance = data.get('date_attendance', {})
    
    # Debug: Print date_attendance to see what we have
    print("DEBUG: date_attendance =", date_attendance)
    
    for date_key in date_attendance:
        try:
            dt = datetime.strptime(date_key, "%d-%m-%Y")
            value = 1 if date_attendance[date_key]['present'] > 0 else 0
            calendar_data.append({'date': dt.strftime("%Y-%m-%d"), 'value': value})
        except ValueError:
            print(f"DEBUG: Failed to parse date: {date_key}")
            continue
    
    # Debug: Print calendar_data to see what we're sending to template
    print("DEBUG: calendar_data =", calendar_data)

    table_data = []
    for i, (code, sub) in enumerate(data["subjects"].items(), start=1):
        table_data.append([i, code, sub["name"], sub["present"], sub["absent"], f"{sub['percentage']}%"])

    table_html = tabulate(
        table_data,
        headers=["S.No", "Course Code", "Course Name", "Present", "Absent", "Percentage"],
        tablefmt="html"
    )

    return render_template("dashboard.html", data=data, calendar_data=calendar_data, table_html=table_html)

def get_lab_subjects(username, password):
    """Fetch lab subjects from the website"""
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
        # Login
        driver.get(COLLEGE_LOGIN_URL)
        time.sleep(2)
        driver.find_element(By.ID, "txt_uname").send_keys(username)
        driver.find_element(By.ID, "txt_pwd").send_keys(password)
        driver.find_element(By.ID, "but_submit").click()
        time.sleep(3)

        # Navigate to lab record page
        driver.get("https://samvidha.iare.ac.in/home?action=labrecord_std")
        time.sleep(3)

        # Find the lab select dropdown - try multiple selectors
        lab_select_element = None
        selectors_to_try = [
            (By.NAME, "lab_name"),
            (By.ID, "lab_name"),
            (By.CSS_SELECTOR, "select[name='lab_name']"),
            (By.CSS_SELECTOR, "select#lab_name"),
            (By.XPATH, "//select[@name='lab_name']"),
            (By.XPATH, "//select[contains(@name, 'lab')]"),
            (By.CSS_SELECTOR, "select")  # Last resort - any select element
        ]
        
        for selector_type, selector_value in selectors_to_try:
            try:
                lab_select_element = driver.find_element(selector_type, selector_value)
                print(f"Found lab dropdown using: {selector_type} = {selector_value}")
                break
            except:
                continue
        
        if not lab_select_element:
            # Debug: Print page source to understand the structure
            print("DEBUG: Page source snippet:")
            page_source = driver.page_source
            # Look for select elements
            import re
            select_matches = re.findall(r'<select[^>]*>.*?</select>', page_source, re.DOTALL | re.IGNORECASE)
            for i, match in enumerate(select_matches[:3]):  # Show first 3 select elements
                print(f"Select {i+1}: {match[:200]}...")
            
            return []
        
        try:
            lab_select = Select(lab_select_element)
            lab_options = []
            for option in lab_select.options:
                if option.value and option.value != "Select Lab":
                    lab_options.append({
                        'value': option.value,
                        'text': option.text
                    })
            return lab_options
        except Exception as e:
            print(f"Error finding lab dropdown: {e}")
            # Try to get all select elements as fallback
            try:
                all_selects = driver.find_elements(By.TAG_NAME, "select")
                print(f"Found {len(all_selects)} select elements on page")
                for i, select_elem in enumerate(all_selects):
                    try:
                        select_obj = Select(select_elem)
                        options = [opt.text for opt in select_obj.options if opt.value]
                        print(f"Select {i+1} options: {options[:5]}...")  # Show first 5 options
                        # If this looks like a lab dropdown, use it
                        if any('lab' in opt.lower() for opt in options):
                            lab_options = []
                            for option in select_obj.options:
                                if option.value and option.value.lower() != "select lab":
                                    lab_options.append({
                                        'value': option.value,
                                        'text': option.text
                                    })
                            return lab_options
                    except:
                        continue
            except:
                pass
            return []

    except Exception as e:
        print(f"Error fetching lab subjects: {e}")
        return []
    finally:
        driver.quit()

def compress_images_to_pdf(image_files, max_size_mb=1):
    """Convert and compress images to PDF under specified size"""
    pdf_buffer = io.BytesIO()
    
    # Create PDF
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4
    
    for image_file in image_files:
        try:
            # Open and process image
            img = Image.open(image_file)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Calculate scaling to fit page
            img_width, img_height = img.size
            scale_w = (width - 40) / img_width  # 20pt margin on each side
            scale_h = (height - 40) / img_height  # 20pt margin on each side
            scale = min(scale_w, scale_h, 1.0)  # Don't upscale
            
            new_width = img_width * scale
            new_height = img_height * scale
            
            # Resize image
            img = img.resize((int(img_width * scale), int(img_height * scale)), Image.Resampling.LANCZOS)
            
            # Save to temporary file
            temp_img = io.BytesIO()
            img.save(temp_img, format='JPEG', quality=85, optimize=True)
            temp_img.seek(0)
            
            # Add to PDF
            x = (width - new_width) / 2
            y = (height - new_height) / 2
            c.drawInlineImage(temp_img, x, y, width=new_width, height=new_height)
            c.showPage()
            
        except Exception as e:
            print(f"Error processing image: {e}")
            continue
    
    c.save()
    pdf_buffer.seek(0)
    
    # Check size and compress if needed
    pdf_size = len(pdf_buffer.getvalue())
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if pdf_size > max_size_bytes:
        # Reduce quality and try again
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        
        for image_file in image_files:
            try:
                image_file.seek(0)  # Reset file pointer
                img = Image.open(image_file)
                
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # More aggressive scaling
                img_width, img_height = img.size
                scale_w = (width - 40) / img_width
                scale_h = (height - 40) / img_height
                scale = min(scale_w, scale_h, 0.8)  # Reduce to 80% max
                
                new_width = img_width * scale
                new_height = img_height * scale
                
                img = img.resize((int(img_width * scale), int(img_height * scale)), Image.Resampling.LANCZOS)
                
                temp_img = io.BytesIO()
                img.save(temp_img, format='JPEG', quality=60, optimize=True)  # Lower quality
                temp_img.seek(0)
                
                x = (width - new_width) / 2
                y = (height - new_height) / 2
                c.drawInlineImage(temp_img, x, y, width=new_width, height=new_height)
                c.showPage()
                
            except Exception as e:
                continue
        
        c.save()
        pdf_buffer.seek(0)
    
    return pdf_buffer

def upload_lab_record(username, password, lab_name, week_no, title, pdf_file):
    """Upload lab record to the website"""
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
        # Login
        driver.get(COLLEGE_LOGIN_URL)
        time.sleep(2)
        driver.find_element(By.ID, "txt_uname").send_keys(username)
        driver.find_element(By.ID, "txt_pwd").send_keys(password)
        driver.find_element(By.ID, "but_submit").click()
        time.sleep(3)

        # Navigate to lab record page
        driver.get("https://samvidha.iare.ac.in/home?action=labrecord_std")
        time.sleep(5)

        # Fill the form - find lab dropdown with multiple selectors
        lab_select_element = None
        selectors_to_try = [
            (By.NAME, "lab_name"),
            (By.ID, "lab_name"),
            (By.CSS_SELECTOR, "select[name='lab_name']"),
            (By.XPATH, "//select[@name='lab_name']"),
            (By.XPATH, "//select[contains(@name, 'lab')]")
        ]
        
        for selector_type, selector_value in selectors_to_try:
            try:
                lab_select_element = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if not lab_select_element:
            return {"success": False, "message": "Could not find lab selection dropdown on the page"}
        
        lab_select = Select(lab_select_element)
        lab_select.select_by_value(lab_name)
        
        # Find week dropdown with multiple selectors
        week_select_element = None
        week_selectors = [
            (By.NAME, "week_no"),
            (By.ID, "week_no"),
            (By.CSS_SELECTOR, "select[name='week_no']"),
            (By.XPATH, "//select[@name='week_no']"),
            (By.XPATH, "//select[contains(@name, 'week')]")
        ]
        
        for selector_type, selector_value in week_selectors:
            try:
                week_select_element = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if not week_select_element:
            return {"success": False, "message": "Could not find week selection dropdown on the page"}
        
        week_select = Select(week_select_element)
        week_select.select_by_value(str(week_no))
        
        # Find title field with multiple selectors
        title_field = None
        title_selectors = [
            (By.NAME, "title"),
            (By.ID, "title"),
            (By.CSS_SELECTOR, "input[name='title']"),
            (By.XPATH, "//input[@name='title']"),
            (By.XPATH, "//input[contains(@placeholder, 'title') or contains(@name, 'title')]")
        ]
        
        for selector_type, selector_value in title_selectors:
            try:
                title_field = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if not title_field:
            return {"success": False, "message": "Could not find title input field on the page"}
        
        title_field.send_keys(title)
        
        # Save PDF to temporary file for upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_file.getvalue())
            temp_file_path = temp_file.name
        
        # Upload file - find file input with multiple selectors
        file_input = None
        file_selectors = [
            (By.NAME, "program_document"),
            (By.ID, "program_document"),
            (By.CSS_SELECTOR, "input[type='file']"),
            (By.XPATH, "//input[@type='file']"),
            (By.XPATH, "//input[contains(@name, 'document') or contains(@name, 'file')]")
        ]
        
        for selector_type, selector_value in file_selectors:
            try:
                file_input = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if not file_input:
            os.unlink(temp_file_path)  # Clean up temp file
            return {"success": False, "message": "Could not find file upload field on the page"}
        
        file_input.send_keys(temp_file_path)
        
        time.sleep(2)
        
        # Submit form - find submit button with multiple selectors
        submit_button = None
        submit_selectors = [
            (By.XPATH, "//input[@type='submit' and @value='Submit']"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//input[@type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Submit')]")
        ]
        
        for selector_type, selector_value in submit_selectors:
            try:
                submit_button = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if not submit_button:
            os.unlink(temp_file_path)  # Clean up temp file
            return {"success": False, "message": "Could not find submit button on the page"}
        
        submit_button.click()
        
        time.sleep(3)
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        # Check for success message or error
        page_source = driver.page_source.lower()
        if "success" in page_source or "uploaded" in page_source:
            return {"success": True, "message": "Lab record uploaded successfully!"}
        elif "error" in page_source or "failed" in page_source:
            return {"success": False, "message": "Upload failed. Please check your inputs and try again."}
        else:
            return {"success": True, "message": "Upload completed. Please verify on the website."}
            
    except Exception as e:
        return {"success": False, "message": f"Error uploading lab record: {str(e)}"}
    finally:
        driver.quit()

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

@app.route("/lab", methods=["GET", "POST"])
def lab():
    data = session.get('attendance_data')
    
    if request.method == "POST":
        # Handle lab record upload
        try:
            lab_name = request.form.get('lab_name')
            week_no = request.form.get('week_no')
            title = request.form.get('title')
            images = request.files.getlist('images')
            
            if not all([lab_name, week_no, title]) or not images:
                return render_template("lab.html", data=data, error="Please fill all fields and select images")
            
            # Get credentials from session or request
            username = session.get('username')
            password = session.get('password')
            
            if not username or not password:
                return render_template("lab.html", data=data, error="Session expired. Please login again.")
            
            # Compress images to PDF
            pdf_file = compress_images_to_pdf(images)
            
            # Upload to website
            result = upload_lab_record(username, password, lab_name, week_no, title, pdf_file)
            
            if result["success"]:
                return render_template("lab.html", data=data, success=result["message"])
            else:
                return render_template("lab.html", data=data, error=result["message"])
                
        except Exception as e:
            return render_template("lab.html", data=data, error=f"Error processing upload: {str(e)}")
    
    return render_template("lab.html", data=data)

@app.route("/get_lab_subjects", methods=["POST"])
def get_lab_subjects_route():
    """API endpoint to fetch lab subjects"""
    try:
        username = session.get('username')
        password = session.get('password')
        
        if not username or not password:
            return {"error": "Session expired"}, 401
        
        lab_subjects = get_lab_subjects(username, password)
        return {"subjects": lab_subjects}
        
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/profile", methods=["GET"])
def profile():
    data = session.get('attendance_data')
    return render_template("profile.html", data=data)

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

if __name__ == "__main__":
    app.run(debug=True)
