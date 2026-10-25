// SafePay PWA - Neumorphic Fintech Frontend
let currentUser = null;
let currentAccount = null;
let selectedLoginUser = null;
let loginPinBuffer = "";
let sendAmountBuffer = "0";
let sendPinBuffer = "";
let pendingPaymentPayload = null;
let deferredPrompt = null;
let activeBillPayItem = null;

// Persistent Hide Balance Single Source of Truth (Stored per user)
let balanceHidden = false;

function initUserPreferences() {
  if (!currentUser) return;
  try {
    balanceHidden = localStorage.getItem(`balanceHidden_${currentUser.id}`) === "true";
  } catch (e) {
    balanceHidden = false;
  }
  renderBalance(currentAccount ? currentAccount.balance : 0);
}

let autoRevealTimer = null;

function formatINR(val) {
  const num = parseFloat(val) || 0;
  return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ----------------- BALANCE RENDERING & EYE TOGGLE FIX -----------------

function renderBalance(rawAmount) {
  const amount = rawAmount !== undefined ? rawAmount : (currentAccount ? currentAccount.balance : 0);
  const balEl = document.getElementById("home-balance-amount");
  const histBalEl = document.getElementById("history-header-balance");
  const profBalEl = document.getElementById("profile-header-balance");
  const eyeBtn = document.getElementById("btn-toggle-balance");
  const eyeIcon = document.getElementById("eye-icon-svg");

  const displayVal = balanceHidden ? "₹ ••••••" : formatINR(amount);

  if (balEl) {
    balEl.textContent = displayVal;
    balEl.style.letterSpacing = balanceHidden ? "2px" : "-0.2px";
  }
  if (histBalEl) {
    histBalEl.textContent = displayVal;
  }
  if (profBalEl) {
    profBalEl.textContent = displayVal;
  }

  if (eyeBtn) {
    eyeBtn.setAttribute("aria-pressed", balanceHidden ? "true" : "false");
  }

  if (eyeIcon) {
    if (balanceHidden) {
      // Eye-off icon (with strike slash)
      eyeIcon.innerHTML = `
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
        <line x1="1" y1="1" x2="23" y2="23"/>
      `;
    } else {
      // Regular eye icon
      eyeIcon.innerHTML = `
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
        <circle cx="12" cy="12" r="3"/>
      `;
    }
  }
}

function toggleBalanceVisibility() {
  balanceHidden = !balanceHidden;
  if (currentUser) {
    try {
      localStorage.setItem(`balanceHidden_${currentUser.id}`, String(balanceHidden));
    } catch (e) {}
  }

  const balEl = document.getElementById("home-balance-amount");
  if (balEl) {
    balEl.style.opacity = "0.4";
    balEl.style.filter = "blur(2px)";
    setTimeout(() => {
      renderBalance();
      balEl.style.opacity = "1";
      balEl.style.filter = "none";
    }, 120);
  } else {
    renderBalance();
  }
}

// Event delegation for reliable toggle handling
document.addEventListener("click", (e) => {
  const toggleBtn = e.target.closest("#btn-toggle-balance");
  if (toggleBtn) {
    e.preventDefault();
    toggleBalanceVisibility();
  }
  // Auto-reveal for 5 seconds when tapping masked balance
  const balEl = e.target.closest("#home-balance-amount");
  if (balEl && balanceHidden) {
    balEl.textContent = formatINR(currentAccount ? currentAccount.balance : 0);
    clearTimeout(autoRevealTimer);
    autoRevealTimer = setTimeout(() => {
      renderBalance();
    }, 5000);
  }
});

// ----------------- INACTIVITY TIMER (5 MINUTES) -----------------
let inactivityTimer = null;
const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

function resetInactivityTimer() {
  if (inactivityTimer) clearTimeout(inactivityTimer);
  if (!currentUser) return;
  inactivityTimer = setTimeout(handleInactivityTimeout, INACTIVITY_TIMEOUT_MS);
}

async function handleInactivityTimeout() {
  if (!currentUser) return;
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch (e) {}
  clearUserSessionState();
  loadLoginUsers();
  navigateTo("login");
  const errEl = document.getElementById("login-error-msg");
  if (errEl) {
    errEl.textContent = "Session auto-locked due to 5 minutes of inactivity. Please sign in again.";
    errEl.style.display = "block";
  }
}

["mousedown", "mousemove", "keydown", "scroll", "touchstart", "click"].forEach((evt) => {
  window.addEventListener(evt, resetInactivityTimer, { passive: true });
});

// Clear all in-memory UI state and caches when user logs in or logs out
function clearUserSessionState() {
  currentUser = null;
  currentAccount = null;
  selectedLoginUser = null;
  allTxns = [];
  loginPinBuffer = "";
  updatePinDots("login-pin-dots", 0);

  if (inactivityTimer) {
    clearTimeout(inactivityTimer);
    inactivityTimer = null;
  }

  const idInput = document.getElementById("login-identifier-input");
  if (idInput) idInput.value = "";

  const userCard = document.getElementById("login-selected-user-card");
  if (userCard) userCard.style.display = "none";

  const balEl = document.getElementById("home-balance-amount");
  if (balEl) balEl.textContent = "₹0.00";
  const histBalEl = document.getElementById("history-header-balance");
  if (histBalEl) histBalEl.textContent = "₹0.00";
  const profBalEl = document.getElementById("profile-header-balance");
  if (profBalEl) profBalEl.textContent = "₹0.00";

  const histList = document.getElementById("history-txns-list");
  if (histList) histList.innerHTML = "";
  const inboxList = document.getElementById("inbox-messages-list");
  if (inboxList) inboxList.innerHTML = "";
  const recentAvatars = document.getElementById("home-recent-avatars");
  if (recentAvatars) recentAvatars.innerHTML = "";

  const errEl = document.getElementById("login-error-msg");
  if (errEl) {
    errEl.textContent = "";
    errEl.style.display = "none";
  }
  const lockedCard = document.getElementById("login-locked-card");
  if (lockedCard) lockedCard.style.display = "none";
}

// ----------------- NAVIGATION & TABS -----------------

function navigateTo(screenName) {
  window.location.hash = screenName;
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  const target = document.getElementById(`screen-${screenName}`);
  if (target) {
    target.classList.add("active");
  }

  // Hide bottom navigation on login screen
  const bottomNav = document.querySelector(".bottom-nav");
  if (bottomNav) {
    bottomNav.style.display = screenName === "login" ? "none" : "flex";
  }

  // Update Bottom Nav active item
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-screen") === screenName);
  });

  if (screenName === "home") loadHomeData();
  if (screenName === "inbox") loadInboxData();
  if (screenName === "history") loadHistoryData();
  if (screenName === "profile") loadProfileData();
}

