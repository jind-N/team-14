import csv
import http.client
import io
import json
import re
import time
import zipfile
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(page_title="HeldBy | Your data, explained", page_icon="🔎")
S = st.session_state
for key, value in {
    "offline": True, "events": [], "results": {}, "done": set(),
    "batch": "", "notice": "", "generation": 0, "last_call": 0.0,
    "breach": None,
}.items():
    S.setdefault(key, value)

MB = 1024 * 1024
READ_ERRORS = (ValueError, OSError, EOFError, RuntimeError, csv.Error,
               zipfile.BadZipFile, zlib.error)

# Company, plain-language label, evidence, priority, action group.
F = {
    "coordinates": ("Google", "Places recorded as coordinates",
                    "Classic Records.json → latitudeE7 and longitudeE7", "High", "location"),
    "contacts": ("Facebook", "Uploaded contact details",
                 "contacts_v2 → details → contact_point", "High", "contacts"),
    "search": ("Google", "Words you searched for",
               "Search record → title starts with 'Searched for '", "Medium", "search"),
    "search_time": ("Google", "When you searched",
                    "Search record → time", "Medium", "search"),
    "ig_login": ("Instagram", "Sign-in records",
                 "account_history_login_history → sign-in details", "Medium", "meta"),
    "fb_login": ("Facebook", "Sign-in records",
                 "account_activity_v2 → login action", "Medium", "meta"),
    "songs": ("Spotify", "Song titles in your listening history",
              "Track name in a playback record", "Medium", "music"),
    "music_time": ("Spotify", "When you listened",
                   "Time in a playback record", "Medium", "music"),
    "country": ("Spotify", "Country of connection, not exact location",
                "Extended playback record → conn_country", "Low", "music"),
}

# Do now, this week, official destination.
A = {
    "search": ("Filter Google My Activity by date and Search. Review the entries.",
               "Check how long Web & App Activity keeps new activity.",
               "https://myactivity.google.com/"),
    "location": ("Review saved places in Google Maps Timeline.",
                 "Review Timeline and location permissions on your devices.",
                 "https://support.google.com/maps/"),
    "contacts": ("Review uploaded contacts in your Meta account.",
                 "Check contact uploading on each device before removing stored contacts.",
                 "https://accountscenter.facebook.com/"),
    "meta": ("Open Accounts Center → Password and security → Where you're logged in.",
             "Sign out unfamiliar sessions and review two-factor authentication.",
             "https://accountscenter.facebook.com/"),
    "music": ("Decide whether you want to keep or request removal of this history.",
              "Ask Spotify about deletion options. Ad settings do not erase listening history.",
              "https://support.spotify.com/"),
    "breach": ("If you used this service, check its official incident notice.",
               "Replace a reused password and enable two-step verification where available.",
               "https://haveibeenpwned.com/"),
}

def forget():
    generation = S.generation + 1
    S.clear()
    S.generation = generation

def record_event(kind, destination, sent):
    event = {"UTC": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "Type": kind, "Destination": destination, "Data": sent, "Outcome": "Started"}
    S.events.append(event)
    return event

def actions(token, group, site=None):
    now, week, default_site = A[group]
    url = site or default_site
    with st.expander("What you can do"):
        st.write("**Do now · about 2 minutes:** " + now)
        st.write("**This week · about 5 minutes:** " + week)
        st.write("**Optional · 1 minute:** Save a summary for yourself.")
        if S.offline:
            st.caption("Official address for later. Offline mode is on.")
            st.code(url, language=None)
        else:
            st.caption("Opening an official site leaves HeldBy. That site sees normal "
                       "browser and connection details. HeldBy does not send your finding.")
            if st.button("Show official link", key="link_" + token):
                event = record_event("Browser handoff offered", url, "No app request")
                event["Outcome"] = "Link shown; external browser traffic is not measured"
                st.link_button("Continue to official site", url)
        if token in S.done:
            st.success("You marked this review as done.")
        elif st.button("I completed my review", key="done_" + token):
            S.done = S.done | {token}
            st.rerun()

