from urllib.parse import parse_qs, urlparse
from core import db

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

def get_verified_merchants():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, upi_id, category, risk_level, verified FROM merchants")
    merchants = [dict(r) for r in cur.fetchall()]
    conn.close()
    return merchants

def parse_upi_string(upi_str):
    """
    Parses upi://pay?pa=...&pn=...&am=...&tn=...
    Also handles raw VPA strings like 'swiggy@icici'.
    """
    upi_str = str(upi_str).strip()
    if not upi_str.startswith("upi://"):
        if "@" in upi_str:
            return {
                "pa": upi_str,
                "pn": "",
                "am": None,
                "tn": "",
                "mode": "00",
                "raw": upi_str
            }
        return None

    try:
        parsed = urlparse(upi_str)
        params = parse_qs(parsed.query)
        pa = params.get("pa", [""])[0].strip()
        pn = params.get("pn", [""])[0].strip()
        am_str = params.get("am", [None])[0]
        am = float(am_str) if am_str else None
        tn = params.get("tn", [""])[0].strip()
        mode = params.get("mode", ["00"])[0].strip()

        return {
            "pa": pa,
            "pn": pn,
            "am": am,
            "tn": tn,
            "mode": mode,
            "raw": upi_str
        }
    except Exception:
        return None

def analyze_upi(upi_str, user_avg_spend=1000.0):
    parsed = parse_upi_string(upi_str)
    if not parsed or not parsed["pa"]:
        return {
            "is_valid": False,
            "risk_score": 0.8,
            "reasons": ["Invalid or malformed UPI payment string"],
            "parsed": {}
        }

    pa = parsed["pa"].lower()
    pn = parsed["pn"].lower()
    am = parsed["am"]
    mode = parsed["mode"]
    tn = parsed["tn"].lower()

    merchants = get_verified_merchants()
    verified_map = {m["upi_id"].lower(): m for m in merchants if m["verified"] == 1}

    reasons = []
    flags = []
    risk_score = 0.0

    # 1. Check if collect request disguised as pay (mode 02 or keywords in note)
    is_collect = False
    if mode == "02" or "collect" in pa or "collect" in tn or "receive" in tn:
        is_collect = True
        risk_score += 0.45
        flags.append("COLLECT_REQUEST")
        reasons.append("UPI Collect Request detected disguised as a payment: authorizing will DEBIT your account!")

    # 2. Check exact verified match
    matched_merchant = verified_map.get(pa)
    if matched_merchant:
        # Check name mismatch
        if pn and matched_merchant["name"].lower() not in pn and pn not in matched_merchant["name"].lower():
            risk_score += 0.25
            flags.append("NAME_MISMATCH")
            reasons.append(f"Name mismatch: QR shows '{parsed['pn']}' but VPA belongs to '{matched_merchant['name']}'")
    else:
        # Check lookalike brand VPA
        lookalike_found = False
        pa_user = pa.split("@")[0]
        for v_upi, v_merch in verified_map.items():
            v_user = v_upi.split("@")[0]
            if pa_user != v_user and 1 <= levenshtein(pa_user, v_user) <= 2:
                risk_score += 0.50
                lookalike_found = True
                flags.append("LOOKALIKE_VPA")
                reasons.append(f"Phishing Lookalike VPA '{pa}' impersonating verified merchant '{v_merch['name']}' ({v_upi})")
                break

        if not lookalike_found:
            risk_score += 0.20
            flags.append("UNKNOWN_VPA")
            reasons.append(f"Unverified recipient VPA '{pa}' not found in official banking merchant registry")

    # 3. Abnormal amount check
    if am is not None and user_avg_spend > 0:
        if am > 5.0 * user_avg_spend:
            risk_score += 0.35
            flags.append("AMOUNT_SPIKE")
            reasons.append(f"Amount Rs {am:,.2f} is more than 5x higher than your usual average spend")

    risk_score = min(1.0, round(risk_score, 4))

    return {
        "is_valid": True,
        "risk_score": risk_score,
        "flags": flags,
        "reasons": reasons,
        "parsed": parsed,
        "matched_merchant": matched_merchant
    }
