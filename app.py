from flask import Flask, render_template, request, redirect, session, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import qrcode
from io import BytesIO

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cyber-cafe-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///cybercafe.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- MODELS ---

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="New")
    priority = db.Column(db.String(30), default="Normal")
    amount = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(50), default="Cash")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class JobToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token_code = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    pc_number = db.Column(db.String(50), nullable=False) # e.g. PC-01, Printer-1
    service_type = db.Column(db.String(100), nullable=False)
    duration_mins = db.Column(db.Integer, default=0) # 0 for no limit / print jobs
    cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default="Active") # Active, Completed, Cancelled
    created_at = db.Column(db.DateTime, default=datetime.now)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False) # Cash, UPI, Card
    payment_date = db.Column(db.DateTime, default=datetime.now)
    notes = db.Column(db.Text)

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(20))
    items = db.Column(db.Text, nullable=False) # Semi-colon separated / JSON format
    subtotal = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Paid") # Paid, Unpaid
    created_at = db.Column(db.DateTime, default=datetime.now)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    notes = db.Column(db.Text)

class WhatsAppMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    direction = db.Column(db.String(20), default="inbound") # inbound, outbound
    timestamp = db.Column(db.DateTime, default=datetime.now)

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    salary = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default="Active") # Active, Inactive
    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    permissions = db.Column(db.Text, default="")

# --- DECORATORS & UTILITIES ---

from functools import wraps

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id") and not session.get("staff_id"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def permission_required(permission_name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get("admin_id") and not session.get("staff_id"):
                return redirect(url_for("login"))
            if session.get("admin_id"):
                return func(*args, **kwargs)
            staff_permissions = session.get("staff_permissions", [])
            if permission_name in staff_permissions:
                return func(*args, **kwargs)
            flash("Access denied: You do not have permission for this module.", "danger")
            return redirect(url_for("dashboard"))
        return wrapper
    return decorator

def get_setting(key, default=""):
    try:
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            return setting.value
    except Exception:
        pass
    return default

@app.context_processor
def inject_cafe():
    return {
        "cafe_name": get_setting("cafe_name", os.getenv("CAFE_NAME", "Anaya's Digital Services")),
        "cafe_address": get_setting("cafe_address", os.getenv("CAFE_ADDRESS", "Your Location")),
        "cafe_whatsapp": get_setting("cafe_whatsapp", os.getenv("CAFE_WHATSAPP_NUMBER", "919876543210")),
        "cafe_upi": get_setting("cafe_upi", "pskaplish@okaxis")
    }

# --- ROUTES ---

@app.route("/")
def home():
    return redirect(url_for("dashboard") if (session.get("admin_id") or session.get("staff_id")) else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_type = request.form.get("login_type", "staff")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if login_type == "admin":
            # Check Admin table
            admin = Admin.query.filter_by(username=username).first()
            if admin and check_password_hash(admin.password_hash, password):
                session.clear()
                session["admin_id"] = admin.id
                session["admin_username"] = admin.username
                flash("Welcome back, Admin!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid admin username or password", "danger")
            
        else:
            # Check Staff table
            role = request.form.get("role", "").strip()
            if not role:
                flash("Please select your assigned staff role.", "danger")
                return redirect(url_for("login"))
                
            staff = Staff.query.filter_by(username=username, role=role, status="Active").first()
            if staff and staff.password_hash and check_password_hash(staff.password_hash, password):
                session.clear()
                session["staff_id"] = staff.id
                session["staff_name"] = staff.name
                session["staff_username"] = staff.username
                session["staff_permissions"] = staff.permissions.split(",") if staff.permissions else []
                flash(f"Welcome back, {staff.name} ({staff.role})!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid staff credentials or role selection", "danger")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))

