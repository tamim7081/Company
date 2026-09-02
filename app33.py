import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import hashlib
import calendar

# ------------------------------
# Database Setup
# ------------------------------
DB_FILE = "factory.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Employees table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            daily_wage REAL DEFAULT 0,
            monthly_salary REAL DEFAULT 0,
            employee_type TEXT DEFAULT 'production',
            active INTEGER DEFAULT 1,
            display_id INTEGER DEFAULT 0
        )
    ''')

    # Add new columns if not exists (for existing databases)
    cursor.execute("PRAGMA table_info(employees)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'monthly_salary' not in columns:
        cursor.execute("ALTER TABLE employees ADD COLUMN monthly_salary REAL DEFAULT 0")
    if 'employee_type' not in columns:
        cursor.execute("ALTER TABLE employees ADD COLUMN employee_type TEXT DEFAULT 'production'")
    if 'display_id' not in columns:
        cursor.execute("ALTER TABLE employees ADD COLUMN display_id INTEGER DEFAULT 0")

    # T-shirt types table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tshirt_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            production_cost REAL NOT NULL,
            labor_rate REAL NOT NULL,
            display_id INTEGER DEFAULT 0
        )
    ''')
    cursor.execute("PRAGMA table_info(tshirt_types)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'display_id' not in columns:
        cursor.execute("ALTER TABLE tshirt_types ADD COLUMN display_id INTEGER DEFAULT 0")

    # Daily production records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS production (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            tshirt_type_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (tshirt_type_id) REFERENCES tshirt_types (id)
        )
    ''')

    # Payments
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id)
        )
    ''')

    # Settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password', ?)",
                   (hashlib.sha256("admin123".encode()).hexdigest(),))

    conn.commit()
    conn.close()

    # Initial display_id assignment if not set
    reassign_employee_display_ids()
    reassign_tshirt_type_display_ids()

# ------------------------------
# Authentication
# ------------------------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Enter admin password", type="password")
        if st.button("Login"):
            conn = get_connection()
            stored_hash = conn.execute("SELECT value FROM settings WHERE key='admin_password'").fetchone()[0]
            conn.close()
            if hashlib.sha256(password.encode()).hexdigest() == stored_hash:
                st.session_state.authenticated = True
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Wrong password")
        return False
    return True

# ------------------------------
# Helper functions
# ------------------------------
def reassign_employee_display_ids():
    conn = get_connection()
    employees = conn.execute("SELECT id FROM employees ORDER BY id").fetchall()
    for idx, emp in enumerate(employees, start=1):
        conn.execute("UPDATE employees SET display_id = ? WHERE id = ?", (idx, emp['id']))
    conn.commit()
    conn.close()

def reassign_tshirt_type_display_ids():
    conn = get_connection()
    types = conn.execute("SELECT id FROM tshirt_types ORDER BY id").fetchall()
    for idx, t in enumerate(types, start=1):
        conn.execute("UPDATE tshirt_types SET display_id = ? WHERE id = ?", (idx, t['id']))
    conn.commit()
    conn.close()

def fetch_all_employees(active_only=True, employee_type=None):
    conn = get_connection()
    query = "SELECT * FROM employees WHERE 1=1"
    params = []
    if active_only:
        query += " AND active=1"
    if employee_type:
        query += " AND employee_type=?"
        params.append(employee_type)
    query += " ORDER BY display_id"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def fetch_all_tshirt_types():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM tshirt_types ORDER BY display_id", conn)
    conn.close()
    return df

