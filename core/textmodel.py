import os
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
TEXT_MODEL_PATH = os.path.join(MODEL_DIR, "text.pkl")

SCAM_KEYWORDS = [
    "urgent", "kyc", "block", "blocked", "suspend", "lottery", "cashback", "winner",
    "refund", "pan", "aadhaar", "immediately", "turant", "overdue", "cut", "claim",
    "expire", "expiring", "reward", "congratulations", "bonus", "unpaid", "customs",
    "wire", "emergency", "bhejo", "band", "penalty", "varna", "secret", "otp"
]

def generate_training_texts():
    """Generates 1600+ synthetic messages with diverse scam, Hinglish, typo, and benign templates."""
    import random
    random.seed(42)

    scam_templates = [
        "Dear customer, your bank account will be blocked today. Update KYC immediately.",
        "Congratulations! You won Rs {amt} cash prize in lucky draw. Claim reward now.",
        "Aapka electricity bill overdue hai Rs {amt}. Aaj raat connection cut hoga. Turant bill pay karein.",
        "Urgent: Your Credit Card is suspended due to PAN linking failure. Verify now.",
        "Part time job: Earn Rs 5000 daily by watching videos. Pay registration fee {amt}.",
        "Dear taxpayer, income tax refund of Rs {amt} is approved. Confirm bank details.",
        "Your SIM card will be deactivated within 24 hours. Call customer care or update KYC.",
        "Parcel #IN9921 is held at customs warehouse due to unpaid clearance fee Rs {amt}.",
        "Bhai emergency hospital admit hai, turant {amt} bhej de is UPI ID par.",
        "I am in meeting. Please wire urgent vendor payment of Rs {amt} to new bank account immediately.",
        "Your Paytm voucher is expiring in 2 hours. Redeem cash reward immediately.",
        "100 USDT free airdrop credited to your wallet. Claim before pool closes.",
        "NPCI auto refund of Rs {amt} failed. Enter UPI PIN to receive money in account.",
        "Aapka 4G SIM band ho jayega. Free 5G activation ke liye turant link par click karein.",
        "SpeedPost: Address incomplete. Pay Rs 35 redelivery fee to avoid return to sender.",
        "Pre-approved personal loan of Rs 5 Lakh credited. Verify OTP to disburse funds.",
        "SBI Netbanking access suspended. Click link to re-verify your PAN and Aadhaar.",
        "HDFC Alert: Unauthorized transaction of Rs {amt} attempted. Cancel immediately here.",
        "Traffic Police: E-challan #{digit} unpaid. Pay fine Rs {amt} immediately to avoid arrest warrant.",
        "Dear EPFO member, your PF withdrawal of Rs {amt} approved. Update bank KYC now.",
        "Your Netflix subscription has expired. Update credit card details to avoid suspension.",
        "Electricity Department: Power disconnection notice generated for consumer #{digit}. Pay Rs {amt} now.",
        "Courier delivery alert: Consignment #{digit} on hold. Pay customs duty Rs {amt}.",
        "Special Festive Cashback: You have earned scratch card of Rs {amt}. Claim into bank now.",
        "Account alert: Security breach detected in your banking app. Install security patch immediately."
    ]

    hinglish_scam_templates = [
        "Aapka bijli bill overdue hai Rs {amt}. Aaj raat 9 baje connection cut ho jayega. Turant pay karein.",
        "SBI customer dhyan de: aapka khata band ho gaya hai, turant kyc update kare varna account freeze hoga.",
        "Bhai emergency hospital me hu, turant {amt} bhej de is UPI ID pe, shaam ko return kar dunga.",
        "Aapka 4G SIM band ho jayega 24 ghante me. Free 5G upgrade ke liye turant verify karein.",
        "GPay lucky winner: Aapko mila hai Rs {amt} ka cash prize. Abhi accept karein.",
        "Police notice: aapke naam par illegal parcel customs me pakda gaya hai, turant contact karein.",
        "Aapki KBC lottery lagi hai Rs {amt} ki. Registration fee deposit karke claim karein.",
        "Traffic challan Rs {amt} baki hai. Court challan se bachne ke liye abhi pay karein.",
        "Bank account me aadhar link nahi hai. Aaj hi link kare nahi to aavedan radd ho jayega.",
        "Mummy ki tabiyat kharab hai advance deposit mang rahe hai hospital wale, jaldi se {amt} bhej do."
    ]

    typo_scam_templates = [
        "Urgnt: Ur bank acct will be blcked today. Updat KYCC immedately.",
        "Congratulation! U won Rs {amt} lottry rewrd. Clam cshback now.",
        "Aapka bijli bil pending hai Rs {amt}. Aaj rat conection cut hoga. Turnt bhej do.",
        "Dear customr, incme tax refnd Rs {amt} aprved. Confrim bank detals.",
        "Urgentt: Credit Card suspendd due to PAN faillure. Verfy now.",
        "Sim deactivatd within 12 hrs. Call custmer suprt or link aadhar card.",
        "Prcl held at custms offce. Pay clearance chrges Rs {amt} to rlease.",
        "NPCI autoo refnd Rs {amt}. Entre UPI PIN to recve money.",
        "Incom tax offce notice: Penaltee of Rs {amt} levied. Clearr immediatelyy.",
        "Pre-aprovd loann Rs 3 Lakh credted. Verfy OТак to disburs fund."
    ]

    benign_templates = [
        "Dear customer, your account ending {digit} is credited with INR {amt} by NEFT. Available balance is INR {amt2}.",
        "{digit} is your secret OTP for transaction at Swiggy. NEVER share OTP with anyone.",
        "Thank you for ordering with Swiggy! Total paid: Rs {amt} via UPI. Enjoy your meal.",
        "Hey! Split for yesterday dinner was Rs {amt}. Pay whenever free to upi id.",
        "PNR 4529182390 Confirmed. Train 12675 KOVAI EXP. Departure 06:10 from MAS.",
        "Your package containing Wireless Mouse has shipped and will arrive tomorrow by Amazon.",
        "INR {amt} debited from your savings account at ATM Coimbatore. If not you, contact bank.",
        "Hey! Here are the high-resolution trip photos from our weekend vacation.",
        "Recharge of Rs 299 for Jio mobile is successful. 1.5GB daily data activated.",
        "Your ITR-1 for AY 2026-27 has been successfully filed and verified. Thank you.",
        "Your trip with Uber was Rs {amt}. Thank you for riding with Uber.",
        "Doctor appointment confirmed for tomorrow 10:30 AM at Apollo Medical Center.",
        "Meeting rescheduled to 4 PM in Board Room B. Please bring updated financial reports.",
        "Monthly electricity bill for meter #8912 is Rs {amt}. Due date is 25th of this month.",
        "Salary slip for July 2026 is ready for download from company employee portal.",
        "Movie tickets confirmed for tonight 7:30 PM at PVR Cinemas Screen 3.",
        "Gym membership renewal successful for 12 months. Welcome to CultFit.",
        "Your grocery order from BigBasket has been packed and out for delivery.",
        "Flight 6E-2415 BLR to DEL is on schedule. Web check-in closes in 2 hours.",
        "Dear customer, maintenance charges for Flat #{digit} Rs {amt} received with thanks.",
        "College notice: Semester end project submissions due this Friday by 5 PM.",
        "Hey bro, are we playing football today evening at the turf?",
        "Zomato delivery partner is arriving in 5 mins. Please be available at door.",
        "Your mutual fund SIP of Rs {amt} has been successfully executed.",
        "Reminder: Library book 'Clean Architecture' is due for return on Monday."
    ]

    hinglish_benign_templates = [
        "Bhai kal sham ko cricket khelne chalte hai ground par, 5 baje aa jana.",
        "Mummy bol rahi hai aate waqt dahi aur bread le aana grocery shop se.",
        "Kal ka morning lecture cancel ho gaya hai, direct 11 baje lab hai.",
        "Dinner ka kya plan hai aaj, bahar chal rahe hai ya ghar par order karein?",
        "Maine movie tickets book kar di hai Sunday 4 baje ki PVR me.",
        "Bhai project report ka final PDF bhej dena review ke liye.",
        "Ghar pahunch gaya hu, sab theek hai, kal baat karte hai.",
        "Kal test ke liye notes bhej de WhatsApp pe agar tere paas hai to."
    ]

    texts, labels = [], []

    # Generate 450 standard scam variations
    for _ in range(450):
        t = random.choice(scam_templates)
        text = t.format(
            amt=random.choice([499, 1420, 4999, 12500, 48000, 24500, 8500, 3500]),
            digit=random.randint(1000, 9999),
            amt2=random.randint(50000, 95000)
        )
        texts.append(text)
        labels.append(1)

    # Generate 200 Hinglish scam variations
    for _ in range(200):
        t = random.choice(hinglish_scam_templates)
        text = t.format(
            amt=random.choice([500, 1420, 2500, 5000, 10000, 25000]),
            digit=random.randint(1000, 9999)
        )
        texts.append(text)
        labels.append(1)

    # Generate 150 Typo scam variations
    for _ in range(150):
        t = random.choice(typo_scam_templates)
        text = t.format(
            amt=random.choice([499, 1200, 4999, 15000]),
            digit=random.randint(1000, 9999)
        )
        texts.append(text)
        labels.append(1)

    # Total scams = 800

    # Generate 600 standard benign variations
    for _ in range(600):
        t = random.choice(benign_templates)
        text = t.format(
            amt=random.choice([150, 420, 1299, 3500, 5000, 12500]),
            digit=random.randint(1000, 9999),
            amt2=random.randint(30000, 85000)
        )
        texts.append(text)
        labels.append(0)

    # Generate 200 Hinglish benign variations
    for _ in range(200):
        t = random.choice(hinglish_benign_templates)
        texts.append(t)
        labels.append(0)

    # Total benign = 800. Overall dataset = 1600 samples

    # Add 2% label noise for realism
    for i in range(len(labels)):
        if random.random() < 0.02:
            labels[i] = 1 - labels[i]

    return texts, labels

