from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import sqlite3

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

class SQLiteCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        sqlite_query = query.replace("%s", "?")
        if params is None:
            return self._cursor.execute(sqlite_query)
        return self._cursor.execute(sqlite_query, params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()


class SQLiteConnectionAdapter:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return SQLiteCursorAdapter(self._connection.cursor())

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()


def get_database_path():
    configured_path = os.getenv("DB_PATH", "data/rental_system.db")
    if os.path.isabs(configured_path):
        return configured_path
    return os.path.join(os.path.dirname(__file__), configured_path)


def init_db():
    db_path = get_database_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    connection = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as schema_file:
        connection.executescript(schema_file.read())
    connection.commit()
    connection.close()


def get_db_connection():
    connection = sqlite3.connect(get_database_path())
    connection.execute("PRAGMA foreign_keys = ON")
    return SQLiteConnectionAdapter(connection)


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-in-production")
init_db()



#Home
@app.route('/')
def home():
    return render_template('home.html')
#login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user'] = user[0]
            flash("Login successful", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")

    return render_template('login.html')

#dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    # Total properties
    cur.execute("SELECT COUNT(*) FROM properties")
    total_properties = cur.fetchone()[0]

    # Total units
    cur.execute("SELECT COUNT(*) FROM units")
    total_units = cur.fetchone()[0]

    # Total tenants
    cur.execute("SELECT COUNT(*) FROM tenants")
    total_tenants = cur.fetchone()[0]

    # Total payments
    cur.execute("SELECT COALESCE(SUM(amount_paid),0) FROM payments")
    total_payments = cur.fetchone()[0]
    #Vacant unit
    cur.execute("SELECT COUNT(*) FROM units WHERE status='vacant'")
    vacant_units = cur.fetchone()[0]

    # Arrears count (current month)
    from datetime import date
    current_month = date.today().replace(day=1)

    cur.execute("""
        SELECT COUNT(*)
        FROM tenants
        JOIN units ON tenants.unit_id = units.id
        LEFT JOIN payments 
            ON tenants.id = payments.tenant_id 
            AND payments.payment_month = %s
        GROUP BY tenants.id, units.rent_amount
        HAVING (units.rent_amount - COALESCE(SUM(payments.amount_paid),0)) > 0
    """, (current_month,))

    arrears_count = len(cur.fetchall())

    cur.close()
    conn.close()

    return render_template('dashboard.html',
                           total_properties=total_properties,
                           total_units=total_units,
                           total_tenants=total_tenants,
                           total_payments=total_payments,
                           vacant_units=vacant_units,
                           arrears_count=arrears_count)
#logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("Logged out successfully", "info")
    return redirect(url_for('login'))
#Adding Properties
@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO properties (name, location) VALUES(%s, %s)", (name, location))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('properties'))
    return render_template('add_property.html')

#Adding Properties
@app.route('/properties')
def properties():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()


    cur.execute("SELECT * FROM properties ORDER BY id DESC")
    properties = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('properties.html', properties=properties)

#Tenants Route
@app.route('/add_tenant', methods=['GET', 'POST'])
def add_tenant():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur =conn.cursor()

    #Fetching Vacant Unit
    cur.execute("SELECT id, unit_number FROM units WHERE status='vacant'")

    units = cur.fetchall()

    if request.method =='POST':
        unit_id = request.form['unit_id']
        full_name = request.form['full_name']
        phone = request.form['phone']
        id_number = request.form['id_number']
        move_in_date = request.form['move_in_date']
        #Data Validation
        if not full_name or not phone or not id_number:
            flash("All fields are required", "danger")
            return redirect(url_for('add_tenant'))
        if not phone.startswith('254') or len(phone) != 12 or not phone.isdigit():
            flash("Phone must be in format 2547XXXXXXXX", "danger")
            return redirect(url_for('add_tenant'))
        if not id_number.isdigit():
            flash("ID number must be numeric", "danger")
            return redirect(url_for('add_tenant'))

        #insert Tenants
        cur.execute(""" INSERT INTO tenants (unit_id, full_name, phone, id_number, move_in_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (unit_id, full_name, phone, id_number, move_in_date))
        #Updating unit status to be occupied
        cur.execute(
            "UPDATE units SET status='occupied' WHERE id=%s",
            (unit_id,)
        )

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for('tenant'))
    return render_template('add_tenant.html', units=units)

#viewing Tenant Route
@app.route('/tenants')
def tenants():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT tenants.id, tenants.full_name, tenants.phone,
               units.unit_number, tenants.move_in_date
        FROM tenants
        LEFT JOIN units ON tenants.unit_id = units.id
        ORDER BY tenants.id DESC
    """)

    tenants = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('tenants.html', tenants=tenants)

#Adding Units
@app.route('/add_unit', methods=['GET', 'POST'])
def add_unit():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch properties for dropdown
    cur.execute("SELECT id, name FROM properties")
    properties = cur.fetchall()

    if request.method == 'POST':
        property_id = request.form['property_id']
        unit_number = request.form['unit_number']
        rent_amount = request.form['rent_amount']

        # 🔥 IMPORTANT: status must be 'vacant'
        cur.execute("""
            INSERT INTO units (property_id, unit_number, rent_amount, status)
            VALUES (%s, %s, %s, %s)
        """, (property_id, unit_number, rent_amount, 'vacant'))

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for('add_unit'))
    return render_template('add_unit.html', properties=properties)
    
#Payments Route
@app.route('/add_payment', methods=['GET', 'POST'])
def add_payment():
    if 'user' not in session:
        return redirect(url_for('login'))
    payment_month = date.today().replace(day=1)
        
    conn = get_db_connection()
    cur = conn.cursor()

    #Fetch Tenants
    cur.execute("SELECT id, full_name FROM tenants")
    tenants = cur.fetchall()

    if request.method == 'POST':
        tenant_id = request.form['tenant_id']
        amount = request.form['amount']
        payment_date = request.form['payment_date']
        method = request.form['payment_method']
        mpesa_code = request.form['mpesa_code']

        #Data Validation
        if not tenant_id or not amount or not payment_date:
            flash("All fields are required", "danger")
            return redirect(url_for('add_payment'))
        try:
            amount = float(amount)
        except:
            flash("Invalid amount", "danger")
            return redirect(url_for('add_payment'))
        if amount <= 0:
            flash("Amount must be greater than 0", "danger")
            return redirect(url_for('add_payment'))
        if amount > 1000000:
            flash("Amount too large", "danger")
            return redirect(url_for('add_payment'))

        cur.execute("""
            INSERT INTO payments (tenant_id, amount_paid, payment_date, payment_method, mpesa_code, payment_month)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (tenant_id, amount, payment_date, method, mpesa_code, payment_month))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('payments'))
    return render_template('add_payment.html', tenants=tenants)
#Viewing Payments Route
@app.route('/payments')
def payments():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT payments.id, tenants.full_name, payments.amount_paid,
               payments.payment_date, payments.payment_method, payments.mpesa_code
        FROM payments
        JOIN tenants ON payments.tenant_id = tenants.id
        ORDER BY payments.id DESC
    """)
    payments = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('payments.html', payments=payments)


#Arrears Route
@app.route('/arrears')
def arrears():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    current_month = date.today().replace(day=1)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
       SELECT tenants.full_name,
               units.unit_number,
               units.rent_amount,
               COALESCE(SUM(payments.amount_paid), 0) AS paid,
               (units.rent_amount - COALESCE(SUM(payments.amount_paid), 0)) AS balance
        FROM tenants
        JOIN units ON tenants.unit_id = units.id
        LEFT JOIN payments 
            ON tenants.id = payments.tenant_id 
            AND payments.payment_month = %s
        GROUP BY tenants.full_name, units.unit_number, units.rent_amount
        HAVING (units.rent_amount - COALESCE(SUM(payments.amount_paid), 0)) > 0
    """, (current_month,))
    arrears = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('arrears.html', arrears=arrears)
#Receipt Route
@app.route('/receipt/<int:payment_id>')
def receipt (payment_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT tenants.full_name, payments.amount_paid,
               payments.payment_date, payments.payment_method, payments.mpesa_code
        FROM payments
        JOIN tenants ON payments.tenant_id = tenants.id
        WHERE payments.id = %s
    """, (payment_id,))
    payment = cur.fetchone()

    cur.close()
    conn.close()
    #creating pdf
    file_name = f"receipt_{payment_id}.pdf"
    pdf = SimpleDocTemplate(file_name)
    styles = getSampleStyleSheet()

    content = []

    content.append(Paragraph("RENT RECEIPT", styles['Title']))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"Tenant: {payment[0]}", styles['Normal']))
    content.append(Paragraph(f"Amount: KES {payment[1]}", styles['Normal']))
    content.append(Paragraph(f"Date: {payment[2]}", styles['Normal']))
    content.append(Paragraph(f"Method: {payment[3]}", styles['Normal']))
    content.append(Paragraph(f"M-Pesa Code: {payment[4]}", styles['Normal']))

    pdf.build(content)

    return send_file(file_name, as_attachment=True)
