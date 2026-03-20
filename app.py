from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
from flask_cors import CORS
import os
import csv
import pandas as pd
from io import BytesIO, StringIO
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///school.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)

db = SQLAlchemy(app)

# ✅ Define allowed extensions
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

# ✅ Define upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Login Required Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Admin Required Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        
        if session.get('role') != 'admin':
            flash('Access denied! Admin privileges required.', 'danger')
            return redirect(url_for('home'))
        
        return f(*args, **kwargs)
    return decorated_function

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), default='user')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    room_no = db.Column(db.String(20))

class ClassLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    period = db.Column(db.String(50))
    class_name = db.Column(db.String(50))
    section = db.Column(db.String(10))
    subject = db.Column(db.String(100))
    teacher = db.Column(db.String(100))
    records = db.Column(db.JSON)

class StudyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    study_type = db.Column(db.String(50))
    teacher = db.Column(db.String(100))
    room_no = db.Column(db.String(20))
    records = db.Column(db.JSON)

class DiaryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100))
    class_name = db.Column(db.String(50))
    section = db.Column(db.String(10))
    date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(50))
    remarks = db.Column(db.Text)

class FileUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_by = db.Column(db.String(80))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

# --- Routes ---

@app.route('/tcs')
def home():
    return render_template('index.html')

@app.route('/tcs/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user.role
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/tcs/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ✅ Regular User Routes
@app.route('/tcs/class_log', methods=['GET', 'POST'])
@login_required
def class_log():
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        records = {}
        for key, value in request.form.items():
            if key.startswith('student_'):
                student_id = key.split('_')[1]
                records[student_id] = value
        
        new_log = ClassLog(
            date=date,
            period=request.form['period'],
            class_name=request.form['class_name'],
            section=request.form['section'],
            subject=request.form['subject'],
            teacher=request.form['teacher'],
            records=records
        )
        db.session.add(new_log)
        db.session.commit()
        flash('Attendance Saved!', 'success')
        return redirect(url_for('class_log'))
    
    classes = ['PP','I', 'II', 'III','IV','V','VI','VII','VIII','IX','X','XI','XII']
    sections = ['A', 'B', 'C','D','Science','Commerce','Arts','NA']
    subjects = ['Dzongkha', 'Mathematics', 'English','Business Entrepreneur','Accountancy','Physics','Biology','Chemistry','Digital Technology & Innovation','Science','Geography','History','Economics','Library','VE','HPE','CGC','AE','Substitution']
    return render_template('class_log.html', classes=classes, sections=sections, subjects=subjects)

@app.route('/tcs/study_log', methods=['GET', 'POST'])
@login_required
def study_log():
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            study_type = request.form.get('study_type')
            teacher = request.form.get('teacher')
            room_no = request.form.get('room_no')
            
            if not date_str or not study_type or not teacher or not room_no:
                flash('All required fields must be filled!', 'danger')
                return redirect(url_for('study_log'))
            
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            records = {}
            for key, value in request.form.items():
                if key.startswith('student_'):
                    student_id = key.split('_')[1]
                    records[student_id] = value
            
            if not records:
                flash('No students selected for attendance!', 'warning')
                return redirect(url_for('study_log'))
            
            new_log = StudyLog(
                date=date,
                study_type=study_type,
                teacher=teacher,
                room_no=room_no,
                records=records
            )
            db.session.add(new_log)
            db.session.commit()
            flash('Study Log Saved!', 'success')
            return redirect(url_for('study_log'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving study log: {str(e)}', 'danger')
            return redirect(url_for('study_log'))
    
    study_types = ['Morning Study', 'Evening Study', 'Night', 'Sunday Study']
    rooms = ['XII Sci','XII Com','XI Sci','XI Com','XI Arts','XA','XB','XC','XD','IXA','IXB','IXC','IXD','VIIIA','VIIIB','VIIA','VIIB','VIA','VIB','V']
    
    return render_template('study_log.html', study_types=study_types, rooms=rooms)

@app.route('/tcs/diary', methods=['GET', 'POST'])
@login_required
def diary():
    if request.method == 'POST':
        try:
            required_fields = ['student_name', 'class_name', 'section', 'date', 'category', 'remarks']
            all_filled = all(request.form.get(field, '').strip() for field in required_fields)
            
            if not all_filled:
                flash('Please fill all fields!', 'warning')
                return redirect(url_for('diary'))
            
            date = datetime.strptime(request.form['date'].strip(), '%Y-%m-%d').date()
            
            entry = DiaryEntry(
                student_name=request.form['student_name'].strip(),
                class_name=request.form['class_name'].strip(),
                section=request.form['section'].strip(),
                date=date,
                category=request.form['category'].strip(),
                remarks=request.form['remarks'].strip()
            )
            db.session.add(entry)
            db.session.commit()
            flash('✅ Diary Entry Saved!', 'success')
            return redirect(url_for('diary'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving diary entry: {str(e)}', 'danger')
            return redirect(url_for('diary'))
    
    # Dropdown data
    categories = ['punctuality', 'Substance Abuse', 'Bulgar/Prowling', 'bunking','illicit relationship','Tresspassing/theft','Bullying']
    classes = ['PP','I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII']
    sections = ['A','B','C','D','NA','Science','Commerce','Arts']
    
    return render_template('diary.html', categories=categories, classes=classes, sections=sections)


@app.route('/tcs/file_upload', methods=['GET', 'POST'])
#@admin_required  # ✅ Only admin can access
def file_upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'danger')
            return redirect(url_for('file_upload'))
        
        file = request.files['file']
        category = request.form.get('category')
        
        if file.filename == '':
            flash('No file selected!', 'danger')
            return redirect(url_for('file_upload'))
        
        if file and allowed_file(file.filename):
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            
            category_folder = os.path.join(UPLOAD_FOLDER, category)
            os.makedirs(category_folder, exist_ok=True)
            
            filename = secure_filename(file.filename)
            filepath = os.path.join(category_folder, filename)
            file.save(filepath)
            
            file_size = os.path.getsize(filepath)
            
            new_file = FileUpload(
                filename=filename,
                original_filename=file.filename,
                category=category,
                file_type=file_ext,
                file_size=file_size,
                uploaded_by=session.get('username', 'Unknown')
            )
            db.session.add(new_file)
            db.session.commit()
            
            flash(f'File "{filename}" uploaded successfully!', 'success')
            return redirect(url_for('file_upload'))
        else:
            flash('Invalid file type! Only PDF and Word files allowed.', 'danger')
            return redirect(url_for('file_upload'))
    
    categories = FileUpload.query.with_entities(FileUpload.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    default_categories = ['Spiritual', 'Cerebral', 'Social', 'Physical', 'Emotional']
    for cat in default_categories:
        if cat not in categories:
            categories.append(cat)
    
    recent_files = FileUpload.query.order_by(FileUpload.upload_date.desc()).limit(10).all()
    
    return render_template('file_upload.html', categories=categories, recent_files=recent_files)

# ✅ Admin-Only Routes
@app.route('/tcs/students', methods=['GET', 'POST'])
@admin_required
def students():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'upload':
            file = request.files.get('file')
            if file:
                try:
                    content = file.stream.read().decode('UTF-8')
                    reader = csv.DictReader(StringIO(content))
                    
                    count = 0
                    for row in reader:
                        student = Student(
                            name=row.get('Name', '').strip(),
                            class_name=row.get('Class', '').strip(),
                            section=row.get('Section', '').strip(),
                            room_no=row.get('Study Room', '').strip()
                        )
                        db.session.add(student)
                        count += 1
                    
                    db.session.commit()
                    flash(f'{count} students uploaded successfully!', 'success')
                    return redirect(url_for('students'))
                    
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error uploading file: {str(e)}', 'danger')
                    return redirect(url_for('students'))
        
        elif action == 'add':
            student_name = request.form.get('student_name', '').strip()
            class_name = request.form.get('class_name', '').strip()
            section = request.form.get('section', '').strip()
            study_room = request.form.get('study_room', '').strip()
            
            if not student_name or not class_name or not section:
                flash('All required fields must be filled!', 'danger')
                return redirect(url_for('students'))
            
            student = Student(
                name=student_name,
                class_name=class_name,
                section=section,
                room_no=study_room
            )
            db.session.add(student)
            db.session.commit()
            flash('Student Added!', 'success')
            return redirect(url_for('students'))
    
    students = Student.query.all()
    return render_template('students.html', students=students)

@app.route('/tcs/attendance')
@admin_required
def attendance():
    class_logs = ClassLog.query.order_by(ClassLog.date.desc()).all()
    study_logs = StudyLog.query.order_by(StudyLog.date.desc()).all()
    return render_template('attendance.html', class_logs=class_logs, study_logs=study_logs)

@app.route('/tcs/reports')
@admin_required
def reports():
    class_logs = ClassLog.query.all()
    study_logs = StudyLog.query.all()
    diary_entries = DiaryEntry.query.all()
    return render_template('reports.html', class_logs=class_logs, study_logs=study_logs, diary_entries=diary_entries)

@app.route('/tcs/manage_users', methods=['GET', 'POST'])
@admin_required
def manage_users():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_user':
            username = request.form.get('username')
            password = request.form.get('password')
            role = request.form.get('role', 'user')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists!', 'danger')
                return redirect(url_for('manage_users'))
            
            new_user = User(username=username, password=password, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash(f'User "{username}" created successfully!', 'success')
            return redirect(url_for('manage_users'))
        
        elif action == 'delete_user':
            user_id = request.form.get('user_id')
            user = User.query.get(user_id)
            if user and user.username != 'tsenkharlacs':
                db.session.delete(user)
                db.session.commit()
                flash(f'User "{user.username}" deleted!', 'success')
            return redirect(url_for('manage_users'))
    
    users = User.query.all()
    return render_template('manage_users.html', users=users)

# ✅ API Endpoint
@app.route('/api/tcs/students')
def get_students():
    """API endpoint to fetch students by class, section, or study room"""
    if 'logged_in' not in session:
        return jsonify({'error': 'Unauthorized - Please login first'}), 401
    
    class_name = request.args.get('class')
    section = request.args.get('section')
    study_room = request.args.get('study_room')
    
    print(f"🔍 API Request: class={class_name}, section={section}, study_room={study_room}")
    
    if not class_name and not section and not study_room:
        return jsonify([]), 400
    
    query = Student.query
    
    if class_name and section:
        query = query.filter_by(class_name=class_name, section=section)
    elif study_room:
        query = query.filter_by(room_no=study_room)
    
    students = query.all()
    
    print(f"📊 Found {len(students)} students")
    
    return jsonify([{'id': s.id, 'name': s.name} for s in students])

# --- Export Routes ---
@app.route('/export/class_log')
@login_required
def export_class_log():
    """Export Class Log Attendance to Excel"""
    class_logs = ClassLog.query.all()
    
    student_ids = set()
    for log in class_logs:
        if log.records:
            student_ids.update(log.records.keys())
    
    student_lookup = {
        str(student.id): student.name 
        for student in Student.query.filter(Student.id.in_(student_ids))
    }
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data = []
        for log in class_logs:
            records = log.records if log.records else {}
            for student_id, status in records.items():
                student_name = student_lookup.get(student_id, 'Unknown')
                
                data.append({
                    'Date': log.date.strftime('%Y-%m-%d'),
                    'Period': log.period,
                    'Class': log.class_name,
                    'Section': log.section,
                    'Subject': log.subject,
                    'Teacher': log.teacher,
                    'Student Name': student_name,
                    'Status': status
                })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='Class Log', index=False)
    
    output.seek(0)
    filename = f'Class_Log_Attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/export/study_log')
@login_required
def export_study_log():
    """Export Study Log Attendance to Excel"""
    study_logs = StudyLog.query.all()
    
    student_ids = set()
    for log in study_logs:
        if log.records:
            student_ids.update(log.records.keys())
    
    student_lookup = {
        str(student.id): student.name 
        for student in Student.query.filter(Student.id.in_(student_ids))
    }
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data = []
        for log in study_logs:
            records = log.records if log.records else {}
            for student_id, status in records.items():
                student_name = student_lookup.get(student_id, 'Unknown')
                
                data.append({
                    'Date': log.date.strftime('%Y-%m-%d'),
                    'Study Type': log.study_type,
                    'Room': log.room_no,
                    'Teacher': log.teacher,
                    'Student Name': student_name,
                    'Status': status
                })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='Study Log', index=False)
    
    output.seek(0)
    filename = f'Study_Log_Attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/export/combined')
@login_required
def export_combined():
    """Export Both Class Log and Study Log to Excel"""
    class_logs = ClassLog.query.all()
    study_logs = StudyLog.query.all()
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        class_data = []
        for log in class_logs:
            records = log.records if log.records else {}
            for student_id, status in records.items():
                class_data.append({
                    'Date': log.date.strftime('%Y-%m-%d'),
                    'Type': 'Class Log',
                    'Period/Study Type': log.period,
                    'Class/Room': f"{log.class_name} - {log.section}",
                    'Subject/Study': log.subject,
                    'Teacher': log.teacher,
                    'Student ID': student_id,
                    'Status': status
                })
        
        study_data = []
        for log in study_logs:
            records = log.records if log.records else {}
            for student_id, status in records.items():
                study_data.append({
                    'Date': log.date.strftime('%Y-%m-%d'),
                    'Type': 'Study Log',
                    'Period/Study Type': log.study_type,
                    'Class/Room': f"Room {log.room_no}",
                    'Subject/Study': 'Study Session',
                    'Teacher': log.teacher,
                    'Student ID': student_id,
                    'Status': status
                })
        
        all_data = class_data + study_data
        df = pd.DataFrame(all_data)
        df.to_excel(writer, sheet_name='Combined Attendance', index=False)
    
    output.seek(0)
    filename = f'Combined_Attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/export/diary')
@login_required
def export_diary():
    """Export Diary Entries to Excel"""
    diary_entries = DiaryEntry.query.all()
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data = []
        for entry in diary_entries:
            data.append({
                'Date': entry.date.strftime('%Y-%m-%d'),
                'Student Name': entry.student_name,
                'Class': entry.class_name,
                'Section': entry.section,
                'Category': entry.category,
                'Remarks': entry.remarks
            })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='Diary Entries', index=False)
    
    output.seek(0)
    filename = f'Diary_Entries_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

# --- File Management Routes ---
@app.route('/tcs/file_list/<category>')
@login_required
def file_list(category):
    """Display all files in a specific category"""
    files = FileUpload.query.filter_by(category=category).order_by(FileUpload.upload_date.desc()).all()
    return render_template('file_list.html', files=files, category=category)

@app.route('/tcs/download/<int:file_id>')
@login_required
def download_file(file_id):
    """Download a specific file"""
    file = FileUpload.query.get_or_404(file_id)
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.category, file.filename)
    
    if not os.path.exists(file_path):
        flash('File not found!', 'danger')
        return redirect(url_for('file_upload'))
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=file.original_filename
    )

# --- Initialize Database and Default Users ---
with app.app_context():
    db.create_all()
    
    # Create admin user if not exists
    if not User.query.filter_by(username='tsenkharlacs').first():
        admin = User(username='tsenkharlacs', password='tsenkharlaHSS@2026', role='admin')
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created!")
    
    # Create regular user if not exists
    if not User.query.filter_by(username='teacher').first():
        teacher = User(username='teacher', password='tsenkharlaHSS@2026', role='user')
        db.session.add(teacher)
        db.session.commit()
        print("✅ Teacher user created!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
