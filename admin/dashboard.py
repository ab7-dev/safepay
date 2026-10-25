import json
import os
import sys
import pandas as pd
import streamlit as st

# Setup path to import core
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from core import db

st.set_page_config(page_title="SafePay Admin - AI Shield Intel", page_icon="🛡️", layout="wide")

st.title("🛡️ SafePay Admin Intel & AI Diagnostics")
st.caption("Monitoring Multi-Vector Fraud Mitigation Models & Security Event Telemetry")

tab_metrics, tab_txns, tab_threats = st.tabs(["📈 Model Metrics (CO5)", "💳 Transaction Telemetry", "🚨 Shield Alerts & Scans"])

with tab_metrics:
    metrics_path = os.path.join(BASE_DIR, "models", "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics = json.load(f)

        st.subheader(f"Best Production Classifier: {metrics.get('best_model')}")
        rf = metrics.get("random_forest", {})
        hgb = metrics.get("hist_gradient_boosting", {})

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("RF Accuracy", f"{rf.get('accuracy', 0)*100:.2f}%")
        col2.metric("RF Precision", f"{rf.get('precision', 0)*100:.2f}%")
        col3.metric("RF Recall", f"{rf.get('recall', 0)*100:.2f}%")
        col4.metric("RF F1 Score", f"{rf.get('f1', 0):.4f}")
        col5.metric("RF PR-AUC", f"{rf.get('pr_auc', 0):.4f}")

        rf_cv = rf.get("cv_metrics", {})
        if rf_cv:
            st.caption(f"5-Fold Stratified CV: F1 = {rf_cv.get('f1', {}).get('mean', 0):.4f} ± {rf_cv.get('f1', {}).get('std', 0):.4f} | PR-AUC = {rf_cv.get('pr_auc', {}).get('mean', 0):.4f} ± {rf_cv.get('pr_auc', {}).get('std', 0):.4f}")

        st.markdown("---")
        c_left, c_right = st.columns(2)
        with c_left:
            st.write("**Random Forest Confusion Matrix**")
            cm_rf = pd.DataFrame(rf.get("confusion_matrix", [[0,0],[0,0]]), index=["Actual Legit", "Actual Fraud"], columns=["Pred Legit", "Pred Fraud"])
            st.dataframe(cm_rf, use_container_width=True)

        with c_right:
            st.write("**HistGradientBoosting Confusion Matrix**")
            cm_hgb = pd.DataFrame(hgb.get("confusion_matrix", [[0,0],[0,0]]), index=["Actual Legit", "Actual Fraud"], columns=["Pred Legit", "Pred Fraud"])
            st.dataframe(cm_hgb, use_container_width=True)

        if "feature_importances" in rf:
            st.subheader("Feature Importance Breakdown")
            fi_df = pd.DataFrame(list(rf["feature_importances"].items()), columns=["Feature", "Importance"]).sort_values("Importance", ascending=True)
            st.bar_chart(fi_df.set_index("Feature"))

        st.markdown("---")
        st.subheader("🌐 URL Phishing & 💬 NLP Message Models")
        col_url, col_msg = st.columns(2)

        url_m = metrics.get("url_model", {})
        msg_m = metrics.get("text_model", {})
        heldout = metrics.get("heldout", {})
        ho_url = heldout.get("url_model", {})
        ho_msg = heldout.get("text_model", {})

        with col_url:
            st.write("### URL Phishing Classifier")
            st.write(f"- **Validation F1:** {url_m.get('f1', 0):.4f} (Acc: {url_m.get('accuracy', 0)*100:.1f}%)")
            st.write(f"- **Held-Out F1:** {ho_url.get('f1', 0):.4f} (Acc: {ho_url.get('accuracy', 0)*100:.1f}%)")
            if "confusion_matrix" in ho_url:
                cm_url = pd.DataFrame(ho_url["confusion_matrix"], index=["Legit URL", "Phish URL"], columns=["Pred Legit", "Pred Phish"])
                st.write("**Held-Out Confusion Matrix**")
                st.dataframe(cm_url, use_container_width=True)

        with col_msg:
            st.write("### NLP Message Scam Classifier")
            st.write(f"- **Validation F1:** {msg_m.get('f1', 0):.4f} (Acc: {msg_m.get('accuracy', 0)*100:.1f}%)")
            st.write(f"- **Held-Out F1:** {ho_msg.get('f1', 0):.4f} (Acc: {ho_msg.get('accuracy', 0)*100:.1f}%)")
            if "confusion_matrix" in ho_msg:
                cm_msg = pd.DataFrame(ho_msg["confusion_matrix"], index=["Legit Msg", "Scam Msg"], columns=["Pred Legit", "Pred Scam"])
                st.write("**Held-Out Confusion Matrix**")
                st.dataframe(cm_msg, use_container_width=True)
    else:
        st.warning("No metrics.json found. Run 'python train.py' to generate model artifacts.")

with tab_txns:
    conn = db.get_connection()
    tx_df = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC LIMIT 500", conn)
    conn.close()

    if not tx_df.empty:
        total = len(tx_df)
        blocked = len(tx_df[tx_df["status"] == "BLOCKED"])
        st.write(f"Auditing recent {total} transactions ({blocked} blocked, {blocked/total*100:.1f}%)")
        st.dataframe(tx_df[["id", "sender_id", "receiver_name", "amount", "status", "risk_score", "decision", "city", "ts"]], use_container_width=True)
    else:
        st.info("No transaction data available.")

with tab_threats:
    conn = db.get_connection()
    alerts_df = pd.read_sql_query("SELECT * FROM alerts ORDER BY id DESC LIMIT 100", conn)
    scans_df = pd.read_sql_query("SELECT * FROM link_scans ORDER BY id DESC LIMIT 100", conn)
    conn.close()

    st.subheader("Active Security Alerts")
    st.dataframe(alerts_df, use_container_width=True)

    st.subheader("Shield URL / Link Scans")
    st.dataframe(scans_df, use_container_width=True)
