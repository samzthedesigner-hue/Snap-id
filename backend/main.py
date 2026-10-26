import os, io, time, hashlib, traceback, secrets, re, base64
from datetime import datetime
from collections import defaultdict
import jwt, bcrypt, numpy as np, cv2, httpx
import psycopg2, psycopg2.extras
from PIL import Image, ImageOps
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# ============================================================
# CONFIG
# ============================================================
BANK_NAME = os.environ.get("BANK_NAME", "Moniepoint")
ACCOUNT_NUMBER = os.environ.get("ACCOUNT_NUMBER", "6964461874")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "Obadimeji Samuel Oluwasogo")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://snapid.vercel.app")

OWNER_EMAIL = "samuelobadimeji500@gmail.com"

PLANS = {
    "3-hour": {"price": 800, "seconds": 3 * 60 * 60}, "daily": {"price": 1500, "seconds": 24 * 60 * 60},
    "weekly": {"price": 3500, "seconds": 7 * 24 * 60 * 60}, "monthly": {"price": 8000, "seconds": 30 * 24 * 60 * 60},
    "yearly": {"price": 32000, "seconds": 365 * 24 * 60 * 60},
}

# ============================================================
# DATABASE (SUPABASE)
# ============================================================
if not DATABASE_URL: raise RuntimeError("DATABASE_URL required.")
def _pg():
    conn = psycopg2.connect(DATABASE_URL); conn.autocommit = True
    return conn, psycopg2.extras.RealDictCursor

def db_init():
    conn, _ = _pg(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at DOUBLE PRECISION)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, device_id TEXT NOT NULL, created_at DOUBLE PRECISION, expires_at DOUBLE PRECISION, is_active BOOLEAN DEFAULT TRUE)""")
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_user ON sessions(user_id) WHERE is_active = TRUE""")
    cur.execute("""CREATE TABLE IF NOT EXISTS plans (id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, plan TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL, receipt_hash TEXT, created_at DOUBLE PRECISION)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS free_uses (user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, tool TEXT NOT NULL, used_at DOUBLE PRECISION, PRIMARY KEY (user_id, tool))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS generations (id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, tool TEXT NOT NULL, filename TEXT NOT NULL, file_data TEXT NOT NULL, created_at DOUBLE PRECISION)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS password_resets (token TEXT PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, expires_at DOUBLE PRECISION, used BOOLEAN DEFAULT FALSE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS used_receipts (hash TEXT PRIMARY KEY, created_at DOUBLE PRECISION)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS user_activity (user_id BIGINT PRIMARY KEY, last_active DOUBLE PRECISION, winback_sent BOOLEAN DEFAULT FALSE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ratings (id BIGSERIAL PRIMARY KEY, stars INT NOT NULL, comment TEXT, device_id TEXT, created_at DOUBLE PRECISION)""")
    cur.close(); conn.close()
db_init()

def db_fetch_one(sql, params=()):
    conn, cf = _pg(); cur = conn.cursor(cursor_factory=cf)
    cur.execute(sql, params); row = cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def db_fetch_all(sql, params=()):
    conn, cf = _pg(); cur = conn.cursor(cursor_factory=cf)
    cur.execute(sql, params); rows = cur.fetchall(); cur.close(); conn.close()
    return [dict(r) for r in rows]

def db_execute(sql, params=()):
    conn, _ = _pg(); cur = conn.cursor(); cur.execute(sql, params); cur.close(); conn.close()

# ============================================================
# HELPERS
# ============================================================
def _hash_pw(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def _check_pw(pw, h):
    try: return bcrypt.checkpw(pw.encode(), h.encode())
    except: return False

def _issue_tokens(device_id, user_id, plan, exp_ts):
    now = int(time.time())
    act = jwt.encode({"type": "activate", "plan": plan, "device_id": device_id, "user_id": user_id, "iat": now, "exp": exp_ts}, JWT_SECRET, algorithm="HS256")
    kill = jwt.encode({"type": "kill", "iat": now, "exp": 4102444800}, JWT_SECRET, algorithm="HS256")
    return act, kill

def free_use_available(user_id, tool):
    if not user_id: return False
    return db_fetch_one("SELECT 1 FROM free_uses WHERE user_id=%s AND tool=%s", (user_id, tool)) is None

def mark_free_use(user_id, tool):
    if not user_id: return
    try: db_execute("INSERT INTO free_uses(user_id, tool, used_at) VALUES (%s,%s,%s)", (user_id, tool, time.time()))
    except: pass

def save_generation(user_id, tool, filename, file_bytes):
    if not user_id: return
    b64 = base64.b64encode(file_bytes).decode('utf-8')
    db_execute("INSERT INTO generations(user_id, tool, filename, file_data, created_at) VALUES (%s,%s,%s,%s,%s)", (user_id, tool, filename, b64, time.time()))

def send_email(to, subject, html_content):
    if not RESEND_API_KEY: return
    try:
        httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}"}, json={
            "from": "SnapID <onboarding@resend.dev>", "to": [to], "subject": subject, "html": html_content
        }, timeout=10)
    except: pass

