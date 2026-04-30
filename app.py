import os
from datetime import date
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import event as sa_event, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import Payment, Property, Tenant, Unit, User, db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def get_database_path():
    configured_path = os.getenv("DB_PATH", "data/rental_system.db")
    if os.path.isabs(configured_path):
        return configured_path
    return os.path.join(os.path.dirname(__file__), configured_path)


def ensure_db_directory():
    db_path = get_database_path()
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def sqlite_database_uri():
    path = os.path.abspath(get_database_path())
    return "sqlite:///" + path.replace("\\", "/")


@sa_event.listens_for(Engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, _connection_record):
    cursor = None
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
    finally:
        if cursor is not None:
            cursor.close()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")
app.config["SQLALCHEMY_DATABASE_URI"] = sqlite_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    ensure_db_directory()
    db.create_all()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user"] = user.id
            flash("Login successful", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        total_properties = Property.query.count()
        total_units = Unit.query.count()
        total_tenants = Tenant.query.count()
        total_payments = db.session.query(
            func.coalesce(func.sum(Payment.amount_paid), 0)
        ).scalar()
        vacant_units = Unit.query.filter_by(status="vacant").count()

        current_month = date.today().replace(day=1).isoformat()
        arrears_sql = text(
            """
            SELECT COUNT(*) FROM (
                SELECT tenants.id
                FROM tenants
                JOIN units ON tenants.unit_id = units.id
                LEFT JOIN payments
                    ON tenants.id = payments.tenant_id
                    AND payments.payment_month = :payment_month
                GROUP BY tenants.id, units.rent_amount
                HAVING (units.rent_amount - COALESCE(SUM(payments.amount_paid), 0)) > 0
            )
            """
        )
        arrears_count = db.session.execute(
            arrears_sql, {"payment_month": current_month}
        ).scalar()

        return render_template(
            "dashboard.html",
            total_properties=total_properties,
            total_units=total_units,
            total_tenants=total_tenants,
            total_payments=total_payments,
            vacant_units=vacant_units,
            arrears_count=arrears_count or 0,
        )

    except Exception as e:
        return f"Error occurred: {e}"


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))


@app.route("/add_property", methods=["GET", "POST"])
def add_property():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        location = request.form["location"]

        db.session.add(Property(name=name, location=location))
        db.session.commit()
        return redirect(url_for("properties"))
    return render_template("add_property.html")


@app.route("/properties")
def properties():
    if "user" not in session:
        return redirect(url_for("login"))

    properties_list = Property.query.order_by(Property.id.desc()).all()

    return render_template("properties.html", properties=properties_list)


@app.route("/add_tenant", methods=["GET", "POST"])
def add_tenant():
    if "user" not in session:
        return redirect(url_for("login"))

    units = Unit.query.filter_by(status="vacant").with_entities(Unit.id, Unit.unit_number).all()

    if request.method == "POST":
        unit_id = request.form["unit_id"]
        full_name = request.form["full_name"]
        phone = request.form["phone"]
        id_number = request.form["id_number"]
        move_in_date = request.form["move_in_date"]
        if not full_name or not phone or not id_number:
            flash("All fields are required", "danger")
            return redirect(url_for("add_tenant"))
        if not phone.startswith("254") or len(phone) != 12 or not phone.isdigit():
            flash("Phone must be in format 2547XXXXXXXX", "danger")
            return redirect(url_for("add_tenant"))
        if not id_number.isdigit():
            flash("ID number must be numeric", "danger")
            return redirect(url_for("add_tenant"))

        tenant = Tenant(
            unit_id=unit_id,
            full_name=full_name,
            phone=phone,
            id_number=id_number,
            move_in_date=move_in_date,
        )
        db.session.add(tenant)

        unit = db.session.get(Unit, int(unit_id))
        if unit:
            unit.status = "occupied"

        db.session.commit()

        return redirect(url_for("tenants"))
    return render_template("add_tenant.html", units=units)


@app.route("/tenants")
def tenants():
    if "user" not in session:
        return redirect(url_for("login"))

    tenants_list = (
        db.session.query(
            Tenant.id,
            Tenant.full_name,
            Tenant.phone,
            Unit.unit_number,
            Tenant.move_in_date,
        )
        .outerjoin(Unit, Tenant.unit_id == Unit.id)
        .order_by(Tenant.id.desc())
        .all()
    )

    return render_template("tenants.html", tenants=tenants_list)


@app.route("/add_unit", methods=["GET", "POST"])
def add_unit():
    if "user" not in session:
        return redirect(url_for("login"))

    properties_rows = Property.query.with_entities(Property.id, Property.name).all()

    if request.method == "POST":
        property_id = request.form["property_id"]
        unit_number = request.form["unit_number"]
        rent_amount = request.form["rent_amount"]

        db.session.add(
            Unit(
                property_id=property_id,
                unit_number=unit_number,
                rent_amount=rent_amount,
                status="vacant",
            )
        )
        db.session.commit()

        return redirect(url_for("add_unit"))
    return render_template("add_unit.html", properties=properties_rows)


