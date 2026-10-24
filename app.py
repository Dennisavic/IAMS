"""
IAMS — Intern & Attachment Management System
Nairobi City County Government · City Hall

A single-file Flask application. Everything lives here: models, routes,
role-based access control, and PDF certificate generation.
"""

import os
import uuid
from datetime import datetime, date, time, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, request,
                   flash, send_file, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "certificates"), exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "iams.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CERT_DIR = os.path.join(BASE_DIR, "certificates")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin | supervisor | intern
    intern_id = db.Column(db.Integer, db.ForeignKey("intern.id"))
    supervisor_id = db.Column(db.Integer, db.ForeignKey("supervisor.id"))

    intern = db.relationship("Intern", foreign_keys=[intern_id])
    supervisor = db.relationship("Supervisor", foreign_keys=[supervisor_id])

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    hod_name = db.Column(db.String(120))
    location = db.Column(db.String(120))


class Supervisor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    department = db.relationship("Department")


class Intern(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    admission_number = db.Column(db.String(40), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    university = db.Column(db.String(120))
    course = db.Column(db.String(120))
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    supervisor_id = db.Column(db.Integer, db.ForeignKey("supervisor.id"))
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="active")  # active | completed | terminated

    department = db.relationship("Department")
    supervisor = db.relationship("Supervisor")
    attendance = db.relationship("Attendance", backref="intern", cascade="all, delete-orphan")
    logs = db.relationship("DailyLog", backref="intern", cascade="all, delete-orphan")
    evaluations = db.relationship("Performance", backref="intern", cascade="all, delete-orphan")
    certificate = db.relationship("Certificate", backref="intern", uselist=False, cascade="all, delete-orphan")


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("intern.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)
    status = db.Column(db.String(20), default="present")  # present | late


class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("intern.id"), nullable=False)
    log_date = db.Column(db.Date, default=date.today, nullable=False)
    activities = db.Column(db.Text, nullable=False)
    challenges = db.Column(db.Text)
    reviewed = db.Column(db.Boolean, default=False)
    supervisor_comment = db.Column(db.Text)


class Performance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("intern.id"), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey("supervisor.id"))
    evaluation_date = db.Column(db.Date, default=date.today)
    score = db.Column(db.Integer, nullable=False)  # 0-100
    grade = db.Column(db.String(2))
    comments = db.Column(db.Text)

    supervisor = db.relationship("Supervisor")

    @staticmethod
    def grade_for(score):
        return ("A" if score >= 80 else "B" if score >= 70 else
                "C" if score >= 60 else "D" if score >= 50 else "E")


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("intern.id"), unique=True, nullable=False)
    certificate_number = db.Column(db.String(40), unique=True, nullable=False)
    issue_date = db.Column(db.Date, default=date.today)
    file_path = db.Column(db.String(255))


class Application(db.Model):
    """Public attachment application awaiting admin approval (sign-up)."""
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    admission_number = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    university = db.Column(db.String(120))
    course = db.Column(db.String(120))
    preferred_department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    motivation = db.Column(db.Text)
    username = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    rejection_reason = db.Column(db.String(255))

    preferred_department = db.relationship("Department")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ----------------------------------------------------------------------------
# RBAC decorator
# ----------------------------------------------------------------------------
def role_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return decorated
    return wrapper


ROLE_HOME = {"admin": "admin_dashboard", "supervisor": "supervisor_dashboard", "intern": "intern_dashboard"}
ROLE_LABEL = {"admin": "Admin", "supervisor": "Supervisor", "intern": "Intern"}


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except (ValueError, TypeError):
        return None


# Navbar badge counts available to every template
@app.context_processor
def inject_badges():
    pending_apps = 0
    if current_user.is_authenticated and current_user.role == "admin":
        pending_apps = Application.query.filter_by(status="pending").count()
    return {"pending_applications": pending_apps}


