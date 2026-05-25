# Boost Vibe Signup

Web UI to generate a Boost account, then poll Mail.tm for the verification code.

## Run locally

```bash
cd boost
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5050

## Deploy on Vercel

1. Install the [Vercel CLI](https://vercel.com/docs/cli) or connect the repo in the Vercel dashboard.
2. Set the project **root directory** to `boost` (this folder).
3. Deploy — Vercel uses `api/index.py` and `vercel.json`.

```bash
cd boost
vercel
```

### Notes for Vercel

- Sessions are stored **in memory** on the server. On serverless, a single user’s polling should stay on one instance; heavy concurrent traffic may need Redis/KV later.
- API routes need up to ~60s for account creation — `maxDuration` is set in `vercel.json`.
- Do not upload `.venv`; it is listed in `.vercelignore`.
