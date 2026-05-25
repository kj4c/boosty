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
2. Set the project **Root Directory** to `boost` (this folder). If you deploy from inside `boost`, you’re already set.
3. Deploy from this folder:

```bash
cd boost
vercel
```

Vercel uses `api/index.py` (exports the Flask `app`), `pyproject.toml`, and `vercel.json`.

If you see *“pattern api/index.py doesn't match”*, you’re probably deploying from the parent repo root — either set Root Directory to `boost` in the Vercel project settings, or run `vercel` from inside `boost`.

### Notes for Vercel

- Sessions are stored **in memory** on the server. Light use is fine; heavy traffic may need Redis/KV later.
- Account creation can take 30–60s. On Pro, raise the function `maxDuration` in the Vercel dashboard if builds time out.
- Do not upload `.venv`; it is listed in `.vercelignore`.