# ----------------------------------------------------------------------------
# Certificate PDF (ReportLab)
# ----------------------------------------------------------------------------
def make_certificate_pdf(intern, cert_number):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas

    green, gold = HexColor("#0b3d2e"), HexColor("#c9a227")
    path = os.path.join(CERT_DIR, f"certificate_{cert_number}.pdf")
    c = canvas.Canvas(path, pagesize=landscape(A4))
    w, h = landscape(A4)

    c.setStrokeColor(green); c.setLineWidth(6); c.rect(1*cm, 1*cm, w-2*cm, h-2*cm)
    c.setStrokeColor(gold); c.setLineWidth(2); c.rect(1.4*cm, 1.4*cm, w-2.8*cm, h-2.8*cm)

    c.setFillColor(green); c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w/2, h-3.2*cm, "NAIROBI CITY COUNTY GOVERNMENT")
    c.setFont("Helvetica", 13); c.drawCentredString(w/2, h-4.0*cm, "City Hall, Nairobi")
    c.setFillColor(gold); c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w/2, h-6.0*cm, "Certificate of Completion")
    c.setFillColor(HexColor("#333333")); c.setFont("Helvetica", 14)
    c.drawCentredString(w/2, h-7.4*cm, "This is to certify that")
    c.setFillColor(green); c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w/2, h-8.8*cm, intern.full_name.upper())

    dept = intern.department.name if intern.department else "Nairobi City County"
    c.setFillColor(HexColor("#333333")); c.setFont("Helvetica", 13)
    uni = f"{intern.university}, " if intern.university else ""
    c.drawCentredString(w/2, h-9.7*cm, f"({uni}Adm. No. {intern.admission_number})")
    start = intern.start_date.strftime("%d %B %Y") if intern.start_date else ""
    end = (intern.end_date or date.today()).strftime("%d %B %Y")
    c.drawCentredString(w/2, h-10.7*cm, f"has successfully completed an industrial attachment in the {dept}")
    c.drawCentredString(w/2, h-11.5*cm, f"from {start} to {end}.")

    c.setFont("Helvetica", 10)
    c.drawString(2.5*cm, 2.8*cm, f"Certificate No: {cert_number}")
    c.drawString(2.5*cm, 2.2*cm, f"Issued: {date.today().strftime('%d %B %Y')}")
    c.line(w-9*cm, 3.0*cm, w-3*cm, 3.0*cm)
    c.drawCentredString(w-6*cm, 2.4*cm, "Authorised Signatory")
    c.drawCentredString(w-6*cm, 1.9*cm, "ICT / Human Resource Department")
    c.showPage(); c.save()
    return path


# ----------------------------------------------------------------------------
# Auth routes
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_HOME[current_user.role]))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_HOME[current_user.role]))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected = request.form.get("role", "")
        user = User.query.filter_by(username=username).first()
        if not user:
            app_row = Application.query.filter_by(username=username).order_by(Application.id.desc()).first()
            if app_row and app_row.status == "pending":
                flash("Your application is still pending review. You can sign in once it's approved.", "info")
            elif app_row and app_row.status == "rejected":
                reason = f" Reason: {app_row.rejection_reason}" if app_row.rejection_reason else ""
                flash(f"Your application was not approved.{reason}", "warning")
            else:
                flash("Invalid username or password.", "danger")
        elif not user.check_password(password):
            flash("Invalid username or password.", "danger")
        elif selected and user.role != selected:
            flash(f"This account is a {ROLE_LABEL[user.role]} account. "
                  f"Select '{ROLE_LABEL[user.role]}' and sign in again.", "warning")
        else:
            login_user(user)
            return redirect(url_for(ROLE_HOME[user.role]))
    return render_template("login.html")


