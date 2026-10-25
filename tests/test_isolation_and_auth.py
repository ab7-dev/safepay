import json
import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app import app
from core import db, seed

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed.seed_all(force=True)

@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()

def test_unauthenticated_access_returns_401(client):
    """Confirm every protected endpoint returns 401 when no session is present."""
    routes_to_test = [
        ("GET", "/api/me"),
        ("GET", "/api/transactions"),
        ("GET", "/api/payees"),
        ("GET", "/api/inbox"),
        ("GET", "/api/alerts"),
        ("GET", "/api/scans"),
        ("POST", "/api/send/preview"),
        ("POST", "/api/send/confirm"),
        ("POST", "/api/topup"),
        ("POST", "/api/account/freeze"),
        ("POST", "/api/scenarios/phishing/run")
    ]
    for method, path in routes_to_test:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json={})
        assert res.status_code == 401, f"{path} did not return 401, got {res.status_code}"
        data = res.get_json()
        assert "Session expired" in data.get("error", "")

def test_login_and_wrong_pin_lockout(client):
    """Test login with wrong PIN, remaining attempts, and lockout after 3 fails."""
    # Attempt 1: wrong PIN
    res1 = client.post("/api/login", json={"identifier": "+919876543210", "pin": "9999"})
    assert res1.status_code == 401
    assert "2 attempts remaining" in res1.get_json()["error"]

    # Attempt 2: wrong PIN
    res2 = client.post("/api/login", json={"identifier": "+919876543210", "pin": "8888"})
    assert res2.status_code == 401
    assert "1 attempt remaining" in res2.get_json()["error"]

    # Attempt 3: wrong PIN -> Lockout
    res3 = client.post("/api/login", json={"identifier": "+919876543210", "pin": "7777"})
    assert res3.status_code == 403
    assert res3.get_json().get("locked") is True

    # Try login while locked
    res_locked = client.post("/api/login", json={"identifier": "+919876543210", "pin": "1234"})
    assert res_locked.status_code == 403

    # Unlock via mock unlock endpoint
    res_unlock = client.post("/api/unlock", json={"identifier": "+919876543210"})
    assert res_unlock.status_code == 200
    assert res_unlock.get_json()["success"] is True

    # Now login succeeds with correct PIN
    res_login = client.post("/api/login", json={"identifier": "+919876543210", "pin": "1234"})
    assert res_login.status_code == 200
    assert res_login.get_json()["user"]["name"] == "Aarav Sharma"

def test_user_data_isolation_and_transfer(client):
    """
    Test user isolation:
    - User A (Aarav Sharma, id=1, Delhi) makes payment to User B (Ananya Iyer, id=2, Chennai).
    - Verify User A balance drops and transaction shows as 'Payment Sent'.
    - Log in as User B:
      - Confirm User B sees User A's payment as 'Received' (+).
      - Confirm User B's balance increased by the payment amount.
      - Confirm User B does NOT see User A's transactions to other people.
    """
    # 1. Login as User A
    client.post("/api/logout")
    res_a = client.post("/api/login", json={"identifier": "+919876543210", "pin": "1234"})
    assert res_a.status_code == 200

    me_a_init = client.get("/api/me").get_json()
    bal_a_init = me_a_init["account"]["balance"]

    # Check User B initial balance directly in DB
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT balance FROM accounts WHERE user_id = 2")
    bal_b_init = c.fetchone()["balance"]
    conn.close()

    # 2. User A transfers Rs 500 to User B ('ananya@okaxis')
    transfer_amt = 500.0
    send_res = client.post("/api/send/confirm", json={
        "to_upi": "ananya@okaxis",
        "amount": transfer_amt,
        "note": "Lunch share",
        "pin": "1234",
        "acknowledged_warning": False
    })
    assert send_res.status_code == 200, f"Transfer failed: {send_res.data}"
    data_sent = send_res.get_json()
    assert data_sent["status"] == "SUCCESS"
    assert data_sent["new_balance"] == pytest.approx(bal_a_init - transfer_amt)

    # User A transactions
    tx_a = client.get("/api/transactions").get_json()["transactions"]
    latest_a = tx_a[0]
    assert latest_a["receiver_upi"] == "ananya@okaxis"
    assert latest_a["amount"] == transfer_amt

    # 3. Logout User A and Login as User B
    client.post("/api/logout")
    res_b = client.post("/api/login", json={"identifier": "+919811223344", "pin": "1234"})
    assert res_b.status_code == 200

    me_b = client.get("/api/me").get_json()
    bal_b_new = me_b["account"]["balance"]
    assert bal_b_new == pytest.approx(bal_b_init + transfer_amt)

    # User B transactions: latest should be received from Aarav
    tx_b = client.get("/api/transactions").get_json()["transactions"]
    latest_b = tx_b[0]
    assert latest_b["receiver_upi"] == "ananya@okaxis"
    assert latest_b["amount"] == transfer_amt
    assert latest_b["sender_id"] == 1
    assert latest_b["sender_name"] == "Aarav Sharma"

    # User B should NOT see User A's third-party merchant transactions
    for t in tx_b:
        is_party = (t["sender_id"] == 2) or (t["receiver_upi"] == "ananya@okaxis")
        assert is_party, f"User B saw unrelated transaction: {t}"

def test_sign_up_flow(client):
    """Test user registration creating unique phone, Rs 5,000 balance, and empty state."""
    client.post("/api/logout")

    unique_phone = "+919998887711"
    reg_res = client.post("/api/register", json={
        "name": "Kavya Patel",
        "phone": unique_phone,
        "pin": "5678",
        "home_city": "Ahmedabad"
    })
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.data}"
    reg_data = reg_res.get_json()
    assert reg_data["success"] is True
    assert reg_data["user"]["upi_id"].startswith("kavyapatel")
    assert reg_data["user"]["home_city"] == "Ahmedabad"

    # Verify session is established
    me_res = client.get("/api/me")
    assert me_res.status_code == 200
    me_data = me_res.get_json()
    assert me_data["user"]["name"] == "Kavya Patel"
    assert me_data["account"]["balance"] == 5000.0

    # Verify clean history
    tx_res = client.get("/api/transactions")
    assert len(tx_res.get_json()["transactions"]) == 0

    # Duplicate phone registration must fail
    dup_res = client.post("/api/register", json={
        "name": "Another Patel",
        "phone": unique_phone,
        "pin": "1234",
        "home_city": "Surat"
    })
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.get_json()["error"]
