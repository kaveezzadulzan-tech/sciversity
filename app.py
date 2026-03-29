from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import io
import base64
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

app = Flask(__name__)
app.secret_key = 'sciversity-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sciversity.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── MODELS ───────────────────────────────────────────────────────────────────

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    hours_logged = db.Column(db.Float, default=0.0)
    hours_paid = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sessions = db.relationship('AttendanceSession', backref='student', lazy=True)
    homework_statuses = db.relationship('HomeworkStatus', backref='student', lazy=True)
    payment_records = db.relationship('PaymentRecord', backref='student', lazy=True)

    @property
    def balance(self):
        return self.hours_logged - self.hours_paid

    @property
    def payment_due(self):
        return self.balance >= 8

    @property
    def cycle_hours(self):
        return self.balance % 8

    @property
    def qr_code(self):
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(f"SCIVERSITY:{self.id}:{self.name}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()


class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    duration = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    class_time = db.Column(db.String(50), default='')   # e.g. "4:00 PM – 6:00 PM"
    note = db.Column(db.String(200), default='')


class PaymentRecord(db.Model):
    """Tracks each time admin marks a payment with timestamp and note."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)
    hours_block = db.Column(db.Float, default=8.0)
    note = db.Column(db.String(200), default='')


class ClassSchedule(db.Model):
    """Admin-defined class time slots shown on QR card / PDF."""
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20), nullable=False)        # e.g. "Monday"
    time_range = db.Column(db.String(50), nullable=False) # e.g. "4:00 PM – 6:00 PM"
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)  # None = open/general slot


class Homework(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    statuses = db.relationship('HomeworkStatus', backref='homework', lazy=True)


class HomeworkStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    homework_id = db.Column(db.Integer, db.ForeignKey('homework.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    done = db.Column(db.Boolean, default=False)
    done_at = db.Column(db.DateTime, nullable=True)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def admin_logged_in():
    return session.get('admin') is True

def student_logged_in():
    return 'student_id' in session

def get_current_student():
    if student_logged_in():
        return Student.query.get(session['student_id'])
    return None

def student_json(s):
    return {
        'success': True,
        'name': s.name,
        'hours_logged': round(s.hours_logged, 2),
        'balance': round(s.balance, 2),
        'payment_due': s.payment_due,
        'cycle_hours': round(s.cycle_hours, 2)
    }

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        student = Student.query.filter_by(email=email, password=password).first()
        if student:
            session['student_id'] = student.id
            return redirect(url_for('student_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('student_login.html')

@app.route('/student/logout')
def student_logout():
    session.pop('student_id', None)
    return redirect(url_for('student_login'))

# ─── ADMIN ────────────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
def admin_dashboard():
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    students = Student.query.order_by(Student.name).all()
    homework_list = Homework.query.order_by(Homework.posted_at.desc()).all()
    schedules = ClassSchedule.query.all()
    # Build schedule list with student names for template
    schedules_data = []
    for sch in schedules:
        student_name = None
        if sch.student_id:
            s = Student.query.get(sch.student_id)
            student_name = s.name if s else None
        schedules_data.append({'id': sch.id, 'day': sch.day, 'time_range': sch.time_range, 'student_id': sch.student_id, 'student_name': student_name})
    return render_template('admin_dashboard.html', students=students, homework_list=homework_list, schedules=schedules, schedules_data=schedules_data)

@app.route('/admin/add_student', methods=['POST'])
def add_student():
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    name = request.form.get('name').strip()
    email = request.form.get('email').strip().lower()
    password = request.form.get('password').strip()
    if not name or not email or not password:
        flash('All fields required', 'danger')
        return redirect(url_for('admin_dashboard'))
    if Student.query.filter_by(email=email).first():
        flash('Email already registered', 'danger')
        return redirect(url_for('admin_dashboard'))
    s = Student(name=name, email=email, password=password)
    db.session.add(s)
    db.session.commit()
    flash(f'Student {name} added!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    s = Student.query.get_or_404(student_id)
    HomeworkStatus.query.filter_by(student_id=student_id).delete()
    AttendanceSession.query.filter_by(student_id=student_id).delete()
    PaymentRecord.query.filter_by(student_id=student_id).delete()
    db.session.delete(s)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/log_session', methods=['POST'])
def log_session():
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    student_id = data.get('student_id')
    duration = float(data.get('duration', 1.0))
    class_time = data.get('class_time', '')
    if duration <= 0:
        return jsonify({'error': 'Duration must be positive'}), 400
    s = Student.query.get(student_id)
    if not s:
        return jsonify({'error': 'Student not found'}), 404
    rec = AttendanceSession(student_id=student_id, duration=duration, class_time=class_time)
    db.session.add(rec)
    s.hours_logged += duration
    db.session.commit()
    return jsonify(student_json(s))

@app.route('/admin/undo_session/<int:student_id>', methods=['POST'])
def undo_session(student_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    s = Student.query.get_or_404(student_id)
    last = AttendanceSession.query.filter_by(student_id=student_id)\
               .order_by(AttendanceSession.date.desc()).first()
    if not last:
        return jsonify({'error': 'No sessions to undo'}), 400
    undone = last.duration
    s.hours_logged = max(0, s.hours_logged - undone)
    db.session.delete(last)
    db.session.commit()
    r = student_json(s)
    r['undone'] = undone
    return jsonify(r)

@app.route('/admin/reset_payment/<int:student_id>', methods=['POST'])
def reset_payment(student_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    note = data.get('note', '')
    s = Student.query.get_or_404(student_id)
    s.hours_paid += 8
    pr = PaymentRecord(student_id=student_id, hours_block=8.0, note=note)
    db.session.add(pr)
    db.session.commit()
    return jsonify(student_json(s))

@app.route('/admin/reset_cycle/<int:student_id>', methods=['POST'])
def reset_cycle(student_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    s = Student.query.get_or_404(student_id)
    s.hours_paid = s.hours_logged
    db.session.commit()
    return jsonify(student_json(s))

@app.route('/admin/student_qr/<int:student_id>')
def student_qr(student_id):
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    s = Student.query.get_or_404(student_id)
    schedules = ClassSchedule.query.all()
    schedules_data = []
    for sch in schedules:
        student_name = None
        if sch.student_id:
            st = Student.query.get(sch.student_id)
            student_name = st.name if st else None
        schedules_data.append({'id': sch.id, 'day': sch.day, 'time_range': sch.time_range, 'student_id': sch.student_id, 'student_name': student_name})
    return render_template('student_qr.html', student=s, schedules=schedules_data)

@app.route('/admin/student_detail/<int:student_id>')
def student_detail(student_id):
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    s = Student.query.get_or_404(student_id)
    sessions = AttendanceSession.query.filter_by(student_id=student_id)\
                   .order_by(AttendanceSession.date.desc()).all()
    payments = PaymentRecord.query.filter_by(student_id=student_id)\
                   .order_by(PaymentRecord.paid_at.desc()).all()
    return render_template('student_detail.html', student=s, sessions=sessions, payments=payments)

# ─── CLASS SCHEDULE ───────────────────────────────────────────────────────────

@app.route('/admin/add_schedule', methods=['POST'])
def add_schedule():
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    day = data.get('day', '').strip()
    time_range = data.get('time_range', '').strip()
    student_id = data.get('student_id') or None
    if student_id:
        student_id = int(student_id)
    if not day or not time_range:
        return jsonify({'error': 'Day and time required'}), 400
    sch = ClassSchedule(day=day, time_range=time_range, student_id=student_id)
    db.session.add(sch)
    db.session.commit()
    student_name = None
    if student_id:
        s = Student.query.get(student_id)
        student_name = s.name if s else None
    return jsonify({'success': True, 'id': sch.id, 'day': sch.day, 'time_range': sch.time_range, 'student_id': student_id, 'student_name': student_name})

@app.route('/admin/delete_schedule/<int:sch_id>', methods=['POST'])
def delete_schedule(sch_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    ClassSchedule.query.filter_by(id=sch_id).delete()
    db.session.commit()
    return jsonify({'success': True})

# ─── PDF REPORT ───────────────────────────────────────────────────────────────

@app.route('/admin/student_pdf/<int:student_id>')
def student_pdf(student_id):
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    s = Student.query.get_or_404(student_id)
    sessions = AttendanceSession.query.filter_by(student_id=student_id)\
                   .order_by(AttendanceSession.date.asc()).all()
    payments = PaymentRecord.query.filter_by(student_id=student_id)\
                   .order_by(PaymentRecord.paid_at.asc()).all()
    schedules = ClassSchedule.query.all()
    schedules_data = []
    for sch in schedules:
        student_name = None
        if sch.student_id:
            st = Student.query.get(sch.student_id)
            student_name = st.name if st else None
        schedules_data.append({'day': sch.day, 'time_range': sch.time_range, 'student_name': student_name})

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle('title', fontSize=24, fontName='Helvetica-Bold',
                                  textColor=colors.HexColor('#3949ab'), alignment=TA_CENTER,
                                  spaceBefore=10, spaceAfter=10)
    sub_style = ParagraphStyle('sub', fontSize=12, textColor=colors.HexColor('#78909c'),
                                alignment=TA_CENTER, spaceAfter=22)
    normal = ParagraphStyle('normal', fontSize=9, fontName='Helvetica', leading=14)
    bold = ParagraphStyle('bold', fontSize=9, fontName='Helvetica-Bold', leading=14)

    story.append(Paragraph("SCIVERSITY", title_style))
    story.append(Paragraph("Student Attendance &amp; Finance Log", sub_style))
    story.append(Spacer(1, 0.3*cm))

    # Student info box
    info_data = [
        ['Student Name', s.name, 'Student ID', f'#{s.id}'],
        ['Email', s.email, 'Report Date', datetime.now().strftime('%d %b %Y, %H:%M')],
        ['Total Hours Logged', f'{s.hours_logged:.1f}h', 'Total Hours Paid', f'{s.hours_paid:.1f}h'],
        ['Current Balance', f'{s.balance:.1f}h', 'Payment Status',
         '⚠ PAYMENT DUE' if s.payment_due else '✓ Active'],
    ]
    info_table = Table(info_data, colWidths=[4*cm, 6*cm, 4*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#e8eaf6')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#e8eaf6')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c5cae9')),
        ('ROWBACKGROUNDS', (1,0), (1,-1), [colors.white]),
        ('ROWBACKGROUNDS', (3,0), (3,-1), [colors.white]),
        ('PADDING', (0,0), (-1,-1), 6),
        ('TEXTCOLOR', (1,3), (1,3), colors.HexColor('#c62828') if s.payment_due else colors.HexColor('#2e7d32')),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # Class Schedule
    if schedules_data:
        story.append(Paragraph("Class Schedule", ParagraphStyle('h2', fontSize=11, fontName='Helvetica-Bold',
                                textColor=colors.HexColor('#3949ab'), spaceBefore=8, spaceAfter=6)))
        sch_data = [['Day', 'Time', 'Student']]
        for sch in schedules_data:
            sch_data.append([sch['day'], sch['time_range'], sch['student_name'] or 'Open slot'])
        sch_table = Table(sch_data, colWidths=[3.5*cm, 8*cm, 6.5*cm])
        sch_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3949ab')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c5cae9')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f3f0ff')]),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(sch_table)
        story.append(Spacer(1, 0.5*cm))

    # Payment History
    story.append(Paragraph("Payment History", ParagraphStyle('h2', fontSize=11, fontName='Helvetica-Bold',
                            textColor=colors.HexColor('#3949ab'), spaceBefore=8, spaceAfter=6)))
    if payments:
        pay_data = [['#', 'Date', 'Day', 'Hours Block', 'Note']]
        for i, p in enumerate(payments, 1):
            pay_data.append([
                str(i),
                p.paid_at.strftime('%d %b %Y'),
                p.paid_at.strftime('%A'),
                f'{p.hours_block:.0f}h block',
                p.note or '—'
            ])
        pay_table = Table(pay_data, colWidths=[1*cm, 3.5*cm, 3*cm, 3.5*cm, 7*cm])
        pay_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2e7d32')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c8e6c9')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f1f8e9')]),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(pay_table)
    else:
        story.append(Paragraph("No payments recorded yet.", normal))
    story.append(Spacer(1, 0.5*cm))

    # Attendance Log — grouped by payment cycle
    story.append(Paragraph("Attendance Log", ParagraphStyle('h2', fontSize=11, fontName='Helvetica-Bold',
                            textColor=colors.HexColor('#3949ab'), spaceBefore=8, spaceAfter=6)))

    # Figure out when payment was due (every 8h from start)
    att_data = [['#', 'Date', 'Day', 'Class Time', 'Duration', 'Cycle Status']]
    running = 0.0
    cycle_num = 1

    for i, sess in enumerate(sessions, 1):
        running += sess.duration
        over = max(0, running - (cycle_num * 8))
        status = ''
        if running >= cycle_num * 8:
            status = f'⚠ Cycle {cycle_num} due'
            if over > 0:
                status += f' (+{over:.1f}h over)'
            cycle_num += 1
        att_data.append([
            str(i),
            sess.date.strftime('%d %b %Y'),
            sess.date.strftime('%A'),
            sess.class_time or '—',
            f'{sess.duration}h',
            status
        ])

    att_table = Table(att_data, colWidths=[0.8*cm, 3*cm, 2.5*cm, 4*cm, 2*cm, 5.7*cm])
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3949ab')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#c5cae9')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f3f0ff')]),
        ('PADDING', (0,0), (-1,-1), 5),
        ('WORDWRAP', (0,0), (-1,-1), True),
    ]))
    # Highlight rows where cycle was due
    for row_idx, row in enumerate(att_data[1:], 1):
        if '⚠' in str(row[5]):
            att_table.setStyle(TableStyle([
                ('BACKGROUND', (0,row_idx), (-1,row_idx), colors.HexColor('#fff3e0')),
                ('TEXTCOLOR', (5,row_idx), (5,row_idx), colors.HexColor('#e65100')),
            ]))

    story.append(att_table)
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(f"Generated by Sciversity on {datetime.now().strftime('%d %b %Y at %H:%M')}",
                            ParagraphStyle('footer', fontSize=8, textColor=colors.HexColor('#90a4ae'), alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=sciversity_{s.name.replace(" ","_")}_log.pdf'
    return response

# ─── HOMEWORK ─────────────────────────────────────────────────────────────────

@app.route('/admin/post_homework', methods=['POST'])
def post_homework():
    if not admin_logged_in():
        return redirect(url_for('admin_login'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    target = request.form.get('target', 'all')
    selected_ids = request.form.getlist('student_ids')
    if not title:
        flash('Homework title is required', 'danger')
        return redirect(url_for('admin_dashboard'))
    hw = Homework(title=title, description=description)
    db.session.add(hw)
    db.session.flush()
    if target == 'all':
        recipients = Student.query.all()
    else:
        if not selected_ids:
            flash('Please select at least one student', 'danger')
            db.session.rollback()
            return redirect(url_for('admin_dashboard'))
        recipients = Student.query.filter(Student.id.in_([int(i) for i in selected_ids])).all()
    for student in recipients:
        db.session.add(HomeworkStatus(homework_id=hw.id, student_id=student.id, done=False))
    db.session.commit()
    count = len(recipients)
    flash(f'Homework posted to {count} student{"s" if count != 1 else ""}!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_homework/<int:hw_id>', methods=['POST'])
def delete_homework(hw_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    HomeworkStatus.query.filter_by(homework_id=hw_id).delete()
    Homework.query.filter_by(id=hw_id).delete()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/homework_status/<int:hw_id>')
def homework_status(hw_id):
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    hw = Homework.query.get_or_404(hw_id)
    statuses = HomeworkStatus.query.filter_by(homework_id=hw_id).all()
    result = []
    for st in statuses:
        student = Student.query.get(st.student_id)
        result.append({
            'name': student.name,
            'done': st.done,
            'done_at': st.done_at.strftime('%d %b %H:%M') if st.done_at else None
        })
    return jsonify({'title': hw.title, 'statuses': result})

# ─── STUDENT ──────────────────────────────────────────────────────────────────

@app.route('/student/dashboard')
def student_dashboard():
    if not student_logged_in():
        return redirect(url_for('student_login'))
    student = get_current_student()
    all_hw = Homework.query.order_by(Homework.posted_at.desc()).all()
    hw_data = []
    for hw in all_hw:
        st = HomeworkStatus.query.filter_by(homework_id=hw.id, student_id=student.id).first()
        if st:
            hw_data.append({'hw': hw, 'done': st.done, 'status_id': st.id})
    sessions = AttendanceSession.query.filter_by(student_id=student.id)\
                   .order_by(AttendanceSession.date.desc()).limit(20).all()
    return render_template('student_dashboard.html', student=student, hw_data=hw_data, sessions=sessions)

@app.route('/student/mark_done/<int:status_id>', methods=['POST'])
def mark_done(status_id):
    if not student_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    st = HomeworkStatus.query.get_or_404(status_id)
    if st.student_id != session['student_id']:
        return jsonify({'error': 'Forbidden'}), 403
    st.done = True
    st.done_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})

# ─── QR SCAN ──────────────────────────────────────────────────────────────────

@app.route('/api/scan', methods=['POST'])
def api_scan():
    if not admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    qr_data = data.get('qr_data', '')
    duration = float(data.get('duration', 1.0))
    class_time = data.get('class_time', '')
    if not qr_data.startswith('SCIVERSITY:'):
        return jsonify({'error': 'Invalid QR code'}), 400
    parts = qr_data.split(':')
    student_id = int(parts[1])
    s = Student.query.get(student_id)
    if not s:
        return jsonify({'error': 'Student not found'}), 404
    rec = AttendanceSession(student_id=student_id, duration=duration, class_time=class_time)
    db.session.add(rec)
    s.hours_logged += duration
    db.session.commit()
    return jsonify(student_json(s))

# ─── INIT ─────────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            db.session.add(Admin(username='admin', password='sciversity2024'))
            db.session.commit()
            print("✅ Default admin created: admin / sciversity2024")

if __name__ == '__main__':
    init_db()
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