window.addEventListener("hashchange", () => {
  const screen = window.location.hash.replace("#", "") || "home";
  if (currentUser) {
    navigateTo(screen);
  } else {
    navigateTo("login");
  }
});

function switchHomeTab(tab) {
  const toggle = document.getElementById("home-pill-toggle");
  const payView = document.getElementById("subview-pay");
  const shieldView = document.getElementById("subview-shield");

  if (tab === "SHIELD") {
    toggle.classList.add("shield-active");
    payView.style.display = "none";
    shieldView.style.display = "block";
  } else {
    toggle.classList.remove("shield-active");
    payView.style.display = "block";
    shieldView.style.display = "none";
  }
}

// ----------------- INITIALIZATION -----------------

async function initApp() {
  updateClock();
  setInterval(updateClock, 1000);

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btn = document.getElementById("btn-install-pwa");
    if (btn) btn.style.display = "block";
  });

  // Check Web Share Target
  const urlParams = new URLSearchParams(window.location.search);
  const sharedText = (urlParams.get("url") || "") + " " + (urlParams.get("text") || "") + " " + (urlParams.get("title") || "");
  const extracted = sharedText.match(/https?:\/\/[^\s<>"']+|www\.[^\s<>"']+/i);

  // Check current session from server: never restore user from localStorage or auto-select
  try {
    const res = await fetch("/api/me");
    if (res.ok) {
      const data = await res.json();
      currentUser = data.user;
      currentAccount = data.account;
      initUserPreferences();
      resetInactivityTimer();
      navigateTo("home");
    } else {
      clearUserSessionState();
      loadLoginUsers();
      navigateTo("login");
    }
  } catch (err) {
    clearUserSessionState();
    loadLoginUsers();
    navigateTo("login");
  }

  if (extracted) {
    setTimeout(() => {
      runShieldInspection(extracted[0], sharedText);
    }, 600);
  }
}

function updateClock() {
  const now = new Date();
  const hrs = String(now.getHours()).padStart(2, "0");
  const mins = String(now.getMinutes()).padStart(2, "0");
  const el = document.getElementById("status-clock");
  if (el) el.textContent = `${hrs}:${mins}`;
}

// ----------------- SIGN IN & SIGN UP -----------------

const AVATAR_COLORS = ["#29B6F6", "#F48FB1", "#26C6DA", "#FFCA28", "#8B5CF6", "#06B6D4", "#10B981"];

// Disabled: quickSelectPersona no longer auto-signs in without a PIN
async function quickSelectPersona(userId) {
  // Disabled as per security requirement - user must enter PIN manually
}

async function loadLoginUsers() {
  try {
    const res = await fetch("/api/users");
    const data = await res.json();
    const container = document.getElementById("login-users-list");
    if (!container) return;
    container.innerHTML = "";

    data.users.forEach((u, idx) => {
      const item = document.createElement("div");
      item.className = "avatar-square-item";
      item.style.cursor = "pointer";
      item.title = `Tap to pre-fill ${u.name} (${u.phone})`;
      item.onclick = () => selectDemoAccount(u);

      const color = AVATAR_COLORS[idx % AVATAR_COLORS.length];
      const initials = u.name.split(" ").map((n) => n[0]).join("").slice(0, 2);

      item.innerHTML = `
        <div class="avatar-square" style="background: ${color};">${initials}</div>
        <div class="avatar-square-name">${u.name.split(" ")[0]}</div>
      `;
      container.appendChild(item);
      // NOTE: Do NOT auto-select or auto-fill here!
    });
  } catch (e) {}
}

function selectDemoAccount(user) {
  selectedLoginUser = user;
  const input = document.getElementById("login-identifier-input");
  if (input) input.value = user.phone;

  const card = document.getElementById("login-selected-user-card");
  if (card) {
    card.style.display = "flex";
    const nameEl = document.getElementById("selected-user-name");
    if (nameEl) nameEl.textContent = user.name;
    const subEl = document.getElementById("selected-user-sub");
    if (subEl) subEl.textContent = `${user.upi_id} • ${user.home_city}`;
    const avEl = document.getElementById("selected-user-avatar");
    if (avEl) avEl.textContent = user.name.split(" ").map((n) => n[0]).join("").slice(0, 2);
  }

  // Reset error / locked cards
  const errEl = document.getElementById("login-error-msg");
  if (errEl) errEl.style.display = "none";
  const lockEl = document.getElementById("login-locked-card");
  if (lockEl) lockEl.style.display = "none";

  clearLoginPin();
}

function clearSelectedDemoUser() {
  selectedLoginUser = null;
  const card = document.getElementById("login-selected-user-card");
  if (card) card.style.display = "none";
  const input = document.getElementById("login-identifier-input");
  if (input) input.value = "";
  clearLoginPin();
}

function handleLoginDigit(digit) {
  if (loginPinBuffer.length < 4) {
    loginPinBuffer += digit;
    updatePinDots("login-pin-dots", loginPinBuffer.length);
    if (loginPinBuffer.length === 4) {
      setTimeout(submitLoginPin, 150);
    }
  }
}

function backspaceLoginPin() {
  if (loginPinBuffer.length > 0) {
    loginPinBuffer = loginPinBuffer.slice(0, -1);
    updatePinDots("login-pin-dots", loginPinBuffer.length);
  }
}

function clearLoginPin() {
  loginPinBuffer = "";
  updatePinDots("login-pin-dots", 0);
}

function updatePinDots(containerId, count) {
  const dots = document.querySelectorAll(`#${containerId} .pin-dot`);
  dots.forEach((dot, idx) => {
    dot.style.background = idx < count ? "var(--accent-purple)" : "var(--bg-surface-elevated)";
    dot.style.boxShadow = idx < count ? "0 0 10px var(--accent-purple-glow)" : "none";
  });
}

async function submitLoginPin() {
  const input = document.getElementById("login-identifier-input");
  const identifier = input && input.value.trim() ? input.value.trim() : (selectedLoginUser ? selectedLoginUser.phone : "");

  const errEl = document.getElementById("login-error-msg");
  const lockEl = document.getElementById("login-locked-card");

  if (!identifier) {
    if (errEl) {
      errEl.textContent = "Please enter your phone number or UPI ID, or tap a demo account below.";
      errEl.style.display = "block";
    }
    return;
  }

  if (loginPinBuffer.length !== 4) {
    if (errEl) {
      errEl.textContent = "Please enter your 4-digit PIN.";
      errEl.style.display = "block";
    }
    return;
  }

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: identifier, pin: loginPinBuffer })
    });
    const data = await res.json();

    if (res.ok) {
      clearLoginPin();
      if (errEl) errEl.style.display = "none";
      if (lockEl) lockEl.style.display = "none";

      currentUser = data.user;
      currentAccount = data.account;
      initUserPreferences();
      resetInactivityTimer();
      navigateTo("home");
    } else {
      triggerPinShake("pin-login-box");
      clearLoginPin();

      if (data.locked) {
        if (lockEl) lockEl.style.display = "block";
        if (errEl) errEl.style.display = "none";
      } else {
        if (errEl) {
          errEl.textContent = data.error || "Invalid PIN. Please try again.";
          errEl.style.display = "block";
        }
      }
    }
  } catch (err) {
    triggerPinShake("pin-login-box");
    clearLoginPin();
    if (errEl) {
      errEl.textContent = "Login failed. Please check connection.";
      errEl.style.display = "block";
    }
  }
}