def fetch_production_records(start_date=None, end_date=None, employee_id=None):
    conn = get_connection()
    query = """
        SELECT p.id, p.date, e.name AS employee, e.display_id AS emp_display_id,
               t.name AS tshirt_type, t.display_id AS type_display_id,
               p.quantity, t.labor_rate, p.quantity * t.labor_rate AS earned
        FROM production p
        JOIN employees e ON p.employee_id = e.id
        JOIN tshirt_types t ON p.tshirt_type_id = t.id
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND p.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND p.date <= ?"
        params.append(end_date)
    if employee_id:
        query += " AND p.employee_id = ?"
        params.append(employee_id)
    query += " ORDER BY p.date DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def fetch_payment_records(start_date=None, end_date=None, employee_id=None, employee_type=None):
    conn = get_connection()
    query = """
        SELECT pay.id, pay.date, e.name AS employee, e.display_id AS emp_display_id,
               e.employee_type, pay.amount, pay.note
        FROM payments pay
        JOIN employees e ON pay.employee_id = e.id
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND pay.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND pay.date <= ?"
        params.append(end_date)
    if employee_id:
        query += " AND pay.employee_id = ?"
        params.append(employee_id)
    if employee_type:
        query += " AND e.employee_type = ?"
        params.append(employee_type)
    query += " ORDER BY pay.date DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def insert_employee(name, daily_wage=0, monthly_salary=0, employee_type='production'):
    conn = get_connection()
    cursor = conn.execute("INSERT INTO employees (name, daily_wage, monthly_salary, employee_type) VALUES (?, ?, ?, ?)",
                          (name, daily_wage, monthly_salary, employee_type))
    conn.commit()
    conn.close()
    reassign_employee_display_ids()

def update_employee(emp_id, name, daily_wage, monthly_salary, employee_type, active):
    conn = get_connection()
    conn.execute("UPDATE employees SET name=?, daily_wage=?, monthly_salary=?, employee_type=?, active=? WHERE id=?",
                 (name, daily_wage, monthly_salary, employee_type, active, emp_id))
    conn.commit()
    conn.close()
    reassign_employee_display_ids()

def delete_employee(emp_id):
    conn = get_connection()
    # Delete related records first (or set null if you prefer, but we delete)
    conn.execute("DELETE FROM production WHERE employee_id=?", (emp_id,))
    conn.execute("DELETE FROM payments WHERE employee_id=?", (emp_id,))
    conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    conn.commit()
    conn.close()
    reassign_employee_display_ids()

def insert_tshirt_type(name, production_cost, labor_rate):
    conn = get_connection()
    conn.execute("INSERT INTO tshirt_types (name, production_cost, labor_rate) VALUES (?, ?, ?)",
                 (name, production_cost, labor_rate))
    conn.commit()
    conn.close()
    reassign_tshirt_type_display_ids()

def update_tshirt_type(type_id, name, production_cost, labor_rate):
    conn = get_connection()
    conn.execute("UPDATE tshirt_types SET name=?, production_cost=?, labor_rate=? WHERE id=?",
                 (name, production_cost, labor_rate, type_id))
    conn.commit()
    conn.close()
    reassign_tshirt_type_display_ids()

def delete_tshirt_type(type_id):
    conn = get_connection()
    conn.execute("DELETE FROM production WHERE tshirt_type_id=?", (type_id,))
    conn.execute("DELETE FROM tshirt_types WHERE id=?", (type_id,))
    conn.commit()
    conn.close()
    reassign_tshirt_type_display_ids()

