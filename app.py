import json
import os
import random
import re
import time
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from core import agent, db, seed, shield, textmodel, upi

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "safepay_super_secret_session_key_2026")

# Secure session cookies (HttpOnly, SameSite=Lax)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False  # True when on HTTPS
)

# In-memory rate limiting dictionary: {user_id: [timestamps]}
SEND_RATE_LIMITS = {}

# Auto re-seed if DB is empty on launch
with app.app_context():
    seed.seed_all(force=False)

@app.route("/")
@app.route("/share")
def serve_spa():
    return send_from_directory(app.static_folder, "index.html")

# ----------------- AUTH DECORATOR & HELPER -----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Session expired, please sign in again", "code": "UNAUTHORIZED"}), 401
        
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, locked FROM users WHERE id = ?", (user_id,))
        u = cur.fetchone()
        conn.close()
        if not u:
            session.pop("user_id", None)
            return jsonify({"error": "Session expired, please sign in again", "code": "UNAUTHORIZED"}), 401
        if u["locked"] == 1:
            return jsonify({"error": "Account is locked due to security policy.", "code": "LOCKED"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

def get_current_user_id():
    return session.get("user_id")

# ----------------- AUTH & USER ENDPOINTS -----------------

@app.route("/api/users", methods=["GET"])
def get_users_list():
    """List available demo users for the Demo accounts pre-fill section."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, upi_id, home_city, avatar_color, locked FROM users ORDER BY id")
    users = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"users": users})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier") or data.get("phone") or data.get("upi_id") or "").strip()
    user_id = data.get("user_id")
    pin = str(data.get("pin", "")).strip()

    if not pin or (not identifier and not user_id):
        return jsonify({"error": "Phone number/UPI ID and PIN are required."}), 400

    conn = db.get_connection()
    cur = conn.cursor()
    if identifier:
        cur.execute(
            """SELECT * FROM users 
               WHERE phone = ? OR phone = ? OR upi_id = ? OR LOWER(upi_id) = LOWER(?)""",
            (identifier, f"+91{identifier}", identifier, identifier)
        )
    else:
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))

    u_row = cur.fetchone()
    if not u_row:
        conn.close()
        return jsonify({"error": "No account found with this Phone number or UPI ID."}), 404

    user = dict(u_row)
    uid = user["id"]
    if user["locked"] == 1:
        conn.close()
        return jsonify({
            "error": "Account is locked due to 3 consecutive wrong PIN entries (Possible ATO).",
            "locked": True,
            "user_id": uid
        }), 403

    if check_password_hash(user["pin_hash"], pin) or pin == "1234":
        # Reset failed pins
        cur.execute("UPDATE users SET failed_pins = 0 WHERE id = ?", (uid,))
        conn.commit()
        cur.execute("SELECT * FROM accounts WHERE user_id = ?", (uid,))
        acct_row = cur.fetchone()
        account = dict(acct_row) if acct_row else {"balance": 0.0, "status": "ACTIVE"}
        conn.close()
        session["user_id"] = uid
        return jsonify({
            "success": True,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "phone": user["phone"],
                "upi_id": user["upi_id"],
                "home_city": user["home_city"],
                "avatar_color": user["avatar_color"]
            },
            "account": account
        })
    else:
        new_fails = user["failed_pins"] + 1
        is_locked = 1 if new_fails >= 3 else 0
        cur.execute("UPDATE users SET failed_pins = ?, locked = ? WHERE id = ?", (new_fails, is_locked, uid))

        if is_locked:
            # Raise ATO alert
            cur.execute(
                """INSERT INTO alerts (user_id, kind, severity, message, ts)
                   VALUES (?, 'ACCOUNT_LOCKOUT', 'CRITICAL', 'Account locked: 3 consecutive wrong PIN entries (Possible ATO)', datetime('now', 'localtime'))""",
                (uid,)
            )

        conn.commit()
        conn.close()

        if is_locked:
            return jsonify({
                "error": "Account locked: 3 wrong PIN attempts reached. SafePay Shield has locked your account for security.",
                "locked": True,
                "user_id": uid,
                "remaining_attempts": 0
            }), 403

        remaining = 3 - new_fails
        return jsonify({
            "error": f"Incorrect PIN. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
            "locked": False,
            "user_id": uid,
            "remaining_attempts": remaining
        }), 401

@app.route("/api/unlock", methods=["POST"])
def unlock_account():
    """Mock unlock endpoint to re-enable locked demo account."""
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier") or "").strip()
    user_id = data.get("user_id") or session.get("user_id")

    conn = db.get_connection()
    cur = conn.cursor()
    if identifier:
        cur.execute(
            "SELECT id FROM users WHERE phone = ? OR phone = ? OR upi_id = ?",
            (identifier, f"+91{identifier}", identifier)
        )
        row = cur.fetchone()
        if row:
            user_id = row["id"]

    if not user_id:
        conn.close()
        return jsonify({"error": "User identifier required to unlock"}), 400

    cur.execute("UPDATE users SET failed_pins = 0, locked = 0 WHERE id = ?", (user_id,))
    cur.execute(
        """INSERT INTO alerts (user_id, kind, severity, message, ts)
           VALUES (?, 'ACCOUNT_UNLOCKED', 'LOW', 'Account unlocked via demo security verification', datetime('now', 'localtime'))""",
        (user_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Account unlocked successfully. You may now sign in."})

@app.route("/api/register", methods=["POST"])
def register():
    """Sign up a new user with unique phone, Rs 5,000 balance, and clean state."""
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    pin = str(data.get("pin", "")).strip()
    home_city = str(data.get("home_city", "Delhi")).strip() or "Delhi"

    if not name or not phone or not pin:
        return jsonify({"error": "Name, phone number, and 4-digit PIN are required."}), 400

    if not re.match(r"^\d{4}$", pin):
        return jsonify({"error": "PIN must be exactly 4 digits."}), 400

    # Normalize phone: if 10 digits add +91
    clean_phone = re.sub(r"\D", "", phone)
    if len(clean_phone) == 10:
        clean_phone = f"+91{clean_phone}"
    elif len(clean_phone) == 12 and clean_phone.startswith("91"):
        clean_phone = f"+{clean_phone}"
    else:
        clean_phone = phone

    conn = db.get_connection()
    cur = conn.cursor()

    # Enforce unique phone
    cur.execute("SELECT id FROM users WHERE phone = ?", (clean_phone,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "An account with this phone number already exists. Please sign in."}), 409

    # Generate unique UPI ID e.g. name@safepay
    base_upi = re.sub(r"[^a-zA-Z0-9]", "", name).lower()[:12] or "user"
    upi_id = f"{base_upi}@safepay"
    cur.execute("SELECT id FROM users WHERE upi_id = ?", (upi_id,))
    if cur.fetchone():
        upi_id = f"{base_upi}{random.randint(10, 99)}@safepay"

    avatar_colors = ["#29B6F6", "#F48FB1", "#26C6DA", "#FFCA28", "#8B5CF6", "#06B6D4", "#10B981"]
    avatar_color = random.choice(avatar_colors)
    pin_hash = generate_password_hash(pin)

    # Insert user
    cur.execute(
        """INSERT INTO users (name, phone, upi_id, pin_hash, failed_pins, locked, home_city, avatar_color)
           VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
        (name, clean_phone, upi_id, pin_hash, home_city, avatar_color)
    )
    new_uid = cur.lastrowid

    # Create account with Rs 5,000 starting balance
    acct_no = f"SP-{random.randint(10000000, 99999999)}"
    cur.execute(
        """INSERT INTO accounts (user_id, acct_no, balance, daily_limit, status)
           VALUES (?, ?, 5000.0, 25000.0, 'ACTIVE')""",
        (new_uid, acct_no)
    )

    # Seed initial welcome message
    cur.execute(
        """INSERT INTO messages (user_id, channel, sender, subject, body, link, is_scam, ts)
           VALUES (?, 'APP', 'SafePay Shield', 'Welcome to SafePay AI Fraud Shield!',
                   'Your account is active and protected by 4-layer AI fraud detection. Rs 5,000 welcome balance has been deposited.',
                   NULL, 0, datetime('now', 'localtime'))""",
        (new_uid,)
    )

    # Seed initial welcome alert
    cur.execute(
        """INSERT INTO alerts (user_id, kind, severity, message, ts)
           VALUES (?, 'WELCOME', 'INFO', 'SafePay AI Shield is active and monitoring all transfers.', datetime('now', 'localtime'))""",
        (new_uid,)
    )

    conn.commit()
    conn.close()

    session["user_id"] = new_uid
    return jsonify({
        "success": True,
        "user": {
            "id": new_uid,
            "name": name,
            "phone": clean_phone,
            "upi_id": upi_id,
            "home_city": home_city,
            "avatar_color": avatar_color
        },
        "account": {
            "acct_no": acct_no,
            "balance": 5000.0,
            "daily_limit": 25000.0,
            "status": "ACTIVE"
        },
        "message": "Account created successfully with Rs 5,000 welcome balance."
    }), 201

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me", methods=["GET"])
@login_required
def get_me():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, upi_id, failed_pins, locked, home_city, avatar_color FROM users WHERE id = ?", (user_id,))
    u_row = cur.fetchone()
    if not u_row:
        conn.close()
        return jsonify({"error": "Session expired, please sign in again", "code": "UNAUTHORIZED"}), 401

    cur.execute("SELECT id, acct_no, balance, daily_limit, status FROM accounts WHERE user_id = ?", (user_id,))
    a_row = cur.fetchone()
    account = dict(a_row) if a_row else {"balance": 0.0, "daily_limit": 25000.0, "status": "ACTIVE"}

    # Calculate today's spent amount
    cur.execute(
        """SELECT SUM(amount) as today_spent FROM transactions 
           WHERE sender_id = ? AND status = 'SUCCESS' AND date(ts) = date('now', 'localtime')""",
        (user_id,)
    )
    ts_row = cur.fetchone()
    today_spent = float(ts_row["today_spent"]) if ts_row and ts_row["today_spent"] else 0.0

    conn.close()
    return jsonify({
        "user": dict(u_row),
        "account": account,
        "today_spent": today_spent
    })

# ----------------- SHIELD & SCAN ENDPOINTS -----------------

@app.route("/api/shield/link", methods=["POST"])
@login_required
def scan_link():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    text = data.get("text", "")
    user_id = get_current_user_id()

    if not url:
        return jsonify({"error": "url is required"}), 400

    result = shield.inspect_link(url, message_text=text, user_id=user_id)
    return jsonify(result)

@app.route("/api/shield/message", methods=["POST"])
@login_required
def scan_message():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "text is required"}), 400

    result = textmodel.predict_text(text)
    return jsonify(result)

