import os
import re
from urllib.parse import urlparse
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
URL_MODEL_PATH = os.path.join(MODEL_DIR, "url.pkl")

SUSPICIOUS_TLDS = {".xyz", ".top", ".click", ".cc", ".online", ".site", ".info", ".link", ".club", ".biz"}
KNOWN_BRANDS = ["sbi", "hdfc", "icici", "axis", "paytm", "gpay", "amazon", "flipkart", "npci", "phonepe", "airtel", "jio"]

def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dele = curr[j] + 1
            sub = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]

def extract_handcrafted_features(url_str):
    url_str = str(url_str).strip()
    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        url_for_parse = "http://" + url_str
    else:
        url_for_parse = url_str

    try:
        parsed = urlparse(url_for_parse)
        netloc = parsed.netloc.lower()
    except Exception:
        netloc = url_str.lower()

    ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}(:\d+)?$"
    is_ip = 1.0 if re.match(ip_pattern, netloc) else 0.0

    tld_risk = 0.0
    for tld in SUSPICIOUS_TLDS:
        if netloc.endswith(tld):
            tld_risk = 1.0
            break

    parts = netloc.split(":")[0].split(".")
    subdomains = max(0, len(parts) - 2)

    brand_lookalike = 0.0
    for part in parts:
        for brand in KNOWN_BRANDS:
            if part != brand and 1 <= levenshtein(part, brand) <= 2:
                brand_lookalike = 1.0
                break

    is_https = 1.0 if url_str.startswith("https://") else 0.0

    return [
        float(len(url_str)),
        float(url_str.count(".")),
        float(sum(c.isdigit() for c in url_str)),
        float(url_str.count("-")),
        float(1.0 if "@" in url_str else 0.0),
        float(subdomains),
        tld_risk,
        brand_lookalike,
        is_https,
        is_ip
    ]

FEATURE_NAMES = [
    "length", "dots", "digits", "hyphens", "has_at",
    "subdomain_count", "tld_risk", "brand_lookalike", "is_https", "is_ip"
]