# ============================================================
# APP & ERROR ALERTS
# ============================================================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def error_handler(request, call_next):
    try: return await call_next(request)
    except Exception as e:
        send_email(OWNER_EMAIL, "🚨 SnapID Server Error", f"<p>Error: {str(e)}</p>")
        raise HTTPException(500, "Internal Server Error")

@app.get("/")
def root(): return {"status": "ok"}
@app.get("/wake")
def wake(): return {"awake": True}

# ============================================================
# AUTH
# ============================================================
def verify_token(authorization: str = Header(None), x_device_id: str = Header(None), x_session: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "Missing token")
    try: payload = jwt.decode(authorization.split(" ", 1)[1], JWT_SECRET, algorithms=["HS256"])
    except: raise HTTPException(401, "Invalid token")
    if x_session:
        sess = db_fetch_one("SELECT is_active FROM sessions WHERE token=%s", (x_session,))
        if not sess or not sess["is_active"]: raise HTTPException(401, "Signed in elsewhere")
    return payload

def verify_token_or_free(tool):
    def dep(authorization: str = Header(None), x_device_id: str = Header(None), x_session: str = Header(None)):
        user_id = None
        user_email = None
        if x_session:
            sess = db_fetch_one("SELECT user_id FROM sessions WHERE token=%s AND is_active=TRUE", (x_session,))
            if sess:
                user_id = sess["user_id"]
                u = db_fetch_one("SELECT email FROM users WHERE id=%s", (user_id,))
                if u: user_email = u["email"]
                
        if not user_id: raise HTTPException(401, "Must be logged in")

        if user_email and user_email == OWNER_EMAIL:
            return {"_free": False, "device_id": x_device_id, "tool": tool, "user_id": user_id, "admin_bypass": True}

        if authorization and authorization.startswith("Bearer "):
            try:
                payload = verify_token(authorization, x_device_id, x_session); payload["_free"] = False; return payload
            except HTTPException as e:
                if "expired" in str(e.detail).lower(): raise
                
        if free_use_available(user_id, tool):
            return {"_free": True, "device_id": x_device_id, "tool": tool, "user_id": user_id}
            
        raise HTTPException(401, "Subscribe to continue")
    return dep

@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...), device_id: str = Form(...)):
    email = email.strip().lower()
    if "@" not in email or len(password) < 16: raise HTTPException(400, "Password must be at least 16 characters.")
    if db_fetch_one("SELECT id FROM users WHERE email=%s", (email,)): raise HTTPException(400, "Email exists")
    
    db_execute("INSERT INTO users(email, password_hash, created_at) VALUES (%s,%s,%s)", (email, _hash_pw(password), time.time()))
    user = db_fetch_one("SELECT id FROM users WHERE email=%s", (email,))
    db_execute("UPDATE sessions SET is_active=FALSE WHERE user_id=%s", (user["id"],))
    
    token = secrets.token_urlsafe(32)
    db_execute("INSERT INTO sessions(token, user_id, device_id, created_at, expires_at, is_active) VALUES (%s,%s,%s,%s,%s,%s)", (token, user["id"], device_id, time.time(), time.time() + 90*24*3600, True))
    return {"ok": True, "email": email, "session_token": token}

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...), device_id: str = Form(...)):
    email = email.strip().lower()
    user = db_fetch_one("SELECT * FROM users WHERE email=%s", (email,))
    if not user or not _check_pw(password, user["password_hash"]): raise HTTPException(401, "Wrong email/password")
    
    db_execute("UPDATE sessions SET is_active=FALSE WHERE user_id=%s", (user["id"],))
    token = secrets.token_urlsafe(32)
    db_execute("INSERT INTO sessions(token, user_id, device_id, created_at, expires_at, is_active) VALUES (%s,%s,%s,%s,%s,%s)", (token, user["id"], device_id, time.time(), time.time() + 90*24*3600, True))
    db_execute("""INSERT INTO user_activity(user_id, last_active, winback_sent) VALUES (%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET last_active=EXCLUDED.last_active, winback_sent=FALSE""", (user["id"], time.time(), False))

    plan_row = db_fetch_one("SELECT plan, expires_at FROM plans WHERE user_id=%s AND expires_at>%s ORDER BY expires_at DESC LIMIT 1", (user["id"], time.time()))
    at = kt = ems = pname = None
    if email == OWNER_EMAIL:
        exp_ts = int(time.time()) + (3650 * 24 * 3600); pname = "Owner"
        at, kt = _issue_tokens(device_id, user["id"], pname, exp_ts); ems = exp_ts * 1000
    elif plan_row:
        exp_ts = int(plan_row["expires_at"]); pname = plan_row["plan"]
        at, kt = _issue_tokens(device_id, user["id"], pname, exp_ts); ems = exp_ts * 1000
    return {"ok": True, "email": user["email"], "session_token": token, "activate_token": at, "kill_token": kt, "expires_at": ems, "plan": pname}