@app.route("/apply", methods=["GET", "POST"])
def apply():
    departments = Department.query.order_by(Department.name).all()
    if request.method == "POST":
        f = request.form
        full_name = f.get("full_name", "").strip()
        admission = f.get("admission_number", "").strip()
        username = f.get("username", "").strip()
        password = f.get("password", "")
        if not all([full_name, admission, username, password]):
            flash("Please fill in all required fields.", "danger")
        elif password != f.get("confirm_password", ""):
            flash("Passwords do not match.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif User.query.filter_by(username=username).first() or \
                Application.query.filter_by(username=username, status="pending").first():
            flash("That username is taken or already pending. Choose another.", "warning")
        else:
            a = Application(
                full_name=full_name, 
                admission_number=admission,
                email=f.get("email", "").strip(), 
                phone=f.get("phone", "").strip(),
                university=f.get("university", "").strip(), 
                course=f.get("course", "").strip(),
                preferred_department_id=f.get("preferred_department_id") or None,
                motivation=f.get("motivation", "").strip(), 
                username=username)
            a.set_password(password)
            db.session.add(a)
            db.session.commit()
            flash("Application submitted. The ICT/HR administrator will review it. "
                  "Once approved, sign in with the username and password you chose.", "success")
            return redirect(url_for("login"))
    return render_template("apply.html", departments=departments)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ----------------------------------------------------------------------------
# Admin routes
# ----------------------------------------------------------------------------
@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    stats = {
        "interns": Intern.query.count(),
        "active": Intern.query.filter_by(status="active").count(),
        "completed": Intern.query.filter_by(status="completed").count(),
        "departments": Department.query.count(),
        "supervisors": Supervisor.query.count(),
        "pending_logs": DailyLog.query.filter_by(reviewed=False).count(),
        "certificates": Certificate.query.count(),
        "applications": Application.query.filter_by(status="pending").count(),
    }
    recent = Intern.query.order_by(Intern.id.desc()).limit(6).all()
    return render_template("admin_dashboard.html", stats=stats, recent=recent)


@app.route("/admin/applications")
@role_required("admin")
def admin_applications():
    show = request.args.get("show", "pending")
    q = Application.query
    if show in ("pending", "approved", "rejected"):
        q = q.filter_by(status=show)
    apps = q.order_by(Application.applied_at.desc()).all()
    return render_template("admin_applications.html", applications=apps, show=show,
                           departments=Department.query.order_by(Department.name).all(),
                           supervisors=Supervisor.query.order_by(Supervisor.full_name).all())


@app.route("/admin/applications/<int:app_id>/approve", methods=["POST"])
@role_required("admin")
def approve_application(app_id):
    a = db.session.get(Application, app_id) or abort(404)
    if a.status != "pending":
        flash("Already reviewed.", "info")
        return redirect(url_for("admin_applications"))
    if User.query.filter_by(username=a.username).first():
        flash("That username was taken since applying. Register the intern manually instead.", "danger")
        return redirect(url_for("admin_applications"))
    intern = Intern(full_name=a.full_name, admission_number=a.admission_number,
                    phone=a.phone, university=a.university, course=a.course,
                    department_id=request.form.get("department_id") or a.preferred_department_id,
                    supervisor_id=request.form.get("supervisor_id") or None,
                    start_date=parse_date(request.form.get("start_date")) or date.today(),
                    end_date=parse_date(request.form.get("end_date")))
    db.session.add(intern)
    db.session.flush()
    u = User(username=a.username, role="intern", intern_id=intern.id, password_hash=a.password_hash)
    db.session.add(u)
    a.status = "approved"
    db.session.commit()
    flash(f"Approved. {intern.full_name} can now sign in as '{a.username}'.", "success")
    return redirect(url_for("admin_applications"))


@app.route("/admin/applications/<int:app_id>/reject", methods=["POST"])
@role_required("admin")
def reject_application(app_id):
    a = db.session.get(Application, app_id) or abort(404)
    if a.status == "pending":
        a.status = "rejected"
        a.rejection_reason = request.form.get("reason", "").strip()
        db.session.commit()
        flash("Application rejected.", "info")
    return redirect(url_for("admin_applications"))


@app.route("/admin/departments", methods=["GET", "POST"])
@role_required("admin")
def admin_departments():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        elif Department.query.filter_by(name=name).first():
            flash("That department already exists.", "warning")
        else:
            db.session.add(Department(name=name, hod_name=request.form.get("hod_name", "").strip(),
                                      location=request.form.get("location", "").strip()))
            db.session.commit()
            flash("Department added.", "success")
        return redirect(url_for("admin_departments"))
    return render_template("admin_departments.html",
                           departments=Department.query.order_by(Department.name).all())


@app.route("/admin/supervisors", methods=["GET", "POST"])
@role_required("admin")
def admin_supervisors():
    if request.method == "POST":
        f = request.form
        full_name, email = f.get("full_name", "").strip(), f.get("email", "").strip().lower()
        username, password = f.get("username", "").strip(), f.get("password", "")
        if not all([full_name, email, username, password]):
            flash("All starred fields are required.", "danger")
        elif Supervisor.query.filter_by(email=email).first():
            flash("A supervisor with that email exists.", "warning")
        elif User.query.filter_by(username=username).first():
            flash("That username is taken.", "warning")
        else:
            s = Supervisor(full_name=full_name, email=email, phone=f.get("phone", "").strip(),
                           department_id=f.get("department_id") or None)
            db.session.add(s)
            db.session.flush()
            u = User(username=username, role="supervisor", supervisor_id=s.id)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f"Supervisor {full_name} registered (login: {username}).", "success")
        return redirect(url_for("admin_supervisors"))
    return render_template("admin_supervisors.html",
                           supervisors=Supervisor.query.order_by(Supervisor.full_name).all(),
                           departments=Department.query.order_by(Department.name).all())


