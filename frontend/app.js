const APP_CONFIG = {
  APP_NAME: "SnapID", BACKEND_URL: "https://snap-id.onrender.com", WHATSAPP: "2348027363235",
  OWNER_EMAIL: "samuelobadimeji500@gmail.com",
  GITHUB_USER: "samzthedesigner-hue",
  GITHUB_REPO: "snapid",
  PLANS: { "3-hour": { price: 800 }, "daily": { price: 1500 }, "weekly": { price: 3500 }, "monthly": { price: 8000 }, "yearly": { price: 32000 } }
};

const LS_ACT = "__act", LS_EXP = "__exp", LS_PLAN = "__plan", LS_SESSION = "__session", LS_DEVICE = "__device_id";
const $ = (id) => document.getElementById(id);

let selectedPlan = null;
let selectedFiles = { pp: null, scan: null, nin: null };
let expiryTimer = null;

// ---------- HELPERS ----------
async function getDeviceId() {
  if (window.Capacitor?.Plugins?.Device) return (await Capacitor.Plugins.Device.getId()).identifier;
  let id = localStorage.getItem(LS_DEVICE);
  if (!id) { id = "web_" + Math.random().toString(36).slice(2); localStorage.setItem(LS_DEVICE, id); }
  return id;
}
function showLoader(t = "Processing…") { $("loaderText").textContent = t; $("loader").classList.remove("hidden"); }
function hideLoader() { $("loader").classList.add("hidden"); }
function lockApp() { $("app").classList.add("hidden"); $("loginScreen").classList.add("hidden"); $("paywall").classList.remove("hidden"); }
function unlockApp() {
  $("paywall").classList.add("hidden"); $("loginScreen").classList.add("hidden"); $("app").classList.remove("hidden");
  const exp = parseInt(localStorage.getItem(LS_EXP) || "0", 10);
  if (exp > Date.now()) $("statusPill").textContent = "Active until " + new Date(exp).toLocaleDateString();
  else $("statusPill").textContent = "Free Mode";
}
function scheduleExpiry(expiresMs) {
  if (expiryTimer) clearTimeout(expiryTimer);
  const ms = expiresMs - Date.now();
  if (ms <= 0) return;
  expiryTimer = setTimeout(() => { lockApp(); alert("Your plan expired."); }, Math.min(ms, 2147483000));
}
function isActive() { return parseInt(localStorage.getItem(LS_EXP) || "0", 10) > Date.now(); }

// ---------- AUTO UPDATER ----------
async function checkForUpdates() {
  try {
    const res = await fetch(`https://api.github.com/repos/${APP_CONFIG.GITHUB_USER}/${APP_CONFIG.GITHUB_REPO}/releases/latest`);
    if (!res.ok) return;
    const data = await res.json();
    
    const remoteVersion = parseInt(data.tag_name.replace("v1.0.", ""), 10);
    const currentVersion = parseInt(localStorage.getItem("__app_version") || "0", 10);
    const apkAsset = data.assets.find(a => a.name.endsWith(".apk"));
    if (!apkAsset) return;

    if (remoteVersion > currentVersion) {
      const modal = document.createElement("div"); modal.className = "modal";
      modal.innerHTML = `
        <div class="modal-card">
          <h3>Update Available</h3>
          <p class="muted">A new version of Snap ID is available. Update for the latest features.</p>
          <a href="${apkAsset.browser_download_url}" class="btn" style="text-decoration:none; display:block; text-align:center; margin-top:15px;" onclick="localStorage.setItem('__app_version', '${remoteVersion}')">Update Now</a>
          <button class="btn ghost" style="margin-top:10px;" onclick="this.closest('.modal').remove()">Skip for now</button>
        </div>`;
      document.body.appendChild(modal);
    } else {
      if (currentVersion === 0) localStorage.setItem("__app_version", remoteVersion);
    }
  } catch (_) {}
}

