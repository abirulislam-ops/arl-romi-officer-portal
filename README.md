# ROMI Officer Portal

No-login Streamlit app where SBU officers add marketing campaigns and view
a read-only ROMI analysis.

## Deploy (Streamlit Cloud)

1. Push this folder to a GitHub repo.
2. Streamlit Cloud → New app → select the repo (main file is `streamlit_app.py`).
3. Add Secrets:

```toml
SUPABASE_URL = "https://rhnpiqlbhihldcrohfxj.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "PASTE_SERVICE_ROLE_KEY"
```

4. Deploy and share the URL with officers.

## Files

- `streamlit_app.py` — the app (officer input + ROMI analysis).
- `supabase_client.py` — Supabase access (service-role, server-side).
- `romi_logic.py` — ROMI formulas + overrides.
- `config.py` — variable names only (no secrets).