async function unlockAccountDemo() {
  const input = document.getElementById("login-identifier-input");
  const identifier = input && input.value.trim() ? input.value.trim() : (selectedLoginUser ? selectedLoginUser.phone : "");

  if (!identifier) {
    alert("Please enter phone number or UPI ID to unlock.");
    return;
  }

  try {
    const res = await fetch("/api/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: identifier })
    });
    const data = await res.json();
    if (res.ok) {
      const lockEl = document.getElementById("login-locked-card");
      if (lockEl) lockEl.style.display = "none";
      const errEl = document.getElementById("login-error-msg");
      if (errEl) {
        errEl.textContent = "Account unlocked! Please enter PIN 1234 to sign in.";
        errEl.style.color = "#86EFAC";
        errEl.style.background = "rgba(34, 197, 94, 0.15)";
        errEl.style.borderColor = "rgba(34, 197, 94, 0.35)";
        errEl.style.display = "block";
      }
      clearLoginPin();
    } else {
      alert(data.error || "Could not unlock account.");
    }
  } catch (e) {
    alert("Failed to communicate with unlock service.");
  }
}

function toggleAuthMode(mode) {
  const signinView = document.getElementById("auth-signin-view");
  const signupView = document.getElementById("auth-signup-view");
  const errEl = document.getElementById("login-error-msg");
  const regErrEl = document.getElementById("reg-error-msg");

  if (errEl) errEl.style.display = "none";
  if (regErrEl) regErrEl.style.display = "none";

  if (mode === "register") {
    if (signinView) signinView.style.display = "none";
    if (signupView) signupView.style.display = "block";
  } else {
    if (signinView) signinView.style.display = "block";
    if (signupView) signupView.style.display = "none";
  }
}

async function submitRegister() {
  const name = document.getElementById("reg-name-input") ? document.getElementById("reg-name-input").value.trim() : "";
  const phone = document.getElementById("reg-phone-input") ? document.getElementById("reg-phone-input").value.trim() : "";
  const city = document.getElementById("reg-city-input") ? document.getElementById("reg-city-input").value.trim() : "";
  const pin = document.getElementById("reg-pin-input") ? document.getElementById("reg-pin-input").value.trim() : "";
  const errEl = document.getElementById("reg-error-msg");

  if (!name || !phone || !city || !pin) {
    if (errEl) {
      errEl.textContent = "All fields (Name, Phone, City, 4-digit PIN) are required.";
      errEl.style.display = "block";
    }
    return;
  }

  if (pin.length !== 4 || !/^\d{4}$/.test(pin)) {
    if (errEl) {
      errEl.textContent = "PIN must be exactly 4 numeric digits.";
      errEl.style.display = "block";
    }
    return;
  }

  try {
    const res = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, home_city: city, pin })
    });
    const data = await res.json();
    if (res.ok) {
      currentUser = data.user;
      currentAccount = data.account;
      initUserPreferences();
      resetInactivityTimer();
      navigateTo("home");
    } else {
      if (errEl) {
        errEl.textContent = data.error || "Registration failed.";
        errEl.style.display = "block";
      }
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = "Registration service unreachable.";
      errEl.style.display = "block";
    }
  }
}

