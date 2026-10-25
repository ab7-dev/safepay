import re
from datetime import datetime
from core import bayes, db, kb, shield, textmodel, txnmodel, upi

class SafePayAgent:
    """
    Model-based, utility-based intelligent fraud mitigation agent (CO1).
    PEAS Formulation:
      - Performance: Maximize detection of multi-vector fraud, minimize false friction, 0 balance loss on block.
      - Environment: PWA payment requests, SQLite user transaction history, merchant registry, threat feeds.
      - Actuators: APPROVE, WARN (step-up ACK), BLOCK, SQLite alerts & audit logging, account freeze.
      - Sensors: Transaction percepts (VPA, amount, device, city, velocity), message texts, links/URLs.
    """

    def __init__(self):
        # Base signal weights
        self.weights = {
            "link": 0.30,
            "message": 0.15,
            "txn_ml": 0.25,
            "rules": 0.15,
            "bayes": 0.15
        }

    def evaluate_percept(self, percept, user_id=None, log_alert=True):
        """
        Evaluates a heterogeneous fraud percept containing any combination of:
          - txn: {receiver_upi, amount, note, city, device_id, is_new_device}
          - url: str
          - text: str
          - upi_str: str
        """
        conn = db.get_connection()
        cur = conn.cursor()

        # Load user history if user_id given
        user = None
        if user_id:
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            u_row = cur.fetchone()
            if u_row:
                user = dict(u_row)
        conn.close()

        signals = {}
        max_override_triggered = False
        override_reason = ""
        fraud_types_detected = []

        # 1. URL / Link Analysis
        url_input = percept.get("url")
        # Check if URL embedded in note or text
        if not url_input and percept.get("text"):
            found_urls = re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", percept["text"])
            if found_urls:
                url_input = found_urls[0]
        if not url_input and percept.get("note"):
            found_urls = re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", percept["note"])
            if found_urls:
                url_input = found_urls[0]

        if url_input:
            msg_ctx = percept.get("text") or percept.get("note")
            link_eval = shield.inspect_link(url_input, message_text=msg_ctx, user_id=user_id)
            score = link_eval["score"]
            signals["link"] = {
                "score": score,
                "reasons": link_eval["reasons"],
                "url": url_input,
                "domain": link_eval["domain"],
                "details": link_eval["layers"]
            }
            if link_eval["layers"]["blocklist"]["hit"]:
                max_override_triggered = True
                override_reason = f"Critical threat: Destination domain '{link_eval['domain']}' is on active cybercrime blocklist"
            elif score >= 0.90:
                max_override_triggered = True
                override_reason = f"High-confidence phishing link detected: {link_eval['reasons'][0]}"
            fraud_types_detected.append(link_eval["fraud_type"])

        # 2. Text / Message NLP Analysis
        text_input = percept.get("text") or percept.get("note")
        if text_input and str(text_input).strip():
            txt_eval = textmodel.predict_text(text_input)
            score = txt_eval["probability"]
            signals["message"] = {
                "score": score,
                "reasons": txt_eval["reasons"],
                "top_words": txt_eval.get("top_words", [])
            }
            if score >= 0.90:
                max_override_triggered = True
                override_reason = "High-confidence social engineering intimidation text detected"
            if txt_eval["reasons"]:
                fraud_types_detected.append("Social Engineering")

        # 3. Transaction / UPI Analysis
        txn_data = percept.get("txn") or {}
        upi_str = percept.get("upi_str")
        if upi_str:
            upi_eval = upi.analyze_upi(upi_str, user_avg_spend=user.get("avg_spend", 1000.0) if user else 1000.0)
            if upi_eval.get("is_valid"):
                parsed = upi_eval["parsed"]
                if not txn_data.get("receiver_upi"):
                    txn_data["receiver_upi"] = parsed["pa"]
                if not txn_data.get("amount") and parsed.get("am"):
                    txn_data["amount"] = parsed["am"]
                if not txn_data.get("note") and parsed.get("tn"):
                    txn_data["note"] = parsed["tn"]

                # If collect request
                if "COLLECT_REQUEST" in upi_eval.get("flags", []):
                    max_override_triggered = True
                    override_reason = "Malicious UPI Collect Request: authorization would immediately debit your balance"
                    fraud_types_detected.append("UPI Collect Scam")

        # If we have transaction parameters
        if txn_data and txn_data.get("receiver_upi"):
            r_upi = txn_data["receiver_upi"]
            amount = float(txn_data.get("amount", 0.0))
            city = txn_data.get("city") or (user.get("home_city") if user else "Unknown")
            is_new_dev = int(txn_data.get("is_new_device", 0))

            # Query recipient merchant or user
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM merchants WHERE upi_id = ?", (r_upi,))
            m_row = cur.fetchone()
            merchant = dict(m_row) if m_row else None

            # Get user historical avg spend and txns in past 10 min
            avg_spend = 1000.0
            recent_10m = 0
            if user:
                cur.execute("SELECT AVG(amount) as avg_amt FROM transactions WHERE sender_id = ? AND is_fraud_label = 0", (user["id"],))
                a_row = cur.fetchone()
                if a_row and a_row["avg_amt"]:
                    avg_spend = float(a_row["avg_amt"])

                # Velocity check
                cur.execute(
                    """SELECT COUNT(*) as cnt FROM transactions 
                       WHERE sender_id = ? AND ts >= datetime('now', '-10 minutes', 'localtime')""",
                    (user["id"],)
                )
                v_row = cur.fetchone()
                recent_10m = int(v_row["cnt"]) if v_row else 0
            conn.close()

            # Rule engine context (CO3)
            now_dt = datetime.now()
            home_c = user.get("home_city", city) if user else city
            city_mismatch = 1 if city.strip().lower() != home_c.strip().lower() else 0
            m_risk_str = merchant.get("risk_level", "LOW") if merchant else "LOW"
            is_new_payee = 1 if not merchant else 0
            dispute_ratio = 0.05
            has_urgency = bool(signals.get("message", {}).get("score", 0) > 0.5)

            kb_ctx = {
                "domain_in_blocklist": bool(signals.get("link", {}).get("score", 0) > 0.9),
                "suspicious_tld": bool("High-risk phishing Top-Level Domain" in str(signals.get("link", {}).get("reasons", []))),
                "ip_host": bool("Direct IP address" in str(signals.get("link", {}).get("reasons", []))),
                "has_urgency_words": has_urgency,
                "has_payment_link": bool(url_input),
                "amount": amount,
                "avg_spend": avg_spend,
                "merchant_risk": m_risk_str,
                "is_new_payee": is_new_payee,
                "vpa_brand_lookalike": bool("Lookalike" in str(signals.get("link", {}).get("reasons", []))),
                "receiver_not_verified": (merchant is None or merchant.get("verified", 0) == 0),
                "is_collect_request": 1 if "COLLECT_REQUEST" in str(signals) else 0,
                "is_new_device": is_new_dev,
                "city_mismatch": city_mismatch,
                "recent_failed_pins": user.get("failed_pins", 0) if user else 0,
                "dispute_ratio": dispute_ratio,
                "is_first_time_payee": is_new_payee,
                "hour": now_dt.hour
            }

            # CO3 KB forward chaining
            kb_res = kb.evaluate_rules(kb_ctx)
            rule_score = kb_res["rule_score"]
            rule_reasons = [r["name"] for r in kb_res["triggered_rules"]]
            signals["rules"] = {
                "score": rule_score,
                "reasons": rule_reasons,
                "triggered": kb_res["triggered_rules"]
            }
            if kb_res["dominant_fraud_type"] != "none":
                fraud_types_detected.append(kb_res["dominant_fraud_type"].upper())

            # CO4 Bayesian Model
            bayes_evidence = {
                "night": 1 if (now_dt.hour < 5 or now_dt.hour >= 23) else 0,
                "new_device": is_new_dev,
                "high_risk_merchant": 1 if m_risk_str == "HIGH" else 0,
                "amount_spike": 1 if amount > 3.0 * avg_spend else 0,
                "city_mismatch": city_mismatch,
                "new_payee": is_new_payee,
                "suspicious_link": 1 if signals.get("link", {}).get("score", 0) > 0.5 else 0
            }
            bayes_res = bayes.predict_bayes(bayes_evidence)
            signals["bayes"] = {
                "score": bayes_res["probability"],
                "reasons": [f"Bayesian posterior probability: {bayes_res['probability']:.2f}"],
                "steps": bayes_res.get("steps", [])
            }

            # CO5 Transaction ML Model
            risk_int_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            txn_features = {
                "amount_ratio": amount / max(1.0, avg_spend),
                "hour": now_dt.hour,
                "txns_last_10min": recent_10m,
                "city_mismatch": city_mismatch,
                "is_new_device": is_new_dev,
                "new_payee": is_new_payee,
                "merchant_risk": risk_int_map.get(m_risk_str, 0),
                "failed_pin_count": user.get("failed_pins", 0) if user else 0,
                "recent_pin_reset": 1 if (user and user.get("failed_pins", 0) >= 2 and is_new_dev) else 0
            }
            txn_ml_res = txnmodel.predict_txn(txn_features)
            signals["txn_ml"] = {
                "score": txn_ml_res["probability"],
                "reasons": txn_ml_res["reasons"],
                "features": txn_features,
                "model": txn_ml_res["model_used"]
            }

            if txn_ml_res["probability"] >= 0.90:
                max_override_triggered = True
                override_reason = f"ML model flagged critical anomaly: {txn_ml_res['reasons'][0] if txn_ml_res['reasons'] else 'Extreme pattern outlier'}"

        # Combine signals with weighted renormalization
        total_w = sum(self.weights[k] for k in signals if k in self.weights)
        if total_w > 0:
            weighted_sum = sum(signals[k]["score"] * self.weights[k] for k in signals if k in self.weights)
            aggregated_risk = weighted_sum / total_w
        else:
            aggregated_risk = 0.05

        # Incorporate multi-vector confirmation (e.g. high-confidence KB rules + coercive message)
        rule_score = signals.get("rules", {}).get("score", 0.0)
        msg_score = signals.get("message", {}).get("score", 0.0)
        if rule_score >= 0.70 or (rule_score >= 0.35 and msg_score >= 0.70):
            aggregated_risk = max(aggregated_risk, 0.76)
        elif rule_score >= 0.30 or msg_score >= 0.50:
            aggregated_risk = max(aggregated_risk, 0.50)

        # Apply MAX-OVERRIDE rule
        if max_override_triggered:
            final_risk = 0.96
        else:
            final_risk = round(aggregated_risk, 4)

        # Decision Thresholds
        if final_risk < 0.40:
            decision = "APPROVE"
        elif final_risk <= 0.70:
            decision = "WARN"
        else:
            decision = "BLOCK"

        # Determine dominant fraud type
        dominant_fraud = fraud_types_detected[0] if fraud_types_detected else "General Anomaly"
        if "Phishing" in dominant_fraud or "KYC" in dominant_fraud:
            dominant_fraud = "Phishing / Malicious Link"
        elif "ATO" in dominant_fraud:
            dominant_fraud = "Account Takeover (ATO)"
        elif "BEC" in dominant_fraud:
            dominant_fraud = "Business Email Compromise (BEC)"
        elif "Collect" in dominant_fraud or "UPI" in dominant_fraud:
            dominant_fraud = "Fake UPI / QR Collect Scam"

        # Construct concise human-readable summary
        summary_parts = []
        if max_override_triggered and override_reason:
            summary_parts.append(override_reason)
        else:
            for s_name, s_data in signals.items():
                if s_data["score"] >= 0.40 and s_data.get("reasons"):
                    summary_parts.append(s_data["reasons"][0])

        if not summary_parts:
            summary_text = "Transaction matches established spending habits and passes all multi-paradigm verification checks."
        else:
            summary_text = "; ".join(summary_parts[:3])

        # Log alert if WARN or BLOCK and user_id present
        if log_alert and user_id and decision in ("WARN", "BLOCK"):
            sev = "CRITICAL" if decision == "BLOCK" else "MEDIUM"
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO alerts (user_id, kind, severity, message, ts)
                   VALUES (?, ?, ?, ?, datetime('now', 'localtime'))""",
                (user_id, dominant_fraud, sev, f"[{decision}] Risk {final_risk:.2f}: {summary_text[:140]}")
            )
            conn.commit()
            conn.close()

        return {
            "decision": decision,
            "risk": final_risk,
            "signals": signals,
            "summary": summary_text,
            "fraud_type": dominant_fraud,
            "max_override": max_override_triggered
        }

_AGENT_INSTANCE = None

def get_agent():
    global _AGENT_INSTANCE
    if _AGENT_INSTANCE is None:
        _AGENT_INSTANCE = SafePayAgent()
    return _AGENT_INSTANCE