def delete_production_record(record_id):
    conn = get_connection()
    conn.execute("DELETE FROM production WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

def delete_payment_record(record_id):
    conn = get_connection()
    conn.execute("DELETE FROM payments WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

# ------------------------------
# Page Functions
# ------------------------------
def page_dashboard():
    st.header("📊 Dashboard")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Active Production Employees", len(fetch_all_employees(employee_type='production')))
    with col2:
        st.metric("Active Salaried Employees", len(fetch_all_employees(employee_type='salaried')))
    with col3:
        st.metric("T-Shirt Types", len(fetch_all_tshirt_types()))

    today = date.today().isoformat()
    st.subheader("Today's Production")
    prod_today = fetch_production_records(start_date=today, end_date=today)
    if not prod_today.empty:
        st.dataframe(prod_today[['date', 'employee', 'tshirt_type', 'quantity', 'earned']], use_container_width=True)
    else:
        st.info("No production recorded today.")

    st.subheader("Recent Payments (All)")
    payments = fetch_payment_records()
    if not payments.empty:
        st.dataframe(payments[['date', 'employee', 'amount', 'note']].head(10), use_container_width=True)
    else:
        st.info("No payments recorded yet.")

def page_manage_employees():
    st.header("👥 Manage Employees")

    tab1, tab2 = st.tabs(["Production Workers", "Salaried Employees"])

    # ----- Production Workers Tab -----
    with tab1:
        st.subheader("Production Workers (Daily Wage)")
        employees = fetch_all_employees(active_only=False, employee_type='production')

        with st.expander("Add New Production Worker", expanded=False):
            with st.form("add_production_employee"):
                name = st.text_input("Name")
                daily_wage = st.number_input("Fixed Daily Wage (if any, else 0)", min_value=0.0, value=0.0, step=10.0)
                submitted = st.form_submit_button("Add Employee")
                if submitted and name:
                    insert_employee(name, daily_wage=daily_wage, monthly_salary=0, employee_type='production')
                    st.success(f"Employee '{name}' added!")
                    st.rerun()

        if not employees.empty:
            for _, emp in employees.iterrows():
                with st.expander(f"{emp['display_id']}. {emp['name']} (ID: {emp['id']})"):
                    col1, col2, col3, col4 = st.columns([3,2,1,1])
                    with col1:
                        new_name = st.text_input("Name", value=emp['name'], key=f"pname_{emp['id']}")
                    with col2:
                        new_wage = st.number_input("Daily Wage", value=float(emp['daily_wage']), min_value=0.0, key=f"pwage_{emp['id']}")
                    with col3:
                        new_active = st.checkbox("Active", value=bool(emp['active']), key=f"pactive_{emp['id']}")
                    with col4:
                        if st.button("Update", key=f"update_pemp_{emp['id']}"):
                            update_employee(emp['id'], new_name, new_wage, 0, 'production', int(new_active))
                            st.success("Updated!")
                            st.rerun()
                    if st.button("Delete", key=f"delete_pemp_{emp['id']}"):
                        delete_employee(emp['id'])
                        st.success("Employee deleted and IDs reassigned!")
                        st.rerun()

    # ----- Salaried Employees Tab -----
    with tab2:
        st.subheader("Salaried Employees (Monthly Salary)")
        employees = fetch_all_employees(active_only=False, employee_type='salaried')

        with st.expander("Add New Salaried Employee", expanded=False):
            with st.form("add_salaried_employee"):
                name = st.text_input("Name")
                monthly_salary = st.number_input("Monthly Salary", min_value=0.0, value=0.0, step=100.0)
                submitted = st.form_submit_button("Add Employee")
                if submitted and name:
                    insert_employee(name, daily_wage=0, monthly_salary=monthly_salary, employee_type='salaried')
                    st.success(f"Employee '{name}' added!")
                    st.rerun()

        if not employees.empty:
            for _, emp in employees.iterrows():
                with st.expander(f"{emp['display_id']}. {emp['name']} (ID: {emp['id']})"):
                    col1, col2, col3, col4 = st.columns([3,2,1,1])
                    with col1:
                        new_name = st.text_input("Name", value=emp['name'], key=f"sname_{emp['id']}")
                    with col2:
                        new_salary = st.number_input("Monthly Salary", value=float(emp['monthly_salary']), min_value=0.0, key=f"ssalary_{emp['id']}")
                    with col3:
                        new_active = st.checkbox("Active", value=bool(emp['active']), key=f"sactive_{emp['id']}")
                    with col4:
                        if st.button("Update", key=f"update_semp_{emp['id']}"):
                            update_employee(emp['id'], new_name, 0, new_salary, 'salaried', int(new_active))
                            st.success("Updated!")
                            st.rerun()
                    if st.button("Delete", key=f"delete_semp_{emp['id']}"):
                        delete_employee(emp['id'])
                        st.success("Employee deleted and IDs reassigned!")
                        st.rerun()

def page_manage_tshirts():
    st.header("👕 Manage T-Shirt Types")
    types = fetch_all_tshirt_types()

    with st.expander("Add New T-Shirt Type", expanded=False):
        with st.form("add_type"):
            name = st.text_input("Name (e.g., Polo, Round Neck)")
            prod_cost = st.number_input("Production Cost (per piece)", min_value=0.0, step=1.0)
            labor_rate = st.number_input("Labor Rate (paid to worker per piece)", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Add Type")
            if submitted and name:
                insert_tshirt_type(name, prod_cost, labor_rate)
                st.success(f"Type '{name}' added!")
                st.rerun()

    if not types.empty:
        st.subheader("Existing Types")
        for _, t in types.iterrows():
            with st.expander(f"{t['display_id']}. {t['name']} (ID: {t['id']})"):
                col1, col2, col3, col4 = st.columns([3,2,2,1])
                with col1:
                    new_name = st.text_input("Name", value=t['name'], key=f"tname_{t['id']}")
                with col2:
                    new_cost = st.number_input("Production Cost", value=float(t['production_cost']), min_value=0.0, key=f"tcost_{t['id']}")
                with col3:
                    new_labor = st.number_input("Labor Rate", value=float(t['labor_rate']), min_value=0.0, key=f"tlabor_{t['id']}")
                with col4:
                    if st.button("Update", key=f"update_type_{t['id']}"):
                        update_tshirt_type(t['id'], new_name, new_cost, new_labor)
                        st.success("Updated!")
                        st.rerun()
                if st.button("Delete", key=f"delete_type_{t['id']}"):
                    delete_tshirt_type(t['id'])
                    st.success("T-shirt type deleted and IDs reassigned!")
                    st.rerun()

def page_daily_production():
    st.header("🏭 Daily Production Entry")
    employees = fetch_all_employees(employee_type='production')
    types = fetch_all_tshirt_types()

    if employees.empty or types.empty:
        st.warning("Please add at least one production employee and one T-shirt type first.")
        return

    with st.form("production_form"):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            prod_date = st.date_input("Date", value=date.today())
        with col2:
            emp = st.selectbox("Employee", employees['id'].tolist(),
                               format_func=lambda x: f"{employees[employees['id'] == x]['display_id'].iloc[0]}. {employees[employees['id'] == x]['name'].iloc[0]}")
        with col3:
            ttype = st.selectbox("T-Shirt Type", types['id'].tolist(),
                                 format_func=lambda x: f"{types[types['id'] == x]['display_id'].iloc[0]}. {types[types['id'] == x]['name'].iloc[0]}")
        with col4:
            qty = st.number_input("Quantity", min_value=1, step=1)
        with col5:
            submitted = st.form_submit_button("Add Record")

        if submitted:
            conn = get_connection()
            conn.execute("INSERT INTO production (date, employee_id, tshirt_type_id, quantity) VALUES (?, ?, ?, ?)",
                         (prod_date.isoformat(), emp, ttype, qty))
            conn.commit()
            conn.close()
            st.success("Production recorded!")
            st.rerun()

    st.subheader("Recent Production Records")
    records = fetch_production_records()
    if not records.empty:
        for _, rec in records.head(20).iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([2,2,2,1,1,1])
            col1.write(rec['date'])
            col2.write(f"{rec['emp_display_id']}. {rec['employee']}")
            col3.write(f"{rec['type_display_id']}. {rec['tshirt_type']}")
            col4.write(rec['quantity'])
            col5.write(f"₹{rec['earned']:.2f}")
            if col6.button("Delete", key=f"del_prod_{rec['id']}"):
                delete_production_record(rec['id'])
                st.rerun()
    else:
        st.info("No production records yet.")

def page_daily_payments():
    st.header("💵 Daily Payment Entry (Production Workers)")
    employees = fetch_all_employees(employee_type='production')

    if employees.empty:
        st.warning("Please add at least one production employee first.")
        return

    with st.form("payment_form"):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            pay_date = st.date_input("Date", value=date.today())
        with col2:
            emp = st.selectbox("Employee", employees['id'].tolist(),
                               format_func=lambda x: f"{employees[employees['id'] == x]['display_id'].iloc[0]}. {employees[employees['id'] == x]['name'].iloc[0]}")
        with col3:
            amount = st.number_input("Amount", min_value=0.0, step=10.0)
        with col4:
            note = st.text_input("Note (optional)")
        with col5:
            submitted = st.form_submit_button("Add Payment")

        if submitted:
            conn = get_connection()
            conn.execute("INSERT INTO payments (date, employee_id, amount, note) VALUES (?, ?, ?, ?)",
                         (pay_date.isoformat(), emp, amount, note))
            conn.commit()
            conn.close()
            st.success("Payment recorded!")
            st.rerun()

    st.subheader("Recent Payments (Production)")
    payments = fetch_payment_records(employee_type='production')
    if not payments.empty:
        for _, pay in payments.head(20).iterrows():
            col1, col2, col3, col4, col5 = st.columns([2,2,1,2,1])
            col1.write(pay['date'])
            col2.write(f"{pay['emp_display_id']}. {pay['employee']}")
            col3.write(f"₹{pay['amount']:.2f}")
            col4.write(pay['note'] if pay['note'] else "")
            if col5.button("Delete", key=f"del_pay_{pay['id']}"):
                delete_payment_record(pay['id'])
                st.rerun()
    else:
        st.info("No payments recorded yet.")

def page_salaried_payments():
    st.header("💼 Salaried Employee Payments")
    employees = fetch_all_employees(employee_type='salaried')

    if employees.empty:
        st.warning("No salaried employees found. Please add them in Manage Employees.")
        return

    with st.form("salaried_payment_form"):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            pay_date = st.date_input("Date", value=date.today())
        with col2:
            emp = st.selectbox("Employee", employees['id'].tolist(),
                               format_func=lambda x: f"{employees[employees['id'] == x]['display_id'].iloc[0]}. {employees[employees['id'] == x]['name'].iloc[0]}")
        with col3:
            amount = st.number_input("Amount", min_value=0.0, step=100.0)
        with col4:
            note = st.text_input("Note (e.g., Weekly Thursday advance)")
        with col5:
            submitted = st.form_submit_button("Add Payment")

        if submitted:
            conn = get_connection()
            conn.execute("INSERT INTO payments (date, employee_id, amount, note) VALUES (?, ?, ?, ?)",
                         (pay_date.isoformat(), emp, amount, note))
            conn.commit()
            conn.close()
            st.success("Payment recorded!")
            st.rerun()

    st.subheader("Recent Salaried Payments")
    payments = fetch_payment_records(employee_type='salaried')
    if not payments.empty:
        for _, pay in payments.head(20).iterrows():
            col1, col2, col3, col4, col5 = st.columns([2,2,1,2,1])
            col1.write(pay['date'])
            col2.write(f"{pay['emp_display_id']}. {pay['employee']}")
            col3.write(f"₹{pay['amount']:.2f}")
            col4.write(pay['note'] if pay['note'] else "")
            if col5.button("Delete", key=f"del_salpay_{pay['id']}"):
                delete_payment_record(pay['id'])
                st.rerun()
    else:
        st.info("No salaried payments recorded yet.")

def page_monthly_profile():
    st.header("📅 Monthly Employee Profile (All Employees)")

    emp_type = st.radio("Select Employee Type", ["Production", "Salaried"], horizontal=True)

    if emp_type == "Production":
        employees = fetch_all_employees(employee_type='production')
    else:
        employees = fetch_all_employees(employee_type='salaried')

    if employees.empty:
        st.warning("No employees found for this type.")
        return

    col1, col2 = st.columns(2)
    with col1:
        emp = st.selectbox("Select Employee", employees['id'].tolist(),
                           format_func=lambda x: f"{employees[employees['id'] == x]['display_id'].iloc[0]}. {employees[employees['id'] == x]['name'].iloc[0]}")
    with col2:
        current_year = date.today().year
        current_month = date.today().month
        year = st.selectbox("Year", range(current_year - 5, current_year + 1), index=5)
        month = st.selectbox("Month", range(1, 13), index=current_month - 1)

    if emp:
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day)

        if emp_type == "Production":
            prod = fetch_production_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)
            payments = fetch_payment_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)

            total_earned = prod['earned'].sum() if not prod.empty else 0
            total_paid = payments['amount'].sum() if not payments.empty else 0
            balance = total_earned - total_paid

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Earned", f"₹{total_earned:.2f}")
            col2.metric("Total Paid", f"₹{total_paid:.2f}")
            col3.metric("Balance", f"₹{balance:.2f}")

            st.subheader("Production Breakdown")
            if not prod.empty:
                prod_summary = prod.groupby('tshirt_type').agg(
                    total_qty=('quantity', 'sum'),
                    total_earned=('earned', 'sum')
                ).reset_index()
                st.dataframe(prod_summary, use_container_width=True)
            else:
                st.info("No production in this month.")

            st.subheader("Payment Records")
            if not payments.empty:
                st.dataframe(payments[['date', 'amount', 'note']], use_container_width=True)
            else:
                st.info("No payments in this month.")

        else:  # Salaried
            emp_data = employees[employees['id'] == emp].iloc[0]
            monthly_salary = emp_data['monthly_salary']
            payments = fetch_payment_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)

            total_paid = payments['amount'].sum() if not payments.empty else 0
            balance = monthly_salary - total_paid

            col1, col2, col3 = st.columns(3)
            col1.metric("Monthly Salary", f"₹{monthly_salary:.2f}")
            col2.metric("Total Paid", f"₹{total_paid:.2f}")
            col3.metric("Balance", f"₹{balance:.2f}")

            st.subheader("Payment Records")
            if not payments.empty:
                st.dataframe(payments[['date', 'amount', 'note']], use_container_width=True)
            else:
                st.info("No payments in this month.")

