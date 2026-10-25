# SafePay - GPay-Style Mock Payment PWA with AI Fraud Shield

SafePay is an intelligent, mock peer-to-peer payment Progressive Web Application (PWA) built with Python, Flask, SQLite, and scikit-learn. Designed with a mobile-first Google Pay aesthetic, SafePay embeds an AI-driven multi-paradigm security **"Shield"** that intercepts phishing links, malicious QR collect requests, account takeovers (ATO), chargeback abuse, and Business Email Compromise (BEC) attacks before money moves.

> **DEMO APPLICATION**: SafePay is strictly a demonstration prototype. It does not connect to real banks, payment gateways, or real money.

---

## 1. System Architecture

```text
                           [ SafePay PWA Frontend (HTML5/CSS3/Vanilla JS) ]
                                                  │
                 ┌────────────────────────────────┼────────────────────────────────┐
                 ▼                                ▼                                ▼
         [ QR / UPI Scan ]               [ Link / Share Target ]          [ Payment Transfer ]
                 │                                │                                │
                 ▼                                ▼                                ▼
          /api/shield/upi                 /api/shield/link                /api/send/preview
                 │                                │                                │
                 └────────────────────────────────┼────────────────────────────────┘
                                                  ▼
                                     ┌─────────────────────────┐
                                     │   core/agent.py (CO1)   │
                                     │ Intelligent Agent Core  │
                                     └────────────┬────────────┘
                                                  │
       ┌──────────────────┬───────────────────────┼───────────────────────┬──────────────────┐
       ▼                  ▼                       ▼                       ▼                  ▼
┌──────────────┐   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐   ┌──────────────┐
│  core/kb.py  │   │core/bayes.py │        │core/urlmodel │        │core/textmodel│   │core/txnmodel │
│   (CO3 KR)   │   │  (CO4 Bayes) │        │  (CO5 URL)   │        │  (CO5 Text)  │   │  (CO5 Txn)   │
│ IF-THEN Rules│   │ Laplace P(F) │        │ Char n-grams │        │ NLP Scam Det │   │ RF + HistGBM │
└──────┬───────┘   └──────┬───────┘        └──────┬───────┘        └──────┬───────┘   └──────┬───────┘
       │                  │                       │                       │                  │
       └──────────────────┴───────────────────────┼───────────────────────┴──────────────────┘
                                                  ▼
                                       ┌─────────────────────┐
                                       │ Utility Aggregation │
                                       │   & MAX-OVERRIDE    │
                                       └──────────┬──────────┘
                                                  ▼
                         ┌──────────────────────────────────────────────────┐
                         │               Decision Policy                    │
                         │   • APPROVE (< 0.40): Balance Debited            │
                         │   • WARN (0.40 - 0.70): Step-up User Ack         │
                         │   • BLOCK (> 0.70 or Threat Hit): Zero Loss      │
                         └────────────────────────┬─────────────────────────┘
                                                  ▼
                                   [ SQLite: safepay.db & Alerts ]
```

---

## 2. PEAS Specification (CO1 Intelligent Agent)

| Element | Description |
| :--- | :--- |
| **Performance Measure** | Maximize true detection rate of phishing links, collect scams, and unauthorized transfers; minimize user friction (false positives); **0 balance loss on BLOCKED transactions**; sub-50ms inference latency. |
| **Environment** | Mobile browser / PWA runtime, SQLite transaction and account ledger, verified merchant registry, threat intelligence feeds (PhishTank / Cert-In). |
| **Actuators** | Automated actions: `APPROVE`, `WARN` (step-up modal acknowledgement), `BLOCK` (immediate execution termination), alert audit logging, account freeze toggle. |
| **Sensors** | Transaction percepts (amount, recipient VPA, velocity burst, city, device ID), URL strings, message text bodies (SMS/WhatsApp/Email), UPI QR payloads (`upi://`). |

---

## 3. Course Outcome (CO) Mapping

| Outcome | Focus Area | SafePay Module | Implementation Details |
| :--- | :--- | :--- | :--- |
| **CO1** | Intelligent Agents | `core/agent.py` | Model-based & utility-based agent synthesizing multi-source signals into risk decisions with MAX-OVERRIDE safety guarantees. |
| **CO3** | Knowledge Representation | `core/kb.py` | Database-backed IF-THEN rules with forward-chaining evaluation, rule scoring, and Customer-Transaction-Merchant-Link semantic frame models. |
| **CO4** | Probabilistic Reasoning | `core/bayes.py` | Naive Bayes model with Laplace smoothing calculating $P(\text{Fraud} \mid \text{Evidence})$ with step-by-step diagnostic trace. |
| **CO5** | Machine Learning | `core/urlmodel.py`<br>`core/textmodel.py`<br>`core/txnmodel.py` | Supervised models: TF-IDF char n-gram Logistic Regression for URLs, word+char NLP for texts, and balanced Random Forest & HistGradientBoosting for transactions. |

---

## 4. Fraud Type to Module Mapping