// ---------- BOOT ----------
async function boot() {
  await checkForUpdates();

  const session = localStorage.getItem(LS_SESSION);
  const email = localStorage.getItem("__email");

  if (!session) {
    $("splash").classList.add("hidden"); $("loginScreen").classList.remove("hidden");
    wireUi(); return;
  }
  if (email === APP_CONFIG.OWNER_EMAIL) {
    unlockApp(); $("splash").classList.add("hidden"); wireUi(); return;
  }
  try {
    const r = await fetch(APP_CONFIG.BACKEND_URL + "/me", { headers: { "X-Session": session } });
    if (r.ok) {
      const d = await r.json();
      $("menuEmail").textContent = d.email;
      if (d.expires_at) { localStorage.setItem(LS_EXP, String(d.expires_at)); localStorage.setItem(LS_PLAN, d.plan); unlockApp(); scheduleExpiry(d.expires_at); }
      else { unlockApp(); }
    } else { localStorage.removeItem(LS_SESSION); $("splash").classList.add("hidden"); $("loginScreen").classList.remove("hidden"); }
  } catch (_) { $("splash").classList.add("hidden"); $("loginScreen").classList.remove("hidden"); }
  wireUi();
}
document.addEventListener("DOMContentLoaded", boot);

// ---------- AUTH ----------
function showForm(type) {
  document.getElementById("authButtons").classList.add("hidden");
  document.getElementById("authForm").classList.remove("hidden");
  if (type === "login") {
    document.getElementById("authTitle").textContent = "Log In";
    document.getElementById("loginBtn").style.display = "block";
    document.getElementById("registerBtn").style.display = "none";
  } else {
    document.getElementById("authTitle").textContent = "Create Account";
    document.getElementById("loginBtn").style.display = "none";
    document.getElementById("registerBtn").style.display = "block";
  }
}

async function doLogin() {
  const email = $("loginEmail").value.trim(), password = $("loginPassword").value, status = $("loginStatus");
  if (password.length < 16) { status.textContent = "Password must be at least 16 characters."; return; }
  status.textContent = "Logging in...";
  const fd = new FormData(); fd.append("email", email); fd.append("password", password); fd.append("device_id", await getDeviceId());
  try {
    const r = await fetch(APP_CONFIG.BACKEND_URL + "/login", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) { status.textContent = data.detail || "Failed"; return; }
    localStorage.setItem(LS_SESSION, data.session_token); localStorage.setItem("__email", data.email);
    $("menuEmail").textContent = data.email;
    if (data.email === APP_CONFIG.OWNER_EMAIL) { if (data.activate_token) localStorage.setItem(LS_ACT, data.activate_token); unlockApp(); return; }
    if (data.activate_token) {
      localStorage.setItem(LS_ACT, data.activate_token); localStorage.setItem(LS_EXP, String(data.expires_at)); localStorage.setItem(LS_PLAN, data.plan);
      unlockApp(); scheduleExpiry(data.expires_at);
    } else { unlockApp(); }
  } catch (_) { status.textContent = "Network error"; }
}

async function doRegister() {
  const email = $("loginEmail").value.trim(), password = $("loginPassword").value, status = $("loginStatus");
  if (password.length < 16) { status.textContent = "Password must be at least 16 characters."; return; }
  status.textContent = "Creating account...";
  const fd = new FormData(); fd.append("email", email); fd.append("password", password); fd.append("device_id", await getDeviceId());
  try {
    const r = await fetch(APP_CONFIG.BACKEND_URL + "/register", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) { status.textContent = data.detail || "Failed"; return; }
    localStorage.setItem(LS_SESSION, data.session_token); localStorage.setItem("__email", data.email);
    $("menuEmail").textContent = data.email;
    lockApp();
  } catch (_) { status.textContent = "Network error"; }
}