import random

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_otp(recipient_email, otp):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_SENDER", smtp_user)
    
    if smtp_server and smtp_port and smtp_user and smtp_password:
        try:
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient_email
            msg['Subject'] = "CyberCafePro Password Recovery OTP"
            
            body = f"Hello,\n\nYour CyberCafePro password recovery OTP is: {otp}\n\nThis OTP is valid for 10 minutes.\n\nRegards,\nCyberCafePro Team"
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
            server.quit()
            print(f"Email sent successfully to {recipient_email}")
            return True
        except Exception as e:
            print(f"Email sending failed: {e}")
            return False
    else:
        print(f"\n======================================")
        print(f"SMTP credentials not set in .env!")
        print(f"SIMULATED EMAIL to {recipient_email}: OTP is {otp}")
        print(f"======================================\n")
        return False

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        
        staff = Staff.query.filter_by(username=username, email=email, status="Active").first()
        if staff:
            # Generate 6-digit OTP
            otp = str(random.randint(100000, 999999))
            session["reset_otp"] = otp
            session["reset_username"] = username
            
            # Send Email
            send_email_otp(email, otp)
            
            # Standard production message: do not show OTP on browser UI
            flash("An OTP has been sent to your registered email address.", "success")
            return redirect(url_for("verify_otp"))
        else:
            flash("No active staff member found with this username and email address.", "danger")
    return render_template("forgot_password.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if not session.get("reset_username") or not session.get("reset_otp"):
        flash("Invalid recovery session. Please start again.", "danger")
        return redirect(url_for("forgot_password"))
        
    if request.method == "POST":
        otp_input = request.form.get("otp", "").strip()
        if otp_input == session.get("reset_otp"):
            session["otp_verified"] = True
            flash("OTP verified successfully! Please choose a new password.", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Invalid OTP. Please try again.", "danger")
    return render_template("verify_otp.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_username") or not session.get("otp_verified"):
        flash("Invalid recovery session. Please start again.", "danger")
        return redirect(url_for("forgot_password"))
        
    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_password"))
            
        username = session.get("reset_username")
        staff = Staff.query.filter_by(username=username, status="Active").first()
        if staff:
            staff.password_hash = generate_password_hash(new_password)
            db.session.commit()
            
            # Clear recovery session
            session.pop("reset_otp", None)
            session.pop("reset_username", None)
            session.pop("otp_verified", None)
            
            flash("Your password has been reset successfully. Please login.", "success")
            return redirect(url_for("login"))
        else:
            flash("Staff member not found.", "danger")
            return redirect(url_for("forgot_password"))
            
    return render_template("reset_password.html")

@app.route("/dashboard")
@login_required
def dashboard():
    total_queries = Query.query.count()
    new_queries = Query.query.filter_by(status="New").count()
    active_tokens = JobToken.query.filter_by(status="Active").count()
    total_customers = Customer.query.count()
    
    # Revenue calculations
    total_payments = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).scalar()
    total_expenses = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0.0)).scalar()
    net_profit = total_payments - total_expenses
    
    recent_tokens = JobToken.query.order_by(JobToken.created_at.desc()).limit(5).all()
    recent_queries = Query.query.order_by(Query.created_at.desc()).limit(5).all()
    
    return render_template(
        "dashboard.html",
        total_queries=total_queries,
        new_queries=new_queries,
        active_tokens=active_tokens,
        total_customers=total_customers,
        total_payments=total_payments,
        total_expenses=total_expenses,
        net_profit=net_profit,
        recent_tokens=recent_tokens,
        recent_queries=recent_queries
    )

# --- CUSTOMERS SECTION ---

@app.route("/customers")
@permission_required("customers")
def customers():
    search = request.args.get("search", "").strip()
    if search:
        like = f"%{search}%"
        custs = Customer.query.filter(Customer.name.ilike(like) | Customer.phone.ilike(like) | Customer.email.ilike(like)).all()
    else:
        custs = Customer.query.order_by(Customer.created_at.desc()).all()
    return render_template("customers.html", customers=custs, search=search)

@app.route("/add-customer", methods=["GET", "POST"])
@permission_required("customers")
def add_customer():
    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()
        
        customer = Customer(name=name, phone=phone, email=email, notes=notes)
        db.session.add(customer)
        db.session.commit()
        flash("Customer added successfully", "success")
        return redirect(url_for("customers"))
    return render_template("add_customer.html")

@app.route("/edit-customer/<int:id>", methods=["GET", "POST"])
@permission_required("customers")
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    if request.method == "POST":
        customer.name = request.form["name"].strip()
        customer.phone = request.form["phone"].strip()
        customer.email = request.form.get("email", "").strip()
        customer.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash("Customer updated successfully", "success")
        return redirect(url_for("customers"))
    return render_template("edit_customer.html", customer=customer)

@app.route("/delete-customer/<int:id>")
@permission_required("customers")
def delete_customer(id):
    customer = Customer.query.get_or_404(id)
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted successfully", "success")
    return redirect(url_for("customers"))

# --- INQUIRIES SECTION ---

def log_query_payment_if_needed(query_item, payment_method="Cash"):
    if query_item.status == "Completed" and query_item.amount > 0:
        # Check if a payment for this inquiry has already been logged
        existing_pmt = Payment.query.filter(Payment.notes.like(f"%Inquiry #{query_item.id}%")).first()
        if not existing_pmt:
            pmt = Payment(
                customer_name=query_item.customer_name,
                amount=query_item.amount,
                payment_method=payment_method or "Cash",
                notes=f"Payment for Completed Inquiry #{query_item.id} - {query_item.service_type}"
            )
            db.session.add(pmt)
            flash(f"Automatic payment of ₹{query_item.amount:.2f} logged successfully via {payment_method or 'Cash'}.", "success")