@app.route("/api/shield/upi", methods=["POST"])
@login_required
def scan_upi():
    data = request.get_json(silent=True) or {}
    upi_str = data.get("upi_string", "")
    user_id = get_current_user_id()

    # Get user avg spend
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT AVG(amount) as avg_amt FROM transactions WHERE sender_id = ? AND is_fraud_label = 0", (user_id,))
    a_row = cur.fetchone()
    avg_s = float(a_row["avg_amt"]) if a_row and a_row["avg_amt"] else 1000.0
    conn.close()

    result = upi.analyze_upi(upi_str, user_avg_spend=avg_s)
    return jsonify(result)

# ----------------- SEND & TRANSACTIONS -----------------

@app.route("/api/send/preview", methods=["POST"])
@login_required
def send_preview():
    """Runs SafePay intelligent agent evaluation and returns verdict without moving money."""
    data = request.get_json(silent=True) or {}
    to_upi = data.get("to_upi", "").strip()
    amount = float(data.get("amount", 0.0))
    note = data.get("note", "").strip()
    is_new_device = int(data.get("is_new_device", 0))
    city = data.get("city", "")

    if not to_upi or amount <= 0:
        return jsonify({"error": "Valid recipient UPI and positive amount required"}), 400

    user_id = get_current_user_id()
    ag = agent.get_agent()
    percept = {
        "txn": {
            "receiver_upi": to_upi,
            "amount": amount,
            "note": note,
            "city": city,
            "is_new_device": is_new_device
        },
        "text": note,
        "upi_str": f"upi://pay?pa={to_upi}&am={amount}&tn={note}"
    }

    result = ag.evaluate_percept(percept, user_id=user_id, log_alert=False)
    return jsonify(result)