// ---------- MY DOCUMENTS ----------
async function openMyDocuments() {
  $("menuDropdown").classList.add("hidden");
  const modal = document.createElement("div"); modal.className = "modal";
  modal.innerHTML = `<div class="modal-card"><h3>My Documents</h3><div id="docList" style="max-height:300px;overflow-y:auto;margin-top:15px;">Loading...</div><button class="btn ghost" style="margin-top:15px;" onclick="this.closest('.modal').remove()">Close</button></div>`;
  document.body.appendChild(modal);
  try {
    const r = await fetch(APP_CONFIG.BACKEND_URL + "/my-documents", { headers: { "X-Session": localStorage.getItem(LS_SESSION) } });
    const data = await r.json();
    if (data.documents.length === 0) { $("docList").innerHTML = "<p class='muted'>No documents yet.</p>"; return; }
    $("docList").innerHTML = data.documents.map(d => `
      <div style="padding:10px 0; border-bottom:1px solid #232a34; display:flex; justify-content:space-between; align-items:center;">
        <div><b>${d.tool.toUpperCase()}</b><br><small class="muted">${new Date(d.created_at*1000).toLocaleDateString()}</small></div>
        <button class="btn secondary" style="width:auto; padding:6px 12px; margin:0;" onclick="downloadDoc(${d.id})">Download</button>
      </div>`).join("");
  } catch (_) { $("docList").innerHTML = "<p class='muted'>Error.</p>"; }
}
async function downloadDoc(id) {
  const r = await fetch(`${APP_CONFIG.BACKEND_URL}/download-doc/${id}`, { headers: { "X-Session": localStorage.getItem(LS_SESSION) } });
  const blob = await r.blob(); const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = `SnapID_Doc`; a.click();
}

