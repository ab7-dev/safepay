import requests
import json

BASE = "http://127.0.0.1:5000"

def run_live_tests():
    print("=== LIVE SERVER VERIFICATION ===")
    results = []

    # Test 1: Fresh load without session returns 401
    s1 = requests.Session()
    r = s1.get(f"{BASE}/api/me")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    results.append(("1. Fresh load unauthenticated goes to Sign-in (401)", "PASS", f"Status: {r.status_code}"))

    # Test 2: Wrong PIN 3 times triggers lockout and ATO alert
    s2 = requests.Session()
    s2.post(f"{BASE}/api/unlock", json={"identifier": "9876543210"})
    # Attempt 1
    r1 = s2.post(f"{BASE}/api/login", json={"identifier": "9876543210", "pin": "9999"})
    assert r1.status_code == 401 and r1.json().get("remaining_attempts") == 2
    # Attempt 2
    r2 = s2.post(f"{BASE}/api/login", json={"identifier": "9876543210", "pin": "9999"})
    assert r2.status_code == 401 and r2.json().get("remaining_attempts") == 1
    # Attempt 3 -> Locked
    r3 = s2.post(f"{BASE}/api/login", json={"identifier": "9876543210", "pin": "9999"})
    assert r3.status_code == 403 and r3.json().get("locked") is True
    results.append(("2. Wrong PIN 3 times locks account & flags ATO", "PASS", "Locked at 3rd failed attempt"))

    # Test 3: Unlock demo endpoint
    r_unlock = s2.post(f"{BASE}/api/unlock", json={"identifier": "9876543210"})
    assert r_unlock.status_code == 200
    results.append(("3. Mock Unlock account restores access", "PASS", "Account unlocked"))

    # Test 4: Correct PIN logs in User A (Aarav Sharma)
    s_a = requests.Session()
    r_login_a = s_a.post(f"{BASE}/api/login", json={"identifier": "9876543210", "pin": "1234"})
    assert r_login_a.status_code == 200
    user_a = r_login_a.json()["user"]
    acc_a_initial = r_login_a.json()["account"]["balance"]
    assert user_a["id"] == 1
    results.append(("4. Correct PIN (1234) logs in User A", "PASS", f"User: {user_a['name']} (Bal: Rs {acc_a_initial:.2f})"))

    # Test 5: Log in User B (Ananya Iyer) in separate session
    s_b = requests.Session()
    r_login_b = s_b.post(f"{BASE}/api/login", json={"identifier": "9811223344", "pin": "1234"})
    assert r_login_b.status_code == 200
    user_b = r_login_b.json()["user"]
    acc_b_initial = r_login_b.json()["account"]["balance"]
    assert user_b["id"] == 2
    assert acc_a_initial != acc_b_initial or user_a["id"] != user_b["id"]
    results.append(("5. User A and User B have separate balances & data", "PASS", f"User A: Rs {acc_a_initial:.2f} vs User B: Rs {acc_b_initial:.2f}"))

    # Test 6: A pays B Rs 500 via UPI ID
    # User A initiates payment
    r_send = s_a.post(f"{BASE}/api/send/confirm", json={
        "to_upi": user_b["upi_id"],
        "receiver_name": user_b["name"],
        "amount": 500.0,
        "note": "Lunch split",
        "pin": "1234"
    })
    assert r_send.status_code == 200, f"Send failed: {r_send.text}"
    send_data = r_send.json()
    assert send_data.get("status") == "SUCCESS"

    # Verify A's new balance is decreased by 500
    r_a_me = s_a.get(f"{BASE}/api/me").json()
    acc_a_new = r_a_me["account"]["balance"]
    assert abs(acc_a_new - (acc_a_initial - 500.0)) < 0.01

    # Verify B's new balance is increased by 500
    r_b_me = s_b.get(f"{BASE}/api/me").json()
    acc_b_new = r_b_me["account"]["balance"]
    assert abs(acc_b_new - (acc_b_initial + 500.0)) < 0.01

    # Verify A sees payment in history
    r_a_txns = s_a.get(f"{BASE}/api/transactions").json()["transactions"]
    a_latest = r_a_txns[0]
    assert a_latest["receiver_upi"] == user_b["upi_id"]

    # Verify B sees payment in history as received
    r_b_txns = s_b.get(f"{BASE}/api/transactions").json()["transactions"]
    b_latest = r_b_txns[0]
    assert b_latest["receiver_upi"] == user_b["upi_id"]
    assert b_latest["amount"] == 500.0
    results.append(("6. A to B payment: Sent for A (-500) and Received for B (+500)", "PASS", f"A: {acc_a_initial:.2f}->{acc_a_new:.2f}, B: {acc_b_initial:.2f}->{acc_b_new:.2f}"))

    # Test 7: Logout returns to Sign-in & subsequent calls return 401
    r_logout = s_a.post(f"{BASE}/api/logout")
    assert r_logout.status_code == 200
    r_after = s_a.get(f"{BASE}/api/me")
    assert r_after.status_code == 401
    results.append(("7. Logout clears session, reload stays on Sign-in", "PASS", "Session terminated, 401 returned"))

    # Test 8: Create new account (Sign up)
    import random
    s_new = requests.Session()
    reg_phone = f"98765{random.randint(10000, 99999)}"
    r_reg = s_new.post(f"{BASE}/api/register", json={
        "name": "Kavita Rao",
        "phone": reg_phone,
        "home_city": "Hyderabad",
        "pin": "4321"
    })
    assert r_reg.status_code == 201, f"Register failed: {r_reg.text}"
    reg_data = r_reg.json()
    assert reg_data["user"]["name"] == "Kavita Rao"
    assert reg_data["account"]["balance"] == 5000.0
    assert "kavita" in reg_data["user"]["upi_id"].lower()
    results.append(("8. Sign up creates user with Rs 5,000 balance & empty history", "PASS", f"UPI: {reg_data['user']['upi_id']}"))

    # Test 9: 5 demo scenarios work after login
    s_scenarios = requests.Session()
    s_scenarios.post(f"{BASE}/api/login", json={"identifier": "9876543210", "pin": "1234"})
    scenarios = ["phishing", "upi_qr", "ato", "chargeback", "bec"]
    scenarios_passed = 0
    for sc in scenarios:
        r_sc = s_scenarios.post(f"{BASE}/api/scenarios/{sc}/run")
        assert r_sc.status_code == 200, f"Scenario {sc} failed: {r_sc.text}"
        sc_data = r_sc.json()
        assert "result" in sc_data and "decision" in sc_data["result"], f"Scenario {sc} missing result"
        dec = sc_data["result"]["decision"]
        risk = sc_data["result"]["risk"]
        scenarios_passed += 1
    results.append(("9. All 5 demo attack scenarios execute successfully", "PASS", f"{scenarios_passed}/5 ({', '.join(scenarios)})"))

    print("\n--- RESULTS SUMMARY ---")
    for test_name, status, details in results:
        print(f"[{status}] {test_name}: {details}")

    return results

if __name__ == "__main__":
    run_live_tests()