async function logout() {
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch (e) {}
  clearUserSessionState();
  loadLoginUsers();
  navigateTo("login");
}

function switchUserAccount() {
  logout();
}

function triggerPinShake(elementId) {
  const box = document.getElementById(elementId);
  if (box) {
    box.classList.remove("shake-anim");
    void box.offsetWidth;
    box.classList.add("shake-anim");
  }
  if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
}

// ----------------- HOME SCREEN DATA -----------------

async function loadHomeData() {
  try {
    const meRes = await fetch("/api/me");
    if (!meRes.ok) return;
    const meData = await meRes.json();
    currentUser = meData.user;
    currentAccount = meData.account;

    renderBalance(currentAccount.balance);

    // Load Live Alert count for promo card
    try {
      const aRes = await fetch("/api/alerts");
      const aData = await aRes.json();
      const count = aData.alerts ? aData.alerts.length : 3;
      const promoText = document.getElementById("promo-shield-blocked-text");
      if (promoText) promoText.textContent = `Shield intercepted ${count} threats this week`;
    } catch (e) {}

    // Load Payees for Recent Rounded-Square Avatars (60px, radius 18px)
    // 4 vivid colours: #29B6F6, #F48FB1, #26C6DA, #FFCA28 with original SVG faces
    const pRes = await fetch("/api/payees");
    const pData = await pRes.json();
    const cScroll = document.getElementById("home-recent-avatars");
    cScroll.innerHTML = "";

    const RECENT_COLORS = ["#29B6F6", "#F48FB1", "#26C6DA", "#FFCA28"];
    const SVG_FACES = [
      `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M6 20v-1a6 6 0 0 1 12 0v1"/></svg>`,
      `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6"/></svg>`,
      `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7.5" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>`,
      `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M6 21v-2a6 6 0 0 1 12 0v2"/></svg>`
    ];

    const displayPayees = (pData.payees || []).slice(0, 4);
    displayPayees.forEach((p, idx) => {
      const item = document.createElement("div");
      item.className = "avatar-square-item";
      item.onclick = () => {
        document.getElementById("send-to-upi").value = p.upi_id;
        navigateTo("send");
      };

      const color = RECENT_COLORS[idx % RECENT_COLORS.length];
      const svgFace = SVG_FACES[idx % SVG_FACES.length];
      const firstName = p.name.split(" ")[0];

      item.innerHTML = `
        <div class="avatar-square" style="background: ${color};">${svgFace}</div>
        <div class="avatar-square-name">${firstName}</div>
      `;
      cScroll.appendChild(item);
    });
  } catch (e) {}
}

// Quick Pay Modal for 4x2 grid
function openBillPay(type, provider, amount) {
  activeBillPayItem = { type, provider, amount };
  document.getElementById("billpay-title").textContent = `Quick Pay • ${type}`;
  document.getElementById("billpay-biller").textContent = `${provider} (Verified Bill Biller)`;
  document.getElementById("billpay-amount").textContent = formatINR(amount);
  document.getElementById("modal-billpay-sheet").classList.add("show");
}

function closeBillPayModal() {
  document.getElementById("modal-billpay-sheet").classList.remove("show");
}

function proceedBillPay() {
  if (!activeBillPayItem) return;
  closeBillPayModal();
  document.getElementById("send-to-upi").value = `${activeBillPayItem.type.toLowerCase().replace(/\s+/g, '')}@icici`;
  sendAmountBuffer = String(activeBillPayItem.amount);
  document.getElementById("send-amount-display").textContent = sendAmountBuffer;
  document.getElementById("send-note-input").value = `${activeBillPayItem.type} payment: ${activeBillPayItem.provider}`;
  navigateTo("send");
}

function openRequestModal() {
  const upi = prompt("Enter payer UPI ID for collect request:", "colleague@oksbi");
  const amt = prompt("Enter request amount (INR):", "500");
  if (upi && amt && parseFloat(amt) > 0) {
    fetch("/api/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_upi: upi, amount: parseFloat(amt), note: "Payment request" })
    }).then(() => alert(`Payment request of Rs ${amt} sent to ${upi}!`));
  }
}

function showTopupModal() {
  const amt = prompt("Enter mock deposit amount (INR):", "5000");
  if (amt && parseFloat(amt) > 0) {
    fetch("/api/topup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount: parseFloat(amt) })
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success) {
          alert(`Successfully credited ${formatINR(amt)}! New Balance: ${formatINR(data.new_balance)}`);
          loadHomeData();
        }
      });
  }
}

// ----------------- SEND FLOW -----------------

function handleSendDigit(d) {
  if (sendAmountBuffer === "0" && d !== ".") {
    sendAmountBuffer = d;
  } else {
    if (d === "." && sendAmountBuffer.includes(".")) return;
    if (sendAmountBuffer.length < 9) sendAmountBuffer += d;
  }
  document.getElementById("send-amount-display").textContent = sendAmountBuffer;
}

function backspaceSendDigit() {
  if (sendAmountBuffer.length > 1) {
    sendAmountBuffer = sendAmountBuffer.slice(0, -1);
  } else {
    sendAmountBuffer = "0";
  }
  document.getElementById("send-amount-display").textContent = sendAmountBuffer;
}

