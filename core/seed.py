import random
from datetime import datetime, timedelta
import numpy as np
from werkzeug.security import generate_password_hash
from core import db

def is_db_empty():
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        row = cur.fetchone()
        return (row["cnt"] == 0) if row else True
    except Exception:
        return True
    finally:
        conn.close()

def seed_all(force=False):
    db.init_db()
    if not force and not is_db_empty():
        return

    random.seed(42)
    conn = db.get_connection()
    cur = conn.cursor()

    # Clear existing
    for tbl in ["messages", "disputes", "rules", "alerts", "link_scans", "blocklist",
                "payment_requests", "transactions", "payees", "accounts", "users", "merchants"]:
        cur.execute(f"DELETE FROM {tbl}")

    # 1. Blocklist: 25 fake domains & 25 safe reference domains
    fake_domains = [
        ("paytm-secure-kyc.xyz", "PhishTank", "KYC Phishing"),
        ("sbi-update-login.in", "Cert-In", "Bank Phishing"),
        ("gpay-reward.top", "ThreatIntel", "Reward Scam"),
        ("hdfc-netbanking-verify.click", "Cert-In", "Credential Harvesting"),
        ("npci-refund.cc", "NPCI Advisory", "UPI Scam"),
        ("amazon-prize-claim.top", "BrandShield", "Lottery Scam"),
        ("icici-alert-notice.xyz", "PhishTank", "Bank Phishing"),
        ("axis-kyc-portal.online", "ThreatIntel", "KYC Scam"),
        ("phonepe-cashback-instant.site", "BrandShield", "Cashback Fraud"),
        ("airtel-sim-block-kyc.info", "Telecom Watch", "Sim Swap"),
        ("jio-free-5g-upgrade.top", "Telecom Watch", "Phishing"),
        ("incometax-instant-refund.cc", "Govt Advisory", "Tax Refund Phishing"),
        ("electricity-bill-paynow.link", "State Grid", "Utility Scam"),
        ("pan-aadhaar-link-urgent.xyz", "Cert-In", "Identity Theft"),
        ("speedpost-customs-parcel.top", "IndiaPost Alert", "Parcel Scam"),
        ("bit.ly/sbi-urgent-alert", "Shortener Blacklist", "Malicious Shortener"),
        ("tinyurl.com/gpay-cashback99", "Shortener Blacklist", "Malicious Shortener"),
        ("cutt.ly/instant-loan-approval", "Shortener Blacklist", "Loan Fraud"),
        ("192.168.1.105", "IP Blacklist", "Direct IP Host"),
        ("45.134.20.12", "IP Blacklist", "Rogue IP Server"),
        ("xn--sbi-8ka.com", "IDN Watch", "Punycode Lookalike"),
        ("paytm-instant-loan.biz", "BrandShield", "Loan Scam"),
        ("flipkart-mega-sale-win.club", "E-commerce Watch", "Fake Shop"),
        ("fastrack-crypto-airdrop.xyz", "Crypto Watch", "Wallet Drainer"),
        ("olx-buyer-protection-verify.top", "Marketplace Alert", "QR Payment Scam")
    ]
    for dom, src, cat in fake_domains:
        cur.execute("INSERT OR REPLACE INTO blocklist (domain, source, category) VALUES (?, ?, ?)", (dom, src, cat))

    safe_domains = [
        "google.com", "paytm.com", "sbi.co.in", "hdfcbank.com", "icicibank.com",
        "axisbank.com", "amazon.in", "flipkart.com", "irctc.co.in", "npci.org.in",
        "incometax.gov.in", "swiggy.com", "zomato.com", "phonepe.com", "bhimupi.org.in",
        "uidai.gov.in", "airtel.in", "jio.com", "myntra.com", "tataneu.com",
        "uber.com", "ola.in", "bigbasket.com", "makemytrip.com", "cleartrip.com"
    ]

    # 2. Users (10 personas across India)
    users_data = [
        # id, name, phone, upi_id, pin, city, persona, color
        (1, "Aarav Sharma", "+919876543210", "aarav@oksbi", "1234", "Delhi", "student", "#6366F1"),
        (2, "Ananya Iyer", "+919811223344", "ananya@okaxis", "1234", "Chennai", "student", "#EC4899"),
        (3, "Rohan Verma", "+919822334455", "rohan@okhdfc", "1234", "Coimbatore", "student", "#14B8A6"),
        (4, "Vikram Malhotra", "+919833445566", "vikram@okicici", "1234", "Mumbai", "salaried", "#F59E0B"),
        (5, "Pooja Hegde", "+919844556677", "pooja@oksbi", "1234", "Bengaluru", "salaried", "#8B5CF6"),
        (6, "Suresh Kumar", "+919855667788", "suresh@okhdfc", "1234", "Chennai", "salaried", "#06B6D4"),
        (7, "Deepika Sen", "+919866778899", "deepika@okaxis", "1234", "Kolkata", "salaried", "#10B981"),
        (8, "Rajesh Singhania", "+919877889900", "rajesh@okicici", "1234", "Mumbai", "business", "#3B82F6"),
        (9, "Harish Reddy", "+919888990011", "harish@oksbi", "1234", "Hyderabad", "business", "#F97316"),
        (10, "Murugan Chettiar", "+919899001122", "murugan@okhdfc", "1234", "Coimbatore", "business", "#84CC16"),
    ]

    for u in users_data:
        cur.execute(
            """INSERT INTO users (id, name, phone, upi_id, pin_hash, failed_pins, locked, home_city, avatar_color)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (u[0], u[1], u[2], u[3], generate_password_hash(u[4]), 0, 0, u[5], u[7])
        )

    # Accounts
    account_balances = [
        (1, 1, "SB-10023489", 4500.0, 25000.0),
        (2, 2, "AX-20098412", 3200.0, 25000.0),
        (3, 3, "HD-30012948", 5800.0, 25000.0),
        (4, 4, "IC-40081239", 48500.0, 100000.0),
        (5, 5, "SB-50019283", 64000.0, 100000.0),
        (6, 6, "HD-60038192", 38200.0, 100000.0),
        (7, 7, "AX-70049182", 52100.0, 100000.0),
        (8, 8, "IC-80019284", 285000.0, 500000.0),
        (9, 9, "SB-90038291", 310000.0, 500000.0),
        (10, 10, "HD-10029384", 420000.0, 500000.0),
    ]
    for ac in account_balances:
        cur.execute(
            "INSERT INTO accounts (id, user_id, acct_no, balance, daily_limit, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
            ac
        )

    # Payees per user
    payees_seed = [
        (1, "Swiggy Food", "swiggy@icici", 1),
        (1, "College Canteen", "canteen@okaxis", 1),
        (1, "Ananya Iyer", "ananya@okaxis", 1),
        (4, "House Rent", "landlord@okhdfc", 1),
        (4, "Amazon India", "amazon@apl", 1),
        (4, "Vikram Office Colleague", "amit.verma@oksbi", 1),
        (8, "Steel Supplier", "venkat.alloys@okaxis", 1),
        (8, "Logistics Fleet", "speedcargolog@icici", 1)
    ]
    for p in payees_seed:
        cur.execute(
            "INSERT INTO payees (user_id, name, upi_id, added_at, is_verified) VALUES (?, ?, ?, ?, ?)",
            (p[0], p[1], p[2], "2026-06-01 10:00:00", p[3])
        )

    # 3. Verified Merchants (20 merchants)
    merchants_data = [
        (1, "Swiggy Food", "swiggy@icici", "Food & Dining", "Pan-India", "LOW", 1),
        (2, "Zomato Dine", "zomato@hdfc", "Food & Dining", "Pan-India", "LOW", 1),
        (3, "Amazon India", "amazon@apl", "Shopping", "Pan-India", "LOW", 1),
        (4, "Flipkart Supermart", "flipkart@axis", "Shopping", "Pan-India", "LOW", 1),
        (5, "IRCTC Indian Railways", "irctc@sbi", "Travel", "Pan-India", "LOW", 1),
        (6, "BigBazaar Hypermarket", "bigbazaar@hdfc", "Groceries", "Pan-India", "LOW", 1),
        (7, "Indian Oil Corporation", "indianoil@sbi", "Fuel", "Pan-India", "LOW", 1),
        (8, "Apollo Pharmacy", "apollo@icici", "Healthcare", "Pan-India", "LOW", 1),
        (9, "Uber Rides India", "uber@axis", "Transport", "Pan-India", "LOW", 1),
        (10, "Croma Megastore", "croma@hdfc", "Electronics", "Pan-India", "MEDIUM", 1),
        (11, "Tanishq Jewellers", "tanishq@axis", "Jewellery", "Pan-India", "MEDIUM", 1),
        (12, "MakeMyTrip Travel", "makemytrip@icici", "Travel", "Pan-India", "MEDIUM", 1),
        (13, "Reliance Digital", "reliancedigital@sbi", "Electronics", "Pan-India", "MEDIUM", 1),
        (14, "Malabar Gold & Diamonds", "malabargold@hdfc", "Jewellery", "Pan-India", "MEDIUM", 1),
        (15, "Nykaa Beauty & Fashion", "nykaa@icici", "Lifestyle", "Pan-India", "LOW", 1),
        (16, "CoinDCX Exchange", "coindcx@yesbank", "Cryptocurrency", "Online", "HIGH", 0),
        (17, "WazirX Token Desk", "wazirx@rbl", "Cryptocurrency", "Online", "HIGH", 0),
        (18, "BetFast Global Games", "betfast@offshore", "Gambling", "Foreign", "HIGH", 0),
        (19, "Offshore Poker Lounge", "offshoregaming@pay", "Gambling", "Foreign", "HIGH", 0),
        (20, "DarkCloud Instant Vouchers", "darkvouchers@crypt", "Digital Goods", "Foreign", "HIGH", 0)
    ]
    for m in merchants_data:
        cur.execute(
            """INSERT INTO merchants (id, name, upi_id, category, city, risk_level, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            m
        )

    # 4. Rules table (CO3 Knowledge Representation)
    rules_seed = [
        ("Phishing URL or Blocklisted Domain", "phishing", "domain_in_blocklist or suspicious_tld or ip_host", 0.40, 1),
        ("Urgent Coercion in Message Text", "phishing", "has_urgency_words and has_payment_link", 0.30, 1),
        ("Extreme Spend Spike (>5x Profile Avg)", "upi_qr", "amount > 5.0 * avg_spend", 0.35, 1),
        ("Unknown High-Risk Merchant VPA", "upi_qr", "merchant_risk == 'HIGH' and is_new_payee", 0.30, 1),
        ("Lookalike Brand VPA Mismatch", "upi_qr", "vpa_brand_lookalike and receiver_not_verified", 0.35, 1),
        ("UPI Collect Request Disguised as Pay", "upi_qr", "is_collect_request == 1", 0.40, 1),
        ("Account Takeover Velocity Spike", "ato", "is_new_device and city_mismatch and recent_failed_pins >= 2", 0.45, 1),
        ("High Dispute/Chargeback History", "chargeback", "dispute_ratio > 0.30", 0.30, 1),
        ("Business Email Compromise (BEC)", "bec", "is_first_time_payee and has_urgency_words and amount > 3.0 * avg_spend", 0.40, 1),
        ("Late Night High-Value Activity", "upi_qr", "hour >= 2 and hour <= 4 and amount > 2.5 * avg_spend", 0.25, 1)
    ]
    for r in rules_seed:
        cur.execute(
            "INSERT INTO rules (name, fraud_type, condition_text, weight, active) VALUES (?, ?, ?, ?, ?)",
            r
        )

    # 5. Disputes baseline
    for u in users_data:
        cur.execute("INSERT INTO disputes (user_id, purchases, disputes) VALUES (?, 100, 2)", (u[0],))
    # Add one high dispute user profile
    cur.execute("INSERT OR REPLACE INTO disputes (user_id, purchases, disputes) VALUES (3, 20, 8)")

    # 6. Inbox Messages (32 messages across SMS, WHATSAPP, EMAIL)
    messages_seed = [
        # Phishing / Scams
        ("SMS", "VK-SBIINB", "SBI Alert: KYC Expired", "Dear customer, your SBI NetBanking will be blocked today. Update Aadhaar KYC immediately at https://sbi-update-login.in to keep active.", "https://sbi-update-login.in", 1, "2026-08-01 09:15:00"),
        ("SMS", "VM-PAYTM", "Paytm Cash Reward", "Congratulations! You won Rs 4,999 cashback in GPay Lucky Draw. Claim instantly to bank: https://gpay-reward.top", "https://gpay-reward.top", 1, "2026-08-02 11:30:00"),
        ("WHATSAPP", "+919988776655", "Electricity Dept Urgent", "Aapka Bijli bill overdue hai Rs 1,420. Aaj raat 9:30 PM connection cut hoga. Turant bill pay karein link: https://electricity-bill-paynow.link", "https://electricity-bill-paynow.link", 1, "2026-08-03 14:20:00"),
        ("SMS", "BZ-HDFCBK", "HDFC Card Block Warning", "Urgent! Your HDFC Credit Card has been suspended due to pending PAN linking. Verify now: https://hdfc-netbanking-verify.click", "https://hdfc-netbanking-verify.click", 1, "2026-08-04 16:45:00"),
        ("WHATSAPP", "+919871234567", "Part-Time Job Offer", "Earn Rs 5000/day by liking YouTube videos! Just register and pay security deposit Rs 500 via upi://pay?pa=earnfast@paytm&am=500", "upi://pay?pa=earnfast@paytm&am=500", 1, "2026-08-05 10:00:00"),
        ("EMAIL", "ceo-office@company-corp.com", "Urgent: Wire Transfer Required", "I am in an emergency client meeting. Please process an urgent vendor invoice of Rs 48,000 to new account immediately. Do not call.", None, 1, "2026-08-06 15:30:00"),
        ("SMS", "AD-INPOST", "IndiaPost Delivery Failed", "Your parcel #IN88921 is held at customs warehouse due to unpaid Rs 35 address fee. Clear payment: https://speedpost-customs-parcel.top", "https://speedpost-customs-parcel.top", 1, "2026-08-07 18:10:00"),
        ("WHATSAPP", "+919123456789", "OLX Buyer QR Payment", "I have sent you the advance payment for your sofa. Scan this QR code or accept collect request to receive money in your bank.", "upi://pay?pa=scamcollect@upi&am=12000&mode=02", 1, "2026-08-08 12:40:00"),
        ("SMS", "AX-ITDEPT", "Income Tax Refund Notice", "Dear Taxpayer, Rs 24,850 refund approved for AY 2025-26. Confirm account details within 24 hours: https://incometax-instant-refund.cc", "https://incometax-instant-refund.cc", 1, "2026-08-09 13:00:00"),
        ("SMS", "JM-JIOINF", "Jio Free 5G SIM Upgrade", "Aapka 4G SIM kal band ho jayega. Free 5G activation ke liye link click karein: https://jio-free-5g-upgrade.top", "https://jio-free-5g-upgrade.top", 1, "2026-08-10 11:15:00"),
        ("SMS", "CP-AIRTEL", "Airtel E-SIM Blocked", "Dear Airtel user, your document verification failed. Call 9876543210 or visit https://airtel-sim-block-kyc.info to avoid disconnection.", "https://airtel-sim-block-kyc.info", 1, "2026-08-11 17:30:00"),
        ("EMAIL", "support@npci-refund.cc", "NPCI Failed UPI Refund", "We noticed a failed transaction of Rs 8,500. Enter your UPI PIN to claim auto-refund: https://npci-refund.cc", "https://npci-refund.cc", 1, "2026-08-12 10:20:00"),
        ("SMS", "DM-AMAZON", "Amazon Festive Lucky Draw", "You are selected for Amazon iPhone 15 lucky winner! Pay shipping Rs 199 to claim: https://amazon-prize-claim.top", "https://amazon-prize-claim.top", 1, "2026-08-13 19:00:00"),
        ("WHATSAPP", "+919566778899", "Friend Emergency Medical", "Bhai urgent hospital emergency hai, 10000 bhej de is upi pe: emergencycare@ybl. Shaam tak wapas karta hu.", "upi://pay?pa=emergencycare@ybl&am=10000", 1, "2026-08-14 23:45:00"),
        ("EMAIL", "accounts-audit@vendor-update.net", "Updated Bank Account for Vendor Payment", "Please note our company bank account has changed due to annual audit. Route all future PO remittances to new UPI ID.", None, 1, "2026-08-15 08:30:00"),
        ("SMS", "HP-PANIOT", "PAN Card Deactivation Alert", "Your PAN will be cancelled within 12 hours. Link Aadhaar immediately to avoid Rs 10000 penalty: https://pan-aadhaar-link-urgent.xyz", "https://pan-aadhaar-link-urgent.xyz", 1, "2026-08-16 14:10:00"),
        ("SMS", "VK-SBIOTP", "Fake Bank Vishing Call", "Dear customer, your debit card was used for Rs 45,000 at Dubai. If not you, immediately call Bank Fraud Desk at 022-69871234.", None, 1, "2026-08-17 16:05:00"),
        ("SMS", "BL-LOAN", "Instant Pre-Approved Loan", "Instant loan of Rs 5 Lakh credited. Verify bank details and OTP at https://cutt.ly/instant-loan-approval", "https://cutt.ly/instant-loan-approval", 1, "2026-08-18 12:20:00"),
        ("WHATSAPP", "+919444332211", "Crypto Airdrop 100 USDT", "Claim your free 100 USDT airdrop today before pool expires: https://fastrack-crypto-airdrop.xyz", "https://fastrack-crypto-airdrop.xyz", 1, "2026-08-19 21:10:00"),
        ("SMS", "CP-CASHB", "Cashback Voucher Expiring", "Your Rs 2,500 Paytm wallet voucher is expiring in 2 hours. Redeem here: https://tinyurl.com/gpay-cashback99", "https://tinyurl.com/gpay-cashback99", 1, "2026-08-20 18:40:00"),

        # Benign / Safe Messages
        ("SMS", "SBI-ALERT", "Salary Credited", "Dear customer, your A/C ending 4899 is credited with INR 65,000.00 on 31-Jul-2026 by NEFT. Available Bal: INR 78,500.00.", None, 0, "2026-08-01 08:00:00"),
        ("SMS", "HDFC-BANK", "HDFC OTP Notice", "492018 is your Secret OTP for online purchase of Rs 1,299 at Swiggy. NEVER SHARE OTP with anyone including bank staff.", None, 0, "2026-08-02 20:15:00"),
        ("EMAIL", "receipts@swiggy.in", "Your Swiggy Order Receipt #8912", "Thank you for ordering with Swiggy! Total paid: Rs 428 via UPI. Track your delivery on official app: https://swiggy.com", "https://swiggy.com", 0, "2026-08-03 20:45:00"),
        ("WHATSAPP", "+919840123456", "Lunch Split", "Hey! Split for yesterday's lunch was Rs 280. Pay whenever free to rohan@okhdfc.", "upi://pay?pa=rohan@okhdfc&am=280", 0, "2026-08-04 13:10:00"),
        ("SMS", "AX-IRCTC", "IRCTC Ticket Booked", "PNR 4529182390 Confirmed. Train 12675 KOVAI EXP. Departure 06:10 from MAS. Check status at https://irctc.co.in", "https://irctc.co.in", 0, "2026-08-05 17:20:00"),
        ("EMAIL", "order-update@amazon.in", "Shipped: Your Amazon Order", "Your package containing Wireless Mouse has shipped and will arrive tomorrow. Track at https://amazon.in", "https://amazon.in", 0, "2026-08-06 11:00:00"),
        ("SMS", "IC-BANK", "ATM Withdrawal", "INR 2,000.00 debited from ICICI A/C ending 1239 at ATM Coimbatore. Call 18001080 if not done by you.", None, 0, "2026-08-07 19:30:00"),
        ("WHATSAPP", "+919444001122", "Trip Photos", "Hey! Here are the high-res photos from our Ooty trip. Check drive link when you get time.", "https://google.com", 0, "2026-08-08 15:00:00"),
        ("SMS", "BP-JIOREC", "Jio Recharge Success", "Recharge of Rs 299 for Jio number 9876543210 is successful. Benefits: 1.5GB/day for 28 days.", None, 0, "2026-08-09 10:15:00"),
        ("EMAIL", "no-reply@incometax.gov.in", "ITR Filing Confirmation", "Your ITR-1 for AY 2026-27 has been successfully e-verified. Download ITR-V acknowledgement at https://incometax.gov.in", "https://incometax.gov.in", 0, "2026-08-10 14:00:00"),
        ("SMS", "UB-RIDES", "Uber Trip Receipt", "Your Tuesday evening trip with Uber was Rs 184. View receipt details on the Uber App.", None, 0, "2026-08-11 21:00:00"),
        ("SMS", "AP-PHARM", "Apollo Order Ready", "Order #AP9012 is ready for pickup at R.S. Puram branch. Amount paid: Rs 450.", None, 0, "2026-08-12 18:20:00")
    ]
    for m in messages_seed:
        cur.execute(
            """INSERT INTO messages (channel, sender, subject, body, link, is_scam, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            m
        )

    # 7. Generate ~6500 historical transactions with overlapping distributions and realistic hard cases
    user_map = {u[0]: u for u in users_data}
    merch_map = {m[0]: m for m in merchants_data}
    txns = []
    base_time = datetime(2026, 5, 1, 8, 0, 0)

    # Persona base average spends
    persona_avgs = {
        "student": 450.0,
        "salaried": 2800.0,
        "business": 22000.0
    }

    # -------------------------------------------------------------
    # 7A. 6,000 Legitimate Transactions (with ~6% Hard Cases)
    # -------------------------------------------------------------
    # Hard case quotas:
    # ~75 large festival / jewellery purchase (5-8x avg)
    # ~75 legit late-night txns (2-4 AM for night-shift/travel)
    # ~75 legit travel (city mismatch)
    # ~70 legit new device after phone upgrade
    # ~65 first-time payee
    legit_hard_indices = set(random.sample(range(6000), 360))
    hard_subtypes = (
        ["festival"] * 75 +
        ["night"] * 75 +
        ["travel"] * 75 +
        ["new_device"] * 70 +
        ["new_payee"] * 65
    )
    random.shuffle(hard_subtypes)
    hard_type_map = dict(zip(legit_hard_indices, hard_subtypes))

    curr_time = base_time
    for i in range(6000):
        uid = random.randint(1, 10)
        u_info = user_map[uid]
        persona = u_info[6]
        home_city = u_info[5]
        base_avg = persona_avgs[persona]

        # Verified merchants standard pool
        valid_mids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
        mid = random.choice(valid_mids)

        # Baseline continuous amount ratio from lognormal (mean 1.0, overlap)
        ratio = float(np.random.lognormal(mean=0.0, sigma=0.55))
        tx_hour = random.randint(7, 22)
        city = home_city
        is_new_dev = 0

        # Inject Legit Hard Cases (~6% of legit)
        if i in hard_type_map:
            ht = hard_type_map[i]
            if ht == "festival":
                # High-value festive/jewellery/appliance purchase (5-8x average)
                ratio = float(np.random.uniform(5.0, 8.0))
                mid = random.choice([8, 10, 11])  # Amazon, Tanishq, Croma
            elif ht == "night":
                # Legitimate night transactions (2-4 AM: airport, late-night cab, fuel)
                tx_hour = random.choice([2, 3, 4])
                mid = random.choice([6, 7, 9])  # Indian Oil, Uber, Apollo
            elif ht == "travel":
                # Legitimate travel (new city)
                city = random.choice(["Goa", "Mumbai", "Delhi", "Bengaluru", "Jaipur", "Kolkata"])
                if city == home_city:
                    city = "Goa"
            elif ht == "new_device":
                # Legitimate new phone / device replacement
                is_new_dev = 1
            elif ht == "new_payee":
                # First-time payee to a legitimate local vendor
                mid = random.choice([12, 13, 14, 15])

        amt = max(10.0, round(base_avg * ratio, 2))
        curr_time += timedelta(minutes=random.randint(15, 60))
        tx_dt = curr_time.replace(hour=tx_hour, minute=random.randint(0, 59))

        txns.append({
            "sender_id": uid,
            "receiver_upi": merch_map[mid][2],
            "receiver_name": merch_map[mid][1],
            "amount": amt,
            "note": random.choice(["Payment", "Bill", "Purchase", "Recharge", "Order", "UPI transfer"]),
            "status": "SUCCESS",
            "city": city,
            "device_id": f"DEV_USR_{uid:02d}_A" if is_new_dev == 0 else f"DEV_USR_{uid:02d}_B",
            "is_new_device": is_new_dev,
            "ts": tx_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "risk_score": round(random.uniform(0.02, 0.25), 4),
            "decision": "APPROVE",
            "reason": "Normal transaction within user spending habit.",
            "is_fraud_label": 0
        })

    # -------------------------------------------------------------
    # 7B. 520 Fraud Transactions (~8% fraud rate, with ~35% Hard Cases)
    # -------------------------------------------------------------
    # ~182 Fraud Hard Cases (~35% of fraud):
    #   - 40 normal-looking amounts (0.7 - 1.8x)
    #   - 35 usual daytime hours (11 AM - 6 PM)
    #   - 30 home city (compromised credentials used locally)
    #   - 30 known device (session hijacking, spyware)
    #   - 25 verified-looking merchant (e-gift cards, digital vouchers)
    #   - 22 small card-testing amounts (0.01 - 0.12x)
    fraud_hard_types = (
        ["normal_amount"] * 40 +
        ["daytime_hours"] * 35 +
        ["home_city"] * 30 +
        ["known_device"] * 30 +
        ["verified_merchant"] * 25 +
        ["card_testing"] * 22
    )
    # 338 Standard / Obvious Fraud cases
    standard_fraud_types = ["obvious"] * (520 - len(fraud_hard_types))
    all_fraud_types = fraud_hard_types + standard_fraud_types
    random.shuffle(all_fraud_types)

    for ft in all_fraud_types:
        uid = random.randint(1, 10)
        u_info = user_map[uid]
        persona = u_info[6]
        home_city = u_info[5]
        base_avg = persona_avgs[persona]

        f_dt = base_time + timedelta(days=random.randint(2, 110), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        ratio = float(np.random.lognormal(mean=0.95, sigma=0.85))

        city = random.choice(["UnknownForeign", "Dubai", "Singapore", "RogueProxy", "DarkCity"])
        is_new_dev = 1
        mid = random.choice([16, 17, 18, 19, 20])  # high risk / unverified
        receiver_upi = merch_map[mid][2]
        receiver_name = merch_map[mid][1]
        note = random.choice(["Immediate settlement", "Wallet topup", "Express transfer", "Crypto token", "Emergency cash"])

        if ft == "normal_amount":
            # Normal amount ratio (0.65 - 1.8x) - deceptive subtle fraud
            ratio = float(np.random.uniform(0.65, 1.8))
            note = "Order purchase"
        elif ft == "daytime_hours":
            # Fraud during usual daytime hours
            f_dt = f_dt.replace(hour=random.randint(11, 18))
        elif ft == "home_city":
            # Fraud executed from victim's home city (phishing or local malware)
            city = home_city
        elif ft == "known_device":
            # Fraud from victim's primary device (session hijack or spyware)
            is_new_dev = 0
        elif ft == "verified_merchant":
            # Fraud directed to legitimate merchant (gift card / food voucher drain)
            mid = random.choice([1, 2, 8, 10])  # Swiggy, Zomato, Amazon, Tanishq
            receiver_upi = merch_map[mid][2]
            receiver_name = merch_map[mid][1]
            note = "E-Gift Card Purchase"
        elif ft == "card_testing":
            # Small micro-probe testing card limits
            ratio = float(np.random.uniform(0.01, 0.12))
            note = "Micro probe"
        else:
            # Standard fraud patterns: high value, weird hours, impossible travel
            if random.random() < 0.4:
                ratio = float(np.random.uniform(5.5, 9.5))
            if random.random() < 0.5:
                f_dt = f_dt.replace(hour=random.choice([2, 3, 4]))

        amt = max(10.0, round(base_avg * ratio, 2))

        txns.append({
            "sender_id": uid,
            "receiver_upi": receiver_upi,
            "receiver_name": receiver_name,
            "amount": amt,
            "note": note,
            "status": "BLOCKED" if ratio > 2.5 else "WARN",
            "city": city,
            "device_id": f"DEV_USR_{uid:02d}_A" if is_new_dev == 0 else f"DEV_FRAUD_{random.randint(100, 999)}",
            "is_new_device": is_new_dev,
            "ts": f_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "risk_score": round(random.uniform(0.65, 0.95), 4),
            "decision": "BLOCK" if ratio > 2.0 else "WARN",
            "reason": "Anomaly detection flag.",
            "is_fraud_label": 1
        })

    # -------------------------------------------------------------
    # 7C. Add ~2% Label Noise (Mimic Disputed / Undetected Cases)
    # -------------------------------------------------------------
    # 2% of legit flipped to 1 (disputes, chargeback confusion)
    # 2% of fraud flipped to 0 (undetected / subtle fraud)
    for t in txns:
        if t["is_fraud_label"] == 0 and random.random() < 0.02:
            t["is_fraud_label"] = 1
        elif t["is_fraud_label"] == 1 and random.random() < 0.02:
            t["is_fraud_label"] = 0

    # Sort all transactions by timestamp
    txns.sort(key=lambda x: x["ts"])

    for t in txns:
        cur.execute(
            """INSERT INTO transactions (
                sender_id, receiver_upi, receiver_name, amount, note, status, city,
                device_id, is_new_device, ts, risk_score, decision, reason, is_fraud_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["sender_id"], t["receiver_upi"], t["receiver_name"], t["amount"], t["note"],
                t["status"], t["city"], t["device_id"], t["is_new_device"], t["ts"],
                t["risk_score"], t["decision"], t["reason"], t["is_fraud_label"]
            )
        )

    # 8. Seed sample alerts & link scans
    alerts_seed = [
        (1, "PHISHING", "HIGH", "Blocked malicious KYC phishing link: https://sbi-update-login.in", "2026-08-01 09:16:00"),
        (4, "FRAUD_TXN", "CRITICAL", "Blocked Rs 28,000 to Tanishq Jewellers due to impossible travel velocity.", "2026-08-04 17:00:00"),
        (8, "BEC_ATTEMPT", "HIGH", "Flagged Rs 55,000 urgent wire payment to first-time payee.", "2026-08-06 15:35:00")
    ]
    for a in alerts_seed:
        cur.execute(
            "INSERT INTO alerts (user_id, kind, severity, message, ts) VALUES (?, ?, ?, ?, ?)",
            a
        )

    link_scans_seed = [
        (1, "https://sbi-update-login.in", "SMS", "BLOCK", 0.98, "Blocklisted domain; Credential harvesting; Urgent KYC", "2026-08-01 09:15:30"),
        (1, "https://gpay-reward.top", "SMS", "BLOCK", 0.95, "Blocklisted domain; Suspicious TLD .top; Lottery scam pattern", "2026-08-02 11:31:00"),
        (4, "https://swiggy.com", "EMAIL", "SAFE", 0.02, "Verified brand domain; Valid HTTPS; Official receipt", "2026-08-03 20:46:00")
    ]
    for s in link_scans_seed:
        cur.execute(
            "INSERT INTO link_scans (user_id, url, source, verdict, score, reasons, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            s
        )

    conn.commit()
    conn.close()

    total_t = len(txns)
    fraud_t = sum(1 for t in txns if t["is_fraud_label"] == 1)
    print(f"SafePay Database seeded successfully: {len(users_data)} users, {len(merchants_data)} merchants, {total_t} transactions ({fraud_t} fraud labels, {fraud_t/total_t*100:.1f}%).")

if __name__ == "__main__":
    seed_all(force=True)
