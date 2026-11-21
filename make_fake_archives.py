#!/usr/bin/env python3
"""Generate FAKE Google / Instagram / Spotify export archives for a demo persona.

Everything here is invented. No real person's data is used.
Folder and file names approximate the real exports; check them against a real
export before you rely on them in your parsers.

Usage:  python3 make_fake_archives.py [output_dir]
"""
import io
import json
import math
import random
import sys
import zipfile
from datetime import datetime, timedelta, timezone

SEED = 42
DAYS = 60
END = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)
START = END - timedelta(days=DAYS)

HOME = (26.9124, 75.7873, "Home")
WORK = (26.8505, 75.8043, "Work")
GYM = (26.8890, 75.8100, "Gym")
CAFE = (26.9050, 75.8000, "Cafe")
MALL = (26.8600, 75.7800, "Mall")

rng = random.Random(SEED)


def jitter(lat, lng, meters=60):
    d = meters / 111_000
    return lat + rng.uniform(-d, d), lng + rng.uniform(-d, d)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def place_for(day, hour):
    weekend = day.weekday() >= 5
    if hour < 8 or hour >= 22:
        return HOME
    if weekend:
        if 11 <= hour < 14:
            return MALL
        if 16 <= hour < 18:
            return CAFE
        return HOME
    if 9 <= hour < 18:
        return WORK
    if hour in (18, 19) and day.weekday() in (1, 3):
        return GYM
    if hour == 8:
        return CAFE
    return HOME