@app.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    user = db_fetch_one("SELECT id FROM users WHERE email=%s", (email.strip().lower(),))
    if user:
        token = secrets.token_urlsafe(32)
        db_execute("INSERT INTO password_resets(token, user_id, expires_at, used) VALUES (%s,%s,%s,%s)", (token, user["id"], time.time() + 3600, False))
        send_email(email, "Reset SnapID Password", f"<p><a href='{FRONTEND_URL}/reset.html?token={token}' style='background:#10b981;color:#fff;padding:10px 20px;text-decoration:none;border-radius:5px;'>Reset Password</a></p>")
    return {"ok": True, "message": "If email exists, link sent."}

@app.get("/me")
async def me(x_session: str = Header(None)):
    sess = db_fetch_one("SELECT user_id FROM sessions WHERE token=%s AND is_active=TRUE", (x_session,))
    if not sess: raise HTTPException(401, "Invalid")
    user = db_fetch_one("SELECT email FROM users WHERE id=%s", (sess["user_id"],))
    plan = db_fetch_one("SELECT plan, expires_at FROM plans WHERE user_id=%s AND expires_at>%s ORDER BY expires_at DESC LIMIT 1", (sess["user_id"], time.time()))
    return {"email": user["email"], "plan": plan["plan"] if plan else None, "expires_at": int(plan["expires_at"]*1000) if plan else None}

@app.get("/my-documents")
async def my_docs(x_session: str = Header(None)):
    sess = db_fetch_one("SELECT user_id FROM sessions WHERE token=%s AND is_active=TRUE", (x_session,))
    if not sess: raise HTTPException(401, "Invalid")
    docs = db_fetch_all("SELECT id, tool, filename, created_at FROM generations WHERE user_id=%s ORDER BY created_at DESC", (sess["user_id"],))
    return {"documents": docs}

@app.get("/download-doc/{doc_id}")
async def download_doc(doc_id: int, x_session: str = Header(None)):
    sess = db_fetch_one("SELECT user_id FROM sessions WHERE token=%s AND is_active=TRUE", (x_session,))
    if not sess: raise HTTPException(401, "Invalid")
    doc = db_fetch_one("SELECT file_data, filename FROM generations WHERE id=%s AND user_id=%s", (doc_id, sess["user_id"]))
    return Response(content=base64.b64decode(doc["file_data"]), headers={"Content-Disposition": f"attachment; filename={doc['filename']}"})

@app.post("/rate")
async def rate(stars: int = Form(...), comment: str = Form(""), device_id: str = Form(None)):
    db_execute("INSERT INTO ratings(stars, comment, device_id, created_at) VALUES (%s,%s,%s,%s)", (stars, comment, device_id, time.time()))
    return {"ok": True}

@app.get("/cron-check")
async def cron_check():
    now = time.time()
    inactive = db_fetch_all("SELECT u.email FROM users u JOIN user_activity a ON u.id = a.user_id WHERE (? - a.last_active) > 604800 AND a.winback_sent = FALSE", (now,))
    for u in inactive:
        send_email(u["email"], "We miss you at SnapID! 💚", f"<p>Come back and get 3 hours for ₦500.</p><p><a href='{FRONTEND_URL}' style='background:#10b981;color:#fff;padding:10px 20px;text-decoration:none;border-radius:5px;'>Claim Offer</a></p>")
        db_execute("UPDATE user_activity SET winback_sent=TRUE WHERE user_id=(SELECT id FROM users WHERE email=%s)", (u["email"],))
    return {"ok": True}