async function runSendPreview() {
  const toUpi = document.getElementById("send-to-upi").value.trim();
  const amt = parseFloat(sendAmountBuffer) || 0;
  const note = document.getElementById("send-note-input").value.trim();

  if (!toUpi) {
    alert("Please enter a recipient UPI ID");
    return;
  }
  if (amt <= 0) {
    alert("Please enter a valid amount");
    return;
  }

  const overlay = document.getElementById("modal-scanning-overlay");
  overlay.classList.add("show");

  try {
    const res = await fetch("/api/send/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to_upi: toUpi,
        amount: amt,
        note: note,
        is_new_device: 0
      })
    });
    const data = await res.json();
    overlay.classList.remove("show");

    pendingPaymentPayload = {
      to_upi: toUpi,
      amount: amt,
      note: note,
      acknowledged_warning: false
    };

    if (data.decision === "BLOCK") {
      showShieldVerdict(data, `Payment to ${toUpi}`);
      navigateTo("shield");
    } else if (data.decision === "WARN") {
      document.getElementById("warn-sheet-reason").textContent = data.summary;
      document.getElementById("modal-warning-sheet").classList.add("show");
      if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
    } else {
      openPinSheet(amt, toUpi);
    }
  } catch (e) {
    overlay.classList.remove("show");
    alert("Preview failed. Please try again.");
  }
}

function openPinSheet(amount, payee) {
  document.getElementById("sheet-amount-label").textContent = formatINR(amount);
  document.getElementById("sheet-payee-label").textContent = payee;
  clearSheetPin();
  document.getElementById("modal-pin-sheet").classList.add("show");
}

function closePinSheet() {
  document.getElementById("modal-pin-sheet").classList.remove("show");
}

function handleSheetDigit(digit) {
  if (sendPinBuffer.length < 4) {
    sendPinBuffer += digit;
    updatePinDots("sheet-pin-dots", sendPinBuffer.length);
    if (sendPinBuffer.length === 4) {
      setTimeout(executeConfirmPayment, 150);
    }
  }
}

function backspaceSheetPin() {
  if (sendPinBuffer.length > 0) {
    sendPinBuffer = sendPinBuffer.slice(0, -1);
    updatePinDots("sheet-pin-dots", sendPinBuffer.length);
  }
}

function clearSheetPin() {
  sendPinBuffer = "";
  updatePinDots("sheet-pin-dots", 0);
}