def train_text_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    texts, labels = generate_training_texts()
    print(f"  Text training set: {len(texts)} samples ({sum(labels)} scam)")

    word_vec = TfidfVectorizer(ngram_range=(1, 2), max_features=1000)
    char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=1000)
    union = FeatureUnion([("word", word_vec), ("char", char_vec)])

    X = union.fit_transform(texts)
    y = np.array(labels)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = LogisticRegression(max_iter=1000, C=2.0, class_weight="balanced", random_state=42)
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

    joblib.dump({"pipeline": union, "classifier": clf, "metrics": metrics}, TEXT_MODEL_PATH)
    print(f"Text Model trained & saved. Metrics: Acc={metrics['accuracy']}, F1={metrics['f1']}")
    return metrics

_CACHED_TEXT_BUNDLE = None

def get_text_bundle():
    global _CACHED_TEXT_BUNDLE
    if _CACHED_TEXT_BUNDLE is None:
        if not os.path.exists(TEXT_MODEL_PATH):
            train_text_model()
        _CACHED_TEXT_BUNDLE = joblib.load(TEXT_MODEL_PATH)
    return _CACHED_TEXT_BUNDLE

def predict_text(message_text):
    if not message_text or not str(message_text).strip():
        return {"probability": 0.0, "reasons": [], "top_words": []}

    bundle = get_text_bundle()
    pipe = bundle["pipeline"]
    clf = bundle["classifier"]

    text_lower = str(message_text).lower()
    x = pipe.transform([message_text])
    prob = float(clf.predict_proba(x)[0][1])

    detected_keywords = [kw for kw in SCAM_KEYWORDS if kw in text_lower]

    reasons = []
    if any(k in detected_keywords for k in ["urgent", "turant", "immediately", "overdue", "expiring"]):
        reasons.append("Psychological urgency and high-pressure coercion detected")
    if any(k in detected_keywords for k in ["kyc", "pan", "aadhaar", "block", "blocked", "suspend", "cut"]):
        reasons.append("Account deactivation and credential intimidation language")
    if any(k in detected_keywords for k in ["lottery", "cashback", "winner", "reward", "prize"]):
        reasons.append("Unsolicited lottery / cash reward bait pattern")
    if any(k in detected_keywords for k in ["secret", "otp"]):
        reasons.append("Social engineering request targeting secret OTP / credentials")
    if any(k in detected_keywords for k in ["wire", "bhejo", "emergency"]):
        reasons.append("Urgent peer transfer or CEO wire compromise indicator")

    if prob >= 0.70 and not reasons:
        reasons.append("NLP classifier flagged suspicious scam syntax and token combination")

    return {
        "probability": round(prob, 4),
        "reasons": reasons,
        "top_words": detected_keywords[:6],
        "metrics": bundle.get("metrics", {})
    }

if __name__ == "__main__":
    train_text_model()