@app.route("/admin/interns", methods=["GET", "POST"])
@role_required("admin")
def admin_interns():
    if request.method == "POST":
        f = request.form
        full_name, admission = f.get("full_name", "").strip(), f.get("admission_number", "").strip()
        username, password = f.get("username", "").strip(), f.get("password", "")
        if not all([full_name, admission, username, password]):
            flash("All starred fields are required.", "danger")
        elif Intern.query.filter_by(admission_number=admission).first():
            flash("That admission number exists.", "warning")
        elif User.query.filter_by(username=username).first():
            flash("That username is taken.", "warning")
        else:
            intern = Intern(full_name=full_name, admission_number=admission,
                            phone=f.get("phone", "").strip(), university=f.get("university", "").strip(),
                            course=f.get("course", "").strip(),
                            department_id=f.get("department_id") or None,
                            supervisor_id=f.get("supervisor_id") or None,
                            start_date=parse_date(f.get("start_date")) or date.today(),
                            end_date=parse_date(f.get("end_date")))
            db.session.add(intern)
            db.session.flush()
            u = User(username=username, role="intern", intern_id=intern.id)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f"Intern {full_name} registered (login: {username}).", "success")
        return redirect(url_for("admin_interns"))
    return render_template("admin_interns.html",
                           interns=Intern.query.order_by(Intern.id.desc()).all(),
                           departments=Department.query.order_by(Department.name).all(),
                           supervisors=Supervisor.query.order_by(Supervisor.full_name).all())


@app.route("/admin/interns/<int:intern_id>")
@role_required("admin")
def admin_intern_detail(intern_id):
    intern = db.session.get(Intern, intern_id) or abort(404)
    return render_template("admin_intern_detail.html", intern=intern)


@app.route("/admin/interns/<int:intern_id>/status", methods=["POST"])
@role_required("admin")
def admin_intern_status(intern_id):
    intern = db.session.get(Intern, intern_id) or abort(404)
    status = request.form.get("status")
    if status in ("active", "completed", "terminated"):
        intern.status = status
        if status == "completed" and not intern.end_date:
            intern.end_date = date.today()
        db.session.commit()
        flash(f"Status updated to {status}.", "success")
    return redirect(url_for("admin_intern_detail", intern_id=intern_id))


@app.route("/admin/interns/<int:intern_id>/certificate", methods=["POST"])
@role_required("admin")
def admin_issue_certificate(intern_id):
    intern = db.session.get(Intern, intern_id) or abort(404)
    if intern.status != "completed":
        flash("Only interns marked 'completed' can be issued a certificate.", "warning")
    elif intern.certificate:
        flash("A certificate already exists for this intern.", "info")
    else:
        num = f"NCC-IAMS-{date.today().year}-{uuid.uuid4().hex[:6].upper()}"
        path = make_certificate_pdf(intern, num)
        db.session.add(Certificate(intern_id=intern.id, certificate_number=num, file_path=path))
        db.session.commit()
        flash(f"Certificate {num} generated.", "success")
    return redirect(url_for("admin_intern_detail", intern_id=intern_id))


@app.route("/admin/certificates")
@role_required("admin")
def admin_certificates():
    certs = Certificate.query.order_by(Certificate.issue_date.desc()).all()
    return render_template("admin_certificates.html", certificates=certs)