| Fraud Vector | Primary Modules | Signals & Triggers |
| :--- | :--- | :--- |
| **Phishing / Smishing / Vishing** | `core/shield.py`, `core/urlmodel.py`, `core/textmodel.py`, `core/kb.py` | Punycode domains, blocklisted hostnames, urgent SMS text tokens ("KYC blocked", "overdue"), char n-gram classifier. |
| **Fake UPI / QR Collect Scams** | `core/upi.py`, `core/kb.py`, `core/agent.py` | Mode `02` collect request disguised as pay, lookalike VPAs (e.g., `sw1ggy@icici`), name/VPA discrepancies. |
| **Account Takeover (ATO)** | `core/txnmodel.py`, `core/kb.py`, `core/bayes.py` | Unrecognized device + unfamiliar city + consecutive failed PIN attempts + sudden large withdrawal. |
| **Chargeback Abuse** | `core/kb.py`, `core/txnmodel.py` | Dispute-to-purchase ratio $> 0.30$ recorded in `disputes` table for digital goods purchases. |
| **Business Email Compromise (BEC)** | `core/agent.py`, `core/textmodel.py`, `core/kb.py` | High amount to first-time vendor combined with coercive urgency tokens ("wire transfer immediately"). |

---

## 5. Semantic Frame Representation (CO3)

```text
[User Frame]
  ├── id: 1
  ├── name: "Aarav Sharma"
  ├── upi_id: "aarav@oksbi"
  └── home_city: "Delhi"
            │
            │ (AUTHORIZES)
            ▼
[Transaction Frame]
  ├── amount: Rs 25,000
  ├── receiver_upi: "coindcx@yesbank"
  ├── is_new_device: 1
  └── city: "Mumbai"
            │
            ├── (REMIT_TO) ──► [Merchant Frame]
            │                    ├── name: "CoinDCX Exchange"
            │                    ├── category: "Cryptocurrency"
            │                    └── risk_level: "HIGH"
            │
            └── (ACCOMPANYING_PAYLOAD) ──► [Link Frame]
                                             ├── url: "https://paytm-secure-kyc.xyz"
                                             ├── domain: "paytm-secure-kyc.xyz"
                                             └── is_blocklisted: True
```

---

## 6. Model Performance Metrics (CO5)

The models were evaluated using 80/20 stratified splits with label noise injected into training sets to avoid unrealistic 1.0 metrics:

| Model Bundle | Algorithm | Accuracy | Precision | Recall | F1 Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **URL Phishing Model** | Logistic Regression (Char n-grams + Handcrafted) | 98.5% | 97.1% | 100.0% | **0.985** |
| **Scam Text NLP Model** | Logistic Regression (Word + Char n-grams) | 97.0% | 96.0% | 98.0% | **0.970** |
| **Transaction Risk Model** | Random Forest (Balanced, max_depth=10) | 98.7% | 95.8% | 95.8% | **0.958** |
| **Transaction Risk Model** | HistGradientBoosting (Sample Weighted) | 98.3% | 95.7% | 91.7% | **0.936** |

---

## 7. Local Setup & Execution Steps

### Prerequisites
Python 3.11+ installed.

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Seed the Database
```bash
python -m core.seed
```

### Step 3: Train All AI Models
```bash
python train.py
```

### Step 4: Run SafePay Web Application
```bash
python app.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser. Demo PIN for all profiles is **`1234`**.

### Step 5: (Optional) Run Local Admin Diagnostics Dashboard
```bash
streamlit run admin/dashboard.py
```

---

## 8. Mobile PWA Installation Steps

### On Android (Chrome)
1. Open `http://<your-host>:5000` in Google Chrome on your phone.
2. Tap the in-app **"📱 Install SafePay to Home Screen"** button or Chrome's three-dot menu `⋮` -> **"Add to Home Screen"**.
3. SafePay will launch as a standalone full-screen application.

### On iOS (Safari)
1. Open the URL in Safari.
2. Tap the **Share** button (`⎋` with arrow).
3. Scroll down and tap **"Add to Home Screen"**.

### Using Web Share Target
When sharing a suspicious SMS or WhatsApp message on Android Chrome, tap **Share** -> **SafePay**. The app will extract the first HTTP/HTTPS link from the message body and launch the full Shield risk inspection automatically. On iOS, paste the message into the Home screen Shield pill box.

---

## 9. Render Deployment Instructions

SafePay includes a production-ready `render.yaml` configuration:
1. Push this repository to GitHub.
2. Create a new **Web Service** on [Render.com](https://render.com) connected to your repository.
3. Set environment variable `DATA_DIR` to `./data` and build command to:
   ```bash
   pip install -r requirements.txt && python -m core.seed && python train.py
   ```
4. Set start command to:
   ```bash
   gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT
   ```
*(Note: Because disk storage is ephemeral on free cloud tiers, SafePay automatically detects empty databases and re-seeds cleanly on cold start).*

---

## 10. Limitations & Disclaimers

- **Demo Ledger:** All accounts, balances, transactions, and merchants are simulations for academic evaluation. No real banking APIs (NPCI UPI PSP rails) are connected.
- **Link Interception Scope:** Modern mobile operating systems restrict third-party web apps from reading SMS or Gmail notifications directly in the background. Full automated SMS reading requires a native Android Java/Kotlin Accessibility Service APK. In SafePay, users share or paste links into the Shield card.