@app.route("/queries")
@permission_required("queries")
def queries():
    status_filter = request.args.get("status", "All")
    search = request.args.get("search", "").strip()
    date_filter = request.args.get("date_filter", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    
    query_obj = Query.query
    if status_filter != "All":
        query_obj = query_obj.filter_by(status=status_filter)
    if search:
        like = f"%{search}%"
        query_obj = query_obj.filter((Query.customer_name.ilike(like)) | (Query.phone.ilike(like)) | (Query.service_type.ilike(like)))
        
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d")
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = datetime.combine(target_date, datetime.max.time())
            query_obj = query_obj.filter(Query.created_at >= start_dt, Query.created_at <= end_dt)
        except ValueError:
            pass
    else:
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query_obj = query_obj.filter(Query.created_at >= start_dt)
            except ValueError:
                pass
        if end_date:
            try:
                end_dt = datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                query_obj = query_obj.filter(Query.created_at <= end_dt)
            except ValueError:
                pass
            
    queries_list = query_obj.order_by(Query.created_at.desc()).all()
    return render_template(
        "queries.html", 
        queries=queries_list, 
        status_filter=status_filter, 
        search=search,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date
    )

import csv
from io import StringIO
from flask import Response

@app.route("/queries/export/csv")
@permission_required("queries")
def export_queries_csv():
    status_filter = request.args.get("status", "All")
    search = request.args.get("search", "").strip()
    date_filter = request.args.get("date_filter", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    
    query_obj = Query.query
    if status_filter != "All":
        query_obj = query_obj.filter_by(status=status_filter)
    if search:
        like = f"%{search}%"
        query_obj = query_obj.filter((Query.customer_name.ilike(like)) | (Query.phone.ilike(like)) | (Query.service_type.ilike(like)))
        
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d")
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = datetime.combine(target_date, datetime.max.time())
            query_obj = query_obj.filter(Query.created_at >= start_dt, Query.created_at <= end_dt)
        except ValueError:
            pass
    else:
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query_obj = query_obj.filter(Query.created_at >= start_dt)
            except ValueError:
                pass
        if end_date:
            try:
                end_dt = datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                query_obj = query_obj.filter(Query.created_at <= end_dt)
            except ValueError:
                pass
                
    queries_list = query_obj.order_by(Query.created_at.desc()).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["Inquiry ID", "Customer Name", "Phone", "Service Type", "Description", "Amount (INR)", "Payment Method", "Status", "Priority", "Registered At", "Notes"])
    
    for q in queries_list:
        cw.writerow([
            q.id,
            q.customer_name,
            q.phone,
            q.service_type,
            q.message,
            f"{q.amount:.2f}",
            q.payment_method or "Cash",
            q.status,
            q.priority,
            q.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            q.notes or ""
        ])
        
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=queries_export.csv"}
    )

