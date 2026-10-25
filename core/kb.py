import ast
import operator
from datetime import datetime
from core import db

ALLOWED_VARIABLES = {
    "domain_in_blocklist",
    "suspicious_tld",
    "ip_host",
    "has_urgency_words",
    "has_payment_link",
    "amount",
    "avg_spend",
    "merchant_risk",
    "is_new_payee",
    "vpa_brand_lookalike",
    "receiver_not_verified",
    "is_collect_request",
    "is_new_device",
    "city_mismatch",
    "recent_failed_pins",
    "dispute_ratio",
    "is_first_time_payee",
    "hour",
}

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

def _safe_eval_node(node, ctx):
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, ctx)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_safe_eval_node(v, ctx) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_safe_eval_node(v, ctx) for v in node.values)
        raise ValueError(f"Unsupported bool op: {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _safe_eval_node(node.operand, ctx)
        if isinstance(node.op, ast.USub):
            return -_safe_eval_node(node.operand, ctx)
        raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left, ctx)
        for op_node, comparator in zip(node.ops, node.comparators):
            op_cls = type(op_node)
            if op_cls not in SAFE_OPS:
                raise ValueError(f"Unsupported compare op: {op_cls.__name__}")
            right = _safe_eval_node(comparator, ctx)
            if not SAFE_OPS[op_cls](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BinOp):
        op_cls = type(node.op)
        if op_cls not in SAFE_OPS:
            raise ValueError(f"Unsupported binary op: {op_cls.__name__}")
        left = _safe_eval_node(node.left, ctx)
        right = _safe_eval_node(node.right, ctx)
        return SAFE_OPS[op_cls](left, right)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
    if isinstance(node, ast.Name):
        if node.id in ALLOWED_VARIABLES:
            return ctx.get(node.id, 0)
        raise ValueError(f"Variable '{node.id}' is not in allowed whitelist")
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")

def safe_eval_condition(condition_text, context):
    try:
        tree = ast.parse(condition_text, mode="eval")
    except SyntaxError:
        return False
    try:
        return bool(_safe_eval_node(tree, context))
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return False

def load_active_rules():
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, fraud_type, condition_text, weight FROM rules WHERE active = 1")
    rules = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rules

def evaluate_rules(context):
    """
    Forward-chaining rule evaluation on context dict.
    Returns:
      rule_score: 0.0 - 1.0 (capped normalized sum of triggered weights)
      triggered_rules: list of dicts with name, fraud_type, weight
      fraud_type: dominant fraud type or 'general'
    """
    rules = load_active_rules()
    triggered = []
    total_weight = 0.0
    type_weights = {}

    for r in rules:
        passed = safe_eval_condition(r["condition_text"], context)

        if passed:
            w = float(r["weight"])
            triggered.append({
                "id": r["id"],
                "name": r["name"],
                "fraud_type": r["fraud_type"],
                "weight": w
            })
            total_weight += w
            ft = r["fraud_type"]
            type_weights[ft] = type_weights.get(ft, 0.0) + w

    score = min(1.0, round(total_weight, 4))
    dominant_type = max(type_weights, key=type_weights.get) if type_weights else "none"

    return {
        "rule_score": score,
        "triggered_rules": triggered,
        "dominant_fraud_type": dominant_type
    }

def get_semantic_frame(user=None, txn=None, merchant=None, link=None):
    """
    Semantic frame representation of User - Transaction - Merchant - Link entities.
    """
    frame = {
        "User_Frame": {
            "ID": user.get("id") if user else None,
            "Name": user.get("name") if user else "Guest",
            "UPI": user.get("upi_id") if user else None,
            "City": user.get("home_city") if user else None
        },
        "Transaction_Frame": {
            "Amount": txn.get("amount") if txn else None,
            "ReceiverUPI": txn.get("receiver_upi") if txn else None,
            "City": txn.get("city") if txn else None,
            "DeviceID": txn.get("device_id") if txn else None,
            "IsNewDevice": txn.get("is_new_device") if txn else 0
        },
        "Merchant_Frame": {
            "Name": merchant.get("name") if merchant else None,
            "UPI": merchant.get("upi_id") if merchant else None,
            "Category": merchant.get("category") if merchant else None,
            "RiskLevel": merchant.get("risk_level") if merchant else "LOW"
        },
        "Link_Frame": {
            "URL": link.get("url") if link else None,
            "Domain": link.get("domain") if link else None,
            "IsBlocklisted": link.get("is_blocklisted") if link else False
        },
        "Semantic_Relations": []
    }

    if user and txn:
        frame["Semantic_Relations"].append(f"User({user.get('name')}) --[AUTHORIZES]--> Txn(Rs {txn.get('amount')})")
    if txn and merchant:
        frame["Semantic_Relations"].append(f"Txn(Rs {txn.get('amount')}) --[REMIT_TO]--> Merchant({merchant.get('name')})")
    if link:
        frame["Semantic_Relations"].append(f"Txn --[ACCOMPANYING_PAYLOAD]--> Link({link.get('url')})")

    return frame