// ---------- CAMERA ----------
let cameraStream = null, currentFacing = "user", cameraCallback = null;
async function openCamera(callback, facing = "user") {
  cameraCallback = callback; currentFacing = facing;
  if (window.Capacitor?.Plugins?.Camera) {
    try {
      const photo = await Capacitor.Plugins.Camera.getPhoto({ quality: 92, resultType: "uri", source: "CAMERA", direction: facing === "user" ? "FRONT" : "REAR" });
      const blob = await (await fetch(photo.webPath)).blob(); callback(new File([blob], "capture.jpg", { type: "image/jpeg" })); return;
    } catch (e) {}
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: currentFacing }, audio: false });
    $("cameraVideo").srcObject = cameraStream; $("cameraModal").classList.remove("hidden");
  } catch (err) { alert("Camera denied."); }
}
function capturePhoto() {
  const v = $("cameraVideo"), c = $("cameraCanvas");
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
  c.toBlob(blob => { closeCamera(); if (cameraCallback) cameraCallback(new File([blob], "capture.jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.92);
}
function closeCamera() { if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; } $("cameraModal").classList.add("hidden"); }

// ---------- TOOLS ----------
async function apiCall(path, fd) {
  const headers = { "Authorization": "Bearer " + (localStorage.getItem(LS_ACT) || ""), "X-Device-Id": await getDeviceId(), "X-Session": localStorage.getItem(LS_SESSION) };
  return fetch(APP_CONFIG.BACKEND_URL + path, { method: "POST", body: fd, headers });
}

async function passportGo() {
  if (!selectedFiles.pp) return alert("Upload a photo first.");
  showLoader("Processing..."); const fd = new FormData(); fd.append("file", selectedFiles.pp); fd.append("spec", $("ppSpec").value);
  try {
    const r = await apiCall("/passport", fd); hideLoader();
    if (!r.ok) throw new Error("Failed");
    const url = URL.createObjectURL(await r.blob());
    $("ppResult").innerHTML = `<img src="${url}"><a class="download-link" href="${url}" download="passport.jpg">⬇ Download</a>`;
    if (r.headers.get("X-Free-Used") === "1") showPremiumPrompt();
  } catch (_) { hideLoader(); $("ppResult").innerHTML = `<div class="err">Error</div>`; }
}

async function signatureGo() {
  const blob = await new Promise(res => $("sigCanvas").toBlob(res, "image/png"));
  showLoader("Processing..."); const fd = new FormData(); fd.append("file", new File([blob], "sig.png", { type: "image/png" }));
  try {
    const r = await apiCall("/signature", fd); hideLoader();
    if (!r.ok) throw new Error("Failed");
    const url = URL.createObjectURL(await r.blob());
    $("sigResult").innerHTML = `<img src="${url}" style="background:transparent"><a class="download-link" href="${url}" download="sig.png">⬇ Download</a>`;
    if (r.headers.get("X-Free-Used") === "1") showPremiumPrompt();
  } catch (_) { hideLoader(); $("sigResult").innerHTML = `<div class="err">Error</div>`; }
}

async function scanGo() {
  if (!selectedFiles.scan) return alert("Upload a doc first.");
  showLoader("Processing..."); const fd = new FormData(); fd.append("file", selectedFiles.scan);
  try {
    const r = await apiCall("/scan", fd); hideLoader();
    if (!r.ok) throw new Error("Failed");
    const url = URL.createObjectURL(await r.blob());
    $("scanResult").innerHTML = `<a class="download-link" href="${url}" download="scan.pdf">⬇ Download PDF</a>`;
    if (r.headers.get("X-Free-Used") === "1") showPremiumPrompt();
  } catch (_) { hideLoader(); $("scanResult").innerHTML = `<div class="err">Error</div>`; }
}

async function ninGo() {
  if (!selectedFiles.nin) return alert("Upload a slip first.");
  showLoader("Processing..."); const fd = new FormData(); fd.append("file", selectedFiles.nin);
  try {
    const r = await apiCall("/nin", fd); hideLoader();
    if (!r.ok) throw new Error("Failed");
    const url = URL.createObjectURL(await r.blob());
    $("ninResult").innerHTML = `<img src="${url}"><a class="download-link" href="${url}" download="nin.jpg">⬇ Download</a>`;
    if (r.headers.get("X-Free-Used") === "1") showPremiumPrompt();
  } catch (_) { hideLoader(); $("ninResult").innerHTML = `<div class="err">Error</div>`; }
}

async function cvGo() {
  const fd = new FormData();
  ["name", "email", "phone", "summary", "experience", "education", "skills"].forEach(k => fd.append(k, $("cv" + k.charAt(0).toUpperCase() + k.slice(1)).value));
  showLoader("Processing...");
  try {
    const r = await apiCall("/cv", fd); hideLoader();
    if (!r.ok) throw new Error("Failed");
    const url = URL.createObjectURL(await r.blob());
    $("cvResult").innerHTML = `<a class="download-link" href="${url}" download="cv.pdf">⬇ Download CV</a>`;
    if (r.headers.get("X-Free-Used") === "1") showPremiumPrompt();
  } catch (_) { hideLoader(); $("cvResult").innerHTML = `<div class="err">Error</div>`; }
}

function showPremiumPrompt() {
  if (isActive()) return;
  const modal = document.createElement("div"); modal.className = "modal";
  modal.innerHTML = `<div class="modal-card"><h3>Are you satisfied? 🎉</h3><p class="muted">You used your 1 free generation. Sign up for Premium to enjoy seamless generations!</p><button class="btn" id="goPremiumBtn" style="margin-top:15px;">View Premium Plans</button><button class="btn ghost" id="closePremiumBtn">Maybe Later</button></div>`;
  document.body.appendChild(modal);
  document.getElementById("closePremiumBtn").onclick = () => modal.remove();
  document.getElementById("goPremiumBtn").onclick = () => { modal.remove(); lockApp(); };
}

// ---------- FEEDBACK & RATINGS ----------
async function submitRating(stars) {
  if (stars < 1) { alert("Please choose a star rating"); return; }
  const comment = $("ratingComment").value.trim();
  const d = await getDeviceId();
  const fd = new FormData(); fd.append("stars", String(stars)); fd.append("comment", comment); fd.append("device_id", d);
  try {
    await fetch(APP_CONFIG.BACKEND_URL + "/rate", { method: "POST", body: fd });
    localStorage.setItem("__rated", "rated");
    $("ratingModal").classList.add("hidden");
    if (stars <= 3) {
      const msg = encodeURIComponent(`I rated SnapID ${stars}⭐. Feedback: ${comment || "(no comment)"}`);
      window.open(`https://wa.me/${APP_CONFIG.WHATSAPP}?text=${msg}`, "_blank");
    } else alert("Thank you! 🎉");
  } catch (_) { alert("Could not submit. Try again."); }
}

function maybeShowRating() {
  if (localStorage.getItem("__rated")) return;
  const count = parseInt(localStorage.getItem("__gen_count") || "0", 10) + 1;
  localStorage.setItem("__gen_count", String(count));
  if (count === 3) {
    $("ratingModal").classList.remove("hidden");
    let chosenStars = 0;
    document.querySelectorAll("#ratingStars button").forEach(s => {
      s.addEventListener("click", () => {
        chosenStars = parseInt(s.dataset.r, 10);
        document.querySelectorAll("#ratingStars button").forEach(x => x.classList.toggle("active", parseInt(x.dataset.r, 10) <= chosenStars));
      });
    });
    $("ratingSubmit").onclick = () => submitRating(chosenStars);
    $("ratingSkip").onclick = () => { localStorage.setItem("__rated", "skipped"); $("ratingModal").classList.add("hidden"); };
  }
}

// ---------- UI WIRING ----------
function wireUi() {
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active")); document.querySelectorAll(".panel").forEach(x => x.classList.remove("active"));
    t.classList.add("active"); $("panel-" + t.dataset.tab).classList.add("active");
  });
  document.querySelectorAll(".plan").forEach(b => b.onclick = () => {
    selectedPlan = b.dataset.plan; $("payPlanLabel").textContent = selectedPlan; $("payAmount").textContent = "₦" + APP_CONFIG.PLANS[selectedPlan].price;
    document.querySelector(".plans").classList.add("hidden"); $("paymentBox").classList.remove("hidden");
  });
  $("loginBtn").onclick = doLogin; $("registerBtn").onclick = doRegister;
  $("menuBtn").onclick = () => $("menuDropdown").classList.toggle("hidden");
  $("menuDocs").onclick = openMyDocuments;
  $("menuLogout").onclick = () => { localStorage.clear(); location.reload(); };
  $("cancelPay").onclick = () => { $("paymentBox").classList.add("hidden"); document.querySelector(".plans").classList.remove("hidden"); };
  $("supportBtn").onclick = () => window.open("https://wa.me/2348027363235", "_blank");
  $("renewBtn").onclick = () => lockApp();
  $("ppCameraBtn").onclick = () => openCamera(f => { selectedFiles.pp = f; alert("Photo ready!"); });
  $("ppFile").onchange = e => selectedFiles.pp = e.target.files[0];
  $("ppGo").onclick = passportGo;
  $("sigGo").onclick = signatureGo;
  $("scanCameraBtn").onclick = () => openCamera(f => { selectedFiles.scan = f; alert("Doc ready!"); }, "environment");
  $("scanFile").onchange = e => selectedFiles.scan = e.target.files[0];
  $("scanGo").onclick = scanGo;
  $("ninCameraBtn").onclick = () => openCamera(f => { selectedFiles.nin = f; alert("NIN ready!"); }, "environment");
  $("ninFile").onchange = e => selectedFiles.nin = e.target.files[0];
  $("ninGo").onclick = ninGo;
  $("cvGo").onclick = cvGo;
  $("cameraCancel").onclick = closeCamera; $("cameraCapture").onclick = capturePhoto;
  
  const c = $("sigCanvas"), ctx = c.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 320, 160); ctx.strokeStyle = "#000"; ctx.lineWidth = 3;
  let draw = false;
  c.onmousedown = c.ontouchstart = e => { draw = true; ctx.beginPath(); ctx.moveTo(e.offsetX || e.touches[0].clientX, e.offsetY || e.touches[0].clientY); };
  c.onmousemove = c.ontouchmove = e => { if (!draw) return; ctx.lineTo(e.offsetX || e.touches[0].clientX, e.offsetY || e.touches[0].clientY); ctx.stroke(); };
  c.onmouseup = c.ontouchend = () => draw = false;
  $("sigClear").onclick = () => { ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 320, 160); };
  
  $("receiptInput").onchange = async e => {
    const f = e.target.files[0]; if (!f || !selectedPlan) return;
    showLoader("Verifying..."); const fd = new FormData(); fd.append("file", f); fd.append("plan", selectedPlan); fd.append("device_id", await getDeviceId()); fd.append("session", localStorage.getItem(LS_SESSION));
    try {
      const r = await fetch(APP_CONFIG.BACKEND_URL + "/verify-receipt", { method: "POST", body: fd }); const data = await r.json(); hideLoader();
      if (!r.ok) { alert(data.detail || "Failed"); return; }
      localStorage.setItem(LS_ACT, data.activate_token); localStorage.setItem(LS_EXP, String(data.expires_at)); localStorage.setItem(LS_PLAN, data.plan);
      unlockApp(); scheduleExpiry(data.expires_at);
    } catch (_) { hideLoader(); alert("Error"); }
  };
      }