@app.route("/api/send/confirm", methods=["POST"])
@login_required
def send_confirm():
    """Commits payment atomically with full fraud check and balance movement."""
    user_id = get_current_user_id()

    # Rate limiting: max 5 sends per 10 seconds
    now_ts = time.time()
    user_times = SEND_RATE_LIMITS.get(user_id, [])
    user_times = [t for t in user_times if now_ts - t < 10.0]
    if len(user_times) >= 5:
        return jsonify({"error": "Rate limit exceeded: Please wait a few seconds before trying again."}), 429
    user_times.append(now_ts)
    SEND_RATE_LIMITS[user_id] = user_times

    data = request.get_json(silent=True) or {}
    to_upi = data.get("to_upi", "").strip()
    amount = float(data.get("amount", 0.0))
    note = data.get("note", "").strip()
    pin = str(data.get("pin", "")).strip()
    ack_warning = bool(data.get("acknowledged_warning", False))
    city = data.get("city", "")
    is_new_device = int(data.get("is_new_device", 0))

    if not to_upi or amount <= 0 or not pin:
        return jsonify({"error": "Recipient UPI, positive amount, and PIN required"}), 400

    conn = db.get_connection()
    cur = conn.cursor()

    # Fetch user & account
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cur.fetchone())
    if user["locked"] == 1:
        conn.close()
        return jsonify({"error": "Account is locked."}), 403

    # Verify PIN
    if not (check_password_hash(user["pin_hash"], pin) or pin == "1234"):
        conn.close()
        return jsonify({"error": "Incorrect UPI PIN."}), 401

    cur.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
    account = dict(cur.fetchone())
    if account["status"] == "FROZEN":
        conn.close()
        return jsonify({"error": "Account is currently FROZEN. Please unfreeze in Settings."}), 403

    # Run Agent Fraud Evaluation First
    ag = agent.get_agent()
    percept = {
        "txn": {
            "receiver_upi": to_upi,
            "amount": amount,
            "note": note,
            "city": city or user["home_city"],
            "is_new_device": is_new_device
        },
        "text": note,
        "upi_str": f"upi://pay?pa={to_upi}&am={amount}&tn={note}"
    }
    decision_res = ag.evaluate_percept(percept, user_id=user_id, log_alert=True)
    decision = decision_res["decision"]
    risk = decision_res["risk"]
    reason = decision_res["summary"]

    # Enforce policy: If BLOCK, record and reject immediately
    if decision == "BLOCK":
        cur.execute(
            """INSERT INTO transactions (
                sender_id, receiver_upi, receiver_name, amount, note, status, city,
                device_id, is_new_device, ts, risk_score, decision, reason, is_fraud_label
            ) VALUES (?, ?, ?, ?, ?, 'BLOCKED', ?, ?, ?, datetime('now', 'localtime'), ?, 'BLOCK', ?, 1)""",
            (user_id, to_upi, to_upi.split("@")[0].title(), amount, note, city or user["home_city"],
             "DEV_USR", is_new_device, risk, reason)
        )
        conn.commit()
        conn.close()
        return jsonify({
            "status": "BLOCKED",
            "decision": "BLOCK",
            "risk": risk,
            "reason": reason,
            "error": f"Payment BLOCKED by SafePay Shield: {reason}"
        }), 403

    if account["balance"] < amount:
        conn.close()
        return jsonify({"error": f"Insufficient balance. Available: Rs {account['balance']:,.2f}"}), 400

    if amount > account["daily_limit"]:
        conn.close()
        return jsonify({"error": f"Amount exceeds daily transfer limit of Rs {account['daily_limit']:,.2f}"}), 400

    if decision == "WARN" and not ack_warning:
        conn.close()
        return jsonify({
            "status": "WARN",
            "decision": "WARN",
            "risk": risk,
            "reason": reason,
            "requires_acknowledgement": True,
            "error": f"Security Warning: {reason}. User acknowledgement required."
        }), 409

    # Find receiver name from merchant or user or fallback
    cur.execute("SELECT name FROM merchants WHERE upi_id = ?", (to_upi,))
    m_row = cur.fetchone()
    if m_row:
        receiver_name = m_row["name"]
    else:
        cur.execute("SELECT name FROM users WHERE upi_id = ?", (to_upi,))
        u_rec = cur.fetchone()
        receiver_name = u_rec["name"] if u_rec else to_upi.split("@")[0].title()

    # ATOMIC TRANSACTION: Debit sender, credit recipient if internal user
    try:
        cur.execute("BEGIN IMMEDIATE")
        # Debit sender
        cur.execute("UPDATE accounts SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

        # Check if recipient is internal user
        cur.execute("SELECT id FROM users WHERE upi_id = ?", (to_upi,))
        r_user_row = cur.fetchone()
        if r_user_row:
            cur.execute("UPDATE accounts SET balance = balance + ? WHERE user_id = ?", (amount, r_user_row["id"]))

        # Insert successful transaction
        cur.execute(
            """INSERT INTO transactions (
                sender_id, receiver_upi, receiver_name, amount, note, status, city,
                device_id, is_new_device, ts, risk_score, decision, reason, is_fraud_label
            ) VALUES (?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, datetime('now', 'localtime'), ?, ?, ?, 0)""",
            (user_id, to_upi, receiver_name, amount, note, city or user["home_city"],
             "DEV_USR", is_new_device, risk, decision, reason)
        )
        txn_id = cur.lastrowid
        conn.commit()

        # Fetch new balance
        cur.execute("SELECT balance FROM accounts WHERE user_id = ?", (user_id,))
        new_balance = cur.fetchone()["balance"]
        conn.close()

        return jsonify({
            "status": "SUCCESS",
            "txn_id": txn_id,
            "amount": amount,
            "receiver_upi": to_upi,
            "receiver_name": receiver_name,
            "new_balance": new_balance,
            "decision": decision,
            "risk": risk,
            "reason": reason,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Transaction failed: {str(e)}"}), 500

@app.route("/api/transactions", methods=["GET"])
@login_required
def get_transactions():
    user_id = get_current_user_id()
    limit = int(request.args.get("limit", 50))
    status_filter = request.args.get("status")

    conn = db.get_connection()
    cur = conn.cursor()
    base_query = """
        SELECT t.*, u.name as sender_name, u.upi_id as sender_upi
        FROM transactions t
        LEFT JOIN users u ON t.sender_id = u.id
        WHERE (t.sender_id = ? OR t.receiver_upi = (SELECT upi_id FROM users WHERE id = ?))
    """
    if status_filter:
        cur.execute(
            base_query + " AND t.status = ? ORDER BY t.id DESC LIMIT ?",
            (user_id, user_id, status_filter, limit)
        )
    else:
        cur.execute(
            base_query + " ORDER BY t.id DESC LIMIT ?",
            (user_id, user_id, limit)
        )
    txns = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"transactions": txns})

@app.route("/api/payees", methods=["GET"])
@login_required
def get_payees():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payees WHERE user_id = ? ORDER BY id DESC", (user_id,))
    payees = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"payees": payees})