def count_fields(name, data):
    counts = Counter()
    if name.lower().endswith(".csv"):
        rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    else:
        obj = json.loads(data)
        if isinstance(obj, dict):
            def records(key):
                items = obj.get(key)
                return (r for r in items if isinstance(r, dict)) if isinstance(items, list) else ()

            if Path(name).name.lower() == "records.json":
                for r in records("locations"):
                    if (type(r.get("latitudeE7")) is int and abs(r["latitudeE7"]) <= 900000000
                            and type(r.get("longitudeE7")) is int
                            and abs(r["longitudeE7"]) <= 1800000000):
                        counts["coordinates"] += 1
            for r in records("contacts_v2"):
                details = r.get("details")
                if isinstance(details, list) and any(
                    isinstance(d, dict) and d.get("contact_point") for d in details
                ):
                    counts["contacts"] += 1
            for r in records("account_history_login_history"):
                fields = r.get("string_map_data")
                if isinstance(fields, dict) and ("IP Address" in fields or "Time" in fields):
                    counts["ig_login"] += 1
            for r in records("account_activity_v2"):
                if str(r.get("action", "")).lower() in {"login", "log in", "logged in"}:
                    counts["fb_login"] += 1
            rows = [obj]
        else:
            rows = obj if isinstance(obj, list) else []

    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("header") == "Search":
            if str(r.get("title", "")).startswith("Searched for "):
                counts["search"] += 1
            if r.get("time"):
                counts["search_time"] += 1
        extended = {"ts", "ms_played", "master_metadata_track_name"}.issubset(r)
        basic = {"endTime", "msPlayed", "trackName"}.issubset(r)
        if extended or basic:
            if r.get("trackName") or r.get("master_metadata_track_name"):
                counts["songs"] += 1
            if r.get("ts") or r.get("endTime"):
                counts["music_time"] += 1
            if extended and r.get("conn_country"):
                counts["country"] += 1
    return counts