#Edit Route
@app.route('/edit_property/<int:id>', methods=['GET', 'POST'])
def edit_property(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        cur.execute("""
            UPDATE properties
            SET name=%s, location=%s
            WHERE id=%s
        """, (name, location, id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('properties'))
    cur.execute("SELECT * FROM properties WHERE id=%s", (id,))
    property = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('edit_property.html', property=property)
#Edit Tenant Route
@app.route('/edit_tenant/<int:id>', methods=['GET', 'POST'])
def edit_tenant(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        id_number = request.form['id_number']

        cur.execute("""
            UPDATE tenants
            SET full_name=%s, phone=%s, id_number=%s
            WHERE id=%s
        """, (full_name, phone, id_number, id))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('tenants'))
    cur.execute("SELECT * FROM tenants WHERE id=%s", (id,))
    tenant = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('edit_tenant.html', tenant=tenant)


@app.route('/edit_payment/<int:id>', methods=['GET', 'POST'])
def edit_payment(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn =get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, full_name FROM tenants")
    tenants = cur.fetchall()

    if request.method == 'POST':
        tenant_id = request.form['tenant_id']
        amount = request.form ['amount']
        payment_date = request.form['payment_date']
        method = request.form['payment_method']
        mpesa_code = request.form['mpesa_code']

        cur.execute("""
            UPDATE payments
            SET tenant_id=%s,
                amount_paid=%s,
                payment_date=%s,
                payment_method=%s,
                mpesa_code=%s
            WHERE id=%s
        """, (tenant_id, amount, payment_date, method, mpesa_code, id))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('payments'))
    
    cur.execute("SELECT * FROM payments WHERE id=%s", (id,))
    payment = cur.fetchone()

    cur.close()
    conn.close()

    return render_template('edit_payment.html', payment=payment, tenants=tenants)

#Registering Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash("All fields are required", "danger")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO users (username, password)
                VALUES (%s, %s)
            """, (username, hashed_password))

            conn.commit()
            flash("Account created successfully", "success")
            return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Username already exists. Try another.", "danger")

        finally:
            cur.close()
            conn.close()

    return render_template('register.html')

if __name__ == '__main__':
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
    )



