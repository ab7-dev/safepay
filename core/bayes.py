from datetime import datetime
import pandas as pd
from core import db

def compute_bayes_model():
    """
    Computes prior probabilities and evidence likelihoods from SQLite database with Laplace smoothing.
    Features:
      night, new_device, high_risk_merchant, amount_spike, city_mismatch, new_payee, suspicious_link
    """
    conn = db.get_connection()
    query = """
        SELECT t.id, t.sender_id, t.receiver_upi, t.amount, t.city, t.is_new_device, t.ts, t.is_fraud_label,
               u.home_city,
               m.risk_level as merchant_risk
        FROM transactions t
        LEFT JOIN users u ON t.sender_id = u.id
        LEFT JOIN merchants m ON t.receiver_upi = m.upi_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return None

    df["dt"] = pd.to_datetime(df["ts"])
    df["night"] = df["dt"].dt.hour.apply(lambda h: 1 if (h < 5 or h >= 23) else 0)
    df["new_device"] = df["is_new_device"].fillna(0).astype(int)
    df["high_risk_merchant"] = df["merchant_risk"].fillna("LOW").apply(lambda r: 1 if str(r).upper() == "HIGH" else 0)
    
    # Calculate user average spends for amount_spike
    user_avgs = df[df["is_fraud_label"] == 0].groupby("sender_id")["amount"].mean().to_dict()
    df["user_avg"] = df["sender_id"].map(user_avgs).fillna(1000.0)
    df["amount_spike"] = (df["amount"] > 3.0 * df["user_avg"]).astype(int)
    
    df["city_mismatch"] = (df["city"].str.strip().str.lower() != df["home_city"].fillna("").str.strip().str.lower()).astype(int)
    # New payee heuristic: if receiver upi occurs < 3 times for that user
    freq = df.groupby(["sender_id", "receiver_upi"])["id"].transform("count")
    df["new_payee"] = (freq <= 2).astype(int)
    # In historical txns, suspicious_link is proxy of high-risk merchant or note with http
    df["suspicious_link"] = df["high_risk_merchant"]

    total = len(df)
    fraud_cnt = int(df["is_fraud_label"].sum())
    legit_cnt = total - fraud_cnt

    # Laplace smoothed priors
    p_fraud = (fraud_cnt + 1) / (total + 2)
    p_legit = (legit_cnt + 1) / (total + 2)

    features = ["night", "new_device", "high_risk_merchant", "amount_spike", "city_mismatch", "new_payee", "suspicious_link"]
    likelihoods = {}

    for f in features:
        f_in_fraud = int(((df[f] == 1) & (df["is_fraud_label"] == 1)).sum())
        f_in_legit = int(((df[f] == 1) & (df["is_fraud_label"] == 0)).sum())

        p_1_given_fraud = (f_in_fraud + 1) / (fraud_cnt + 2)
        p_1_given_legit = (f_in_legit + 1) / (legit_cnt + 2)

        likelihoods[f] = {
            "p_1_given_fraud": p_1_given_fraud,
            "p_0_given_fraud": 1.0 - p_1_given_fraud,
            "p_1_given_legit": p_1_given_legit,
            "p_0_given_legit": 1.0 - p_1_given_legit
        }

    return {
        "p_fraud": p_fraud,
        "p_legit": p_legit,
        "fraud_count": fraud_cnt,
        "legit_count": legit_cnt,
        "likelihoods": likelihoods
    }

_CACHED_BAYES_MODEL = None

def get_bayes_model():
    global _CACHED_BAYES_MODEL
    if _CACHED_BAYES_MODEL is None:
        _CACHED_BAYES_MODEL = compute_bayes_model()
    return _CACHED_BAYES_MODEL

def predict_bayes(evidence_dict):
    """
    Computes P(Fraud | Evidence) with Laplace smoothing and trace steps.
    evidence_dict keys: night, new_device, high_risk_merchant, amount_spike, city_mismatch, new_payee, suspicious_link (values 0 or 1)
    """
    model = get_bayes_model()
    if not model:
        return {"probability": 0.08, "steps": ["Bayes model uninitialized"]}

    like_fraud = model["p_fraud"]
    like_legit = model["p_legit"]

    steps = [
        f"Prior P(Fraud=1): {model['p_fraud']:.4f} | Prior P(Legit=1): {model['p_legit']:.4f} (Laplace alpha=1)"
    ]

    features = ["night", "new_device", "high_risk_merchant", "amount_spike", "city_mismatch", "new_payee", "suspicious_link"]
    for f in features:
        val = int(evidence_dict.get(f, 0))
        cond_f = model["likelihoods"][f]["p_1_given_fraud"] if val == 1 else model["likelihoods"][f]["p_0_given_fraud"]
        cond_l = model["likelihoods"][f]["p_1_given_legit"] if val == 1 else model["likelihoods"][f]["p_0_given_legit"]

        like_fraud *= cond_f
        like_legit *= cond_l

        steps.append(f"Evidence '{f}'={val} -> P(E|Fraud)={cond_f:.4f}, P(E|Legit)={cond_l:.4f}")

    total = like_fraud + like_legit
    posterior = like_fraud / total if total > 0 else 0.0

    steps.append(f"Joint Numerator: Fraud={like_fraud:.6e}, Legit={like_legit:.6e}")
    steps.append(f"Posterior P(Fraud | Evidence) = {posterior:.4f}")

    return {
        "probability": round(float(posterior), 4),
        "steps": steps,
        "evidence": evidence_dict
    }