# ============================================================
# TOOLS
# ============================================================
PASSPORT_SPECS = {"2x2": (600, 600, 240), "1x1": (300, 300, 100), "jamb": (400, 400, 50), "nysc": (300, 300, 100), "nin": (300, 300, 50), "waec": (275, 354, 50), "ngpassport": (400, 400, 100), "bvn": (400, 400, 100), "usvisa": (600, 600, 240), "ukpassport": (600, 750, 240), "schengen": (413, 531, 240), "canada": (420, 540, 240)}

def _read(b): return ImageOps.exif_transpose(Image.open(io.BytesIO(b)))
def _to_bytes(img, fmt="PNG", quality=95):
    buf = io.BytesIO()
    if fmt.upper() == "JPEG" and img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.save(buf, format=fmt, quality=quality); return buf.getvalue()
def _compress(img, target_kb, fmt="JPEG"):
    lo, hi, best = 10, 95, None
    for _ in range(8):
        q = (lo + hi) // 2; data = _to_bytes(img, fmt=fmt, quality=q)
        if len(data) / 1024 <= target_kb: best = data; lo = q + 1
        else: hi = q - 1
    return best or _to_bytes(img, fmt=fmt, quality=10)

@app.post("/passport")
async def passport(file: UploadFile = File(...), spec: str = Form("2x2"), auth=Depends(verify_token_or_free("passport"))):
    raw = await file.read(); src = _read(raw).convert("RGB")
    try:
        from rembg import remove
        cut = remove(src, session=None)
        if isinstance(cut, bytes): cut = Image.open(io.BytesIO(cut))
    except: cut = src
    bg = Image.new("RGBA", cut.size, (255, 255, 255, 255)); bg.alpha_composite(cut.convert("RGBA")); img = bg.convert("RGB")
    w, h, max_kb = PASSPORT_SPECS.get(spec, PASSPORT_SPECS["2x2"])
    img = ImageOps.fit(img, (w, h), method=Image.LANCZOS); data = _compress(img, max_kb)
    save_generation(auth["user_id"], "passport", f"Passport_{int(time.time())}.jpg", data)
    if auth.get("_free"): mark_free_use(auth["user_id"], "passport")
    return Response(content=data, media_type="image/jpeg", headers={"Content-Disposition": "attachment; filename=passport.jpg", "X-Free-Used": "1" if auth.get("_free") else "0"})

@app.post("/signature")
async def signature(file: UploadFile = File(...), auth=Depends(verify_token_or_free("signature"))):
    raw = await file.read(); img = _read(raw).convert("L"); arr = np.array(img)
    mask = (arr < 220).astype(np.uint8) * 255
    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel); mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    ys, xs = np.where(mask > 0)
    if len(xs) > 0: mask = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    ink = Image.fromarray(mask); canvas = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ink = ink.resize((180, 80), Image.LANCZOS); pos = ((200 - ink.width) // 2, (100 - ink.height) // 2)
    black = Image.new("RGBA", ink.size, (0, 0, 0, 255)); canvas.paste(black, pos, ink)
    data = _to_bytes(canvas, fmt="PNG")
    save_generation(auth["user_id"], "signature", f"Signature_{int(time.time())}.png", data)
    if auth.get("_free"): mark_free_use(auth["user_id"], "signature")
    return Response(content=data, media_type="image/png", headers={"Content-Disposition": "attachment; filename=signature.png", "X-Free-Used": "1" if auth.get("_free") else "0"})

@app.post("/scan")
async def scan(file: UploadFile = File(...), auth=Depends(verify_token_or_free("scan"))):
    raw = await file.read(); img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(cv2.normalize(255 - cv2.absdiff(gray, cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), 21)), None, 0, 255, cv2.NORM_MINMAX), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 15)
    from reportlab.pdfgen import canvas as rl_canvas; from reportlab.lib.utils import ImageReader
    pdf_buf = io.BytesIO(); pil = Image.fromarray(th).convert("RGB"); w, h = pil.size
    cv = rl_canvas.Canvas(pdf_buf, pagesize=(w, h)); cv.drawImage(ImageReader(pil), 0, 0, width=w, height=h); cv.save()
    data = pdf_buf.getvalue()
    save_generation(auth["user_id"], "scan", f"Scan_{int(time.time())}.pdf", data)
    if auth.get("_free"): mark_free_use(auth["user_id"], "scan")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=scanned.pdf", "X-Free-Used": "1" if auth.get("_free") else "0"})

