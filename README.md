# 🔍 HeldBy — Your data, explained.

**Team 14** · Personal Data Footprint Auditor

> Find out what companies recorded about you. See the evidence. Choose one fix. **Then we verify the fix actually worked.**

## Why HeldBy is different

Most privacy tools say "your risk score is 7/10, good luck."
HeldBy does three things nobody else does:

1. **Shows evidence, not scores.** Every finding shows exactly *where* it was found in your file — without ever displaying your private values.
2. **Verifies the fix.** Clean a photo's GPS tag, recheck the cleaned copy, and HeldBy proves the tag is gone. Before/after, not "trust us."
3. **Tells you what it can't do.** No fake loan checks. No fake breach claims. If a feature needs a partner API, it's labelled — not invented.

## What works right now

| Feature | Status | Local? |
|---|---|---|
| Archive scan (Google Search/Location, Spotify history, Facebook contacts/logins, Instagram logins) | ✅ Working | 100% on-device |
| Photo hidden-tag check + clean + **verify** | ✅ Working | 100% on-device |
| Illustrated export guide (Google Takeout, with real screenshots) | ✅ Working | 100% offline |
| Public company breach check | ✅ Working | Opt-in, one network call, logged |
| PDF privacy receipt download | ✅ Working | 100% on-device |
| Network Activity log ("what did we send?") | ✅ Working | Always visible |

## Run it (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install streamlit reportlab pillow
.\.venv\Scripts\python.exe -m streamlit run heldby_v2.py --server.address=127.0.0.1