def generate_training_urls():
    """Generates 3000+ synthetic URLs with diverse templates, typos, Hinglish slugs."""
    import random
    random.seed(42)

    safe_base = [
        "https://www.google.com", "https://paytm.com", "https://www.sbi.co.in", "https://netbanking.hdfcbank.com",
        "https://infinity.icicibank.com", "https://www.axisbank.com", "https://www.amazon.in", "https://www.flipkart.com",
        "https://www.irctc.co.in", "https://www.npci.org.in", "https://www.incometax.gov.in", "https://www.swiggy.com",
        "https://www.zomato.com", "https://www.phonepe.com", "https://www.bhimupi.org.in", "https://uidai.gov.in",
        "https://www.airtel.in", "https://www.jio.com", "https://www.myntra.com", "https://www.tataneu.com",
        "https://uber.com", "https://ola.in", "https://www.bigbasket.com", "https://www.makemytrip.com",
        "https://www.cleartrip.com", "https://www.goibibo.com", "https://www.redbus.in", "https://www.bajajfinserv.in",
        "https://www.reliancejio.com", "https://www.bookmyshow.com", "https://www.policybazaar.com",
        "https://www.groww.in", "https://www.zerodha.com", "https://www.upstox.com", "https://www.paytmmoney.com",
        "https://www.cred.club", "https://www.slice.credit", "https://www.navi.com", "https://www.lenskart.com",
        "https://www.nykaa.com", "https://www.tatacliq.com", "https://www.ajio.com", "https://www.meesho.com",
        "https://www.snapdeal.com", "https://www.1mg.com", "https://www.pharmeasy.in", "https://www.netmeds.com",
        "https://www.olacabs.com", "https://www.dunzo.com", "https://www.blinkit.com",
    ]
    safe_paths = [
        "", "/login", "/home", "/offers", "/payment/gateway", "/my-account", "/orders/track",
        "/support/contact", "/dashboard", "/wallet", "/history", "/recharge", "/bill-pay",
        "/profile/settings", "/help", "/faq", "/about-us", "/terms",
    ]
    safe_params = [
        "", "?ref=home", "?utm_source=google", "?lang=hi", "?page=2",
        f"?session={random.randint(100000,999999)}", "?tab=payments",
    ]

    fake_base = [
        "https://paytm-secure-kyc.xyz", "https://sbi-update-login.in", "https://gpay-reward.top",
        "https://hdfc-netbanking-verify.click", "https://npci-refund.cc", "https://amazon-prize-claim.top",
        "https://icici-alert-notice.xyz", "https://axis-kyc-portal.online", "https://phonepe-cashback-instant.site",
        "https://airtel-sim-block-kyc.info", "https://jio-free-5g-upgrade.top", "https://incometax-instant-refund.cc",
        "https://electricity-bill-paynow.link", "https://pan-aadhaar-link-urgent.xyz", "https://speedpost-customs-parcel.top",
        "http://bit.ly/sbi-urgent-alert", "http://tinyurl.com/gpay-cashback99", "http://cutt.ly/instant-loan-approval",
        "http://192.168.1.105/sbi/verify", "http://45.134.20.12/kyc-update", "https://paytm-instant-loan.biz",
        "https://flipkart-mega-sale-win.club", "https://fastrack-crypto-airdrop.xyz", "https://olx-buyer-protection-verify.top",
        # Expanded fakes
        "https://sbi-netbanking-update.xyz", "http://hdfc-card-reactivate.top", "https://icici-otp-verify.click",
        "https://aadhaar-pan-link-now.site", "https://rbi-digital-rupee-claim.xyz", "http://bsnl-sim-verification.info",
        "https://kotak-alert-important.online", "https://bajaj-finance-approve.top", "http://epfo-pf-claim-fast.cc",
        "https://lic-maturity-bonus.biz", "http://neft-failed-refund.xyz", "https://gas-subsidy-link-today.top",
        "https://upi-reward-2026.click", "https://ration-card-ekyc.site", "https://passport-renewal-fast.info",
        "http://challan-pay-now.link", "https://mutual-fund-redeem.cc", "https://train-ticket-refund.xyz",
        "http://water-bill-overdue.top", "https://cibil-score-free-check.online",
        "https://sbl-online-banking.xyz", "https://hfdc-netbanking.top", "https://amazom-offers.click",
        "https://flpkart-sale.online", "http://phonepa-cashback.site", "https://axls-bank-login.xyz",
        "https://googl-pay-reward.top", "https://icicl-bank-verify.click", "https://pnb-login-secure.cc",
        "https://canara-update-kyc.biz", "https://bob-netbanking-alert.info", "https://union-bank-reactivate.link",
        "http://103.24.56.78/sbi-login", "http://78.91.23.45/hdfc-verify", "http://210.56.12.89/paytm-kyc",
    ]
    fake_paths = [
        "/kyc", "/verify-now", "/claim-reward", "/instant-cash", "/pin-reset", "/claim-refund",
        "/update-pan", "/aadhaar-link", "/otp-verify", "/unblock-account", "/accept-payment",
        "/free-recharge", "/activate-sim", "/link-upi",
    ]
    fake_params = [
        "", "?user_token=8821&urgent=1", "?ref=sms&action=verify", "?id=victim_2026",
        "?otp=auto&claim=now", f"?uid={random.randint(10000,99999)}", "?deadline=24h",
    ]

    # Hinglish slug variations for fakes
    hinglish_slugs = [
        "turant-verify-karein", "apna-account-bachao", "paisa-wapas-lo", "sim-band-hone-se-bachao",
        "abhi-click-karein", "jaldi-payment-karein", "free-cashback-claim", "kyc-update-jaruri",
    ]

    urls, labels = [], []

    # 1500 safe
    for _ in range(1500):
        b = random.choice(safe_base)
        p = random.choice(safe_paths)
        q = random.choice(safe_params)
        urls.append(b + p + q)
        labels.append(0)

    # 1500 fake
    for _ in range(1200):
        b = random.choice(fake_base)
        p = random.choice(fake_paths)
        q = random.choice(fake_params)
        urls.append(b + p + q)
        labels.append(1)

    # Extra fakes with Hinglish slugs
    for _ in range(150):
        dom = random.choice(["kyc-portal", "bank-alert", "upi-refund", "sim-update", "loan-approve"])
        tld = random.choice([".xyz", ".top", ".click", ".site", ".online", ".cc"])
        slug = random.choice(hinglish_slugs)
        urls.append(f"https://{dom}{tld}/{slug}?urgent=true")
        labels.append(1)

    # Extra fakes with IP addresses
    for _ in range(80):
        ip = f"http://{random.randint(10,220)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        path = random.choice(["/login", "/verify", "/kyc", "/sbi-update", "/hdfc-reactivate"])
        urls.append(ip + path)
        labels.append(1)

    # Extra fakes with typo domains (brand lookalikes)
    for _ in range(70):
        typo_brand = random.choice(["sbii", "hdfcc", "icicl", "axls", "paytn", "gpey", "amazn", "flpkart"])
        tld = random.choice([".com", ".in", ".co.in", ".org"])
        path = random.choice(["/login", "/verify", "/kyc-update", "/account"])
        urls.append(f"http://{typo_brand}{tld}{path}")
        labels.append(1)

    # ~3% label noise for realism
    for i in range(len(labels)):
        if random.random() < 0.03:
            labels[i] = 1 - labels[i]

    return urls, labels