@app.route("/queries/export/print")
@permission_required("queries")
def export_queries_print():
    status_filter = request.args.get("status", "All")
    search = request.args.get("search", "").strip()
    date_filter = request.args.get("date_filter", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    
    query_obj = Query.query
    if status_filter != "All":
        query_obj = query_obj.filter_by(status=status_filter)
    if search:
        like = f"%{search}%"
        query_obj = query_obj.filter((Query.customer_name.ilike(like)) | (Query.phone.ilike(like)) | (Query.service_type.ilike(like)))
        
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d")
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = datetime.combine(target_date, datetime.max.time())
            query_obj = query_obj.filter(Query.created_at >= start_dt, Query.created_at <= end_dt)
        except ValueError:
            pass
    else:
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query_obj = query_obj.filter(Query.created_at >= start_dt)
            except ValueError:
                pass
        if end_date:
            try:
                end_dt = datetime.strptime(end_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                query_obj = query_obj.filter(Query.created_at <= end_dt)
            except ValueError:
                pass
                
    queries_list = query_obj.order_by(Query.created_at.desc()).all()
    return render_template("print_queries.html", queries=queries_list)

@app.route("/add-query", methods=["GET", "POST"])
@permission_required("queries")
def add_query():
    if request.method == "POST":
        item = Query(
            customer_name=request.form["customer_name"].strip(),
            phone=request.form["phone"].strip(),
            service_type=request.form["service_type"],
            message=request.form["message"].strip(),
            priority=request.form.get("priority", "Normal"),
            amount=float(request.form.get("amount") or 0),
            payment_method=request.form.get("payment_method", "Cash"),
            notes=request.form.get("notes", "").strip(),
            status="New"
        )
        db.session.add(item)
        db.session.commit()
        flash("Query saved successfully", "success")
        return redirect(url_for("queries"))
    return render_template("add_query.html", services=Service.query.all())

@app.route("/edit-query/<int:query_id>", methods=["GET", "POST"])
@permission_required("queries")
def edit_query(query_id):
    item = Query.query.get_or_404(query_id)
    if request.method == "POST":
        item.customer_name = request.form["customer_name"].strip()
        item.phone = request.form["phone"].strip()
        item.service_type = request.form["service_type"]
        item.message = request.form["message"].strip()
        item.status = request.form["status"]
        item.priority = request.form.get("priority", "Normal")
        item.amount = float(request.form.get("amount") or 0)
        item.payment_method = request.form.get("payment_method", "Cash")
        item.notes = request.form.get("notes", "").strip()
        
        # Log payment if it transitions to Completed
        log_query_payment_if_needed(item, item.payment_method)
        
        db.session.commit()
        flash("Query updated successfully", "success")
        return redirect(url_for("queries"))
    return render_template("edit_query.html", item=item)

@app.route("/update-status/<int:query_id>/<status>")
@permission_required("queries")
def update_status(query_id, status):
    if status not in ["New", "Pending", "Completed", "Cancelled"]:
        flash("Invalid status", "danger")
        return redirect(url_for("queries"))
    item = Query.query.get_or_404(query_id)
    item.status = status
    
    # Log payment if it transitions to Completed
    log_query_payment_if_needed(item, item.payment_method)
    
    db.session.commit()
    flash("Status updated", "success")
    return redirect(url_for("queries"))

@app.route("/delete-query/<int:query_id>")
@permission_required("queries")
def delete_query(query_id):
    item = Query.query.get_or_404(query_id)
    db.session.delete(item)
    db.session.commit()
    flash("Query deleted", "success")
    return redirect(url_for("queries"))

# --- JOBS & TOKENS SECTION ---

@app.route("/jobs")
@permission_required("jobs")
def jobs():
    job_tokens = JobToken.query.order_by(JobToken.created_at.desc()).all()
    return render_template("jobs.html", job_tokens=job_tokens)

@app.route("/add-job", methods=["GET", "POST"])
@permission_required("jobs")
def add_job():
    if request.method == "POST":
        token_code = request.form["token_code"].strip()
        customer_name = request.form["customer_name"].strip()
        pc_number = request.form["pc_number"].strip()
        service_type = request.form["service_type"].strip()
        duration_mins = int(request.form.get("duration_mins") or 0)
        cost = float(request.form.get("cost") or 0.0)
        
        job = JobToken(
            token_code=token_code,
            customer_name=customer_name,
            pc_number=pc_number,
            service_type=service_type,
            duration_mins=duration_mins,
            cost=cost,
            status="Active"
        )
        db.session.add(job)
        db.session.commit()
        
        flash("Job & Token generated successfully", "success")
        return redirect(url_for("jobs"))
    
    import random
    auto_token = f"CCP-{random.randint(1000, 9999)}"
    return render_template("add_job.html", auto_token=auto_token, services=Service.query.all())

@app.route("/edit-job/<int:id>", methods=["GET", "POST"])
@permission_required("jobs")
def edit_job(id):
    job = JobToken.query.get_or_404(id)
    if request.method == "POST":
        job.customer_name = request.form["customer_name"].strip()
        job.pc_number = request.form["pc_number"].strip()
        job.service_type = request.form["service_type"].strip()
        job.duration_mins = int(request.form.get("duration_mins") or 0)
        job.cost = float(request.form.get("cost") or 0.0)
        job.status = request.form["status"]
        db.session.commit()
        flash("Job updated successfully", "success")
        return redirect(url_for("jobs"))
    return render_template("edit_job.html", job=job)

@app.route("/delete-job/<int:id>")
@permission_required("jobs")
def delete_job(id):
    job = JobToken.query.get_or_404(id)
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted", "success")
    return redirect(url_for("jobs"))

# --- SERVICES & PRICES SECTION ---

@app.route("/services")
@permission_required("services")
def services():
    srvs = Service.query.all()
    return render_template("services.html", services=srvs)

@app.route("/add-service", methods=["GET", "POST"])
@permission_required("services")
def add_service():
    if request.method == "POST":
        name = request.form["name"].strip()
        price = float(request.form["price"] or 0.0)
        description = request.form.get("description", "").strip()
        
        srv = Service(name=name, price=price, description=description)
        db.session.add(srv)
        db.session.commit()
        flash("Service added successfully", "success")
        return redirect(url_for("services"))
    return render_template("add_service.html")

@app.route("/edit-service/<int:id>", methods=["GET", "POST"])
@permission_required("services")
def edit_service(id):
    srv = Service.query.get_or_404(id)
    if request.method == "POST":
        srv.name = request.form["name"].strip()
        srv.price = float(request.form["price"] or 0.0)
        srv.description = request.form.get("description", "").strip()
        db.session.commit()
        flash("Service updated successfully", "success")
        return redirect(url_for("services"))
    return render_template("edit_service.html", service=srv)

@app.route("/delete-service/<int:id>")
@permission_required("services")
def delete_service(id):
    srv = Service.query.get_or_404(id)
    db.session.delete(srv)
    db.session.commit()
    flash("Service deleted successfully", "success")
    return redirect(url_for("services"))

# --- PAYMENTS SECTION ---

@app.route("/payments")
@permission_required("payments")
def payments():
    pmts = Payment.query.order_by(Payment.payment_date.desc()).all()
    return render_template("payments.html", payments=pmts)

@app.route("/add-payment", methods=["GET", "POST"])
@permission_required("payments")
def add_payment():
    if request.method == "POST":
        customer_name = request.form["customer_name"].strip()
        amount = float(request.form["amount"] or 0.0)
        payment_method = request.form["payment_method"]
        notes = request.form.get("notes", "").strip()
        
        pmt = Payment(customer_name=customer_name, amount=amount, payment_method=payment_method, notes=notes)
        db.session.add(pmt)
        db.session.commit()
        flash("Payment logged successfully", "success")
        return redirect(url_for("payments"))
    return render_template("add_payment.html")

@app.route("/delete-payment/<int:id>")
@permission_required("payments")
def delete_payment(id):
    pmt = Payment.query.get_or_404(id)
    db.session.delete(pmt)
    db.session.commit()
    flash("Payment log deleted", "success")
    return redirect(url_for("payments"))

# --- INQUIRIES SECTION ---
# --- INVOICES SECTION ---

@app.route("/invoices")
@permission_required("invoices")
def invoices():
    invs = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template("invoices.html", invoices=invs)

@app.route("/add-invoice", methods=["GET", "POST"])
@permission_required("invoices")
def add_invoice():
    if request.method == "POST":
        customer_name = request.form["customer_name"].strip()
        customer_phone = request.form.get("customer_phone", "").strip()
        
        item_names = request.form.getlist("item_name[]")
        item_rates = request.form.getlist("item_rate[]")
        item_qty = request.form.getlist("item_qty[]")
        
        parsed_items = []
        subtotal = 0.0
        for name, rate, qty in zip(item_names, item_rates, item_qty):
            if name.strip():
                r = float(rate or 0.0)
                q = int(qty or 1)
                total = r * q
                subtotal += total
                parsed_items.append(f"{name.strip()} ({q}x ₹{r}) - ₹{total}")
                
        tax = float(request.form.get("tax") or 0.0)
        discount = float(request.form.get("discount") or 0.0)
        total_amount = subtotal + tax - discount
        
        import random
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
        
        inv = Invoice(
            invoice_number=invoice_number,
            customer_name=customer_name,
            customer_phone=customer_phone,
            items="; ".join(parsed_items),
            subtotal=subtotal,
            tax=tax,
            discount=discount,
            total_amount=total_amount,
            status=request.form["status"]
        )
        db.session.add(inv)
        
        if request.form["status"] == "Paid":
            pmt = Payment(customer_name=customer_name, amount=total_amount, payment_method="Cash", notes=f"Automatic from Invoice {invoice_number}")
            db.session.add(pmt)
            
        db.session.commit()
        flash("Invoice created successfully", "success")
        return redirect(url_for("invoices"))
    return render_template("add_invoice.html", services=Service.query.all())

@app.route("/view-invoice/<int:id>")
@permission_required("invoices")
def view_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    invoice_items = []
    if invoice.items:
        import re
        for line in invoice.items.split(";"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(.*) \((\d+)x ₹([\d.]+)\) - ₹([\d.]+)$", line)
            if m:
                invoice_items.append({
                    "name": m.group(1),
                    "qty": int(m.group(2)),
                    "rate": float(m.group(3)),
                    "total": float(m.group(4))
                })
            else:
                invoice_items.append({
                    "name": line,
                    "qty": 1,
                    "rate": invoice.total_amount,
                    "total": invoice.total_amount
                })
    return render_template("invoice_detail.html", invoice=invoice, items=invoice_items)

@app.route("/edit-invoice/<int:id>", methods=["GET", "POST"])
@permission_required("invoices")
def edit_invoice(id):
    import re
    inv = Invoice.query.get_or_404(id)
    if request.method == "POST":
        inv.customer_name = request.form["customer_name"].strip()
        inv.customer_phone = request.form.get("customer_phone", "").strip()
        
        item_names = request.form.getlist("item_name[]")
        item_rates = request.form.getlist("item_rate[]")
        item_qty = request.form.getlist("item_qty[]")
        
        parsed_items = []
        subtotal = 0.0
        for name, rate, qty in zip(item_names, item_rates, item_qty):
            if name.strip():
                r = float(rate or 0.0)
                q = int(qty or 1)
                total = r * q
                subtotal += total
                parsed_items.append(f"{name.strip()} ({q}x ₹{r}) - ₹{total}")
                
        inv.items = "; ".join(parsed_items)
        inv.tax = float(request.form.get("tax") or 0.0)
        inv.discount = float(request.form.get("discount") or 0.0)
        inv.total_amount = subtotal + inv.tax - inv.discount
        
        old_status = inv.status
        inv.status = request.form["status"]
        
        if inv.status == "Paid" and old_status != "Paid":
            existing_pmt = Payment.query.filter(Payment.notes.like(f"%Invoice {inv.invoice_number}%")).first()
            if not existing_pmt:
                pmt = Payment(customer_name=inv.customer_name, amount=inv.total_amount, payment_method="Cash", notes=f"Automatic from Invoice {inv.invoice_number}")
                db.session.add(pmt)
                
        db.session.commit()
        flash("Invoice updated successfully", "success")
        return redirect(url_for("invoices"))
        
    # Reconstruct item lines for display in the template
    lines = []
    if inv.items:
        for line in inv.items.split(";"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(.*) \((\d+)x ₹([\d.]+)\) - ₹([\d.]+)$", line)
            if m:
                lines.append({
                    "name": m.group(1),
                    "qty": int(m.group(2)),
                    "rate": float(m.group(3))
                })
            else:
                lines.append({
                    "name": line,
                    "qty": 1,
                    "rate": 0.0
                })
                
    if not lines:
        lines = [{"name": "", "qty": 1, "rate": 0.0}]
        
    return render_template("edit_invoice.html", invoice=inv, lines=lines, services=Service.query.all())

@app.route("/delete-invoice/<int:id>")
@permission_required("invoices")
def delete_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    flash("Invoice deleted", "success")
    return redirect(url_for("invoices"))

# --- EXPENSES SECTION ---

@app.route("/expenses")
@permission_required("expenses")
def expenses():
    exps = Expense.query.order_by(Expense.date.desc()).all()
    return render_template("expenses.html", expenses=exps)

@app.route("/add-expense", methods=["GET", "POST"])
@permission_required("expenses")
def add_expense():
    if request.method == "POST":
        title = request.form["title"].strip()
        category = request.form["category"]
        amount = float(request.form["amount"] or 0.0)
        notes = request.form.get("notes", "").strip()
        
        exp = Expense(title=title, category=category, amount=amount, notes=notes)
        db.session.add(exp)
        db.session.commit()
        flash("Expense added successfully", "success")
        return redirect(url_for("expenses"))
    return render_template("add_expense.html")

@app.route("/delete-expense/<int:id>")
@permission_required("expenses")
def delete_expense(id):
    exp = Expense.query.get_or_404(id)
    db.session.delete(exp)
    db.session.commit()
    flash("Expense deleted successfully", "success")
    return redirect(url_for("expenses"))

# --- WHATSAPP INBOX SECTION ---

@app.route("/whatsapp-inbox")
@permission_required("whatsapp")
def whatsapp_inbox():
    messages = WhatsAppMessage.query.order_by(WhatsAppMessage.timestamp.desc()).all()
    return render_template("whatsapp_inbox.html", messages=messages)

@app.route("/send-whatsapp", methods=["POST"])
@permission_required("whatsapp")
def send_whatsapp():
    recipient = request.form["recipient"].strip()
    msg = request.form["message"].strip()
    
    out_msg = WhatsAppMessage(sender=recipient, message=msg, direction="outbound")
    db.session.add(out_msg)
    db.session.commit()
    
    flash("WhatsApp message recorded. Opening Chat window...", "success")
    wa_url = f"https://wa.me/{recipient}?text={msg.replace(' ', '%20')}"
    return render_template("redirect.html", target_url=wa_url)

# --- QR CODES SECTION ---

@app.route("/qr-codes")
@permission_required("qr_codes")
def qr_codes():
    number = get_setting("cafe_whatsapp", os.getenv("CAFE_WHATSAPP_NUMBER", "919876543210"))
    text = "Hello, I need help from your Cyber Cafe."
    whatsapp_link = f"https://wa.me/{number}?text={text.replace(' ', '%20')}"
    img = qrcode.make(whatsapp_link)
    os.makedirs("static/img", exist_ok=True)
    img.save("static/img/whatsapp_qr.png")
    
    upi_id = get_setting("cafe_upi", "pskaplish@okaxis")
    return render_template("qr_codes.html", whatsapp_link=whatsapp_link, number=number, upi_id=upi_id)

@app.route("/generate-upi-qr")
@permission_required("qr_codes")
def generate_upi_qr():
    upi_id = get_setting("cafe_upi", "pskaplish@okaxis")
    amount = request.args.get("amount", "0")
    cafe_name = get_setting("cafe_name", "Cyber Cafe Pro")
    upi_link = f"upi://pay?pa={upi_id}&pn={cafe_name.replace(' ', '%20')}&am={amount}&cu=INR"
    img = qrcode.make(upi_link)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# --- REPORTS & ANALYTICS SECTION ---

@app.route("/reports")
@permission_required("reports")
def reports():
    from datetime import timedelta
    import json as _json

    total_sales = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).scalar()
    total_exps = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0.0)).scalar()
    net_profit = total_sales - total_exps
    
    customers_count = Customer.query.count()
    completed_jobs = JobToken.query.filter_by(status="Completed").count()
    active_jobs = JobToken.query.filter_by(status="Active").count()
    
    cash_payments = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).filter_by(payment_method="Cash").scalar()
    upi_payments = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).filter_by(payment_method="UPI").scalar()
    card_payments = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).filter_by(payment_method="Card").scalar()
    
    # ---- Last 7 days daily revenue chart data ----
    today = datetime.now().date()
    daily_labels = []
    daily_revenue = []
    daily_expenses = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        rev = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).filter(
            Payment.payment_date >= day_start, Payment.payment_date <= day_end).scalar()
        exp = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0.0)).filter(
            Expense.date >= day_start, Expense.date <= day_end).scalar()
        daily_labels.append(day.strftime('%d %b'))
        daily_revenue.append(round(float(rev), 2))
        daily_expenses.append(round(float(exp), 2))

    # ---- Last 6 months monthly revenue chart data ----
    monthly_labels = []
    monthly_revenue = []
    monthly_expenses = []
    import calendar as _cal
    for i in range(5, -1, -1):
        # Use total months from epoch to avoid boundary issues
        total_months = today.year * 12 + (today.month - 1) - i
        target_year = total_months // 12
        target_month = (total_months % 12) + 1
        m_start = datetime(target_year, target_month, 1)
        last_day = _cal.monthrange(target_year, target_month)[1]
        m_end = datetime(target_year, target_month, last_day, 23, 59, 59)
        rev_m = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0.0)).filter(
            Payment.payment_date >= m_start, Payment.payment_date <= m_end).scalar()
        exp_m = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0.0)).filter(
            Expense.date >= m_start, Expense.date <= m_end).scalar()
        monthly_labels.append(m_start.strftime('%b %Y'))
        monthly_revenue.append(round(float(rev_m), 2))
        monthly_expenses.append(round(float(exp_m), 2))

    return render_template(
        "reports.html",
        total_sales=total_sales,
        total_expenses=total_exps,
        net_profit=net_profit,
        customers_count=customers_count,
        completed_jobs=completed_jobs,
        active_jobs=active_jobs,
        cash_payments=cash_payments,
        upi_payments=upi_payments,
        card_payments=card_payments,
        daily_labels=_json.dumps(daily_labels),
        daily_revenue=_json.dumps(daily_revenue),
        daily_expenses=_json.dumps(daily_expenses),
        monthly_labels=_json.dumps(monthly_labels),
        monthly_revenue=_json.dumps(monthly_revenue),
        monthly_expenses=_json.dumps(monthly_expenses),
    )

