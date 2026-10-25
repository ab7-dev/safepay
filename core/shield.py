import re
from urllib.parse import urlparse
from core import db, textmodel, urlmodel

SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "t.co", "goo.gl", "is.gd", "rb.gy"}
SUSPICIOUS_TLDS = {".xyz", ".top", ".click", ".cc", ".online", ".site", ".info", ".link", ".club", ".biz"}

def extract_domain(url_str):
    url_str = str(url_str).strip()
    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        url_str = "http://" + url_str
    try:
        parsed = urlparse(url_str)
        host = parsed.netloc.lower().split(":")[0]
        # remove www.
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return url_str.lower()

def check_blocklist(domain):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT domain, source, category FROM blocklist WHERE domain = ?", (domain,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "hit": True,
            "source": row["source"],
            "category": row["category"],
            "reason": f"Known threat domain listed in {row['source']} blocklist under '{row['category']}'"
        }
    return {"hit": False}

def run_heuristics(url_str, domain):
    reasons = []
    score = 0.0

    # Shortener
    if domain in SHORTENERS or any(domain.endswith("." + s) for s in SHORTENERS):
        reasons.append("URL shortener detected hiding target destination")
        score += 0.35

    # Punycode / IDN homograph
    if "xn--" in domain:
        reasons.append("Punycode / IDN internationalized domain lookalike pattern")
        score += 0.45

    # Direct IP host
    ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if re.match(ip_pattern, domain):
        reasons.append("Direct IP address used as website host")
        score += 0.40

    # Suspicious TLD
    if any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS):
        reasons.append("Registered under high-abuse phishing TLD")
        score += 0.30

    # Insecure HTTP
    if url_str.startswith("http://"):
        reasons.append("Plain unencrypted HTTP connection")
        score += 0.15

    # Sensitive path keywords
    low_url = url_str.lower()
    if any(k in low_url for k in ["kyc", "verify-now", "claim-reward", "update-pan", "refund-instant"]):
        reasons.append("Path contains high-risk phishing trigger keyword")
        score += 0.25

    return {
        "score": min(1.0, round(score, 4)),
        "reasons": reasons
    }

def inspect_link(url_str, message_text=None, user_id=None):
    """
    4-layer Shield Link Guard:
      1. Blocklist
      2. Heuristics
      3. URL Machine Learning
      4. Message NLP Model (if text provided)
    """
    domain = extract_domain(url_str)
    all_reasons = []

    # Layer 1: Blocklist
    bl_res = check_blocklist(domain)
    blocklist_hit = bl_res["hit"]
    if blocklist_hit:
        all_reasons.append(bl_res["reason"])

    # Layer 2: Heuristics
    heur_res = run_heuristics(url_str, domain)
    all_reasons.extend(heur_res["reasons"])

    # Layer 3: URL ML Model
    ml_res = urlmodel.predict_url(url_str)
    url_ml_prob = ml_res["probability"]
    all_reasons.extend(ml_res["reasons"])

    # Layer 4: Text Model
    text_prob = 0.0
    text_reasons = []
    top_words = []
    if message_text and str(message_text).strip():
        txt_res = textmodel.predict_text(message_text)
        text_prob = txt_res["probability"]
        text_reasons = txt_res["reasons"]
        top_words = txt_res.get("top_words", [])
        all_reasons.extend(text_reasons)

    # Composite Score Calculation
    # If blocklist hit: instant 0.99
    if blocklist_hit:
        final_score = 0.99
    else:
        # Weighted combination of layers
        if message_text and str(message_text).strip():
            final_score = (0.35 * heur_res["score"]) + (0.35 * url_ml_prob) + (0.30 * text_prob)
        else:
            final_score = (0.45 * heur_res["score"]) + (0.55 * url_ml_prob)

    final_score = min(1.0, round(final_score, 4))

    # Verdict Policy
    if final_score < 0.40:
        verdict = "SAFE"
    elif final_score <= 0.70:
        verdict = "WARN"
    else:
        verdict = "BLOCK"

    # Deduplicate reasons
    unique_reasons = list(dict.fromkeys(all_reasons))
    if not unique_reasons:
        unique_reasons = ["Domain matches verified legitimate standards and safe communication pattern."]

    # Fraud type attribution
    fraud_type = "Phishing"
    low_comb = (url_str + " " + str(message_text or "")).lower()
    if any(k in low_comb for k in ["kyc", "pan", "aadhaar", "login", "verify"]):
        fraud_type = "KYC / Credential Phishing"
    elif any(k in low_comb for k in ["lottery", "prize", "winner", "reward", "cashback"]):
        fraud_type = "Lottery / Reward Scam"
    elif any(k in low_comb for k in ["parcel", "customs", "delivery"]):
        fraud_type = "Parcel Delivery Scam"
    elif any(k in low_comb for k in ["upi", "refund", "collect"]):
        fraud_type = "UPI Payment Scam"

    result = {
        "url": url_str,
        "domain": domain,
        "verdict": verdict,
        "score": final_score,
        "reasons": unique_reasons,
        "fraud_type": fraud_type,
        "highlight_words": top_words,
        "layers": {
            "blocklist": {
                "hit": blocklist_hit,
                "score": 1.0 if blocklist_hit else 0.0,
                "detail": bl_res.get("category", "Clean")
            },
            "heuristics": {
                "score": heur_res["score"],
                "reasons": heur_res["reasons"]
            },
            "url_ml": {
                "probability": url_ml_prob,
                "reasons": ml_res["reasons"]
            },
            "text_ml": {
                "probability": text_prob,
                "reasons": text_reasons,
                "top_words": top_words
            }
        }
    }

    # Log to link_scans in DB
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO link_scans (user_id, url, source, verdict, score, reasons, ts)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
            (user_id, url_str, "Shield Scanner", verdict, final_score, "; ".join(unique_reasons[:3]))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return result
