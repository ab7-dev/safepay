import os
import sqlite3

def get_data_dir():
    data_dir = os.environ.get("DATA_DIR")
    if not data_dir:
        # Default to ./data relative to safepay root directory
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_db_path():
    return os.path.join(get_data_dir(), "safepay.db")

def get_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        upi_id TEXT UNIQUE NOT NULL,
        pin_hash TEXT NOT NULL,
        failed_pins INTEGER DEFAULT 0,
        locked INTEGER DEFAULT 0,
        home_city TEXT NOT NULL,
        avatar_color TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        acct_no TEXT UNIQUE NOT NULL,
        balance REAL NOT NULL,
        daily_limit REAL NOT NULL,
        status TEXT DEFAULT 'ACTIVE',
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS payees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        upi_id TEXT NOT NULL,
        added_at TEXT NOT NULL,
        is_verified INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_upi TEXT NOT NULL,
        receiver_name TEXT NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        status TEXT NOT NULL,
        city TEXT NOT NULL,
        device_id TEXT NOT NULL,
        is_new_device INTEGER DEFAULT 0,
        ts TEXT NOT NULL,
        risk_score REAL DEFAULT 0.0,
        decision TEXT DEFAULT 'APPROVE',
        reason TEXT,
        is_fraud_label INTEGER DEFAULT 0,
        FOREIGN KEY (sender_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER NOT NULL,
        to_upi TEXT NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        status TEXT DEFAULT 'PENDING',
        ts TEXT NOT NULL,
        FOREIGN KEY (from_user) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS merchants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        upi_id TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        city TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        verified INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS blocklist (
        domain TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        category TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS link_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        url TEXT NOT NULL,
        source TEXT NOT NULL,
        verdict TEXT NOT NULL,
        score REAL NOT NULL,
        reasons TEXT NOT NULL,
        ts TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        kind TEXT NOT NULL,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        ts TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        fraud_type TEXT NOT NULL,
        condition_text TEXT NOT NULL,
        weight REAL NOT NULL,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS disputes (
        user_id INTEGER PRIMARY KEY,
        purchases INTEGER NOT NULL,
        disputes INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT NOT NULL,
        sender TEXT NOT NULL,
        subject TEXT,
        body TEXT NOT NULL,
        link TEXT,
        is_scam INTEGER NOT NULL,
        ts TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized at:", get_db_path())