@app.route("/add_payment", methods=["GET", "POST"])
def add_payment():
    if "user" not in session:
        return redirect(url_for("login"))
    payment_month = date.today().replace(day=1).isoformat()

    tenants_rows = Tenant.query.with_entities(Tenant.id, Tenant.full_name).all()

    if request.method == "POST":
        tenant_id = request.form["tenant_id"]
        amount = request.form["amount"]
        payment_date = request.form["payment_date"]
        method = request.form["payment_method"]
        mpesa_code = request.form["mpesa_code"]

        if not tenant_id or not amount or not payment_date:
            flash("All fields are required", "danger")
            return redirect(url_for("add_payment"))
        try:
            amount = float(amount)
        except ValueError:
            flash("Invalid amount", "danger")
            return redirect(url_for("add_payment"))
        if amount <= 0:
            flash("Amount must be greater than 0", "danger")
            return redirect(url_for("add_payment"))
        if amount > 1000000:
            flash("Amount too large", "danger")
            return redirect(url_for("add_payment"))

        db.session.add(
            Payment(
                tenant_id=tenant_id,
                amount_paid=amount,
                payment_date=payment_date,
                payment_method=method,
                mpesa_code=mpesa_code,
                payment_month=payment_month,
            )
        )
        db.session.commit()
        return redirect(url_for("payments"))
    return render_template("add_payment.html", tenants=tenants_rows)


@app.route("/payments")
def payments():
    if "user" not in session:
        return redirect(url_for("login"))

    payments_list = (
        db.session.query(
            Payment.id,
            Tenant.full_name,
            Payment.amount_paid,
            Payment.payment_date,
            Payment.payment_method,
            Payment.mpesa_code,
        )
        .join(Tenant, Payment.tenant_id == Tenant.id)
        .order_by(Payment.id.desc())
        .all()
    )

    return render_template("payments.html", payments=payments_list)


@app.route("/arrears")
def arrears():
    if "user" not in session:
        return redirect(url_for("login"))

    current_month = date.today().replace(day=1).isoformat()
    arrears_sql = text(
        """
       SELECT tenants.full_name,
               units.unit_number,
               units.rent_amount,
               COALESCE(SUM(payments.amount_paid), 0) AS paid,
               (units.rent_amount - COALESCE(SUM(payments.amount_paid), 0)) AS balance
        FROM tenants
        JOIN units ON tenants.unit_id = units.id
        LEFT JOIN payments
            ON tenants.id = payments.tenant_id
            AND payments.payment_month = :payment_month
        GROUP BY tenants.full_name, units.unit_number, units.rent_amount
        HAVING (units.rent_amount - COALESCE(SUM(payments.amount_paid), 0)) > 0
    """
    )
    arrears_rows = db.session.execute(arrears_sql, {"payment_month": current_month}).all()

    return render_template("arrears.html", arrears=arrears_rows)


@app.route("/receipt/<int:payment_id>")
def receipt(payment_id):
    if "user" not in session:
        return redirect(url_for("login"))

    row = (
        db.session.query(
            Tenant.full_name,
            Payment.amount_paid,
            Payment.payment_date,
            Payment.payment_method,
            Payment.mpesa_code,
        )
        .join(Tenant, Payment.tenant_id == Tenant.id)
        .filter(Payment.id == payment_id)
        .first()
    )

    if not row:
        flash("Payment not found", "danger")
        return redirect(url_for("payments"))

    file_name = f"receipt_{payment_id}.pdf"
    pdf = SimpleDocTemplate(file_name)
    styles = getSampleStyleSheet()

    content = [
        Paragraph("RENT RECEIPT", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"Tenant: {row.full_name}", styles["Normal"]),
        Paragraph(f"Amount: KES {row.amount_paid}", styles["Normal"]),
        Paragraph(f"Date: {row.payment_date}", styles["Normal"]),
        Paragraph(f"Method: {row.payment_method}", styles["Normal"]),
        Paragraph(f"M-Pesa Code: {row.mpesa_code or ''}", styles["Normal"]),
    ]

    pdf.build(content)

    return send_file(file_name, as_attachment=True)


@app.route("/edit_property/<int:id>", methods=["GET", "POST"])
def edit_property(id):
    if "user" not in session:
        return redirect(url_for("login"))

    prop = db.session.get(Property, id)
    if prop is None:
        abort(404)

    if request.method == "POST":
        prop.name = request.form["name"]
        prop.location = request.form["location"]
        db.session.commit()
        return redirect(url_for("properties"))

    return render_template("edit_property.html", property=prop)


@app.route("/edit_tenant/<int:id>", methods=["GET", "POST"])
def edit_tenant(id):
    if "user" not in session:
        return redirect(url_for("login"))

    tenant = db.session.get(Tenant, id)
    if tenant is None:
        abort(404)

    if request.method == "POST":
        tenant.full_name = request.form["full_name"]
        tenant.phone = request.form["phone"]
        tenant.id_number = request.form["id_number"]

        db.session.commit()
        return redirect(url_for("tenants"))

    return render_template("edit_tenant.html", tenant=tenant)


@app.route("/edit_payment/<int:id>", methods=["GET", "POST"])
def edit_payment(id):
    if "user" not in session:
        return redirect(url_for("login"))

    payment = db.session.get(Payment, id)
    if payment is None:
        abort(404)
    tenants_rows = Tenant.query.with_entities(Tenant.id, Tenant.full_name).all()

    if request.method == "POST":
        payment.tenant_id = int(request.form["tenant_id"])
        payment.amount_paid = float(request.form["amount"])
        payment.payment_date = request.form["payment_date"]
        payment.payment_method = request.form["payment_method"]
        payment.mpesa_code = request.form["mpesa_code"]

        db.session.commit()
        return redirect(url_for("payments"))

    return render_template("edit_payment.html", payment=payment, tenants=tenants_rows)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if not username or not password:
            flash("All fields are required", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        db.session.add(User(username=username, password=hashed_password))

        try:
            db.session.commit()
            flash("Account created successfully", "success")
            return redirect(url_for("login"))
        except IntegrityError:
            db.session.rollback()
            flash("Username already exists. Try another.", "danger")

    return render_template("register.html")


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
    )