def page_yearly_profile():
    st.header("📆 Yearly Employee Profile (All Employees)")

    emp_type = st.radio("Select Employee Type", ["Production", "Salaried"], horizontal=True)

    if emp_type == "Production":
        employees = fetch_all_employees(employee_type='production')
    else:
        employees = fetch_all_employees(employee_type='salaried')

    if employees.empty:
        st.warning("No employees found for this type.")
        return

    col1, col2 = st.columns(2)
    with col1:
        emp = st.selectbox("Select Employee", employees['id'].tolist(),
                           format_func=lambda x: f"{employees[employees['id'] == x]['display_id'].iloc[0]}. {employees[employees['id'] == x]['name'].iloc[0]}")
    with col2:
        current_year = date.today().year
        year = st.selectbox("Year", range(current_year - 5, current_year + 1), index=5)

    if emp:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        if emp_type == "Production":
            prod = fetch_production_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)
            payments = fetch_payment_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)

            total_earned = prod['earned'].sum() if not prod.empty else 0
            total_paid = payments['amount'].sum() if not payments.empty else 0
            balance = total_earned - total_paid

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Earned (Year)", f"₹{total_earned:.2f}")
            col2.metric("Total Paid (Year)", f"₹{total_paid:.2f}")
            col3.metric("Balance (Year)", f"₹{balance:.2f}")

            st.subheader("Monthly Breakdown")
            if not prod.empty:
                prod['month'] = pd.to_datetime(prod['date']).dt.month
                monthly_summary = prod.groupby('month').agg(
                    total_qty=('quantity', 'sum'),
                    total_earned=('earned', 'sum')
                ).reset_index()
                monthly_summary['month_name'] = monthly_summary['month'].apply(lambda x: calendar.month_name[x])
                st.dataframe(monthly_summary[['month_name', 'total_qty', 'total_earned']], use_container_width=True)
            else:
                st.info("No production in this year.")

            st.subheader("Payment Records (Year)")
            if not payments.empty:
                st.dataframe(payments[['date', 'amount', 'note']], use_container_width=True)
            else:
                st.info("No payments in this year.")

        else:  # Salaried
            emp_data = employees[employees['id'] == emp].iloc[0]
            yearly_salary = emp_data['monthly_salary'] * 12
            payments = fetch_payment_records(start_date=start_date.isoformat(), end_date=end_date.isoformat(), employee_id=emp)

            total_paid = payments['amount'].sum() if not payments.empty else 0
            balance = yearly_salary - total_paid

            col1, col2, col3 = st.columns(3)
            col1.metric("Yearly Salary (Expected)", f"₹{yearly_salary:.2f}")
            col2.metric("Total Paid", f"₹{total_paid:.2f}")
            col3.metric("Balance", f"₹{balance:.2f}")

            st.subheader("Payment Records (Year)")
            if not payments.empty:
                st.dataframe(payments[['date', 'amount', 'note']], use_container_width=True)
            else:
                st.info("No payments in this year.")

# ------------------------------
# Main App
# ------------------------------
def main():
    st.set_page_config(page_title="Factory Production Manager", layout="wide")
    init_db()

    if not check_password():
        st.stop()

    st.sidebar.title("Factory Manager")
    page = st.sidebar.radio(
        "Navigate",
        [
            "Dashboard",
            "Manage Employees",
            "Manage T-Shirt Types",
            "Daily Production",
            "Daily Payments",
            "Salaried Payments",
            "Monthly Employee Profile",
            "Yearly Employee Profile"
        ]
    )

    if page == "Dashboard":
        page_dashboard()
    elif page == "Manage Employees":
        page_manage_employees()
    elif page == "Manage T-Shirt Types":
        page_manage_tshirts()
    elif page == "Daily Production":
        page_daily_production()
    elif page == "Daily Payments":
        page_daily_payments()
    elif page == "Salaried Payments":
        page_salaried_payments()
    elif page == "Monthly Employee Profile":
        page_monthly_profile()
    elif page == "Yearly Employee Profile":
        page_yearly_profile()

if __name__ == "__main__":
    main()