# --- STAFF SECTION ---

@app.route("/staff")
@permission_required("staff")
def staff():
    stf = Staff.query.all()
    return render_template("staff.html", staff=stf)

@app.route("/add-staff", methods=["GET", "POST"])
@permission_required("staff")
def add_staff():
    if request.method == "POST":
        name = request.form["name"].strip()
        role = request.form["role"].strip()
        phone = request.form["phone"].strip()
        email = request.form.get("email", "").strip() or None
        salary = float(request.form.get("salary") or 0.0)
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected_permissions = request.form.getlist("permissions[]")
        
        if username:
            if username.lower() == os.getenv("ADMIN_USERNAME", "admin").lower():
                flash("Username is reserved for Admin.", "danger")
                return redirect(url_for("add_staff"))
            existing = Staff.query.filter_by(username=username).first()
            if existing:
                flash("Username is already taken by another staff member.", "danger")
                return redirect(url_for("add_staff"))
                
        if email:
            existing_email = Staff.query.filter_by(email=email).first()
            if existing_email:
                flash("Email address is already registered to another staff member.", "danger")
                return redirect(url_for("add_staff"))
        
        password_hash = generate_password_hash(password) if password else None
        permissions_str = ",".join(selected_permissions)
        
        stf = Staff(
            name=name,
            role=role,
            phone=phone,
            email=email,
            salary=salary,
            status="Active",
            username=username if username else None,
            password_hash=password_hash,
            permissions=permissions_str
        )
        db.session.add(stf)
        db.session.commit()
        flash("Staff member added successfully", "success")
        return redirect(url_for("staff"))
    return render_template("add_staff.html")

