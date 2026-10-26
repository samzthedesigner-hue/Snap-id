# SnapID — 5-in-1 Document Tools

Passport Maker • Signature Maker • Doc Scanner • NIN Extractor • CV→PDF

## 📂 Structure
- `backend/` — FastAPI server with Supabase Postgres integration, Resend Email, and EasyOCR/Rembg.
- `frontend/` — Capacitor Android app + PWA files for Vercel hosting.
- `.github/workflows/build-apk.yml` — Auto-builds the Android APK.

## 🌍 Deployment Links
- **Render (Backend API):** `https://snapid-api.onrender.com`
- **Vercel (Frontend/Testing/Download):** `https://snapid.vercel.app`
- **GitHub Actions (APK):** Check the "Releases" tab on this repo.

## 🔑 Render Environment Variables
To deploy the backend, add these to your Render Web Service environment:
- `JWT_SECRET` = (Long random string)
- `DATABASE_URL` = (Supabase Connection URI)
- `RESEND_API_KEY` = (Your Resend API key)
- `FRONTEND_URL` = `https://snapid.vercel.app`
- `TEST_MODE_EXPIRES_AT` = (Unix timestamp for test expiry)
- `BANK_NAME` = Moniepoint
- `ACCOUNT_NUMBER` = 6964461874
- `ACCOUNT_NAME` = Obadimeji Samuel Oluwasogo

## 🚀 How to Deploy Updates
1. Push code to `main`.
2. **Render** auto-deploys the backend.
3. **Vercel** auto-deploys the frontend.
4. **GitHub Actions** builds a new APK and puts it in Releases.