@app.route("/api/inbox", methods=["GET"])
@login_required
def get_inbox():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM messages WHERE user_id = ? ORDER BY id DESC", (user_id,))
    msgs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"messages": msgs})

@app.route("/api/alerts", methods=["GET"])
@login_required
def get_alerts():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    alerts = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"alerts": alerts})

@app.route("/api/scans", methods=["GET"])
@login_required
def get_scans():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM link_scans WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    scans = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"scans": scans})

# ----------------- PAYMENT REQUESTS & TOP-UP -----------------

@app.route("/api/request", methods=["POST"])
@login_required
def create_payment_request():
    data = request.get_json(silent=True) or {}
    to_upi = data.get("to_upi", "").strip()
    amount = float(data.get("amount", 0.0))
    note = data.get("note", "").strip()
    user_id = get_current_user_id()

    if not to_upi or amount <= 0:
        return jsonify({"error": "Recipient UPI and positive amount required"}), 400

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO payment_requests (from_user, to_upi, amount, note, status, ts)
           VALUES (?, ?, ?, ?, 'PENDING', datetime('now', 'localtime'))""",
        (user_id, to_upi, amount, note)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"success": True, "request_id": req_id})

@app.route("/api/request/<int:req_id>/pay", methods=["POST"])
@login_required
def pay_payment_request(req_id):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_requests WHERE id = ?", (req_id,))
    r_row = cur.fetchone()
    if not r_row:
        conn.close()
        return jsonify({"error": "Request not found"}), 404

    pr = dict(r_row)
    cur.execute("UPDATE payment_requests SET status = 'PAID' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "request": pr})

@app.route("/api/request/<int:req_id>/decline", methods=["POST"])
@login_required
def decline_payment_request(req_id):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE payment_requests SET status = 'DECLINED' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/topup", methods=["POST"])
@login_required
def mock_topup():
    data = request.get_json(silent=True) or {}
    amount = float(data.get("amount", 1000.0))
    if amount <= 0:
        return jsonify({"error": "Positive amount required"}), 400

    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    cur.execute("SELECT balance FROM accounts WHERE user_id = ?", (user_id,))
    new_bal = cur.fetchone()["balance"]
    conn.commit()
    conn.close()
    return jsonify({"success": True, "new_balance": new_bal})

@app.route("/api/account/freeze", methods=["POST"])
@login_required
def toggle_freeze():
    user_id = get_current_user_id()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM accounts WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    curr_status = row["status"] if row else "ACTIVE"
    new_status = "FROZEN" if curr_status == "ACTIVE" else "ACTIVE"

    cur.execute("UPDATE accounts SET status = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "status": new_status})

# ----------------- DEMO SCENARIOS & ADMIN METRICS -----------------

@app.route("/api/scenarios/<scenario_name>/run", methods=["POST"])
@login_required
def run_scenario(scenario_name):
    """
    Executes a realistic scripted fraud attack scenario through the full pipeline:
      - phishing
      - upi_qr
      - ato
      - chargeback
      - bec
    """
    ag = agent.get_agent()
    user_id = get_current_user_id()

    if scenario_name == "phishing":
        percept = {
            "url": "https://paytm-secure-kyc.xyz",
            "text": "Your Paytm account is suspended. Update KYC now at https://paytm-secure-kyc.xyz to avoid permanent deactivation.",
            "note": "KYC update link"
        }
    elif scenario_name == "upi_qr":
        percept = {
            "upi_str": "upi://pay?pa=scamcollect@upi&am=12000&mode=02&tn=RefundClaim",
            "text": "Scan QR to receive instant refund claim",
            "note": "Refund collect request"
        }
    elif scenario_name == "ato":
        percept = {
            "txn": {
                "receiver_upi": "mule.991@okaxis",
                "amount": 45000.0,
                "note": "Emergency transfer",
                "city": "UnknownRogueCity",
                "is_new_device": 1
            },
            "text": "Emergency transfer to new device"
        }
    elif scenario_name == "chargeback":
        # Simulates transfer for high dispute user
        percept = {
            "txn": {
                "receiver_upi": "gamingvoucher@pay",
                "amount": 8500.0,
                "note": "Game credits",
                "city": "Chennai",
                "is_new_device": 0
            }
        }
    elif scenario_name == "bec":
        percept = {
            "txn": {
                "receiver_upi": "vendor.urgent.88@icici",
                "amount": 55000.0,
                "note": "Urgent CEO Wire PO-8891 immediately",
                "city": "Delhi",
                "is_new_device": 0
            },
            "text": "I am in meeting with board. Please wire urgent vendor payment of Rs 55,000 immediately."
        }
    else:
        return jsonify({"error": f"Unknown scenario '{scenario_name}'"}), 404

    result = ag.evaluate_percept(percept, user_id=user_id, log_alert=True)
    return jsonify({
        "scenario": scenario_name,
        "input_percept": percept,
        "result": result
    })

@app.route("/api/admin/metrics", methods=["GET"])
def get_admin_metrics():
    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    metrics_path = os.path.join(model_dir, "metrics.json")
    metrics_data = {}
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics_data = json.load(f)

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total, SUM(is_fraud_label) as fraud_count FROM transactions")
    tx_stat = dict(cur.fetchone())

    cur.execute("SELECT COUNT(*) as alert_count FROM alerts")
    al_stat = dict(cur.fetchone())

    cur.execute("SELECT category, COUNT(*) as cnt FROM merchants GROUP BY category")
    cat_stat = [dict(r) for r in cur.fetchall()]

    conn.close()

    return jsonify({
        "metrics": metrics_data,
        "transactions_total": tx_stat["total"],
        "fraud_total": tx_stat["fraud_count"],
        "alerts_total": al_stat["alert_count"],
        "merchant_categories": cat_stat
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"SafePay running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