@app.route("/edit-staff/<int:id>", methods=["GET", "POST"])
@permission_required("staff")
def edit_staff(id):
    stf = Staff.query.get_or_404(id)
    if request.method == "POST":
        stf.name = request.form["name"].strip()
        stf.role = request.form["role"].strip()
        stf.phone = request.form["phone"].strip()
        email = request.form.get("email", "").strip() or None
        stf.salary = float(request.form.get("salary") or 0.0)
        stf.status = request.form["status"]
        
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected_permissions = request.form.getlist("permissions[]")
        
        if username:
            if username.lower() == os.getenv("ADMIN_USERNAME", "admin").lower():
                flash("Username is reserved for Admin.", "danger")
                return redirect(url_for("edit_staff", id=id))
            existing = Staff.query.filter(Staff.username == username, Staff.id != id).first()
            if existing:
                flash("Username is already taken by another staff member.", "danger")
                return redirect(url_for("edit_staff", id=id))
            stf.username = username
        else:
            stf.username = None
            
        if email:
            existing_email = Staff.query.filter(Staff.email == email, Staff.id != id).first()
            if existing_email:
                flash("Email address is already registered to another staff member.", "danger")
                return redirect(url_for("edit_staff", id=id))
            stf.email = email
        else:
            stf.email = None
            
        if password:
            stf.password_hash = generate_password_hash(password)
            
        stf.permissions = ",".join(selected_permissions)
        db.session.commit()
        flash("Staff member updated successfully", "success")
        return redirect(url_for("staff"))
        
    perms = stf.permissions.split(",") if stf.permissions else []
    return render_template("edit_staff.html", staff=stf, perms=perms)

