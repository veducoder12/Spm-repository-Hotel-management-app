from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("HMS_SECRET_KEY", "change-this-demo-secret-key")
DB_PATH = os.path.join(os.path.dirname(__file__), "hotel.db")

ROLES = ["Admin", "Manager", "Receptionist", "Billing"]

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      full_name TEXT NOT NULL,
      role TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS rooms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      number TEXT UNIQUE NOT NULL,
      room_type TEXT NOT NULL,
      rate REAL NOT NULL CHECK(rate >= 0),
      status TEXT NOT NULL DEFAULT 'Available'
    );
    CREATE TABLE IF NOT EXISTS guests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      email TEXT DEFAULT '',
      address TEXT DEFAULT '',
      id_document TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS bookings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      guest_id INTEGER NOT NULL REFERENCES guests(id),
      room_id INTEGER NOT NULL REFERENCES rooms(id),
      check_in TEXT NOT NULL,
      check_out TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Booked',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      booking_id INTEGER NOT NULL REFERENCES bookings(id),
      amount REAL NOT NULL CHECK(amount >= 0),
      method TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Paid',
      paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        demo_users = [
          ("admin", "admin123", "System Administrator", "Admin"),
          ("manager", "manager123", "Hotel Manager", "Manager"),
          ("reception", "reception123", "Front Desk", "Receptionist"),
          ("billing", "billing123", "Billing Staff", "Billing"),
        ]
        con.executemany("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                        [(u, generate_password_hash(p), n, r) for u,p,n,r in demo_users])
    if con.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        con.executemany("INSERT INTO rooms(number,room_type,rate,status) VALUES(?,?,?,?)", [
          ("101","Single",1800,"Available"), ("102","Single",1800,"Available"),
          ("201","Double",2800,"Available"), ("202","Double",2800,"Available"),
          ("301","Deluxe",4200,"Available"), ("401","Suite",6500,"Available"),
        ])
    con.commit()
    con.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def get_stats(con):
    today = date.today().isoformat()
    total = con.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    available = con.execute("SELECT COUNT(*) FROM rooms WHERE status='Available'").fetchone()[0]
    occupied = con.execute("SELECT COUNT(*) FROM bookings WHERE status='Checked In'").fetchone()[0]
    active = con.execute("SELECT COUNT(*) FROM bookings WHERE status IN ('Booked','Checked In')").fetchone()[0]
    revenue = con.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='Paid'").fetchone()[0]
    return {"total_rooms":total,"available":available,"occupied":occupied,"active_bookings":active,"revenue":revenue}

@app.context_processor
def inject_globals():
    return {"current_user": session.get("full_name"), "current_role": session.get("role")}

@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        con = db()
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        con.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], username=user["username"],
                           full_name=user["full_name"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    con = db()
    stats = get_stats(con)
    recent = con.execute("""SELECT b.id,g.name AS guest,r.number AS room,b.check_in,b.check_out,b.status
        FROM bookings b JOIN guests g ON g.id=b.guest_id JOIN rooms r ON r.id=b.room_id
        ORDER BY b.id DESC LIMIT 6""").fetchall()
    con.close()
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/rooms", methods=["GET","POST"])
@roles_required("Admin","Manager","Receptionist")
def rooms():
    con = db()
    if request.method == "POST":
        action = request.form.get("action","add")
        if action == "delete":
            rid = request.form.get("room_id")
            active = con.execute("SELECT COUNT(*) FROM bookings WHERE room_id=? AND status IN ('Booked','Checked In')",(rid,)).fetchone()[0]
            if active:
                flash("Cannot delete a room with an active booking.", "error")
            else:
                con.execute("DELETE FROM rooms WHERE id=?", (rid,))
                con.commit()
                flash("Room deleted.", "success")
            con.close()
            return redirect(url_for("rooms"))
        number = request.form.get("number","").strip()
        room_type = request.form.get("room_type","").strip()
        try:
            rate = float(request.form.get("rate","0"))
            if not number or not room_type or rate < 0: raise ValueError()
            if action == "edit":
                con.execute("UPDATE rooms SET number=?,room_type=?,rate=? WHERE id=?",
                            (number,room_type,rate,request.form.get("room_id")))
                flash("Room updated.", "success")
            else:
                con.execute("INSERT INTO rooms(number,room_type,rate,status) VALUES(?,?,?,'Available')",
                            (number,room_type,rate))
                flash("Room added.", "success")
            con.commit()
        except sqlite3.IntegrityError:
            flash("Room number already exists.", "error")
        except (ValueError, TypeError):
            flash("Enter a valid room number, type and non-negative rate.", "error")
    rows = con.execute("SELECT * FROM rooms ORDER BY number").fetchall()
    con.close()
    return render_template("rooms.html", rooms=rows)

@app.route("/guests", methods=["GET","POST"])
@roles_required("Admin","Manager","Receptionist")
def guests():
    con = db()
    if request.method == "POST":
        name=request.form.get("name","").strip()
        phone=request.form.get("phone","").strip()
        if not name or not phone:
            flash("Guest name and phone are required.", "error")
        else:
            con.execute("INSERT INTO guests(name,phone,email,address,id_document) VALUES(?,?,?,?,?)",
                (name,phone,request.form.get("email","").strip(),request.form.get("address","").strip(),
                 request.form.get("id_document","").strip()))
            con.commit()
            flash("Guest registered.", "success")
            con.close()
            return redirect(url_for("guests"))
    rows=con.execute("SELECT * FROM guests ORDER BY id DESC").fetchall()
    con.close()
    return render_template("guests.html", guests=rows)

def room_is_available(con, room_id, start, end, ignore_booking=None):
    sql = """SELECT COUNT(*) FROM bookings WHERE room_id=? AND status IN ('Booked','Checked In')
             AND NOT (check_out <= ? OR check_in >= ?)"""
    args=[room_id,start,end]
    if ignore_booking:
        sql += " AND id != ?"
        args.append(ignore_booking)
    return con.execute(sql,args).fetchone()[0] == 0

@app.route("/bookings", methods=["GET","POST"])
@roles_required("Admin","Manager","Receptionist")
def bookings():
    con=db()
    if request.method=="POST":
        try:
            guest_id=int(request.form["guest_id"]); room_id=int(request.form["room_id"])
            start=request.form["check_in"]; end=request.form["check_out"]
            start_date=date.fromisoformat(start); end_date=date.fromisoformat(end)
            if end_date <= start_date: raise ValueError("Check-out must be after check-in.")
            if start_date < date.today(): raise ValueError("Check-in date cannot be in the past.")
            room=con.execute("SELECT * FROM rooms WHERE id=?",(room_id,)).fetchone()
            if not room: raise ValueError("Select a valid room.")
            if not room_is_available(con,room_id,start,end): raise ValueError("Room is not available for those dates.")
            con.execute("INSERT INTO bookings(guest_id,room_id,check_in,check_out,status) VALUES(?,?,?,?,'Booked')",
                        (guest_id,room_id,start,end))
            con.commit()
            flash("Reservation created.", "success")
            con.close()
            return redirect(url_for("bookings"))
        except (ValueError,KeyError):
            flash("Check guest, room and dates. Check-out must be after check-in; room must be available.", "error")
        except sqlite3.IntegrityError:
            flash("Could not create reservation. Check the selected guest and room.", "error")
    guest_rows=con.execute("SELECT * FROM guests ORDER BY name").fetchall()
    room_rows=con.execute("SELECT * FROM rooms ORDER BY number").fetchall()
    
    booking_rows=con.execute("""SELECT b.*,g.name AS guest,r.number AS room,r.rate,
    CAST(julianday(b.check_out)-julianday(b.check_in) AS INTEGER) AS nights
    FROM bookings b JOIN guests g ON g.id=b.guest_id JOIN rooms r ON r.id=b.room_id
    ORDER BY b.id DESC""").fetchall()

    con.close()
    return render_template("bookings.html", guests=guest_rows, rooms=room_rows, bookings=booking_rows,
                           today=date.today().isoformat())

@app.route("/bookings/<int:booking_id>/status", methods=["POST"])
@roles_required("Admin","Manager","Receptionist")
def booking_status(booking_id):
    new_status=request.form.get("status")
    allowed=["Cancelled","Checked In","Checked Out"]
    if new_status not in allowed: abort(400)
    con=db()
    booking=con.execute("SELECT * FROM bookings WHERE id=?",(booking_id,)).fetchone()
    if not booking:
        con.close(); abort(404)
    if booking["status"] in ["Cancelled","Checked Out"]:
        flash("This booking is already closed.", "error")
    elif new_status=="Checked In":
        if booking["status"]!="Booked":
            flash("Only booked reservations can be checked in.", "error")
        else:
            con.execute("UPDATE bookings SET status='Checked In' WHERE id=?",(booking_id,))
            con.execute("UPDATE rooms SET status='Occupied' WHERE id=?",(booking["room_id"],))
            con.commit(); flash("Guest checked in.", "success")
    elif new_status=="Checked Out":
        if booking["status"]!="Checked In":
            flash("Check-in is required before check-out.", "error")
        else:
            con.execute("UPDATE bookings SET status='Checked Out' WHERE id=?",(booking_id,))
            con.execute("UPDATE rooms SET status='Available' WHERE id=?",(booking["room_id"],))
            con.commit(); flash("Guest checked out. Generate/record the bill in Billing.", "success")
    else:
        if booking["status"]=="Checked In":
            flash("A checked-in guest cannot be cancelled; check them out instead.", "error")
        else:
            con.execute("UPDATE bookings SET status='Cancelled' WHERE id=?",(booking_id,))
            con.commit(); flash("Reservation cancelled.", "success")
    con.close()
    return redirect(url_for("bookings"))

@app.route("/billing", methods=["GET","POST"])
@roles_required("Admin","Manager","Billing")
def billing():
    con=db()
    if request.method=="POST":
        try:
            bid=int(request.form["booking_id"])
            amount=float(request.form["amount"])
            method=request.form["method"]
            status=request.form.get("status","Paid")
            if amount < 0 or status not in ["Paid","Pending"] or method not in ["Cash","Card","UPI","Bank Transfer"]:
                raise ValueError()
            exists=con.execute("SELECT id FROM bookings WHERE id=?",(bid,)).fetchone()
            if not exists: raise ValueError()
            con.execute("INSERT INTO payments(booking_id,amount,method,status) VALUES(?,?,?,?)",
                        (bid,amount,method,status))
            con.commit(); flash("Payment record saved.", "success")
            con.close()
            return redirect(url_for("billing"))
        except (ValueError,KeyError):
            flash("Enter a valid booking, amount, payment method and status.", "error")
    booking_rows=con.execute("""SELECT b.id,b.check_in,b.check_out,b.status,g.name AS guest,r.number AS room,r.rate,
        CAST(julianday(b.check_out)-julianday(b.check_in) AS INTEGER) AS nights,
        COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.booking_id=b.id AND p.status='Paid'),0) AS paid
        FROM bookings b JOIN guests g ON g.id=b.guest_id JOIN rooms r ON r.id=b.room_id
        WHERE b.status != 'Cancelled' ORDER BY b.id DESC""").fetchall()
    payment_rows=con.execute("""SELECT p.*,g.name AS guest,r.number AS room
        FROM payments p JOIN bookings b ON b.id=p.booking_id JOIN guests g ON g.id=b.guest_id
        JOIN rooms r ON r.id=b.room_id ORDER BY p.id DESC""").fetchall()
    con.close()
    return render_template("billing.html", bookings=booking_rows, payments=payment_rows)

@app.route("/reports")
@roles_required("Admin","Manager","Billing")
def reports():
    con=db()
    stats=get_stats(con)
    by_status=con.execute("SELECT status,COUNT(*) AS count FROM bookings GROUP BY status").fetchall()
    by_type=con.execute("""SELECT r.room_type,COUNT(*) AS count FROM rooms r GROUP BY r.room_type ORDER BY r.room_type""").fetchall()
    payments=con.execute("""SELECT p.id,p.booking_id,p.amount,p.method,p.status,p.paid_at,g.name AS guest,r.number AS room
      FROM payments p JOIN bookings b ON b.id=p.booking_id JOIN guests g ON g.id=b.guest_id
      JOIN rooms r ON r.id=b.room_id ORDER BY p.id DESC""").fetchall()
    con.close()
    return render_template("reports.html", stats=stats, by_status=by_status, by_type=by_type, payments=payments)

@app.route("/users", methods=["GET","POST"])
@roles_required("Admin")
def users():
    con=db()
    if request.method=="POST":
        username=request.form.get("username","").strip()
        full_name=request.form.get("full_name","").strip()
        password=request.form.get("password","")
        role=request.form.get("role","")
        if not username or not full_name or len(password)<6 or role not in ROLES:
            flash("Enter all fields. Password must be at least 6 characters.", "error")
        else:
            try:
                con.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                            (username,generate_password_hash(password),full_name,role))
                con.commit(); flash("User created.", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists.", "error")
    rows=con.execute("SELECT id,username,full_name,role FROM users ORDER BY id").fetchall()
    con.close()
    return render_template("users.html", users=rows, roles=ROLES)

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to access this page."),403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The requested page or record was not found."),404

init_db()

if __name__ == "__main__":
    app.run(debug=True)