def scan(file):
    if file.size > 25 * MB:
        raise ValueError("Too large")
    file.seek(0)
    result, skipped = Counter(), 0

    def read_one(name, stream):
        nonlocal skipped
        data = stream.read(8 * MB + 1)
        if len(data) > 8 * MB:
            skipped += 1
            return
        try:
            hits = count_fields(name, data)
        except READ_ERRORS:
            hits = {}
        result.update(hits)
        skipped += int(not hits)

    ext = Path(file.name).suffix.lower()
    if ext in {".json", ".csv"}:
        read_one(file.name, file)
    elif ext == ".zip":
        with zipfile.ZipFile(file) as archive:
            entries = archive.infolist()
            if len(entries) > 300:
                raise ValueError("Too many entries")
            parts = [p for p in entries if not p.is_dir()
                     and Path(p.filename).suffix.lower() in {".json", ".csv"}]
            skipped += sum(not p.is_dir() for p in entries) - len(parts)
            if sum(p.file_size for p in parts) > 32 * MB:
                raise ValueError("Too much expanded data")
            for p in parts:
                if (p.file_size > 8 * MB or p.flag_bits & 1
                        or p.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    skipped += 1
                    continue
                try:
                    with archive.open(p) as member:
                        read_one(p.filename, member)
                except READ_ERRORS:
                    skipped += 1
    else:
        skipped = 1
    return dict(result), skipped

def make_pdf():
    from reportlab.pdfgen.canvas import Canvas
    from textwrap import wrap
    out = io.BytesIO()
    pdf = Canvas(out, pagesize=(595, 842))
    y = 800
    lines = ["HeldBy - My privacy review", "Source: my selected export, not a live account scan.", ""]
    for k in F:
        if k not in S.results:
            continue
        company, title, field, priority, group = F[k]
        lines += [f"{company}: {title}", f"Evidence: {S.results[k]} record(s). {field}",
                  f"Review priority: {priority}. Next step: {A[group][0]}",
                  "Review marked done: " + ("Yes" if k in S.done else "No"), ""]
    for line in lines:
        for part in wrap(line.replace("→", ">"), 83) or [""]:
            if y < 50:
                pdf.showPage()
                y = 800
            pdf.setFont("Helvetica", 10)
            pdf.drawString(40, y, part)
            y -= 15
    pdf.save()
    return out.getvalue()

def show_archive():
    with st.expander("How do I get my archive file?"):
        guide_app = st.selectbox(
            "Which app is your data in?",
            ["Google", "Instagram", "Facebook", "Another app"],
        )
        if guide_app == "Google":
            guide_dir = Path(__file__).parent / "docs" / "guides" / "google" / "web"
            guide_steps = [
                ("Open Google Takeout",
                 "In your browser, go to takeout.google.com. Check that the account "
                 "shown at the top right is the one you want."),
                ("Pick only My Activity",
                 "Click 'Deselect all'. Scroll down and tick 'My Activity'. "
                 "If you see a format button beside it, open it and choose JSON."),
                ("Choose how to get the file",
                 "Scroll down and click 'Next step'. Choose a download link by email, "
                 "'Export once', and the .zip file type."),
                ("Create the export and bring it back",
                 "Click 'Create export'. Google emails you when the file is ready. "
                 "This can take minutes or days. Download the ZIP to this device."),
            ]
            st.write("**Google Takeout · computer browser**")
            for number, (title, text) in enumerate(guide_steps, start=1):
                st.write(f"**Step {number} of {len(guide_steps)}: {title}**")
                st.write(text)
                picture = guide_dir / f"step{number}.png"
                if picture.exists():
                    try:
                        st.image(str(picture))
                    except Exception:
                        st.caption("This picture could not be opened.")
            st.success("Have your ZIP? Close this guide and choose the file just below.")
            st.caption("Pictures taken by Team 14 on a computer browser. Menus can change.")
        elif guide_app in ("Instagram", "Facebook"):
            st.write(
                "Open Accounts Center, then 'Your information and permissions'. "
                "Choose the export option, select your profile, and pick JSON."
            )
            st.caption("Text guide. Pictures not added yet.")
        else:
            st.write(
                "Open the app's settings and look for 'Privacy', 'Your data', or "
                "'Download your information'. Choose JSON or CSV if offered."
            )
            st.caption("General guide. Menus differ between apps.")
    label = st.text_input("Label for this import", "My account", max_chars=40,
                          help="Use a nickname, not an email or phone number.")
    file = st.file_uploader("Choose a ZIP, JSON, or CSV", key=f"archive_{S.generation}")
    if st.button("Read on this laptop", disabled=file is None):
        S.results, S.done, S.batch = {}, set(), label
        try:
            with st.spinner("Checking supported records on your laptop…"):
                S.results, skipped = scan(file)
            S.notice = f"Files unreadable, unsupported, or without a recognized finding: {skipped}."
        except READ_ERRORS:
            S.notice = ("Could not complete this scan. Try an individual JSON or CSV under "
                        "8 MB. Large, damaged, or encrypted archives may not be readable.")
    if S.notice:
        st.text("Last import: " + S.batch)
        st.caption(S.notice)
        if not S.results:
            st.info("No supported findings in this scan. This is not proof the company has no data.")
    for k, (company, title, field, priority, group) in F.items():
        if k not in S.results:
            continue
        st.subheader(f"{company} · {title}")
        st.write(f"**{priority} review priority** · {S.results[k]} matching record(s)")
        st.caption("Source: selected export. High confidence that the field is present; "
                   "current account settings are unknown.")
        with st.expander("How do we know?"):
            st.text(field)
        site = "https://accountscenter.instagram.com/" if k == "ig_login" else None
        actions(k, group, site)
    if S.results:
        try:
            pdf = make_pdf()
        except ImportError:
            st.caption("PDF export is optional. Install reportlab in this environment to enable it.")
        else:
            st.download_button("Save local PDF report", pdf, "heldby-report.pdf", "application/pdf")

def show_image():
    photo = st.file_uploader("Choose a JPEG photo", type=["jpg", "jpeg"],
                             key=f"photo_{S.generation}")
    if not photo:
        st.info("Choose a photo to check its hidden tags. No photo is shown or sent.")
        return
    try:
        photo.seek(0)
        with Image.open(photo) as im:
            if im.format != "JPEG" or im.width * im.height > 16_000_000:
                raise ValueError("Unsupported image")
            ex = im.getexif()
            gps = ex.get_ifd(34853) if 34853 in ex else {}
            camera = ex.get_ifd(34665) if 34665 in ex else {}
            tags = []
            if 2 in gps and 4 in gps:
                tags.append("Location coordinates")
            if ex.get(271) or ex.get(272):
                tags.append("Camera or phone model information")
            if ex.get(306) or camera.get(36867) or camera.get(36868):
                tags.append("Date or time information")
            st.write("**Found:** " + (", ".join(tags) if tags else "None of the checked tags."))
            st.caption("Source: this photo's EXIF fields. This does not inspect text in the picture.")
            pixels = ImageOps.exif_transpose(im).convert("RGB")
            clean = Image.new("RGB", pixels.size)
            clean.paste(pixels)
            out = io.BytesIO()
            clean.save(out, "JPEG", quality=92)
        st.write("**What you can do:** Share a new copy without the original metadata. "
                 "Re-saving can slightly change image quality. Your original stays as it is.")
        st.download_button("Save cleaned copy", out.getvalue(), "heldby-clean.jpg", "image/jpeg")
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, Image.DecompressionBombError):
        st.warning("Could not read this photo. Try a JPEG of 16 megapixels or less.")

class MockLoanAdapter:
    def report(self):
        return {"Source": "Fictional demo — not your credit report", "Accounts": 1,
                "Lender": "Example Lender", "Example balance": "INR 5,000",
                "Status": "Open", "Report date": "2025-03-01"}