@app.route("/certificate/<int:cert_id>/download")
@login_required
def download_certificate(cert_id):
    cert = db.session.get(Certificate, cert_id) or abort(404)
    if current_user.role == "intern" and current_user.intern_id != cert.intern_id:
        abort(403)
    if current_user.role == "supervisor" and cert.intern.supervisor_id != current_user.supervisor_id:
        abort(403)
    return send_file(cert.file_path, as_attachment=True, download_name=f"{cert.certificate_number}.pdf")


@app.route("/admin/reports")
@role_required("admin")
def admin_reports():
    per_dept = (db.session.query(Department.name, db.func.count(Intern.id))
                .outerjoin(Intern, Intern.department_id == Department.id)
                .group_by(Department.id).all())
    avg_scores = (db.session.query(Intern.full_name, db.func.avg(Performance.score))
                  .join(Performance, Performance.intern_id == Intern.id)
                  .group_by(Intern.id).all())
    return render_template("admin_reports.html", per_dept=per_dept, avg_scores=avg_scores,
                           attendance_today=Attendance.query.filter_by(date=date.today()).count())


# ----------------------------------------------------------------------------
# Supervisor routes
# ----------------------------------------------------------------------------
def my_interns():
    return Intern.query.filter_by(supervisor_id=current_user.supervisor_id)


@app.route("/supervisor")
@role_required("supervisor")
def supervisor_dashboard():
    interns = my_interns().all()
    ids = [i.id for i in interns]
    pending = (DailyLog.query.filter(DailyLog.intern_id.in_(ids), DailyLog.reviewed.is_(False))
               .order_by(DailyLog.log_date.desc()).all()) if ids else []
    return render_template("supervisor_dashboard.html", interns=interns, pending=pending)


@app.route("/supervisor/interns/<int:intern_id>")
@role_required("supervisor")
def supervisor_intern_detail(intern_id):
    intern = db.session.get(Intern, intern_id) or abort(404)
    if intern.supervisor_id != current_user.supervisor_id:
        abort(403)
    return render_template("supervisor_intern_detail.html", intern=intern)


@app.route("/supervisor/logs")
@role_required("supervisor")
def supervisor_logs():
    ids = [i.id for i in my_interns().all()]
    show = request.args.get("show", "pending")
    q = DailyLog.query.filter(DailyLog.intern_id.in_(ids)) if ids else DailyLog.query.filter(db.false())
    if show == "pending":
        q = q.filter(DailyLog.reviewed.is_(False))
    return render_template("supervisor_logs.html",
                           logs=q.order_by(DailyLog.log_date.desc()).all(), show=show)


@app.route("/supervisor/logs/<int:log_id>/review", methods=["POST"])
@role_required("supervisor")
def supervisor_review_log(log_id):
    log = db.session.get(DailyLog, log_id) or abort(404)
    if log.intern.supervisor_id != current_user.supervisor_id:
        abort(403)
    log.reviewed = True
    log.supervisor_comment = request.form.get("comment", "").strip()
    db.session.commit()
    flash("Log approved.", "success")
    return redirect(request.referrer or url_for("supervisor_logs"))


@app.route("/supervisor/interns/<int:intern_id>/evaluate", methods=["GET", "POST"])
@role_required("supervisor")
def supervisor_evaluate(intern_id):
    intern = db.session.get(Intern, intern_id) or abort(404)
    if intern.supervisor_id != current_user.supervisor_id:
        abort(403)
    if request.method == "POST":
        try:
            score = int(request.form.get("score", ""))
            assert 0 <= score <= 100
        except (ValueError, AssertionError):
            flash("Score must be a whole number from 0 to 100.", "danger")
            return redirect(url_for("supervisor_evaluate", intern_id=intern_id))
        db.session.add(Performance(intern_id=intern.id, supervisor_id=current_user.supervisor_id,
                                   score=score, grade=Performance.grade_for(score),
                                   comments=request.form.get("comments", "").strip()))
        db.session.commit()
        flash(f"Evaluation saved: {score}/100 (Grade {Performance.grade_for(score)}).", "success")
        return redirect(url_for("supervisor_intern_detail", intern_id=intern_id))
    return render_template("supervisor_evaluate.html", intern=intern)