@app.post("/nin")
async def nin(file: UploadFile = File(...), auth=Depends(verify_token_or_free("nin"))):
    raw = await file.read(); img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
    if len(faces) == 0: raise HTTPException(400, "No face.")
    x, y, fw, fh = max(faces, key=lambda f: f[2]*f[3]); pad = int(max(fw, fh) * 0.25)
    face = img[max(0, y-pad):min(img.shape[0], y+fh+pad), max(0, x-pad):min(img.shape[1], x+fw+pad)]
    ch, cw = face.shape[:2]; s = max(ch, cw); sq = np.full((s, s, 3), 255, dtype=np.uint8)
    sq[(s-ch)//2:(s-ch)//2+ch, (s-cw)//2:(s-cw)//2+cw] = face
    data = _to_bytes(Image.fromarray(cv2.cvtColor(sq, cv2.COLOR_BGR2RGB)).resize((400, 400), Image.LANCZOS), fmt="JPEG", quality=92)
    save_generation(auth["user_id"], "nin", f"NIN_{int(time.time())}.jpg", data)
    if auth.get("_free"): mark_free_use(auth["user_id"], "nin")
    return Response(content=data, media_type="image/jpeg", headers={"Content-Disposition": "attachment; filename=nin.jpg", "X-Free-Used": "1" if auth.get("_free") else "0"})

@app.post("/cv")
async def cv_to_pdf(name: str = Form(...), email: str = Form(...), phone: str = Form(...), address: str = Form(""), summary: str = Form(""), experience: str = Form(""), education: str = Form(""), skills: str = Form(""), auth=Depends(verify_token_or_free("cv"))):
    from reportlab.lib.pagesizes import A4; from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle; from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable; from reportlab.lib.units import mm; from reportlab.lib import colors
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet(); H = ParagraphStyle("H", parent=styles["Heading1"], fontSize=20); sec = ParagraphStyle("sec", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0a6"))
    story = [Paragraph(name, H), Paragraph(f"{email} | {phone} | {address}", styles["Normal"]), HRFlowable(width="100%", color=colors.HexColor("#0a6"))]
    def add_s(t, x):
        if x.strip():
            story.append(Paragraph(t, sec))
            for ln in x.split("\n"): 
                if ln.strip(): story.append(Paragraph(ln.strip(), styles["Normal"]))
            story.append(Spacer(1, 4))
    add_s("Summary", summary); add_s("Experience", experience); add_s("Education", education); add_s("Skills", skills)
    doc.build(story); data = buf.getvalue()
    save_generation(auth["user_id"], "cv", f"CV_{int(time.time())}.pdf", data)
    if auth.get("_free"): mark_free_use(auth["user_id"], "cv")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=cv.pdf", "X-Free-Used": "1" if auth.get("_free") else "0"})

@app.post("/verify-receipt")
async def verify_receipt(file: UploadFile = File(...), plan: str = Form(...), device_id: str = Form(...), session: str = Form(None)):
    if plan not in PLANS: raise HTTPException(400, "Invalid plan")
    expected = PLANS[plan]["price"]; duration = PLANS[plan]["seconds"]
    raw = await file.read(); h = hashlib.sha256(raw).hexdigest()
    if db_fetch_one("SELECT 1 FROM used_receipts WHERE hash=%s", (h,)): raise HTTPException(400, "Receipt used.")
    
    db_execute("INSERT INTO used_receipts(hash, created_at) VALUES (%s,%s)", (h, time.time()))
    now = int(time.time()); exp = now + duration
    user_id = None
    if session:
        sess = db_fetch_one("SELECT user_id FROM sessions WHERE token=%s AND is_active=TRUE", (session,))
        if sess:
            user_id = sess["user_id"]
            db_execute("UPDATE plans SET expires_at=%s WHERE user_id=%s AND expires_at>%s", (now, user_id, now))
            db_execute("INSERT INTO plans(user_id, plan, expires_at, receipt_hash, created_at) VALUES (%s,%s,%s,%s,%s)", (user_id, plan, float(exp), h, time.time()))
    act, kill = _issue_tokens(device_id, user_id, plan, exp)
    return {"ok": True, "activate_token": act, "kill_token": kill, "expires_at": exp * 1000, "plan": plan}