async function executeConfirmPayment() {
  if (!pendingPaymentPayload) return;

  const payload = {
    ...pendingPaymentPayload,
    pin: sendPinBuffer
  };

  try {
    const res = await fetch("/api/send/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closePinSheet();

    if (res.ok) {
      document.getElementById("receipt-amount").textContent = formatINR(data.amount);
      document.getElementById("receipt-payee").textContent = `To ${data.receiver_name} (${data.receiver_upi})`;
      document.getElementById("receipt-txn-id").textContent = `#TXN-${data.txn_id}`;
      document.getElementById("receipt-ts").textContent = data.ts;
      document.getElementById("receipt-new-bal").textContent = formatINR(data.new_balance);

      document.getElementById("modal-receipt-sheet").classList.add("show");
      sendAmountBuffer = "0";
      document.getElementById("send-amount-display").textContent = "0";
      document.getElementById("send-note-input").value = "";
    } else {
      if (data.decision === "BLOCK") {
        showShieldVerdict(data, `Blocked transfer to ${payload.to_upi}`);
        navigateTo("shield");
      } else {
        alert(data.error || "Payment was rejected");
      }
    }
  } catch (err) {
    closePinSheet();
    alert("Transaction network error");
  }
}

function closeReceiptSheet() {
  document.getElementById("modal-receipt-sheet").classList.remove("show");
  navigateTo("home");
}

function closeWarningSheet() {
  document.getElementById("modal-warning-sheet").classList.remove("show");
}

function confirmWithWarningAck() {
  closeWarningSheet();
  if (pendingPaymentPayload) {
    pendingPaymentPayload.acknowledged_warning = true;
    openPinSheet(pendingPaymentPayload.amount, pendingPaymentPayload.to_upi);
  }
}

// ----------------- PAYMENT HISTORY (DASHED DIVIDER CARDS) -----------------

let allTxns = [];

async function loadHistoryData() {
  renderBalance();
  try {
    const res = await fetch("/api/transactions?limit=100");
    const data = await res.json();
    allTxns = data.transactions;
    renderHistoryCards(allTxns);
  } catch (e) {}
}

function renderHistoryCards(txns) {
  const container = document.getElementById("history-txns-list");
  container.innerHTML = "";
  if (!txns.length) {
    container.innerHTML = `<p style="text-align: center; margin-top: 30px; color: var(--text-secondary);">No transactions recorded.</p>`;
    return;
  }

  const AVATAR_COLORS = ["#29B6F6", "#F48FB1", "#26C6DA", "#FFCA28", "#8B5CF6", "#06B6D4"];

  txns.forEach((tx, idx) => {
    const card = document.createElement("div");
    card.className = "history-card";

    const isBlocked = tx.status === "BLOCKED";
    const isCredit = tx.status === "SUCCESS" && currentUser && tx.receiver_upi === currentUser.upi_id;

    let titleText = "Payment Sent";
    let amtClass = "debit";
    let sign = "- ";
    if (isBlocked) {
      titleText = "Blocked by Shield";
      amtClass = "blocked";
      sign = "";
    } else if (isCredit) {
      titleText = "Payment Received";
      amtClass = "credit";
      sign = "+ ";
    }

    const color = AVATAR_COLORS[idx % AVATAR_COLORS.length];
    const displayName = isCredit ? (tx.sender_name || tx.sender_upi || "Received") : (tx.receiver_name || tx.receiver_upi);
    const displaySub = isCredit ? `Received from ${tx.sender_upi || tx.sender_name || "sender"}` : `${tx.receiver_upi}${tx.note ? ' • ' + tx.note : ''}`;
    const initials = displayName.slice(0, 2).toUpperCase();

    card.innerHTML = `
      <div class="history-top-row">
        <div>
          <div class="history-title">${titleText}</div>
          <div class="history-datetime">${tx.ts}</div>
        </div>
        <div class="history-amount ${amtClass}">${sign}${formatINR(tx.amount)}</div>
      </div>
      <div class="history-dashed-divider"></div>
      <div class="history-bottom-row">
        <div class="history-sub-avatar" style="background: ${isBlocked ? '#F59E0B' : (isCredit ? '#22C55E' : color)};">
          ${initials}
        </div>
        <div style="overflow: hidden;">
          <div class="history-payee-name">${displayName}</div>
          <div class="history-payee-sub">${displaySub}</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function filterHistory(filterType) {
  document.querySelectorAll(".filter-chips-row .filter-chip").forEach((c) => c.classList.remove("active"));
  event.target.classList.add("active");

  if (filterType === "ALL") {
    renderHistoryCards(allTxns);
  } else if (filterType === "BLOCKED") {
    renderHistoryCards(allTxns.filter((t) => t.status === "BLOCKED"));
  } else if (filterType === "CREDIT") {
    renderHistoryCards(allTxns.filter((t) => t.status === "SUCCESS" && currentUser && t.receiver_upi === currentUser.upi_id));
  } else if (filterType === "DEBIT") {
    renderHistoryCards(allTxns.filter((t) => t.status === "SUCCESS" && (!currentUser || t.receiver_upi !== currentUser.upi_id)));
  }
}

// ----------------- SHIELD THREAT INSPECTOR -----------------

function runTabShieldCheck() {
  const input = document.getElementById("shield-tab-input").value.trim();
  if (!input) return;
  runShieldInspection(input);
}

async function runShieldInspection(target, contextMsg = null) {
  navigateTo("shield");
  document.getElementById("shield-verdict-title").textContent = "ANALYZING...";
  document.getElementById("shield-target-url").textContent = target;

  try {
    let res;
    if (target.startsWith("upi://") || target.includes("@")) {
      res = await fetch("/api/shield/upi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upi_string: target })
      });
      const data = await res.json();
      showShieldVerdict({
        decision: data.risk_score > 0.7 ? "BLOCK" : (data.risk_score > 0.4 ? "WARN" : "SAFE"),
        risk: data.risk_score,
        summary: data.reasons.join("; "),
        fraud_type: "UPI / QR Inspection",
        signals: {
          upi_eval: { score: data.risk_score, reasons: data.reasons }
        }
      }, target);
      return;
    }

    res = await fetch("/api/shield/link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: target, text: contextMsg })
    });
    const data = await res.json();
    showShieldVerdict({
      decision: data.verdict === "BLOCK" ? "BLOCK" : (data.verdict === "WARN" ? "WARN" : "SAFE"),
      risk: data.score,
      summary: data.reasons.join("; "),
      fraud_type: data.fraud_type,
      reasons: data.reasons,
      highlight_words: data.highlight_words,
      signals: data.layers
    }, target, contextMsg);
  } catch (err) {
    alert("Shield inspection failed.");
  }
}

function showShieldVerdict(result, targetUrl, contextMsg = "") {
  const dec = result.decision || (result.verdict === "BLOCK" ? "BLOCK" : "WARN");
  const risk = result.risk !== undefined ? result.risk : (result.score || 0.0);
  const reasons = result.reasons || (result.summary ? result.summary.split("; ") : ["Suspicious risk detected"]);
  const fraudType = result.fraud_type || "Threat Alert";

  const card = document.getElementById("shield-verdict-card");
  const badge = document.getElementById("shield-hero-badge");
  const title = document.getElementById("shield-verdict-title");
  const typeChip = document.getElementById("shield-fraud-type-chip");
  const riskPercent = document.getElementById("shield-risk-percent");
  const riskCircle = document.getElementById("shield-risk-circle");
  const reasonsList = document.getElementById("shield-reasons-list");
  const signalsBox = document.getElementById("shield-signals-breakdown");
  const proceedBtn = document.getElementById("btn-proceed-warn");
  const msgPreview = document.getElementById("shield-message-preview");

  document.getElementById("shield-target-url").textContent = targetUrl;

  if (dec === "SAFE") {
    card.style.borderColor = "var(--color-success)";
    badge.style.background = "rgba(34, 197, 94, 0.2)";
    badge.style.color = "var(--color-success)";
    title.textContent = "VERIFIED SAFE";
    title.style.color = "var(--color-success)";
    riskCircle.setAttribute("stroke", "var(--color-success)");
    proceedBtn.style.display = "none";
  } else if (dec === "WARN") {
    card.style.borderColor = "var(--color-warning)";
    badge.style.background = "rgba(245, 158, 11, 0.2)";
    badge.style.color = "var(--color-warning)";
    title.textContent = "SECURITY WARNING";
    title.style.color = "#FBBF24";
    riskCircle.setAttribute("stroke", "var(--color-warning)");
    proceedBtn.style.display = "block";
    if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
  } else {
    card.style.borderColor = "var(--color-danger)";
    badge.style.background = "rgba(239, 68, 68, 0.2)";
    badge.style.color = "var(--color-danger)";
    title.textContent = "THREAT BLOCKED";
    title.style.color = "#F87171";
    riskCircle.setAttribute("stroke", "var(--color-danger)");
    proceedBtn.style.display = "none";
    if (navigator.vibrate) navigator.vibrate([150, 80, 150]);
  }

  typeChip.textContent = fraudType;
  const pct = Math.round(risk * 100);
  riskPercent.textContent = `${pct}%`;

  const offset = 339.29 * (1 - Math.min(1.0, risk));
  riskCircle.style.strokeDashoffset = offset;

  reasonsList.innerHTML = "";
  reasons.forEach((r) => {
    const li = document.createElement("li");
    li.textContent = r;
    reasonsList.appendChild(li);
  });

  if (contextMsg) {
    let highlighted = contextMsg;
    const words = result.highlight_words || [];
    words.forEach((w) => {
      const reg = new RegExp(`(${w})`, "gi");
      highlighted = highlighted.replace(reg, `<span style="background:rgba(239,68,68,0.3);color:#FCA5A5;font-weight:700;padding:1px 4px;border-radius:4px;">$1</span>`);
    });
    msgPreview.innerHTML = `<strong>Message Context:</strong><br>${highlighted}`;
    msgPreview.style.display = "block";
  } else {
    msgPreview.style.display = "none";
  }

  signalsBox.innerHTML = "";
  const sigs = result.signals || {};
  Object.keys(sigs).forEach((k) => {
    const val = sigs[k];
    const sScore = typeof val === "object" && val !== null ? (val.score || val.probability || 0.0) : (parseFloat(val) || 0.0);
    const row = document.createElement("div");
    row.innerHTML = `
      <div style="display:flex; justify-content:space-between; margin-bottom: 2px;">
        <span style="font-weight:600; text-transform:uppercase;">${k.replace('_', ' ')}</span>
        <span>${Math.round(sScore * 100)}%</span>
      </div>
      <div style="height:6px; background:var(--bg-input); border-radius:3px; overflow:hidden;">
        <div style="height:100%; width:${sScore * 100}%; background:${sScore > 0.7 ? '#EF4444' : (sScore > 0.4 ? '#F59E0B' : '#22C55E')};"></div>
      </div>
    `;
    signalsBox.appendChild(row);
  });
}

function proceedPastWarning() {
  if (confirm("Proceeding may compromise your funds or credentials. Are you sure you want to proceed?")) {
    navigateTo("home");
  }
}

// ----------------- ATTACK SCENARIOS -----------------

async function runAttackScenario(name) {
  const overlay = document.getElementById("modal-scanning-overlay");
  overlay.classList.add("show");

  try {
    const res = await fetch(`/api/scenarios/${name}/run`, { method: "POST" });
    const data = await res.json();
    overlay.classList.remove("show");

    const input = data.input_percept;
    const target = input.url || input.upi_str || (input.txn ? `${input.txn.receiver_upi} (Rs ${input.txn.amount})` : name);
    showShieldVerdict(data.result, target, input.text || input.note);
    navigateTo("shield");
  } catch (e) {
    overlay.classList.remove("show");
    alert("Attack scenario execution failed");
  }
}

// ----------------- SCAN QR -----------------

function selectSampleQr(type) {
  const ta = document.getElementById("raw-upi-paste");
  if (type === "safe") {
    ta.value = "upi://pay?pa=swiggy@icici&pn=Swiggy Food&am=350&tn=Order8912";
  } else if (type === "collect") {
    ta.value = "upi://pay?pa=scamcollect@upi&am=12000&mode=02&tn=RefundClaim";
  } else if (type === "lookalike") {
    ta.value = "upi://pay?pa=sw1ggy@icici&pn=Swiggy Official&am=450";
  }
}

function processScannedUpi() {
  const raw = document.getElementById("raw-upi-paste").value.trim();
  if (!raw) {
    alert("Please enter or select a UPI QR string");
    return;
  }
  runShieldInspection(raw);
}

function tryCameraScan() {
  if ("BarcodeDetector" in window) {
    alert("Camera scanner initialized. Point at UPI QR code.");
  } else {
    alert("Native BarcodeDetector not available in this browser. Please use the paste box or pick a sample QR code.");
  }
}

// ----------------- INBOX -----------------

let allInboxMessages = [];

async function loadInboxData() {
  try {
    const res = await fetch("/api/inbox");
    const data = await res.json();
    allInboxMessages = data.messages;
    renderInboxMessages(allInboxMessages);
  } catch (e) {}
}

function renderInboxMessages(messages) {
  const container = document.getElementById("inbox-messages-list");
  container.innerHTML = "";

  messages.forEach((m) => {
    const card = document.createElement("div");
    card.className = "neu-card";
    card.style.marginBottom = "0";

    const chColor = m.channel === "SMS" ? "#38BDF8" : (m.channel === "WHATSAPP" ? "#22C55E" : "#818CF8");
    const scamBadge = m.is_scam === 1
      ? `<span style="font-size:10px;font-weight:700;color:#F87171;background:rgba(239,68,68,0.15);padding:2px 8px;border-radius:99px;">SCAM</span>`
      : `<span style="font-size:10px;font-weight:700;color:#4ADE80;background:rgba(34,197,94,0.15);padding:2px 8px;border-radius:99px;">SAFE</span>`;

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-size: 11px; font-weight: 700; color: ${chColor};">${m.channel} • ${m.sender}</span>
        ${scamBadge}
      </div>
      <div style="font-weight: 700; font-size: 14px; margin-bottom: 4px;">${m.subject || 'Notice'}</div>
      <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">${m.body}</p>
      ${m.link ? `<button class="btn-neu-primary" style="font-size: 11px; padding: 6px 12px; width: auto;" onclick="inspectInboxLink('${m.link}', '${encodeURIComponent(m.body)}')">🛡️ Shield Check Link</button>` : ''}
    `;
    container.appendChild(card);
  });
}

function filterInbox(type) {
  document.querySelectorAll("#screen-inbox .filter-chip").forEach((c) => c.classList.remove("active"));
  event.target.classList.add("active");

  if (type === "ALL") {
    renderInboxMessages(allInboxMessages);
  } else if (type === "SCAM") {
    renderInboxMessages(allInboxMessages.filter((m) => m.is_scam === 1));
  } else {
    renderInboxMessages(allInboxMessages.filter((m) => m.is_scam === 0));
  }
}

function inspectInboxLink(link, encodedBody) {
  const body = decodeURIComponent(encodedBody);
  runShieldInspection(link, body);
}

// ----------------- PROFILE & CONTROLS -----------------

async function loadProfileData() {
  if (!currentUser) return;
  renderBalance();
  document.getElementById("profile-name").textContent = currentUser.name;
  document.getElementById("profile-phone").textContent = currentUser.phone;
  document.getElementById("profile-city").textContent = `${currentUser.home_city} • ${currentUser.upi_id}`;

  const av = document.getElementById("profile-avatar");
  av.textContent = currentUser.name.split(" ").map((n) => n[0]).join("").slice(0, 2);

  const freezeBtn = document.getElementById("btn-freeze-toggle");
  freezeBtn.textContent = currentAccount && currentAccount.status === "FROZEN" ? "FROZEN" : "ACTIVE";

  try {
    const mRes = await fetch("/api/admin/metrics");
    const mData = await mRes.json();
    const metricsDiv = document.getElementById("profile-model-metrics");
    const m = mData.metrics || {};
    const ho = m.heldout || {};
    const hoUrl = ho.url_model || {};
    const hoTxt = ho.text_model || {};
    const urlM = m.url_model || {};
    const txtM = m.text_model || {};
    const rf = m.random_forest || {};
    const hgb = m.hist_gradient_boosting || {};

    const fmtCm = cm => cm ? `[[${cm[0][0]}, ${cm[0][1]}], [${cm[1][0]}, ${cm[1][1]}]]` : 'N/A';
    const fiStr = rf.feature_importances ? Object.entries(rf.feature_importances).slice(0, 4).map(([k, v]) => `${k} (${v})`).join(', ') : '';
    const rfCv = rf.cv_metrics ? rf.cv_metrics.f1 : null;

    metricsDiv.innerHTML = `
      <div style="margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);">
        <div style="font-weight: 600; color: #a5b4fc; margin-bottom: 4px;">💳 Transaction Risk Models (CO5 Calibrated)</div>
        <div>Best Model: <strong>${m.best_model || 'RandomForest'}</strong></div>
        <div>RF Test F1: <strong>${rf.f1 !== undefined ? rf.f1 : 'N/A'}</strong> (PR-AUC: ${rf.pr_auc !== undefined ? rf.pr_auc : 'N/A'}${rfCv ? `, 5-Fold CV: ${rfCv.mean}±${rfCv.std}` : ''})</div>
        <div>HGB Test F1: <strong>${hgb.f1 !== undefined ? hgb.f1 : 'N/A'}</strong> (PR-AUC: ${hgb.pr_auc !== undefined ? hgb.pr_auc : 'N/A'})</div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">RF Confusion Matrix: ${fmtCm(rf.confusion_matrix)}</div>
        ${fiStr ? `<div style="font-size: 11px; color: var(--text-muted);">Top Features: ${fiStr}</div>` : ''}
      </div>
      <div style="margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);">
        <div style="font-weight: 600; color: #a5b4fc; margin-bottom: 4px;">🌐 URL Phishing Classifier (CO5)</div>
        <div>Val F1: <strong>${urlM.f1 !== undefined ? urlM.f1 : 'N/A'}</strong> | CM: ${fmtCm(urlM.confusion_matrix)}</div>
        <div>Held-Out F1: <strong>${hoUrl.f1 !== undefined ? hoUrl.f1 : 'N/A'}</strong> (Acc: ${hoUrl.accuracy !== undefined ? (hoUrl.accuracy * 100).toFixed(1) + '%' : 'N/A'})</div>
        <div style="font-size: 11px; color: var(--text-muted);">Held-Out CM: ${fmtCm(hoUrl.confusion_matrix)}</div>
      </div>
      <div style="margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);">
        <div style="font-weight: 600; color: #a5b4fc; margin-bottom: 4px;">💬 NLP Message Scam Classifier (CO5)</div>
        <div>Val F1: <strong>${txtM.f1 !== undefined ? txtM.f1 : 'N/A'}</strong> | CM: ${fmtCm(txtM.confusion_matrix)}</div>
        <div>Held-Out F1: <strong>${hoTxt.f1 !== undefined ? hoTxt.f1 : 'N/A'}</strong> (Acc: ${hoTxt.accuracy !== undefined ? (hoTxt.accuracy * 100).toFixed(1) + '%' : 'N/A'})</div>
        <div style="font-size: 11px; color: var(--text-muted);">Held-Out CM: ${fmtCm(hoTxt.confusion_matrix)}</div>
      </div>
      <div style="font-size: 11px; color: var(--text-muted);">
        Total Txns Audited: <strong>${mData.transactions_total || 0}</strong> (${mData.fraud_total || 0} frauds flagged)
      </div>
    `;
  } catch (e) {}
}

async function toggleFreezeAccount() {
  try {
    const res = await fetch("/api/account/freeze", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      if (currentAccount) currentAccount.status = data.status;
      loadProfileData();
    }
  } catch (e) {}
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const newTheme = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", newTheme);
}

function switchUserAccount() {
  fetch("/api/logout", { method: "POST" }).then(() => {
    currentUser = null;
    currentAccount = null;
    loadLoginUsers();
    navigateTo("login");
  });
}

function triggerPwaInstall() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => {
      deferredPrompt = null;
    });
  }
}

// Start App
document.addEventListener("DOMContentLoaded", initApp);