@app.route("/supervisor/attendance")
@role_required("supervisor")
def supervisor_attendance():
    ids = [i.id for i in my_interns().all()]
    records = (Attendance.query.filter(Attendance.intern_id.in_(ids))
               .order_by(Attendance.date.desc()).limit(200).all()) if ids else []
    return render_template("supervisor_attendance.html", records=records)


# ----------------------------------------------------------------------------
# Intern routes
# ----------------------------------------------------------------------------
def me():
    return db.session.get(Intern, current_user.intern_id)


@app.route("/intern")
@role_required("intern")
def intern_dashboard():
    intern = me()
    today = Attendance.query.filter_by(intern_id=intern.id, date=date.today()).first()
    recent = sorted(intern.logs, key=lambda x: x.log_date, reverse=True)[:5]
    return render_template("intern_dashboard.html", intern=intern, today=today, recent=recent)


@app.route("/intern/attendance")
@role_required("intern")
def intern_attendance():
    intern = me()
    today = Attendance.query.filter_by(intern_id=intern.id, date=date.today()).first()
    records = sorted(intern.attendance, key=lambda x: x.date, reverse=True)
    return render_template("intern_attendance.html", records=records, today=today)


@app.route("/intern/check-in", methods=["POST"])
@role_required("intern")
def intern_check_in():
    intern = me()
    if Attendance.query.filter_by(intern_id=intern.id, date=date.today()).first():
        flash("You already checked in today.", "info")
    else:
        now = datetime.now().time().replace(microsecond=0)
        db.session.add(Attendance(intern_id=intern.id, date=date.today(), check_in=now,
                                  status="late" if now > time(8, 30) else "present"))
        db.session.commit()
        flash(f"Checked in at {now.strftime('%H:%M')}.", "success")
    return redirect(url_for("intern_attendance"))


@app.route("/intern/check-out", methods=["POST"])
@role_required("intern")
def intern_check_out():
    intern = me()
    rec = Attendance.query.filter_by(intern_id=intern.id, date=date.today()).first()
    if not rec:
        flash("You haven't checked in today.", "warning")
    elif rec.check_out:
        flash("You already checked out today.", "info")
    else:
        rec.check_out = datetime.now().time().replace(microsecond=0)
        db.session.commit()
        flash(f"Checked out at {rec.check_out.strftime('%H:%M')}.", "success")
    return redirect(url_for("intern_attendance"))


@app.route("/intern/logs", methods=["GET", "POST"])
@role_required("intern")
def intern_logs():
    intern = me()
    if request.method == "POST":
        activities = request.form.get("activities", "").strip()
        if not activities:
            flash("Please describe your activities.", "danger")
        elif DailyLog.query.filter_by(intern_id=intern.id, log_date=date.today()).first():
            flash("You already submitted a log today.", "warning")
        else:
            db.session.add(DailyLog(intern_id=intern.id, log_date=date.today(), activities=activities,
                                    challenges=request.form.get("challenges", "").strip()))
            db.session.commit()
            flash("Daily log submitted for review.", "success")
        return redirect(url_for("intern_logs"))
    logs = sorted(intern.logs, key=lambda x: x.log_date, reverse=True)
    submitted = DailyLog.query.filter_by(intern_id=intern.id, log_date=date.today()).first() is not None
    return render_template("intern_logs.html", logs=logs, submitted_today=submitted)


@app.route("/intern/performance")
@role_required("intern")
def intern_performance():
    intern = me()
    evals = sorted(intern.evaluations, key=lambda x: x.evaluation_date, reverse=True)
    return render_template("intern_performance.html", evaluations=evals, intern=intern)


# ----------------------------------------------------------------------------
# Error handlers
# ----------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