def train_url_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    urls, labels = generate_training_urls()
    print(f"  URL training set: {len(urls)} samples ({sum(labels)} phishing)")

    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), max_features=1200)
    X_tfidf = vectorizer.fit_transform(urls)

    X_hand = np.array([extract_handcrafted_features(u) for u in urls])
    X = hstack([X_tfidf, X_hand])
    y = np.array(labels)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = LogisticRegression(max_iter=1000, C=1.5, class_weight="balanced", random_state=42)
    clf.fit(X_train, y_train)

    from sklearn.metrics import confusion_matrix
    preds = clf.predict(X_test)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, preds)), 4),
        "precision": round(float(precision_score(y_test, preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, preds, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_test, preds).tolist()
    }

    joblib.dump({"vectorizer": vectorizer, "classifier": clf, "metrics": metrics}, URL_MODEL_PATH)
    print(f"URL Model trained & saved. Metrics: Acc={metrics['accuracy']}, F1={metrics['f1']}")
    return metrics

_CACHED_URL_BUNDLE = None

def get_url_bundle():
    global _CACHED_URL_BUNDLE
    if _CACHED_URL_BUNDLE is None:
        if not os.path.exists(URL_MODEL_PATH):
            train_url_model()
        _CACHED_URL_BUNDLE = joblib.load(URL_MODEL_PATH)
    return _CACHED_URL_BUNDLE

def predict_url(url_str):
    bundle = get_url_bundle()
    vec = bundle["vectorizer"]
    clf = bundle["classifier"]

    x_tfidf = vec.transform([url_str])
    x_hand = np.array([extract_handcrafted_features(url_str)])
    x_all = hstack([x_tfidf, x_hand])

    prob = float(clf.predict_proba(x_all)[0][1])

    reasons = []
    hand = extract_handcrafted_features(url_str)
    if hand[6] > 0:
        reasons.append("High-risk phishing Top-Level Domain (.top/.xyz/.click/.cc)")
    if hand[7] > 0:
        reasons.append("Lookalike domain impersonating recognized Indian banking brand")
    if hand[9] > 0:
        reasons.append("Direct IP address used as URL host (suspicious bypass)")
    if hand[8] == 0:
        reasons.append("Insecure plain HTTP connection")
    if prob >= 0.70 and not reasons:
        reasons.append("Machine learning character n-gram pattern flagged phishing syntax")

    return {
        "probability": round(prob, 4),
        "reasons": reasons,
        "metrics": bundle.get("metrics", {})
    }

if __name__ == "__main__":
    train_url_model()