@app.route("/delete-staff/<int:id>")
@permission_required("staff")
def delete_staff(id):
    stf = Staff.query.get_or_404(id)
    db.session.delete(stf)
    db.session.commit()
    flash("Staff record deleted", "success")
    return redirect(url_for("staff"))

# --- SETTINGS SECTION ---

@app.route("/settings", methods=["GET", "POST"])
@permission_required("settings")
def settings():
    if request.method == "POST":
        for key in ["cafe_name", "cafe_address", "cafe_whatsapp", "cafe_upi"]:
            val = request.form.get(key, "").strip()
            setting_obj = Setting.query.filter_by(key=key).first()
            if setting_obj:
                setting_obj.value = val
            else:
                db.session.add(Setting(key=key, value=val))
        db.session.commit()
        flash("Settings saved successfully", "success")
        return redirect(url_for("settings"))
        
    return render_template(
        "settings.html",
        cafe_name=get_setting("cafe_name", os.getenv("CAFE_NAME", "Cyber Cafe Pro")),
        cafe_address=get_setting("cafe_address", os.getenv("CAFE_ADDRESS", "Your Location")),
        cafe_whatsapp=get_setting("cafe_whatsapp", os.getenv("CAFE_WHATSAPP_NUMBER", "919876543210")),
        cafe_upi=get_setting("cafe_upi", "pskaplish@okaxis")
    )

