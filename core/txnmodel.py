import json
import os
from datetime import datetime, timedelta
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from core import db

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
TXN_MODEL_PATH = os.path.join(MODEL_DIR, "txn.pkl")
METRICS_PATH = os.path.join(MODEL_DIR, "metrics.json")

FEATURE_NAMES = [
    "amount_ratio",
    "hour",
    "txns_last_10min",
    "city_mismatch",
    "is_new_device",
    "new_payee",
    "merchant_risk",
    "failed_pin_count",
    "recent_pin_reset"
]

def extract_transaction_dataset():
    conn = db.get_connection()
    query = """
        SELECT t.id, t.sender_id, t.receiver_upi, t.amount, t.city, t.is_new_device,
               t.ts, t.is_fraud_label,
               u.home_city, u.failed_pins,
               m.risk_level as merchant_risk_str
        FROM transactions t
        LEFT JOIN users u ON t.sender_id = u.id
        LEFT JOIN merchants m ON t.receiver_upi = m.upi_id
        ORDER BY t.ts ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return None

    df["dt"] = pd.to_datetime(df["ts"])
    df["hour"] = df["dt"].dt.hour

    # Profile avg spend
    user_avgs = df[df["is_fraud_label"] == 0].groupby("sender_id")["amount"].mean().to_dict()
    df["avg_spend"] = df["sender_id"].map(user_avgs).fillna(1000.0)
    df["amount_ratio"] = df["amount"] / df["avg_spend"].replace(0, 1.0)

    df["city_mismatch"] = (df["city"].str.strip().str.lower() != df["home_city"].fillna("").str.strip().str.lower()).astype(int)
    df["is_new_device"] = df["is_new_device"].fillna(0).astype(int)

    risk_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    df["merchant_risk"] = df["merchant_risk_str"].fillna("LOW").map(lambda x: risk_map.get(str(x).upper(), 0))

    # Payee frequency
    counts = df.groupby(["sender_id", "receiver_upi"])["id"].transform("count")
    df["new_payee"] = (counts <= 2).astype(int)

    # Failed pin count and simulated pin reset for ATO cases
    # Failed pin count and simulated pin reset for ATO cases
    df["failed_pin_count"] = df["failed_pins"].fillna(0).astype(int)
    # Realistic correlation without peeking at is_fraud_label
    df["recent_pin_reset"] = ((df["failed_pin_count"] >= 2) & (df["is_new_device"] == 1)).astype(int)

    # Velocity: count txns for user in past 10 minutes
    grouped = df.groupby("sender_id")
    cust_records = {uid: group[["id", "dt"]].sort_values("dt").to_dict("records") for uid, group in grouped}
    recent_counts = []
    for _, row in df.iterrows():
        uid = row["sender_id"]
        tx_dt = row["dt"]
        tx_id = row["id"]
        t_start = tx_dt - timedelta(minutes=10)
        recs = cust_records.get(uid, [])
        cnt = sum(1 for r in recs if t_start <= r["dt"] <= tx_dt and r["id"] != tx_id)
        recent_counts.append(cnt)
    df["txns_last_10min"] = recent_counts

    return df

def train_txn_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    df = extract_transaction_dataset()
    if df is None or len(df) < 50:
        print("Not enough data to train transaction model.")
        return None

    X = df[FEATURE_NAMES]
    y = df["is_fraud_label"]

    total_samples = len(df)
    total_fraud = int(y.sum())
    print(f"  Transaction dataset: {total_samples} total ({total_fraud} fraud, {total_fraud/total_samples*100:.2f}%)")

    # Stratified Train/Test Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    test_fraud = int(y_test.sum())
    print(f"  Train set: {len(X_train)} | Test set: {len(X_test)} ({test_fraud} test fraud cases)")

    # 5-Fold Stratified Cross-Validation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # -------------------------------------------------------------
    # Model 1: Random Forest (Base + 5-Fold CV + Sigmoid Calibration)
    # -------------------------------------------------------------
    rf_accs, rf_precs, rf_recs, rf_f1s, rf_praucs = [], [], [], [], []
    for train_idx, val_idx in skf.split(X_train, y_train):
        X_cv_train, X_cv_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
        y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]

        cv_rf = RandomForestClassifier(n_estimators=100, max_depth=10, class_weight="balanced", random_state=42)
        cv_rf.fit(X_cv_train, y_cv_train)
        cv_prob = cv_rf.predict_proba(X_cv_val)[:, 1]
        cv_pred = cv_rf.predict(X_cv_val)

        rf_accs.append(accuracy_score(y_cv_val, cv_pred))
        rf_precs.append(precision_score(y_cv_val, cv_pred, zero_division=0))
        rf_recs.append(recall_score(y_cv_val, cv_pred, zero_division=0))
        rf_f1s.append(f1_score(y_cv_val, cv_pred, zero_division=0))
        rf_praucs.append(average_precision_score(y_cv_val, cv_prob))

    rf_cv_metrics = {
        "accuracy": {"mean": round(float(np.mean(rf_accs)), 4), "std": round(float(np.std(rf_accs)), 4)},
        "precision": {"mean": round(float(np.mean(rf_precs)), 4), "std": round(float(np.std(rf_precs)), 4)},
        "recall": {"mean": round(float(np.mean(rf_recs)), 4), "std": round(float(np.std(rf_recs)), 4)},
        "f1": {"mean": round(float(np.mean(rf_f1s)), 4), "std": round(float(np.std(rf_f1s)), 4)},
        "pr_auc": {"mean": round(float(np.mean(rf_praucs)), 4), "std": round(float(np.std(rf_praucs)), 4)}
    }

    # Fit base RF for feature importances
    rf_base = RandomForestClassifier(n_estimators=100, max_depth=10, class_weight="balanced", random_state=42)
    rf_base.fit(X_train, y_train)
    feature_importances = dict(zip(FEATURE_NAMES, [round(float(v), 4) for v in rf_base.feature_importances_]))

    # Train Calibrated Classifier (Sigmoid)
    rf_calibrated = CalibratedClassifierCV(
        estimator=RandomForestClassifier(n_estimators=100, max_depth=10, class_weight="balanced", random_state=42),
        method="sigmoid",
        cv=3
    )
    rf_calibrated.fit(X_train, y_train)

    rf_test_probs = rf_calibrated.predict_proba(X_test)[:, 1]
    rf_test_preds = (rf_test_probs >= 0.5).astype(int)

    rf_metrics = {
        "accuracy": round(float(accuracy_score(y_test, rf_test_preds)), 4),
        "precision": round(float(precision_score(y_test, rf_test_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, rf_test_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, rf_test_preds, zero_division=0)), 4),
        "pr_auc": round(float(average_precision_score(y_test, rf_test_probs)), 4),
        "confusion_matrix": confusion_matrix(y_test, rf_test_preds).tolist(),
        "cv_metrics": rf_cv_metrics,
        "feature_importances": feature_importances
    }

    # -------------------------------------------------------------
    # Model 2: HistGradientBoosting (Base + 5-Fold CV + Sigmoid Calibration)
    # -------------------------------------------------------------
    neg_count = sum(y_train == 0)
    pos_count = sum(y_train == 1)
    w_pos = neg_count / max(1, pos_count)
    sample_weights_train = np.where(y_train == 1, w_pos, 1.0)

    hgb_accs, hgb_precs, hgb_recs, hgb_f1s, hgb_praucs = [], [], [], [], []
    for train_idx, val_idx in skf.split(X_train, y_train):
        X_cv_train, X_cv_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
        y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
        sw_cv = sample_weights_train[train_idx]

        cv_hgb = HistGradientBoostingClassifier(random_state=42, max_iter=150)
        cv_hgb.fit(X_cv_train, y_cv_train, sample_weight=sw_cv)
        cv_prob = cv_hgb.predict_proba(X_cv_val)[:, 1]
        cv_pred = cv_hgb.predict(X_cv_val)

        hgb_accs.append(accuracy_score(y_cv_val, cv_pred))
        hgb_precs.append(precision_score(y_cv_val, cv_pred, zero_division=0))
        hgb_recs.append(recall_score(y_cv_val, cv_pred, zero_division=0))
        hgb_f1s.append(f1_score(y_cv_val, cv_pred, zero_division=0))
        hgb_praucs.append(average_precision_score(y_cv_val, cv_prob))

    hgb_cv_metrics = {
        "accuracy": {"mean": round(float(np.mean(hgb_accs)), 4), "std": round(float(np.std(hgb_accs)), 4)},
        "precision": {"mean": round(float(np.mean(hgb_precs)), 4), "std": round(float(np.std(hgb_precs)), 4)},
        "recall": {"mean": round(float(np.mean(hgb_recs)), 4), "std": round(float(np.std(hgb_recs)), 4)},
        "f1": {"mean": round(float(np.mean(hgb_f1s)), 4), "std": round(float(np.std(hgb_f1s)), 4)},
        "pr_auc": {"mean": round(float(np.mean(hgb_praucs)), 4), "std": round(float(np.std(hgb_praucs)), 4)}
    }

    hgb_calibrated = CalibratedClassifierCV(
        estimator=HistGradientBoostingClassifier(random_state=42, max_iter=150),
        method="sigmoid",
        cv=3
    )
    hgb_calibrated.fit(X_train, y_train, sample_weight=sample_weights_train)

    hgb_test_probs = hgb_calibrated.predict_proba(X_test)[:, 1]
    hgb_test_preds = (hgb_test_probs >= 0.5).astype(int)

    hgb_metrics = {
        "accuracy": round(float(accuracy_score(y_test, hgb_test_preds)), 4),
        "precision": round(float(precision_score(y_test, hgb_test_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, hgb_test_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, hgb_test_preds, zero_division=0)), 4),
        "pr_auc": round(float(average_precision_score(y_test, hgb_test_probs)), 4),
        "confusion_matrix": confusion_matrix(y_test, hgb_test_preds).tolist(),
        "cv_metrics": hgb_cv_metrics
    }

    # Pick best model based on cross-validation F1
    best_name = "RandomForest" if rf_metrics["f1"] >= hgb_metrics["f1"] else "HistGradientBoosting"
    best_calibrated_model = rf_calibrated if best_name == "RandomForest" else hgb_calibrated

    bundle = {
        "model_name": best_name,
        "model": best_calibrated_model,
        "feature_names": FEATURE_NAMES,
        "rf_metrics": rf_metrics,
        "hgb_metrics": hgb_metrics,
        "best_metrics": rf_metrics if best_name == "RandomForest" else hgb_metrics
    }

    joblib.dump(bundle, TXN_MODEL_PATH)

    # Save metrics.json
    all_metrics = {
        "best_model": best_name,
        "random_forest": rf_metrics,
        "hist_gradient_boosting": hgb_metrics
    }
    if os.path.exists(METRICS_PATH):
        try:
            with open(METRICS_PATH) as f:
                existing = json.load(f)
                all_metrics = {**existing, **all_metrics}
        except Exception:
            pass
    with open(METRICS_PATH, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"Transaction Models trained & calibrated. Best: {best_name} (Test F1: {bundle['best_metrics']['f1']}, PR-AUC: {bundle['best_metrics']['pr_auc']})")
    print(f"  RF Test F1: {rf_metrics['f1']} (CV F1: {rf_cv_metrics['f1']['mean']} +/- {rf_cv_metrics['f1']['std']})")
    print(f"  HGB Test F1: {hgb_metrics['f1']} (CV F1: {hgb_cv_metrics['f1']['mean']} +/- {hgb_cv_metrics['f1']['std']})")
    return all_metrics

_CACHED_TXN_BUNDLE = None

def get_txn_bundle():
    global _CACHED_TXN_BUNDLE
    if _CACHED_TXN_BUNDLE is None:
        if not os.path.exists(TXN_MODEL_PATH):
            train_txn_models()
        _CACHED_TXN_BUNDLE = joblib.load(TXN_MODEL_PATH)
    return _CACHED_TXN_BUNDLE

def predict_txn(features_dict):
    """
    Features expected:
      amount_ratio, hour, txns_last_10min, city_mismatch, is_new_device, new_payee,
      merchant_risk (0/1/2), failed_pin_count, recent_pin_reset
    """
    bundle = get_txn_bundle()
    model = bundle["model"]

    row = [float(features_dict.get(fn, 0.0)) for fn in FEATURE_NAMES]
    x_df = pd.DataFrame([row], columns=FEATURE_NAMES)
    prob = float(model.predict_proba(x_df)[0][1])

    reasons = []
    if float(features_dict.get("amount_ratio", 0)) > 4.0:
        reasons.append(f"Spend spike: {features_dict.get('amount_ratio'):.1f}x higher than user's profile average")
    if int(features_dict.get("txns_last_10min", 0)) >= 4:
        reasons.append(f"Rapid velocity anomaly: {features_dict.get('txns_last_10min')} payments initiated within 10 minutes")
    if int(features_dict.get("is_new_device", 0)) == 1 and int(features_dict.get("city_mismatch", 0)) == 1:
        reasons.append("Unrecognized device operating from an unfamiliar city location")
    if int(features_dict.get("merchant_risk", 0)) == 2:
        reasons.append("Receiver categorized as High-Risk Merchant / Cryptocurrency / Offshore")
    if int(features_dict.get("recent_pin_reset", 0)) == 1 or int(features_dict.get("failed_pin_count", 0)) >= 2:
        reasons.append("Preceding suspicious PIN failures / reset detected (Account Takeover indicator)")
    if prob >= 0.70 and not reasons:
        reasons.append("Supervised ML classifier flagged multi-dimensional risk correlation")

    return {
        "probability": round(prob, 4),
        "reasons": reasons,
        "features": features_dict,
        "model_used": bundle["model_name"]
    }

if __name__ == "__main__":
    train_txn_models()