# ----------------------------------------------------------------------------
# First-run demo data
# ----------------------------------------------------------------------------
def seed_if_empty():
    if User.query.filter_by(username="admin").first():
        return  # already seeded — never wipe existing data

    ict = Department(name="ICT Department", hod_name="Eng. P. Kariuki", location="City Hall Annexe, 3rd Floor")
    health = Department(name="Public Health", hod_name="Dr. A. Wambui", location="City Hall, 5th Floor")
    finance = Department(name="Finance & Economic Planning", hod_name="CPA J. Otieno", location="City Hall, 2nd Floor")
    db.session.add_all([ict, health, finance])
    db.session.flush()

    sup1 = Supervisor(full_name="Grace Achieng", email="grace.achieng@nairobi.go.ke",
                      phone="0722000111", department_id=ict.id)
    sup2 = Supervisor(full_name="Samuel Mwangi", email="samuel.mwangi@nairobi.go.ke",
                      phone="0733000222", department_id=finance.id)
    db.session.add_all([sup1, sup2])
    db.session.flush()

    i1 = Intern(full_name="Kellie Wanjiru", admission_number="KINAP-2026-014", phone="0700111222",
                university="KINAP", course="ICT Level 6", department_id=ict.id, supervisor_id=sup1.id,
                start_date=date.today()-timedelta(days=30), end_date=date.today()+timedelta(days=60), status="active")
    i2 = Intern(full_name="Brian Otieno", admission_number="JKUAT-BBIT-2210", phone="0700333444",
                university="JKUAT", course="BBIT", department_id=ict.id, supervisor_id=sup1.id,
                start_date=date.today()-timedelta(days=90), end_date=date.today()-timedelta(days=1), status="completed")
    i3 = Intern(full_name="Faith Njeri", admission_number="KCA-MSDA-118", phone="0700555666",
                university="KCA University", course="BSc Applied Statistics", department_id=finance.id,
                supervisor_id=sup2.id, start_date=date.today()-timedelta(days=10), status="active")
    db.session.add_all([i1, i2, i3])
    db.session.flush()

    def mkuser(username, pw, role, **fk):
        u = User(username=username, role=role, **fk); u.set_password(pw); db.session.add(u)

    mkuser("admin", "admin123", "admin")
    mkuser("grace", "grace123", "supervisor", supervisor_id=sup1.id)
    mkuser("samuel", "samuel123", "supervisor", supervisor_id=sup2.id)
    mkuser("kellie", "kellie123", "intern", intern_id=i1.id)
    mkuser("brian", "brian123", "intern", intern_id=i2.id)
    mkuser("faith", "faith123", "intern", intern_id=i3.id)

    for d in range(5, 0, -1):
        day = date.today() - timedelta(days=d)
        if day.weekday() >= 5:
            continue
        db.session.add(Attendance(intern_id=i1.id, date=day, check_in=time(8, 10+d),
                                  check_out=time(17, 0), status="present"))
        db.session.add(DailyLog(intern_id=i1.id, log_date=day,
                                activities=f"Assisted with helpdesk tickets and network patching on {day.strftime('%A')}.",
                                challenges="Slow VPN in the afternoon.", reviewed=(d > 2)))

    db.session.add(Performance(intern_id=i2.id, supervisor_id=sup1.id, score=87, grade="A",
                               comments="Excellent Flask work on the CIDP tracker module."))

    a1 = Application(full_name="Dennis Njuguna", admission_number="25-0666",
                     email="dennis.njuguna@student.ac.ke", phone="0711222333",
                     university="Zetech University", course="DICT",
                     preferred_department_id=ict.id, username="dennis",
                     motivation="I proposed the IAMS during my attachment and would like to keep developing it.")
    a1.set_password("dennis123")
    a2 = Application(full_name="Mercy Atieno", admission_number="TUK-CS-1187",
                     email="mercy.atieno@student.ac.ke", phone="0722999888",
                     university="Technical University of Kenya", course="BSc Computer Science",
                     preferred_department_id=finance.id, username="mercy",
                     motivation="Interested in county revenue data systems and public sector analytics.")
    a2.set_password("mercy123")
    db.session.add_all([a1, a2])

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_if_empty()


if __name__ == "__main__":
    print("=" * 52)
    print("  IAMS · Nairobi City County Government")
    print("  Open:  http://127.0.0.1:5000")
    print("  Login: admin / admin123")
    print("=" * 52)
    app.run(debug=True, host="127.0.0.1", port=5000)