# --- WHATSAPP WEBHOOK ---

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "cybercafe_verify_token")
        if mode == "subscribe" and token == verify_token:
            return challenge, 200
        return "Verification token mismatch", 403
        
    elif request.method == "POST":
        data = request.json
        if not data:
            return "No payload", 400
        try:
            if data.get("object") == "whatsapp_business_account":
                for entry in data.get("entry", []):
                    for change in entry.get("changes", []):
                        value = change.get("value", {})
                        if "messages" in value:
                            for message in value.get("messages", []):
                                msg_type = message.get("type")
                                from_num = message.get("from")
                                msg_body = ""
                                if msg_type == "text":
                                    msg_body = message.get("text", {}).get("body", "")
                                else:
                                    msg_body = f"[{msg_type.upper()} message attachment received]"
                                
                                contacts = value.get("contacts", [])
                                customer_name = "WhatsApp User"
                                if contacts:
                                    customer_name = contacts[0].get("profile", {}).get("name", "WhatsApp User")
                                
                                new_msg = WhatsAppMessage(sender=customer_name, message=msg_body, direction="inbound")
                                db.session.add(new_msg)
                                
                                new_query = Query(
                                    customer_name=customer_name,
                                    phone=from_num,
                                    service_type="WhatsApp Request",
                                    message=msg_body,
                                    status="New",
                                    priority="Normal",
                                    amount=0.0,
                                    notes="Automatically created from WhatsApp Message"
                                )
                                db.session.add(new_query)
                            db.session.commit()
            return "EVENT_RECEIVED", 200
        except Exception as e:
            print(f"Webhook error: {e}")
            return "Internal Server Error", 500

# --- DB INIT ---

with app.app_context():
    db.create_all()
    
    # Run migration for staff table schema updates
    try:
        db.session.execute(db.text("SELECT username FROM staff LIMIT 1"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE staff ADD COLUMN username VARCHAR(80)"))
            db.session.execute(db.text("ALTER TABLE staff ADD COLUMN password_hash VARCHAR(255)"))
            db.session.execute(db.text("ALTER TABLE staff ADD COLUMN permissions TEXT"))
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            print(f"Schema migration warning: {ex}")
            
    # Run migration to check if email column exists in staff
    try:
        db.session.execute(db.text("SELECT email FROM staff LIMIT 1"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE staff ADD COLUMN email VARCHAR(120)"))
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            print(f"Staff email migration warning: {ex}")
            
    # Run migration for query table schema updates
    try:
        db.session.execute(db.text("SELECT payment_method FROM query LIMIT 1"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE query ADD COLUMN payment_method VARCHAR(50) DEFAULT 'Cash'"))
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            print(f"Query table schema migration warning: {ex}")
    
    default_username = os.getenv("ADMIN_USERNAME", "admin")
    default_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if not Admin.query.filter_by(username=default_username).first():
        db.session.add(Admin(username=default_username, password_hash=generate_password_hash(default_password)))
        
    defaults = {
        "cafe_name": os.getenv("CAFE_NAME", "Anaya's Digital Services"),
        "cafe_address": os.getenv("CAFE_ADDRESS", "Your Location"),
        "cafe_whatsapp": os.getenv("CAFE_WHATSAPP_NUMBER", "919876543210"),
        "cafe_upi": "pskaplish@okaxis"
    }
    for k, v in defaults.items():
        if not Setting.query.filter_by(key=k).first():
            db.session.add(Setting(key=k, value=v))
            
    if not Service.query.first():
        db.session.add(Service(name="Computer Use (1 Hour)", price=40.0, description="High speed internet browsing and system access."))
        db.session.add(Service(name="Black & White Printout (A4)", price=5.0, description="Laser print per page."))
        db.session.add(Service(name="Color Printout (A4)", price=15.0, description="Laser color print per page."))
        db.session.add(Service(name="Scanning Documents", price=10.0, description="Scan to PDF / Email."))
        db.session.add(Service(name="Lamination (A4)", price=30.0, description="Standard plastic sealing."))
        
    db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