# ----------------------------------------------------------------- Google
def google_zip():
    locations = []
    visits_by_month = {}
    day = START
    while day <= END:
        for hour in range(0, 24):
            p = place_for(day, hour)
            for _ in range(rng.randint(1, 3)):
                lat, lng = jitter(p[0], p[1])
                t = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
                locations.append({
                    "latitudeE7": int(lat * 1e7),
                    "longitudeE7": int(lng * 1e7),
                    "accuracy": rng.choice([10, 15, 20, 35, 65]),
                    "source": rng.choice(["GPS", "WIFI", "CELL"]),
                    "timestamp": iso(t),
                })
        key = (day.year, day.strftime("%B").upper())
        visits_by_month.setdefault(key, [])
        for hour_start, hour_end in ((9, 18),):
            if day.weekday() < 5:
                s = day.replace(hour=hour_start, minute=0, second=0)
                e = day.replace(hour=hour_end, minute=0, second=0)
                visits_by_month[key].append({"placeVisit": {
                    "location": {
                        "latitudeE7": int(WORK[0] * 1e7), "longitudeE7": int(WORK[1] * 1e7),
                        "placeId": "FAKE_PLACE_WORK", "name": "Fake Tech Park",
                        "address": "Fake Road, Jaipur", "semanticType": "TYPE_WORK"},
                    "duration": {"startTimestamp": iso(s), "endTimestamp": iso(e)},
                    "placeConfidence": "HIGH_CONFIDENCE"}})
        day += timedelta(days=1)

    searches = ["best biryani near me", "knee pain after running", "loan eligibility calculator",
                "cheap flights to goa", "how to switch jobs", "iphone vs pixel", "gym near malviya nagar",
                "symptoms of anxiety", "rent agreement format", "credit card offers"]
    activity = []
    for i in range(300):
        t = START + timedelta(minutes=rng.randint(0, DAYS * 24 * 60))
        activity.append({"header": "Search", "title": "Searched for " + rng.choice(searches),
                         "time": iso(t), "products": ["Search"]})
    activity.sort(key=lambda x: x["time"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Takeout/Location History/Records.json", json.dumps({"locations": locations}))
        for (year, month), objs in visits_by_month.items():
            z.writestr(f"Takeout/Location History/Semantic Location History/{year}/{year}_{month}.json",
                       json.dumps({"timelineObjects": objs}))
        z.writestr("Takeout/My Activity/Search/MyActivity.json", json.dumps(activity))
    return buf.getvalue()


# -------------------------------------------------------------- Instagram
def sm(label, value, ts=None):
    d = {"label": label, "value": value}
    if ts is not None:
        d["timestamp"] = ts
    return d


def instagram_zip():
    interests = ["Fitness", "Cricket", "Street food", "Budget travel", "Personal finance",
                 "Smartphones", "Startups", "Stand-up comedy", "Running"]
    advertisers = ["FitFuel Nutrition", "QuickLoan India", "GoaStays", "PhoneKart", "StyleHub"]
    contacts = [("Fake Person %02d" % i, "+91-98000-%05d" % (10000 + i)) for i in range(1, 41)]
    logins = []
    for i in range(25):
        t = int((START + timedelta(hours=rng.randint(0, DAYS * 24))).timestamp())
        logins.append({"string_map_data": {
            "IP Address": {"value": "49.36.%d.%d" % (rng.randint(1, 250), rng.randint(1, 250))},
            "Time": {"timestamp": t},
            "User Agent": {"value": rng.choice(["Instagram 330 Android", "Mozilla/5.0 (Windows)"])}}})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("preferences/your_topics/your_topics.json", json.dumps({
            "topics_your_topics": [{"string_map_data": {"Name": {"value": x}}} for x in interests]}))
        z.writestr("ads_information/instagram_ads_and_businesses/advertisers_using_your_activity_or_information.json",
                   json.dumps({"ig_custom_audiences_all_types": [
                       {"advertiser_name": a, "has_data_file_custom_audience": True,
                        "has_remarketing_custom_audience": rng.choice([True, False])} for a in advertisers]}))
        z.writestr("connections/contacts/synced_contacts.json", json.dumps({
            "contacts_contact_info": [{"string_map_data": {"Name": {"value": n},
                                                           "Contact": {"value": p}}} for n, p in contacts]}))
        z.writestr("security_and_login_information/login_and_account_creation/login_activity.json",
                   json.dumps({"account_history_login_history": logins}))
        z.writestr("your_instagram_activity/likes/liked_posts.json", json.dumps({"likes_media_likes": [
            {"title": "fake_user_%d" % i, "string_list_data": [{"timestamp": int(
                (START + timedelta(hours=rng.randint(0, DAYS * 24))).timestamp())}]} for i in range(120)]}))
    return buf.getvalue()


# ---------------------------------------------------------------- Spotify
def spotify_zip():
    tracks = [("Fake Artist A", "Midnight Drive"), ("Fake Artist B", "Monsoon Loop"),
              ("Fake Artist C", "Gym Anthem"), ("Fake Artist D", "Slow Sunday"),
              ("Fake Artist E", "Study Beats"), ("Fake Artist F", "Heartbreak Radio")]
    hist, ext = [], []
    for _ in range(900):
        t = START + timedelta(minutes=rng.randint(0, DAYS * 24 * 60))
        art, trk = rng.choice(tracks)
        ms = rng.randint(20_000, 240_000)
        hist.append({"endTime": t.strftime("%Y-%m-%d %H:%M"), "artistName": art,
                     "trackName": trk, "msPlayed": ms})
        ext.append({"ts": iso(t), "platform": rng.choice(["Android OS", "Windows"]),
                    "ms_played": ms, "conn_country": "IN",
                    "ip_addr": "49.36.%d.%d" % (rng.randint(1, 250), rng.randint(1, 250)),
                    "master_metadata_track_name": trk, "master_metadata_album_artist_name": art,
                    "reason_start": rng.choice(["trackdone", "clickrow"]),
                    "reason_end": rng.choice(["trackdone", "fwdbtn"]),
                    "shuffle": rng.choice([True, False]), "skipped": ms < 30_000,
                    "offline": False, "incognito_mode": False})
    hist.sort(key=lambda x: x["endTime"])
    ext.sort(key=lambda x: x["ts"])
    inferences = {"inferences": [
        "Fake_Segment_Age_25_34", "Fake_Segment_Fitness_Enthusiast", "Fake_Segment_Commuter",
        "Fake_Segment_Premium_Prospect", "Fake_Segment_Night_Listener"]}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Spotify Account Data/StreamingHistory_music_0.json", json.dumps(hist))
        z.writestr("Spotify Account Data/Inferences.json", json.dumps(inferences))
        z.writestr("Spotify Extended Streaming History/Streaming_History_Audio_2026_0.json", json.dumps(ext))
    return buf.getvalue()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    for name, fn in (("fake_google_takeout.zip", google_zip),
                     ("fake_instagram_export.zip", instagram_zip),
                     ("fake_spotify_export.zip", spotify_zip)):
        data = fn()
        with open(f"{out}/{name}", "wb") as f:
            f.write(data)
        print(f"wrote {name} ({len(data)//1024} KB)")


if __name__ == "__main__":
    main()