def public_check(domain):
    if S.offline:
        return
    if S.last_call and time.monotonic() - S.last_call < 60:
        st.info("Wait one minute before another public check.")
        return
    S.last_call = time.monotonic()
    S.breach = None
    ev = record_event("Public breach catalogue", "haveibeenpwned.com/api/v3/breaches",
                      "Fixed GET, app header, connection IP; no identifier or request body")
    conn = http.client.HTTPSConnection("haveibeenpwned.com", timeout=10)
    try:
        conn.request("GET", "/api/v3/breaches", headers={"User-Agent": "HeldBy-Team14",
                                                        "Accept": "application/json"})
        res = conn.getresponse()
        ev["Outcome"] = f"HTTP {res.status}"
        if res.status != 200:
            st.warning("The provider did not return its catalogue. No conclusion can be drawn.")
            return
        data = res.read(8 * MB + 1)
        if len(data) > 8 * MB:
            raise ValueError("Response too large")
        reports = json.loads(data)
        if not isinstance(reports, list):
            raise ValueError("Unexpected response")
        matches = [(r.get("BreachDate", "Unknown date"), r.get("DataClasses", []))
                   for r in reports if isinstance(r, dict) and r.get("IsVerified")
                   and (r.get("Domain") or "").lower() == domain]
        S.breach = (domain, matches)
    except (OSError, ValueError, http.client.HTTPException):
        ev["Outcome"] = "Could not complete check"
        st.warning("Could not complete the public check. Local features still work.")
    finally:
        conn.close()

st.title("HeldBy")
st.caption("Your data, explained. No account required.")
body = st.container()
pages = ["My Data", "Email ID", "Settings & Trust"]
labels = {
    "My Data": "My files",
    "Email ID": "Company breach reports",
    "Settings & Trust": "Privacy",
}

if S.get("nav") not in pages:
    S["nav"] = "My Data"

page = st.radio(
    "Choose a tool", pages, horizontal=True, key="nav",
    format_func=lambda p: labels[p],
)
with body:
    if page == "Home":
        st.subheader("What do companies know about you?")
        st.write("1. Choose your export.  \n2. See what was recorded.  \n3. Choose one action.")
        if st.button("Start with My Data",
                     on_click=lambda: S.update({"nav": "My Data"})):
            pass
        if S.results:
            first = next(k for k in F if k in S.results)
            st.write(f"**Review first:** {F[first][0]} · {F[first][1]}")
            st.write(f"Reviews marked done: {len(set(S.results) & S.done)} of {len(S.results)}")
            if "coordinates" in S.results or "country" in S.results:
                st.write("Location signals were found. A country code is not a precise location.")
            st.caption("Data selling and advertising use are not determined by this scan.")
        else:
            st.info("No export checked yet. Nothing here is pre-filled.")

    elif page == "My Data":
        section = st.radio("Choose what to check", ["Archive Data", "Images"], horizontal=True)
        if section == "Archive Data":
            show_archive()
        else:
            show_image()

    elif page == "Contact Info":
        st.subheader("Phone and credit checks")
        st.write("No credit provider is connected. Do not enter a real phone number. "
                 "A number alone does not prove who owns a loan.")
        if st.checkbox("Show a fictional loan report"):
            st.json(MockLoanAdapter().report())
            st.write("**What you can do about an unfamiliar real loan:** Get your own "
                     "official credit report. Contact the named lender and bureau through "
                     "their official dispute channels. Keep the case numbers.")
        st.caption("Uploaded contacts may belong to other people. They are not a list "
                   "of services linked to your phone number.")

    elif page == "Email ID":
        st.subheader("Was a company involved in a known breach?")
        st.write("This checks a company, not your personal email. "
                 "A match does not prove that you had an account or that your details leaked.")
        domain = st.text_input("Company domain, not an email", placeholder="example.com").strip().lower()
        st.caption("One request downloads the public catalogue from Have I Been Pwned. "
                   "They see your IP, request time, and app header. The domain you typed "
                   "is compared here and is not sent.")
        if S.offline:
            st.info("Offline mode is on. To allow this optional check, use Settings & Trust.")
        if st.button("Send this one public request", disabled=S.offline):
            if not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", domain) or len(domain) > 253:
                st.warning("Enter just a company domain, such as example.com.")
            else:
                public_check(domain)
        if S.breach and S.breach[0] == domain:
            hits = S.breach[1]
            if hits:
                for date, categories in hits:
                    st.text(f"Reported incident: {date}\nData types: {', '.join(categories)}")
                actions("public_breach_" + domain, "breach")
            else:
                st.info("No verified report matched this exact domain in this catalogue. "
                        "This is not a safety guarantee.")

    else:
        st.subheader("Settings & Trust")
        preference = st.toggle("Offline mode — block app requests", value=S.offline)
        if preference != S.offline:
            S.offline = preference
            st.rerun()
        calls = sum(e["Type"] == "Public breach catalogue" for e in S.events)
        st.metric("Outside API requests attempted this session", calls)
        st.caption("This counts HeldBy feature requests, not all traffic on your PC. "
                   "Your browser talks to the app on this laptop.")
        if S.events:
            st.dataframe(S.events, hide_index=True)
        else:
            st.success("No outside requests or browser handoffs recorded.")
        st.write("No history database. Raw values are not included in the PDF. "
                 "Downloaded files are ordinary files under your control.")
        st.button("Forget this session", on_click=forget)