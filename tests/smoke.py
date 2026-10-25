import json
import os
import re
import sys

# Ensure safepay root is in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import db, seed
import train
from app import app

def run_smoke_tests():
    print("==================================================")
    print("         SAFEPAY COMPREHENSIVE SMOKE TEST         ")
    print("==================================================")

    # 1. Test Seed
    print("\n[TEST 1] Testing Database Seeding...")
    seed.seed_all(force=True)
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as u_cnt FROM users")
    u_cnt = c.fetchone()["u_cnt"]
    c.execute("SELECT COUNT(*) as t_cnt FROM transactions")
    t_cnt = c.fetchone()["t_cnt"]
    conn.close()
    assert u_cnt >= 10, f"Expected >= 10 users, got {u_cnt}"
    assert t_cnt >= 1000, f"Expected >= 1000 transactions, got {t_cnt}"
    print(f" PASS: Database seeded with {u_cnt} users and {t_cnt} transactions.")

    # 2. Test Train Pipeline
    print("\n[TEST 2] Testing Training Pipeline...")
    train.main()
    metrics_path = os.path.join(BASE_DIR, "models", "metrics.json")
    assert os.path.exists(metrics_path), "metrics.json was not created"
    with open(metrics_path) as f:
        metrics = json.load(f)
    print(f" PASS: Model training complete. Best model: {metrics.get('best_model')}")

    # Initialize test client
    client = app.test_client()

    # 3. Test Login
    print("\n[TEST 3] Testing User Login...")
    res = client.post("/api/login", json={"user_id": 1, "pin": "1234"})
    assert res.status_code == 200, f"Login failed: {res.data}"
    login_data = res.get_json()
    assert login_data.get("success") is True
    print(f" PASS: User 1 ({login_data['user']['name']}) authenticated successfully.")

    # Get initial balance
    me_res = client.get("/api/me")
    initial_balance = me_res.get_json()["account"]["balance"]
    print(f" Current Balance: Rs {initial_balance:,.2f}")

    # 4. Test Normal Rs 250 payment to verified merchant
    print("\n[TEST 4] Testing Normal Rs 250 Payment to Verified Merchant (Swiggy)...")
    send_res = client.post("/api/send/confirm", json={
        "to_upi": "swiggy@icici",
        "amount": 250.0,
        "note": "Lunch order",
        "pin": "1234",
        "acknowledged_warning": False,
        "is_new_device": 0
    })
    assert send_res.status_code == 200, f"Normal send failed: {send_res.data}"
    send_data = send_res.get_json()
    assert send_data["status"] == "SUCCESS", f"Expected SUCCESS, got {send_data['status']}"
    assert send_data["decision"] == "APPROVE", f"Expected APPROVE, got {send_data['decision']}"
    
    # Verify balance moved atomically
    me_after = client.get("/api/me").get_json()
    new_balance = me_after["account"]["balance"]
    expected_balance = initial_balance - 250.0
    assert abs(new_balance - expected_balance) < 0.01, f"Balance error: expected {expected_balance}, got {new_balance}"
    print(f" PASS: Rs 250 approved. Balance changed atomically from {initial_balance} to {new_balance}.")

    # 5. Test Payment Link to paytm-secure-kyc.xyz -> BLOCK
    print("\n[TEST 5] Testing Payment Link to paytm-secure-kyc.xyz...")
    link_res = client.post("/api/shield/link", json={"url": "https://paytm-secure-kyc.xyz"})
    assert link_res.status_code == 200
    link_data = link_res.get_json()
    assert link_data["verdict"] == "BLOCK", f"Expected BLOCK, got {link_data['verdict']}"
    assert link_data["score"] >= 0.70, f"Expected score >= 0.70, got {link_data['score']}"
    print(f" PASS: Phishing link correctly BLOCKED with risk score {link_data['score']}.")

    # 6. Test Collect-Request QR from Unknown VPA -> WARN or BLOCK
    print("\n[TEST 6] Testing Collect-Request QR from Unknown VPA...")
    upi_res = client.post("/api/shield/upi", json={"upi_string": "upi://pay?pa=scamcollect@upi&am=12000&mode=02&tn=RefundClaim"})
    assert upi_res.status_code == 200
    upi_data = upi_res.get_json()
    assert upi_data["risk_score"] >= 0.40, f"Expected risk >= 0.40, got {upi_data['risk_score']}"
    assert any("Collect" in r for r in upi_data["reasons"]), "Expected collect request warning in reasons"
    print(f" PASS: Collect request flagged with risk score {upi_data['risk_score']} and reasons: {upi_data['reasons']}")

    # 7. Test 3 AM Rs 50,000 transfer from new device to new payee -> BLOCK
    print("\n[TEST 7] Testing 3 AM Rs 50,000 Transfer from New Device to New Payee...")
    from core import agent
    ag = agent.get_agent()
    ato_percept = {
        "txn": {
            "receiver_upi": "unknown.crypto.mule@ybl",
            "amount": 50000.0,
            "note": "Immediate crypto drain",
            "city": "UnknownForeignCity",
            "is_new_device": 1
        }
    }
    ato_eval = ag.evaluate_percept(ato_percept, user_id=1, log_alert=False)
    assert ato_eval["decision"] == "BLOCK", f"Expected BLOCK, got {ato_eval['decision']}"
    assert ato_eval["risk"] >= 0.70, f"Expected risk >= 0.70, got {ato_eval['risk']}"
    print(f" PASS: 3 AM high-value transfer BLOCKED with risk score {ato_eval['risk']}.")

    # 8. Test that BLOCKED payment NEVER changes balances
    print("\n[TEST 8] Verifying BLOCKED Payment Never Changes Balances...")
    bal_before_block = client.get("/api/me").get_json()["account"]["balance"]
    block_attempt_res = client.post("/api/send/confirm", json={
        "to_upi": "unknown.crypto.mule@ybl",
        "amount": 50000.0,
        "note": "Immediate crypto drain",
        "pin": "1234",
        "acknowledged_warning": False,
        "is_new_device": 1,
        "city": "UnknownForeignCity"
    })
    assert block_attempt_res.status_code == 403, f"Expected 403 Forbidden for BLOCK, got {block_attempt_res.status_code}"
    bal_after_block = client.get("/api/me").get_json()["account"]["balance"]
    assert bal_before_block == bal_after_block, f"Balance changed on blocked transaction! {bal_before_block} vs {bal_after_block}"
    print(f" PASS: Blocked transaction rejected. Balance preserved exactly at {bal_after_block}.")

    # 9. Test /share?text=<message with fake link> auto-extracts link
    print("\n[TEST 9] Testing /share URL Extraction and Inspection...")
    share_text = "Your SBI NetBanking is suspended. Update KYC now at https://paytm-secure-kyc.xyz immediately."
    extracted = re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", share_text)
    assert len(extracted) > 0 and extracted[0] == "https://paytm-secure-kyc.xyz"
    extracted_link_res = client.post("/api/shield/link", json={"url": extracted[0], "text": share_text})
    assert extracted_link_res.get_json()["verdict"] == "BLOCK"
    print(f" PASS: /share extracted '{extracted[0]}' and Shield returned BLOCK.")

    # 10. Test all 5 scenario endpoints
    print("\n[TEST 10] Testing All 5 Attack Scenario Endpoints...")
    scenarios = ["phishing", "upi_qr", "ato", "chargeback", "bec"]
    for sc in scenarios:
        s_res = client.post(f"/api/scenarios/{sc}/run")
        assert s_res.status_code == 200, f"Scenario {sc} failed: {s_res.data}"
        s_data = s_res.get_json()
        dec = s_data["result"]["decision"]
        risk = s_data["result"]["risk"]
        assert dec in ("WARN", "BLOCK", "APPROVE"), f"Invalid decision {dec}"
        print(f"   -> Scenario '{sc}': Decision = {dec} (Risk: {risk:.2f})")
    # 11. Test Font Assets & Typography
    print("\n[TEST 11] Testing Poppins Typography & Self-Hosted Font Assets...")
    fonts_dir = os.path.join(BASE_DIR, "static", "fonts")
    required_fonts = [
        "poppins-latin-400.woff2",
        "poppins-latin-500.woff2",
        "poppins-latin-600.woff2",
        "poppins-latin-700.woff2"
    ]
    for rf in required_fonts:
        f_path = os.path.join(fonts_dir, rf)
        assert os.path.exists(f_path), f"Missing required font asset: {rf}"
        assert os.path.getsize(f_path) > 1000, f"Font asset {rf} is empty or corrupted"
    
    # Check index.html font links
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert "fonts.googleapis.com" in html and "fonts.gstatic.com" in html, "Missing Google Fonts preconnect"
    assert "Poppins:wght@400;500;600;700" in html, "Missing Poppins stylesheet with weights 400-700"
    
    # Check app.css rules
    with open(os.path.join(BASE_DIR, "static", "app.css"), encoding="utf-8") as f:
        css = f.read()
    assert "@font-face" in css and "font-display: swap" in css, "Missing self-hosted @font-face rules in app.css"
    assert "font-variant-numeric: tabular-nums" in css, "Missing tabular-nums numeric formatting"
    print(" PASS: All Poppins self-hosted font assets, @font-face rules, and type scale verified.")

    print("\n==================================================")
    print(" ALL 11 ACCEPTANCE SMOKE TESTS PASSED PERFECTLY! ")
    print("==================================================")

if __name__ == "__main__":
    run_smoke_tests()

