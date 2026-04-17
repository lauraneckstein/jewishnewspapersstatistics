#!/usr/bin/env python3
"""
build_visualization.py
----------------------
Run this script to regenerate subscriber_visualization.html from any updated CSV.

Usage:
    python build_visualization.py                          # uses default filename below
    python build_visualization.py my_updated_data.csv     # specify a CSV path
    python build_visualization.py data.csv output.html    # specify both input and output

The CSV must have the same column structure as the original Subscribers2026 file.
Required columns: Newspaper_Name, Subscriber name edited, Place_edited, State, Country,
                  Latitude, Longitude, Year, Datetime, Agent_UUID, Subscriber Agent,
                  Final_Classification, Subscriber Type, People_UUID
"""

import csv
import json
import sys
import os
from collections import defaultdict, Counter
from datetime import datetime
from itertools import combinations

# ── CONFIG ────────────────────────────────────────────────────────────────────

DEFAULT_CSV = "Subscribers2026 (6).csv"   # change this if your file has a different name
DEFAULT_OUT = "subscriber_visualization.html"

SHORT = {
    "The Occident, and American Jewish Advocate": "Occident",
    "The Israelite": "Israelite",
    "The Jewish Messenger": "Messenger",
    "The Weekly Gleaner": "Gleaner",
}
PAPERS = ["Occident", "Israelite", "Messenger", "Gleaner"]

REGIONS = {
    "New England":   ["Maine","New Hampshire","Vermont","Massachusetts","Rhode Island","Connecticut"],
    "Mid-Atlantic":  ["New York","New Jersey","Pennsylvania","Maryland","Delaware","District of Columbia"],
    "South":         ["Virginia","West Virginia","North Carolina","South Carolina","Georgia","Florida",
                      "Alabama","Mississippi","Louisiana","Tennessee","Kentucky","Arkansas","Texas"],
    "Midwest":       ["Ohio","Indiana","Illinois","Michigan","Wisconsin","Minnesota","Iowa",
                      "Kansas","Nebraska","North Dakota","South Dakota","Missouri"],
    "West":          ["California","Oregon","Washington","Nevada","Utah","Colorado","Arizona",
                      "New Mexico","Idaho","Montana","Wyoming"],
    "Canada/Caribbean/Other": [],
}

def get_region(state):
    for r, states in REGIONS.items():
        if state in states:
            return r
    return "Canada/Caribbean/Other"

def short(paper):
    return SHORT.get(paper, paper)

# ── LOAD ──────────────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ── DATA BUILDERS ─────────────────────────────────────────────────────────────

def build_map_data(rows):
    places = defaultdict(lambda: {"lat": None, "lng": None, "state": "", "country": "", "papers": defaultdict(int), "years": set()})
    for r in rows:
        loc = r["Place_edited"].strip()
        lat = r["Latitude"].strip()
        lng = r["Longitude"].strip()
        if not loc or not lat or not lng:
            continue
        try:
            lat_f, lng_f = float(lat), float(lng)
        except ValueError:
            continue
        p = places[loc]
        p["lat"] = lat_f
        p["lng"] = lng_f
        p["state"] = r["State"].strip()
        p["country"] = r["Country"].strip()
        p["papers"][r["Newspaper_Name"]] += 1
        if r["Year"].strip():
            p["years"].add(r["Year"].strip())

    result = []
    for loc, d in places.items():
        total = sum(d["papers"].values())
        result.append({
            "loc": loc, "lat": d["lat"], "lng": d["lng"],
            "state": d["state"], "country": d["country"],
            "total": total,
            "num_papers": sum(1 for v in d["papers"].values() if v > 0),
            "papers": dict(d["papers"]),
            "years": sorted(d["years"]),
        })
    return sorted(result, key=lambda x: -x["total"])


def build_timeline(rows):
    paper_year = defaultdict(Counter)
    for r in rows:
        yr = r["Year"].strip()
        if yr:
            paper_year[short(r["Newspaper_Name"])][yr] += 1
    all_years = sorted(set(y for p in paper_year.values() for y in p))
    timeline = []
    for yr in all_years:
        entry = {"year": int(yr)}
        for p in PAPERS:
            entry[p] = paper_year[p].get(yr, 0)
        timeline.append(entry)
    return timeline, all_years


def build_flow(rows):
    name_data = defaultdict(list)
    for r in rows:
        name = r["Subscriber name edited"].strip()
        yr = r["Year"].strip()
        if name and name.lower() != "unknown" and yr:
            name_data[name].append({"year": int(yr), "paper": short(r["Newspaper_Name"])})

    transitions = defaultdict(Counter)
    for name, apps in name_data.items():
        paper_set = set(a["paper"] for a in apps)
        if len(paper_set) < 2:
            continue
        first_year = {}
        for a in sorted(apps, key=lambda x: x["year"]):
            if a["paper"] not in first_year:
                first_year[a["paper"]] = a["year"]
        for p1, y1 in first_year.items():
            for p2, y2 in first_year.items():
                if p1 != p2 and y1 < y2:
                    transitions[(p1, p2)][y2] += 1

    flow_data = []
    for (src, tgt), yr_counts in transitions.items():
        for yr, count in yr_counts.items():
            flow_data.append({"from": src, "to": tgt, "year": int(yr), "count": count})
    return flow_data


def build_class_data(rows):
    class_data = {}
    for p_full, p_short in SHORT.items():
        c = Counter(r["Final_Classification"] for r in rows if r["Newspaper_Name"] == p_full)
        class_data[p_short] = {"Individual": c.get("Individual", 0), "Business": c.get("Business", 0)}
    return class_data


def build_region_data(rows, all_years):
    region_paper_year = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        yr = r["Year"].strip()
        state = r["State"].strip()
        p = short(r["Newspaper_Name"])
        if yr and p:
            region_paper_year[get_region(state)][p][yr] += 1

    region_names = list(REGIONS.keys())
    region_data = {
        reg: {p: [region_paper_year[reg][p].get(y, 0) for y in all_years] for p in PAPERS}
        for reg in region_names
    }
    return region_data, region_names


def build_weekly(rows):
    weekly_data = defaultdict(lambda: defaultdict(int))
    weekly_agent = defaultdict(lambda: defaultdict(int))
    for r in rows:
        dt_raw = r["Datetime"].strip()
        p = short(r["Newspaper_Name"])
        agent = r.get("Agent_UUID", "").strip() or r.get("Subscriber Agent", "").strip()
        if not dt_raw or not p:
            continue
        try:
            dt_str = dt_raw.replace("Z", "").split("T")[0]
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            yr, wk, _ = dt.isocalendar()
            wkey = f"{yr}-W{wk:02d}"
            weekly_data[wkey][p] += 1
            if agent:
                weekly_agent[wkey][p] += 1
        except ValueError:
            continue

    all_weeks = sorted(weekly_data.keys())
    return [
        {
            "week": w,
            **{p: weekly_data[w].get(p, 0) for p in PAPERS},
            **{f"agent_{p}": weekly_agent[w].get(p, 0) for p in PAPERS},
        }
        for w in all_weeks
    ]


def build_state_data(rows):
    state_paper = defaultdict(Counter)
    for r in rows:
        state = r["State"].strip()
        p = short(r["Newspaper_Name"])
        if state and p:
            state_paper[state][p] += 1
    top = sorted(state_paper.items(), key=lambda x: -sum(x[1].values()))[:25]
    return [
        {
            "state": s,
            **{p: d.get(p, 0) for p in PAPERS},
            "total": sum(d.values()),
            "num_papers": sum(1 for v in d.values() if v > 0),
        }
        for s, d in top
    ]


def build_type_data(rows):
    TYPE_GROUPS = {
        "Male": ["Male"],
        "Female": ["Female", "Woman"],
        "Clergy": ["Clergy", "Scholar"],
        "Business": ["Business", "Insurance"],
        "Synagogue/Org": ["Synagogue", "Organization", "Religious Organization"],
        "Military/Political": ["Military", "Politician", "Judge"],
    }
    def normalize(t):
        for grp, vals in TYPE_GROUPS.items():
            if t in vals:
                return grp
        return None

    type_paper = defaultdict(Counter)
    for r in rows:
        st = r.get("Subscriber Type", "").strip()
        p = short(r["Newspaper_Name"])
        if st and p:
            norm = normalize(st)
            if norm:
                type_paper[p][norm] += 1

    return {p: dict(type_paper[p]) for p in PAPERS}


def build_clergy_data(rows, all_years):
    CLERGY_TYPES = {"Clergy", "Scholar", "Synagogue", "Organization", "Religious Organization"}
    clergy_year = defaultdict(Counter)
    for r in rows:
        st = r.get("Subscriber Type", "").strip()
        yr = r["Year"].strip()
        p = short(r["Newspaper_Name"])
        if st in CLERGY_TYPES and yr and p:
            clergy_year[p][yr] += 1
    return {p: [clergy_year[p].get(y, 0) for y in all_years] for p in PAPERS}


def build_gleaner_exits(rows):
    """Where did Gleaner subscribers go after the Gleaner?"""
    name_data = defaultdict(list)
    for r in rows:
        name = r["Subscriber name edited"].strip()
        yr = r["Year"].strip()
        if name and name.lower() != "unknown" and yr:
            name_data[name].append({"year": int(yr), "paper": short(r["Newspaper_Name"])})

    gleaner_names = {n for n, apps in name_data.items() if any(a["paper"] == "Gleaner" for a in apps)}
    after = Counter()
    for name in gleaner_names:
        apps = name_data[name]
        last_gleaner = max(a["year"] for a in apps if a["paper"] == "Gleaner")
        for a in apps:
            if a["year"] > last_gleaner and a["paper"] != "Gleaner":
                after[a["paper"]] += 1

    total_gleaner = len(gleaner_names)
    elsewhere = sum(after.values())
    not_found = total_gleaner - len({n for n in gleaner_names if any(a["paper"] != "Gleaner" and a["year"] > max(x["year"] for x in name_data[n] if x["paper"] == "Gleaner") for a in name_data[n])})
    return {
        "Israelite": after.get("Israelite", 0),
        "Occident": after.get("Occident", 0),
        "Messenger": after.get("Messenger", 0),
        "not_found": total_gleaner - elsewhere,
        "total": total_gleaner,
    }


# ── MONOPOLY TOWNS ───────────────────────────────────────────────────────────

def build_monopoly_data(map_data):
    """Split map_data into monopoly towns (1 paper) and shared towns (2+ papers)."""
    monopoly = []
    shared   = []
    for place in map_data:
        if place["num_papers"] == 1:
            paper_full = list(place["papers"].keys())[0]
            monopoly.append({**place, "dominant": SHORT.get(paper_full, paper_full)})
        else:
            # dominant = paper with most subs
            dominant_full = max(place["papers"], key=place["papers"].get)
            shared.append({**place, "dominant": SHORT.get(dominant_full, dominant_full)})
    return {
        "monopoly": sorted(monopoly, key=lambda x: -x["total"]),
        "shared":   sorted(shared,   key=lambda x: -x["total"]),
        "monopoly_counts": {
            p: sum(1 for m in monopoly if m["dominant"] == p) for p in PAPERS
        },
        "monopoly_subs": {
            p: sum(m["total"] for m in monopoly if m["dominant"] == p) for p in PAPERS
        },
    }


# ── SUMMARY STATS ─────────────────────────────────────────────────────────────

def build_summary(rows):
    paper_counts = Counter(r["Newspaper_Name"] for r in rows)
    years = [r["Year"].strip() for r in rows if r["Year"].strip()]
    uuid_filled = sum(1 for r in rows if r.get("People_UUID", "").strip())
    final_class = Counter(r["Final_Classification"] for r in rows if r["Final_Classification"].strip())
    return {
        "total_rows": len(rows),
        "paper_counts": {short(k): v for k, v in paper_counts.items()},
        "year_min": min(years) if years else "?",
        "year_max": max(years) if years else "?",
        "uuid_pct": round(uuid_filled / len(rows) * 100, 1) if rows else 0,
        "individual": final_class.get("Individual", 0),
        "business": final_class.get("Business", 0),
    }


# ── AGENT DATA ───────────────────────────────────────────────────────────────

# Default agent CSV filenames (relative to working directory or specified via CLI)
DEFAULT_AGENT_CSVS = {
    "Israelite": "Israelite Agents.csv",
    "Occident":  "Occident Agents.csv",
    "Messenger": "The Jewish Messenger Agents.csv",
    "Gleaner":   "The Weekly Gleaner Agents.csv",
}

# Prebuilt geocode cache for major agent cities (lat/lng)
GEOCACHE = {
    "Albany":{"lat":42.6526,"lng":-73.7562},"Atlanta":{"lat":33.749,"lng":-84.388},
    "Augusta":{"lat":33.4735,"lng":-82.0105},"Baltimore":{"lat":39.2904,"lng":-76.6122},
    "Boston":{"lat":42.3601,"lng":-71.0589},"Buffalo":{"lat":42.8864,"lng":-78.8784},
    "Charleston":{"lat":32.7765,"lng":-79.9311},"Chicago":{"lat":41.8781,"lng":-87.6298},
    "Cincinnati":{"lat":39.1031,"lng":-84.512},"Cleveland":{"lat":41.4993,"lng":-81.6944},
    "Columbus":{"lat":39.9612,"lng":-82.9988},"Detroit":{"lat":42.3314,"lng":-83.0458},
    "Hartford":{"lat":41.7637,"lng":-72.6851},"Houston":{"lat":29.7604,"lng":-95.3698},
    "Indianapolis":{"lat":39.7684,"lng":-86.1581},"Jacksonville":{"lat":30.3322,"lng":-81.6557},
    "Kansas City":{"lat":39.0997,"lng":-94.5786},"Louisville":{"lat":38.2527,"lng":-85.7585},
    "Memphis":{"lat":35.1495,"lng":-90.049},"Milwaukee":{"lat":43.0389,"lng":-87.9065},
    "Mobile":{"lat":30.6954,"lng":-88.0399},"Nashville":{"lat":36.1627,"lng":-86.7816},
    "New Haven":{"lat":41.3083,"lng":-72.9279},"New Orleans":{"lat":29.9511,"lng":-90.0715},
    "New York":{"lat":40.7128,"lng":-74.006},"New York City":{"lat":40.7128,"lng":-74.006},
    "Newark":{"lat":40.7357,"lng":-74.1724},"Norfolk":{"lat":36.8508,"lng":-76.2859},
    "Philadelphia":{"lat":39.9526,"lng":-75.1652},"Pittsburgh":{"lat":40.4406,"lng":-79.9959},
    "Portland":{"lat":45.5051,"lng":-122.675},"Providence":{"lat":41.824,"lng":-71.4128},
    "Richmond":{"lat":37.5407,"lng":-77.436},"Rochester":{"lat":43.1566,"lng":-77.6088},
    "Sacramento":{"lat":38.5816,"lng":-121.4944},"San Francisco":{"lat":37.7749,"lng":-122.4194},
    "Savannah":{"lat":32.0835,"lng":-81.0998},"St. Louis":{"lat":38.627,"lng":-90.1994},
    "Syracuse":{"lat":43.0481,"lng":-76.1474},"Troy":{"lat":42.7284,"lng":-73.6918},
    "Utica":{"lat":43.1009,"lng":-75.2327},"Washington":{"lat":38.9072,"lng":-77.0369},
    "Wilmington":{"lat":39.7447,"lng":-75.5484},"Worcester":{"lat":42.2626,"lng":-71.8023},
    "Harrisburg":{"lat":40.2732,"lng":-76.8867},"Lancaster":{"lat":40.0379,"lng":-76.3055},
    "Reading":{"lat":40.3356,"lng":-75.9269},"Allentown":{"lat":40.6023,"lng":-75.4714},
    "Pottsville":{"lat":40.6862,"lng":-76.1955},"Erie":{"lat":42.1292,"lng":-80.0851},
    "Scranton":{"lat":41.4090,"lng":-75.6624},"Wheeling":{"lat":40.0640,"lng":-80.7209},
    "Lexington":{"lat":38.0406,"lng":-84.5037},"Covington":{"lat":39.0837,"lng":-84.5086},
    "Dayton":{"lat":39.7589,"lng":-84.1916},"Toledo":{"lat":41.6639,"lng":-83.5552},
    "Zanesville":{"lat":39.9403,"lng":-82.0132},"Sandusky":{"lat":41.4553,"lng":-82.7077},
    "Springfield":{"lat":39.9242,"lng":-83.8088},"Chillicothe":{"lat":39.3334,"lng":-82.9821},
    "Quincy":{"lat":39.9356,"lng":-91.4099},"Galena":{"lat":42.4170,"lng":-90.4290},
    "Peoria":{"lat":40.6936,"lng":-89.5890},"Rockford":{"lat":42.2711,"lng":-89.0940},
    "Madison":{"lat":43.0731,"lng":-89.4012},"Kenosha":{"lat":42.5847,"lng":-87.8212},
    "Racine":{"lat":42.7261,"lng":-87.7829},"Fond du Lac":{"lat":43.7730,"lng":-88.4471},
    "Green Bay":{"lat":44.5133,"lng":-88.0133},"La Crosse":{"lat":43.8014,"lng":-91.2396},
    "Dubuque":{"lat":42.5006,"lng":-90.6646},"Davenport":{"lat":41.5236,"lng":-90.5776},
    "Burlington":{"lat":40.8073,"lng":-91.1128},"Des Moines":{"lat":41.5868,"lng":-93.6250},
    "St. Paul":{"lat":44.9537,"lng":-93.0900},"Leavenworth":{"lat":39.3111,"lng":-94.9225},
    "Galveston":{"lat":29.3013,"lng":-94.7977},"San Antonio":{"lat":29.4241,"lng":-98.4936},
    "Denver":{"lat":39.7392,"lng":-104.9903},"Salt Lake City":{"lat":40.7608,"lng":-111.891},
    "Los Angeles":{"lat":34.0522,"lng":-118.2437},"Portland ME":{"lat":43.6615,"lng":-70.2553},
    "Bangor":{"lat":44.8016,"lng":-68.7712},"Bath":{"lat":43.9120,"lng":-69.8195},
    "Concord":{"lat":43.2081,"lng":-71.5376},"Nashua":{"lat":42.7654,"lng":-71.4676},
    "Springfield MA":{"lat":42.1015,"lng":-72.5898},"Lowell":{"lat":42.6334,"lng":-71.3162},
    "Lynn":{"lat":42.4668,"lng":-70.9495},"New Bedford":{"lat":41.6362,"lng":-70.9342},
    "Taunton":{"lat":41.9001,"lng":-71.0898},"Trenton":{"lat":40.2171,"lng":-74.7429},
    "Camden":{"lat":39.9259,"lng":-75.1196},"Elizabeth":{"lat":40.6640,"lng":-74.2107},
    "Paterson":{"lat":40.9176,"lng":-74.1719},"Bridgeport":{"lat":41.1865,"lng":-73.1952},
    "Waterbury":{"lat":41.5582,"lng":-73.0515},"New London":{"lat":41.3557,"lng":-72.0995},
    "Norwalk":{"lat":41.1177,"lng":-73.4082},"Middletown":{"lat":41.5623,"lng":-72.6507},
    "Yreka":{"lat":41.7349,"lng":-122.6347},"Stockton":{"lat":37.9577,"lng":-121.2908},
    "Marysville":{"lat":39.1457,"lng":-121.5910},"Grass Valley":{"lat":39.2196,"lng":-121.0605},
    "Nevada City":{"lat":39.2613,"lng":-121.0080},"Placerville":{"lat":38.7296,"lng":-120.7985},
    "Columbia":{"lat":34.0007,"lng":-81.0348},"Georgetown":{"lat":38.9072,"lng":-77.0369},
    "Natchez":{"lat":31.5604,"lng":-91.4032},"Vicksburg":{"lat":32.3526,"lng":-90.8779},
    "Baton Rouge":{"lat":30.4515,"lng":-91.1871},"Shreveport":{"lat":32.5252,"lng":-93.7502},
    "Pensacola":{"lat":30.4213,"lng":-87.2169},"Tallahassee":{"lat":30.4383,"lng":-84.2807},
    "Montgomery":{"lat":32.3668,"lng":-86.3000},"Selma":{"lat":32.4074,"lng":-87.0211},
    "Tuscaloosa":{"lat":33.2098,"lng":-87.5692},"Huntsville":{"lat":34.7304,"lng":-86.5861},
    "Knoxville":{"lat":35.9606,"lng":-83.9207},"Chattanooga":{"lat":35.0456,"lng":-85.3097},
    "Clarksville":{"lat":36.5298,"lng":-87.3595},"Memphis TN":{"lat":35.1495,"lng":-90.049},
    "Raleigh":{"lat":35.7796,"lng":-78.6382},"Wilmington NC":{"lat":34.2257,"lng":-77.9447},
    "Fayetteville":{"lat":35.0527,"lng":-78.8784},"Petersburg":{"lat":37.2279,"lng":-77.4019},
    "Fredericksburg":{"lat":38.3032,"lng":-77.4605},"Alexandria":{"lat":38.8048,"lng":-77.0469},
    "Lynchburg":{"lat":37.4138,"lng":-79.1423},"Staunton":{"lat":38.1496,"lng":-79.0717},
    "Montreal":{"lat":45.5017,"lng":-73.5673},"Toronto":{"lat":43.6532,"lng":-79.3832},
    "Hamilton":{"lat":43.2557,"lng":-79.8711},"London":{"lat":42.9849,"lng":-81.2453},
    "Kingston":{"lat":44.2312,"lng":-76.4860},"Quebec City":{"lat":46.8139,"lng":-71.2080},
    "Halifax":{"lat":44.6488,"lng":-63.5752},"St. John":{"lat":45.2733,"lng":-66.0633},
}

def geocode_agent_city(city):
    """Return (lat, lng) for a city string, or (None, None) if unknown."""
    if not city:
        return None, None
    # Try exact match first
    g = GEOCACHE.get(city)
    if g:
        return g["lat"], g["lng"]
    # Try stripping state suffix like "Boston, MA"
    if "," in city:
        base = city.split(",")[0].strip()
        g = GEOCACHE.get(base)
        if g:
            return g["lat"], g["lng"]
    return None, None


def build_agent_data(agent_files):
    """
    Process four agent CSV files and return a dict with agent map points,
    timeline, tenure, and city competition data.

    agent_files: dict mapping paper short name -> file path (or None if missing)
    """
    agent_map = []   # [{paper, name, city, state, lat, lng, start, end, addr, notes}]
    agent_timeline = {}   # {paper: {year: count}}
    agent_tenure = []     # [{paper, name, city, start, end, duration}]
    city_papers = defaultdict(lambda: defaultdict(int))   # city -> paper -> count

    for paper, fpath in agent_files.items():
        if not fpath or not os.path.exists(fpath):
            continue
        try:
            with open(fpath, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            print(f"  Warning: could not read {fpath}: {e}")
            continue

        tl = defaultdict(int)

        for row in rows:
            # Column name is Agent_Name across all four CSVs
            name = row.get("Agent_Name", row.get("Agent Name", row.get("Name", ""))).strip()
            if not name:
                continue

            city = row.get("Agent_City", row.get("City", "")).strip()
            state = row.get("Agent_State", row.get("State", "")).strip()
            addr = row.get("Agent_Address", row.get("Address", "")).strip()
            # Gleaner uses "Notes" instead of "Agent_Notes"
            notes = (row.get("Agent_Notes") or row.get("Notes") or "").strip()

            # Dates are ISO timestamps like "1860-12-28T00:00:00Z" - extract year
            start_raw = (row.get("Start_Date") or row.get("Agent_Start_Year") or "").strip()
            end_raw = (row.get("End_Date") or row.get("Agent_End_Year") or "").strip()

            # Skip "Travelling" as it has no fixed location
            if city.lower() == "travelling":
                city = ""

            # Use lat/lng from CSV if available; fall back to geocode cache
            lat = None
            lng = None
            try:
                lat_raw = row.get("Latitude", "").strip()
                lng_raw = row.get("Longitude", "").strip()
                if lat_raw and lng_raw:
                    lat = float(lat_raw)
                    lng = float(lng_raw)
            except (ValueError, AttributeError):
                pass
            if lat is None and city:
                lat, lng = geocode_agent_city(city)

            start_yr = None
            end_yr = None
            # Parse year from ISO timestamp ("1860-12-28T00:00:00Z") or plain int
            def parse_year(raw):
                if not raw:
                    return None
                try:
                    return int(raw[:4])  # works for both ISO dates and plain year strings
                except (ValueError, TypeError):
                    return None
            start_yr = parse_year(start_raw)
            end_yr = parse_year(end_raw)

            # Build timeline entry: count agents active in each year
            if start_yr:
                if end_yr and end_yr >= start_yr:
                    for yr in range(start_yr, end_yr + 1):
                        tl[str(yr)] += 1
                else:
                    tl[str(start_yr)] += 1

            # Build tenure record for agents with both dates
            if start_yr and end_yr and end_yr >= start_yr:
                agent_tenure.append({
                    "paper": paper,
                    "name": name,
                    "city": city,
                    "start": start_yr,
                    "end": end_yr,
                    "duration": end_yr - start_yr
                })

            # Map point
            agent_map.append({
                "paper": paper,
                "name": name,
                "city": city,
                "state": state,
                "lat": lat,
                "lng": lng,
                "start": start_yr,
                "end": end_yr,
                "addr": addr,
                "notes": notes,
            })

            if city:
                city_papers[city][paper] += 1

        agent_timeline[paper] = sorted(tl.items())

    # Compute all years range
    all_years = set()
    for tl_items in agent_timeline.values():
        for yr_str, _ in tl_items:
            try:
                all_years.add(int(yr_str))
            except ValueError:
                pass
    all_years_sorted = sorted(all_years)

    def tl_series(paper):
        d = dict(agent_timeline.get(paper, []))
        return [d.get(str(y), 0) for y in all_years_sorted]

    # Multi-paper city competition
    multi_cities = {c: dict(papers) for c, papers in city_papers.items() if len(papers) >= 2}
    multi_sorted = sorted(multi_cities.items(), key=lambda x: -sum(x[1].values()))[:15]
    multi_city_labels = [c for c, _ in multi_sorted]
    multi_city_data = {p: [multi_cities.get(c, {}).get(p, 0) for c, _ in multi_sorted]
                       for p in PAPERS}

    # Tenure distribution buckets
    tenure_buckets = [0, 0, 0, 0]  # 0yr, 1-2yr, 3-5yr, 6+yr
    for t in agent_tenure:
        dur = t["duration"]
        if dur == 0:
            tenure_buckets[0] += 1
        elif dur <= 2:
            tenure_buckets[1] += 1
        elif dur <= 5:
            tenure_buckets[2] += 1
        else:
            tenure_buckets[3] += 1

    return {
        "agent_map": agent_map,
        "agent_timeline": {p: tl_series(p) for p in PAPERS},
        "all_years_agent": all_years_sorted,
        "multi_city_labels": multi_city_labels,
        "multi_city_data": multi_city_data,
        "tenure_buckets": tenure_buckets,
    }


# ── ARCHIVAL COVERAGE + NORMALIZATION DATA ────────────────────────────────────

# Publication frequencies (issues per year) for each paper
PAPER_FREQS = {"Occident": 12, "Israelite": 52, "Messenger": 52, "Gleaner": 52}

def build_coverage_data(rows):
    """
    For each paper/year, compute how many distinct issue-periods (weeks for
    weeklies, months for monthlies) have at least one subscriber record.
    Returns {paper: {year: {count, expected, pct}}}.
    """
    from datetime import datetime as _dt
    issue_dates = defaultdict(lambda: defaultdict(set))  # paper -> year -> set of period keys
    for r in rows:
        paper = SHORT.get(r["Newspaper_Name"], "")
        year  = r.get("Year", "").strip()
        dt_s  = r.get("Datetime", "").strip()
        if not (paper and year and dt_s):
            continue
        try:
            d = _dt.fromisoformat(dt_s.rstrip("Z").replace("T", " ").split(" ")[0])
            freq = PAPER_FREQS.get(paper, 52)
            key  = d.isocalendar()[1] if freq >= 52 else d.month
            issue_dates[paper][year].add(key)
        except Exception:
            pass

    coverage = {}
    for paper in PAPERS:
        coverage[paper] = {}
        for year, dates in sorted(issue_dates[paper].items()):
            exp = PAPER_FREQS.get(paper, 52)
            coverage[paper][year] = {
                "count": len(dates),
                "expected": exp,
                "pct": round(len(dates) / exp * 100, 1),
            }
    return coverage


def build_place_year_data(rows, map_data):
    """
    For each place in map_data, return a year-by-year breakdown of subscription
    counts per paper: {loc: {year: {paper_short: count}}}.
    """
    top_locs = {p["loc"] for p in map_data}
    place_year = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        paper = SHORT.get(r["Newspaper_Name"], "")
        loc   = r.get("Place_edited", "").strip()
        year  = r.get("Year", "").strip()
        if paper and loc and year and loc in top_locs:
            place_year[loc][year][paper] += 1
    return {loc: {yr: dict(papers) for yr, papers in yrs.items()}
            for loc, yrs in place_year.items()}


def build_agent_network_data(rows, agent_files):
    """
    Builds two network datasets:
    1. agent_net: top agents by subscriber recruitment (from Subscriber Agent field).
    2. paper_competition: pairs of papers with lists of shared agent cities.
    """
    from itertools import combinations as _comb

    # Agent recruitment from subscriber CSV
    agent_city_subs = defaultdict(lambda: defaultdict(int))  # (agent, paper) -> city -> count
    for r in rows:
        paper = SHORT.get(r["Newspaper_Name"], "")
        agent = r.get("Subscriber Agent", "").strip()
        city  = r.get("Place_edited", "").strip()
        if agent and paper and city:
            agent_city_subs[(agent, paper)][city] += 1

    agent_totals = {k: sum(v.values()) for k, v in agent_city_subs.items()}
    top_agents = sorted(agent_totals.items(), key=lambda x: -x[1])[:20]
    agent_net = []
    for (agent, paper), total in top_agents:
        top_cities = dict(sorted(agent_city_subs[(agent, paper)].items(),
                                 key=lambda x: -x[1])[:8])
        agent_net.append({"agent": agent, "paper": paper,
                          "total": total, "cities": top_cities})

    # Paper-competition from agent CSV files
    paper_city_agents = defaultdict(set)
    for paper, fpath in (agent_files or {}).items():
        if not fpath or not os.path.exists(fpath):
            continue
        try:
            with open(fpath, encoding="utf-8-sig") as f:
                for ag in csv.DictReader(f):
                    city = ag.get("Agent_City", "").strip()
                    if city and city.lower() != "travelling":
                        paper_city_agents[paper].add(city)
        except Exception:
            pass

    paper_competition = {}
    for p1, p2 in _comb(PAPERS, 2):
        shared = sorted(paper_city_agents[p1] & paper_city_agents[p2])
        if shared:
            paper_competition[f"{p1}|{p2}"] = shared

    return {"agent_net": agent_net, "paper_competition": paper_competition}


# ── HTML TEMPLATE ─────────────────────────────────────────────────────────────

def build_html(data):
    d = data

    # Agent data (may be empty if no agent CSVs provided)
    ag = d.get("agents", {})
    agent_map_json = json.dumps(ag.get("agent_map", []))
    all_years_agent_json = json.dumps(ag.get("all_years_agent", []))
    agent_tl_json = json.dumps(ag.get("agent_timeline", {p: [] for p in PAPERS}))
    multi_city_labels_json = json.dumps(ag.get("multi_city_labels", []))
    multi_city_data_json = json.dumps(ag.get("multi_city_data", {p: [] for p in PAPERS}))
    tenure_json = json.dumps(ag.get("tenure_buckets", [0, 0, 0, 0]))

    js_data = "\n".join([
        f"const MAP_DATA={json.dumps(d['map'])};",
        f"const MONO_DATA={json.dumps(d['monopoly'])};",
        f"const TIMELINE_DATA={json.dumps(d['timeline'])};",
        f"const FLOW_DATA={json.dumps(d['flow'])};",
        f"const CLASS_DATA={json.dumps(d['class_data'])};",
        f"const REGION_DATA={json.dumps(d['region_data'])};",
        f"const REGION_NAMES={json.dumps(d['region_names'])};",
        f"const ALL_YEARS={json.dumps(d['all_years'])};",
        f"const WEEKLY_DATA={json.dumps(d['weekly'])};",
        f"const STATE_DATA={json.dumps(d['states'])};",
        f"const TYPE_DATA={json.dumps(d['types'])};",
        f"const CLERGY_DATA={json.dumps(d['clergy'])};",
        f"const PAPER_TOTALS={json.dumps(d['paper_totals'])};",
        f"const TYPE_TOTALS={json.dumps(d['type_totals'])};",
        f"const GLEANER_EXIT={json.dumps(d['gleaner_exits'])};",
        f"const SUMMARY={json.dumps(d['summary'])};",
        f"const AGENT_MAP_DATA={agent_map_json};",
        f"const ALL_YEARS_AGENT={all_years_agent_json};",
        f"const AGENT_TL={agent_tl_json};",
        f"const MULTI_CITY_LABELS={multi_city_labels_json};",
        f"const MULTI_CITY_DATA={multi_city_data_json};",
        f"const TENURE_BUCKETS={tenure_json};",
        f"const PLACE_YEAR_DATA={json.dumps(d.get('place_year', {}))};",
        f"const COVERAGE_DATA={json.dumps(d.get('coverage', {}))};",
        f"const AGENT_NET_DATA={json.dumps(d.get('agent_net', []))};",
        f"const PAPER_COMPETITION={json.dumps(d.get('paper_competition', {}))};",
    ])

    s = d["summary"]
    subtitle = f"{s['total_rows']:,} subscriptions &middot; {len(s['paper_counts'])} newspapers &middot; {s['year_min']}&ndash;{s['year_max']} &middot; {len(d['map'])} places"

    js_logic = r"""
const C = {Occident:"#4e79a7",Israelite:"#e15759",Messenger:"#59a14f",Gleaner:"#f28e2b"};
const PAPERS = ["Occident","Israelite","Messenger","Gleaner"];
const S2F = {Occident:"The Occident, and American Jewish Advocate",Israelite:"The Israelite",Messenger:"The Jewish Messenger",Gleaner:"The Weekly Gleaner"};
const RCOLS = {"New England":"#a6cee3","Mid-Atlantic":"#1f78b4","South":"#b2df8a","Midwest":"#33a02c","West":"#fb9a99","Canada/Caribbean/Other":"#cab2d6"};
const GC = "#ede5d8";

const _inited = {};
function showPanel(name, btn) {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav button").forEach(b => b.classList.remove("active"));
  document.getElementById("panel-" + name).classList.add("active");
  btn.classList.add("active");
  const fns = {monopoly:initMonopoly,timeline:initTimeline,weekly:initWeekly,regions:initRegions,states:initStates,demo:initDemo,flow:initFlow,agentmap:initAgentMap,agents:initAgents};
  if (!_inited[name] && fns[name]) { _inited[name] = true; fns[name](); }
}

const mLayers = {};
const activePapers = {Occident:true,Israelite:true,Messenger:true,Gleaner:true};
let mapYear = null;
const lmap = L.map("map").setView([38,-92],4);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",{attribution:"&copy; OSM &copy; CARTO",maxZoom:18}).addTo(lmap);
PAPERS.forEach(p => { mLayers[p] = L.layerGroup().addTo(lmap); });

function getYrCount(place, sn) {
  if (!mapYear) return place.papers[S2F[sn]] || 0;
  return ((PLACE_YEAR_DATA[place.loc] || {})[String(mapYear)] || {})[sn] || 0;
}

function rebuildMapLayers() {
  PAPERS.forEach(p => mLayers[p].clearLayers());
  MAP_DATA.forEach(place => {
    if (!place.lat || !place.lng) return;
    const paperCounts = Object.fromEntries(PAPERS.map(p => [p, getYrCount(place, p)]));
    const total = Object.values(paperCounts).reduce((a,b)=>a+b,0);
    if (!total) return;
    const nP = PAPERS.filter(p => paperCounts[p]>0).length;
    PAPERS.forEach(sn => {
      const count = paperCounts[sn];
      if (!count) return;
      const r = Math.max(5, Math.min(45, Math.sqrt(count) * 3));
      const circ = L.circleMarker([place.lat, place.lng], {
        radius:r, fillColor:C[sn], color:nP>1?"#2c2416":C[sn],
        weight:nP>1?1.8:0.5, fillOpacity:0.6, opacity:0.85
      });
      const bars = PAPERS.filter(p=>paperCounts[p]>0).map(p => {
        const pct = Math.round(paperCounts[p] / total * 100);
        return `<div class=pr><span>${p}</span><span>${paperCounts[p]}</span></div><div class=pbw><div class=pb style="width:${pct}%;background:${C[p]}"></div></div>`;
      }).join("");
      const yrLabel = mapYear ? `Year: ${mapYear}` : `Active: ${place.years[0]}\u2013${place.years[place.years.length-1]}`;
      circ.bindPopup(`<div class=pt>${place.loc}${place.state?", "+place.state:""}</div><div class=pr><span>${mapYear?"Subscribers":"Total"}</span><span><b>${total}</b></span></div><div style="margin-top:6px">${bars}</div><div style="margin-top:6px;opacity:.5;font-size:.68rem">${yrLabel}</div>`);
      if (activePapers[sn]) mLayers[sn].addLayer(circ);
    });
  });
}

rebuildMapLayers();

function setMapYear(yr) {
  mapYear = yr ? parseInt(yr) : null;
  const note = document.getElementById("mapCovNote");
  if (mapYear) {
    const covInfo = PAPERS.map(p => {
      const c = (COVERAGE_DATA[p] || {})[String(mapYear)];
      return c ? p+": "+c.pct+"%" : null;
    }).filter(Boolean).join(" \u00b7 ");
    note.textContent = covInfo ? "Archival coverage \u2014 "+covInfo : "";
  } else {
    note.textContent = "";
  }
  rebuildMapLayers();
}

function togglePaper(p) {
  activePapers[p] = !activePapers[p];
  document.getElementById("pill-"+p).classList.toggle("off", !activePapers[p]);
  activePapers[p] ? mLayers[p].addTo(lmap) : lmap.removeLayer(mLayers[p]);
}

function mkChart(id, cfg) { return new Chart(document.getElementById(id), cfg); }
function axes() { return {x:{grid:{color:GC}}, y:{grid:{color:GC},beginAtZero:true}}; }
function sAxes() { return {x:{stacked:true,grid:{color:GC}}, y:{stacked:true,grid:{color:GC},beginAtZero:true}}; }
function roll(arr, w) {
  return arr.map((_,i) => {
    const sl = arr.slice(Math.max(0,i-w+1), i+1);
    return sl.reduce((a,b) => a+b, 0) / sl.length;
  });
}

let tlChart = null;
function tlRawOrNorm(paper, year) {
  const raw = (TIMELINE_DATA.find(d=>d.year===year)||{})[paper] || 0;
  const norm = document.getElementById("tlNorm") && document.getElementById("tlNorm").checked;
  if (!norm) return raw;
  const cov = (COVERAGE_DATA[paper]||{})[String(year)];
  if (!cov || cov.pct < 5) return raw;
  return Math.round(raw / (cov.pct / 100));
}

function covWarningPoints(paper) {
  return TIMELINE_DATA.map(d => {
    const cov = (COVERAGE_DATA[paper]||{})[String(d.year)];
    return cov && cov.pct < 50 ? tlRawOrNorm(paper, d.year) : null;
  });
}

function initTimeline() {
  const yrs = TIMELINE_DATA.map(d => d.year);
  tlChart = mkChart("c-timeline",{type:"line",data:{labels:yrs,datasets:[
    ...PAPERS.map(p=>({label:p, data:yrs.map(y=>tlRawOrNorm(p,y)), borderColor:C[p], backgroundColor:C[p]+"18", tension:0.3, borderWidth:2.5, pointRadius:2.5, fill:false})),
    ...PAPERS.map(p=>({label:p+" (low coverage)", data:covWarningPoints(p), borderColor:C[p], backgroundColor:C[p]+"55", borderWidth:0, pointRadius:6, pointStyle:"rectRot", fill:false, showLine:false}))
  ]},options:{responsive:true,plugins:{legend:{labels:{color:"#5a4a32",filter:i=>!i.text.includes("(low")},position:"top"},tooltip:{callbacks:{afterBody:lines=>{const yr=lines[0].label; return PAPERS.map(p=>{const c=(COVERAGE_DATA[p]||{})[String(yr)]; return c?p+" coverage: "+c.pct+"%":null;}).filter(Boolean).join("\n");}}}},scales:axes()}});
  mkChart("c-stacked",{type:"bar",data:{labels:yrs,datasets:PAPERS.map(p=>({label:p,data:TIMELINE_DATA.map(d=>d[p]),backgroundColor:C[p]+"bb",borderWidth:0}))},options:{responsive:true,plugins:{legend:{position:"top"}},scales:sAxes()}});
  const pn = Object.keys(CLASS_DATA);
  mkChart("c-class",{type:"bar",data:{labels:pn,datasets:[{label:"Individual",data:pn.map(p=>CLASS_DATA[p].Individual),backgroundColor:"#7b9dc9bb",borderWidth:0},{label:"Business",data:pn.map(p=>CLASS_DATA[p].Business),backgroundColor:"#c97b7bbb",borderWidth:0}]},options:{responsive:true,plugins:{legend:{position:"top"}},scales:sAxes()}});
}

function updateTimeline() {
  if (!tlChart) return;
  const yrs = TIMELINE_DATA.map(d => d.year);
  PAPERS.forEach((p,i) => { tlChart.data.datasets[i].data = yrs.map(y=>tlRawOrNorm(p,y)); });
  PAPERS.forEach((p,i) => { tlChart.data.datasets[PAPERS.length+i].data = covWarningPoints(p); });
  tlChart.update();
}

let covChart = null;
function toggleCovChart() {
  const show = document.getElementById("tlCov").checked;
  document.getElementById("cov-chart-box").style.display = show ? "" : "none";
  if (show && !covChart) {
    const yrs = TIMELINE_DATA.map(d=>d.year);
    covChart = mkChart("c-coverage",{type:"bar",data:{labels:yrs,datasets:PAPERS.map(p=>({label:p,data:yrs.map(y=>{const c=(COVERAGE_DATA[p]||{})[String(y)];return c?c.pct:0;}),backgroundColor:yrs.map(y=>{const c=(COVERAGE_DATA[p]||{})[String(y)];return c&&c.pct<50?C[p]+"66":C[p]+"bb";}),borderWidth:0}))},options:{responsive:true,plugins:{legend:{labels:{color:"#5a4a32"},position:"top"}},scales:{x:{stacked:true,grid:{color:GC},ticks:{color:"#7a6a52"}},y:{stacked:false,max:105,grid:{color:GC},ticks:{color:"#7a6a52",callback:v=>v+"%"},title:{display:true,text:"% issues with records",color:"#7a6a52"}}}}});
  }
}

let wChart = null;
function initWeekly() {
  const ys = [...new Set(WEEKLY_DATA.map(d => d.week.split("-W")[0]))].sort();
  const s1 = document.getElementById("wy1"), s2 = document.getElementById("wy2");
  ys.forEach(y => { s1.add(new Option(y,y)); s2.add(new Option(y,y)); });
  s1.value = ys[Math.max(0,ys.indexOf("1857"))];
  s2.value = ys[Math.min(ys.length-1,ys.indexOf("1862")<0?ys.length-1:ys.indexOf("1862"))];
  updateWeekly();
}
function updateWeekly() {
  const y1 = document.getElementById("wy1").value;
  const y2 = document.getElementById("wy2").value;
  const showAg = document.getElementById("showAgent").checked;
  const w = parseInt(document.getElementById("wroll").value);
  const fil = WEEKLY_DATA.filter(d => { const y=d.week.split("-W")[0]; return y>=y1 && y<=y2; });
  const labels = fil.map(d => d.week);
  const datasets = [];
  PAPERS.forEach(p => {
    datasets.push({label:p, data:roll(fil.map(d=>d[p]||0),w), borderColor:C[p], backgroundColor:"transparent", borderWidth:2.5, tension:0.3, pointRadius:0});
    if (showAg) {
      datasets.push({label:p+" (agent)", data:roll(fil.map(d=>d["agent_"+p]||0),w), borderColor:C[p], backgroundColor:"transparent", borderWidth:1.5, borderDash:[5,4], tension:0.3, pointRadius:0});
    }
  });
  if (wChart) wChart.destroy();
  wChart = mkChart("c-weekly",{type:"line",data:{labels,datasets},options:{responsive:true,animation:false,plugins:{legend:{position:"top",labels:{filter:i=>!i.text.includes("(agent)")}}},scales:{x:{ticks:{maxTicksLimit:24,maxRotation:45},grid:{color:GC}},y:{beginAtZero:true,grid:{color:GC},title:{display:true,text:"Subscriptions per week"}}}}});
}

let rTimeChart = null;
function initRegions() {
  updateRegionTime();
  mkChart("c-regiontotal",{type:"bar",data:{labels:REGION_NAMES,datasets:PAPERS.map(p=>({label:p,data:REGION_NAMES.map(r=>ALL_YEARS.reduce((a,y,i)=>a+(REGION_DATA[r][p][i]||0),0)),backgroundColor:C[p]+"bb",borderWidth:0}))},options:{responsive:true,plugins:{legend:{position:"top"}},scales:{x:{grid:{color:GC},ticks:{maxRotation:30}},y:{beginAtZero:true,grid:{color:GC}}}}});
  const propTotals = PAPERS.map(p => REGION_NAMES.reduce((a,r)=>a+ALL_YEARS.reduce((b,y,i)=>b+(REGION_DATA[r][p][i]||0),0),0));
  mkChart("c-regionprop",{type:"bar",data:{labels:PAPERS,datasets:REGION_NAMES.map((r,ri)=>({label:r,data:PAPERS.map((p,pi)=>{const t=propTotals[pi];const v=ALL_YEARS.reduce((a,y,i)=>a+(REGION_DATA[r][p][i]||0),0);return t?Math.round(v/t*100):0;}),backgroundColor:Object.values(RCOLS)[ri]+"cc",borderWidth:0}))},options:{responsive:true,plugins:{legend:{position:"right",labels:{font:{size:10}}}},scales:{x:{stacked:true,grid:{color:GC}},y:{stacked:true,beginAtZero:true,max:100,grid:{color:GC},title:{display:true,text:"% of paper subscribers"}}}}});
}
function updateRegionTime() {
  const p = document.getElementById("regionPaper").value;
  const datasets = REGION_NAMES.map(r => ({label:r, data:REGION_DATA[r][p], backgroundColor:RCOLS[r]+"cc", borderWidth:0}));
  if (rTimeChart) rTimeChart.destroy();
  rTimeChart = mkChart("c-regiontime",{type:"bar",data:{labels:ALL_YEARS,datasets},options:{responsive:true,plugins:{legend:{position:"right",labels:{font:{size:10}}}},scales:sAxes()}});
}

function initStates() {
  mkChart("c-states",{type:"bar",data:{labels:STATE_DATA.map(d=>d.state),datasets:PAPERS.map(p=>({label:p,data:STATE_DATA.map(d=>d[p]),backgroundColor:C[p]+"cc",borderWidth:0}))},options:{indexAxis:"y",responsive:true,plugins:{legend:{position:"top"}},scales:{x:{stacked:true,grid:{color:GC}},y:{stacked:true,ticks:{font:{size:11}}}}}});
  const multi = STATE_DATA.filter(d=>d.num_papers>1).slice(0,20);
  mkChart("c-multistates",{type:"bar",data:{labels:multi.map(d=>d.state),datasets:PAPERS.map(p=>({label:p,data:multi.map(d=>d[p]),backgroundColor:C[p]+"cc",borderWidth:0}))},options:{indexAxis:"y",responsive:true,plugins:{legend:{position:"top"}},scales:{x:{stacked:true,grid:{color:GC}},y:{stacked:true,ticks:{font:{size:11}}}}}});
}

function initDemo() {
  const grps = ["Male","Female","Clergy","Business","Synagogue/Org","Military/Political"];
  const gCols = ["#4e79a7","#e15759","#59a14f","#f28e2b","#9467bd","#8c564b"];
  mkChart("c-type",{type:"bar",data:{labels:PAPERS,datasets:grps.map((t,i)=>({label:t,data:PAPERS.map(p=>{const d=TYPE_DATA[p]||{};const tot=TYPE_TOTALS[p]||1;return Math.round((d[t]||0)/tot*100);}),backgroundColor:gCols[i]+"cc",borderWidth:0}))},options:{responsive:true,plugins:{legend:{position:"top"}},scales:{x:{stacked:true,grid:{color:GC}},y:{stacked:true,max:100,beginAtZero:true,grid:{color:GC},title:{display:true,text:"% of typed rows"}}}}});
  mkChart("c-clergy",{type:"line",data:{labels:ALL_YEARS,datasets:PAPERS.map(p=>({label:p,data:CLERGY_DATA[p],borderColor:C[p],backgroundColor:C[p]+"18",tension:0.3,borderWidth:2,pointRadius:2,fill:false}))},options:{responsive:true,plugins:{legend:{position:"top"}},scales:axes()}});
  mkChart("c-typecomp",{type:"bar",data:{labels:PAPERS,datasets:[{label:"Typed rows",data:PAPERS.map(p=>TYPE_TOTALS[p]),backgroundColor:PAPERS.map(p=>C[p]+"cc"),borderWidth:0},{label:"Untyped",data:PAPERS.map(p=>PAPER_TOTALS[p]-TYPE_TOTALS[p]),backgroundColor:"#cccccc88",borderWidth:0}]},options:{responsive:true,plugins:{legend:{position:"top"}},scales:sAxes()}});
}

function initFlow() {
  drawSankey();
  const occYears = [...new Set(FLOW_DATA.filter(d=>d.from==="Occident").map(d=>d.year))].sort();
  mkChart("c-occflow",{type:"bar",data:{labels:occYears,datasets:["Israelite","Messenger","Gleaner"].map(t=>({label:t,data:occYears.map(y=>{const m=FLOW_DATA.find(d=>d.from==="Occident"&&d.to===t&&d.year===y);return m?m.count:0;}),backgroundColor:C[t]+"bb",borderWidth:0}))},options:{responsive:true,plugins:{legend:{position:"top"}},scales:{x:{stacked:true,grid:{color:GC}},y:{stacked:true,beginAtZero:true,grid:{color:GC}}}}});
  const ge = GLEANER_EXIT;
  mkChart("c-gleaner",{type:"doughnut",data:{labels:["Israelite","Occident","Messenger","Not found elsewhere"],datasets:[{data:[ge.Israelite,ge.Occident,ge.Messenger,ge.not_found],backgroundColor:[C.Israelite,C.Occident,C.Messenger,"#ccc"],borderWidth:2,borderColor:"#f5f0e8"}]},options:{responsive:true,plugins:{legend:{position:"bottom"},tooltip:{callbacks:{label:ctx=>`${ctx.raw} names (${Math.round(ctx.raw/ge.total*100)}%)`}}}}});
}
function drawSankey() {
  const nodeX = {Occident:110,Israelite:310,Messenger:510,Gleaner:710};
  const nodeY = 130;
  const flows = {};
  FLOW_DATA.forEach(d => { const k=d.from+">"+d.to; flows[k]=(flows[k]||0)+d.count; });
  const maxF = Math.max(...Object.values(flows));
  let svg = "";
  Object.entries(flows).forEach(([key,count]) => {
    const [fr,to] = key.split(">");
    if (!nodeX[fr]||!nodeX[to]) return;
    const x1=nodeX[fr], x2=nodeX[to], sw=Math.max(2,(count/maxF)*30);
    const off=x1<x2?-35:35, cx=(x1+x2)/2;
    const al=Math.round(50+(count/maxF)*160).toString(16).padStart(2,"0");
    svg += `<path d="M ${x1} ${nodeY} C ${cx} ${nodeY+off-30}, ${cx} ${nodeY+off-30}, ${x2} ${nodeY}" fill="none" stroke="${C[fr]+al}" stroke-width="${sw}" opacity=".75"/>`;
    if (count>=30) svg += `<text x="${cx}" y="${nodeY+off-42}" text-anchor="middle" font-size="11" font-family="Georgia,serif" fill="#5a4a32">${count}</text>`;
  });
  PAPERS.forEach(p => {
    const x=nodeX[p], tf=Object.entries(flows).reduce((a,[k,v])=>{if(k.startsWith(p+">")||k.endsWith(">"+p))a+=v;return a;},0);
    svg += `<rect x="${x-46}" y="${nodeY-26}" width="92" height="52" rx="6" fill="${C[p]}" opacity=".92"/>`;
    svg += `<text x="${x}" y="${nodeY+6}" text-anchor="middle" font-size="13" font-weight="bold" fill="white" font-family="Georgia,serif">${p}</text>`;
    svg += `<text x="${x}" y="${nodeY+50}" text-anchor="middle" font-size="10" fill="#5a4a32" font-family="Georgia,serif">flow: ${tf}</text>`;
  });
  document.getElementById("sankey").innerHTML = svg;
}

// MONOPOLY MAP
let monoMap = null;
const monoLayers = {};
const monoActive = {Occident:true,Israelite:true,Messenger:true,Gleaner:true,shared:true};

function initMonopoly() {
  monoMap = L.map("mono-map").setView([38,-92],4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",{attribution:"&copy; OSM &copy; CARTO",maxZoom:18}).addTo(monoMap);

  // Shared towns layer (grey, small, background context)
  monoLayers["shared"] = L.layerGroup();
  MONO_DATA.shared.forEach(place => {
    if (!place.lat || !place.lng) return;
    const r = Math.max(3, Math.min(20, Math.sqrt(place.total) * 1.8));
    const circ = L.circleMarker([place.lat, place.lng], {
      radius:r, fillColor:"#999", color:"#666", weight:0.5, fillOpacity:0.3, opacity:0.5
    });
    const paperList = Object.entries(place.papers).map(([fn,c]) => {
      const sn = Object.keys(S2F).find(k => S2F[k]===fn);
      return `${sn||fn}: ${c}`;
    }).join(", ");
    circ.bindPopup(`<div class=pt>${place.loc}${place.state?", "+place.state:""}</div><div class=pr><span>Shared town &mdash; ${Object.keys(place.papers).length} papers</span></div><div style="margin-top:5px;font-size:.75rem;opacity:.8">${paperList}</div>`);
    monoLayers["shared"].addLayer(circ);
  });

  // Monopoly layers per paper
  PAPERS.forEach(p => { monoLayers[p] = L.layerGroup(); });
  MONO_DATA.monopoly.forEach(place => {
    if (!place.lat || !place.lng) return;
    const p = place.dominant;
    if (!C[p]) return;
    const r = Math.max(5, Math.min(38, Math.sqrt(place.total) * 3.2));
    const circ = L.circleMarker([place.lat, place.lng], {
      radius:r, fillColor:C[p], color:C[p], weight:0.5, fillOpacity:0.72, opacity:0.9
    });
    const yr0=place.years[0], yr1=place.years[place.years.length-1];
    circ.bindPopup(`<div class=pt>${place.loc}${place.state?", "+place.state:""}</div><div class=pr><span>Sole paper</span><span><b>${p}</b></span></div><div class=pr><span>Subscriptions</span><span>${place.total}</span></div><div style="margin-top:6px;opacity:.5;font-size:.68rem">Active: ${yr0}&ndash;${yr1}</div>`);
    monoLayers[p].addLayer(circ);
  });

  // Add all layers (shared first so monopoly towns render on top)
  monoLayers["shared"].addTo(monoMap);
  PAPERS.forEach(p => monoLayers[p].addTo(monoMap));

  // Summary bar charts
  const md = MONO_DATA;
  mkChart("c-mono-towns",{type:"bar",data:{labels:PAPERS,datasets:[{label:"Monopoly towns",data:PAPERS.map(p=>md.monopoly_counts[p]||0),backgroundColor:PAPERS.map(p=>C[p]+"cc"),borderWidth:0}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{color:GC}},y:{beginAtZero:true,grid:{color:GC}}}}});
  mkChart("c-mono-subs",{type:"bar",data:{labels:PAPERS,datasets:[{label:"Subscriptions in monopoly towns",data:PAPERS.map(p=>md.monopoly_subs[p]||0),backgroundColor:PAPERS.map(p=>C[p]+"cc"),borderWidth:0}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{color:GC}},y:{beginAtZero:true,grid:{color:GC}}}}});
}

function toggleMono(p) {
  monoActive[p] = !monoActive[p];
  document.getElementById("mpill-"+p).classList.toggle("off", !monoActive[p]);
  monoActive[p] ? monoLayers[p].addTo(monoMap) : monoMap.removeLayer(monoLayers[p]);
}

// ── Agent Map ────────────────────────────────────────────────────────
let agentMap = null, agentLayers = {}, agentActive = {Occident:true,Israelite:true,Messenger:true,Gleaner:true};
function initAgentMap() {
  if (agentMap) return;
  if (!AGENT_MAP_DATA.length) {
    document.getElementById("agent-map").innerHTML = "<p style='padding:40px;color:#888;text-align:center'>No agent CSV data was provided when this file was generated. Run build_visualization.py with the agent CSV files to enable this tab.</p>";
    return;
  }
  agentMap = L.map("agent-map").setView([38, -92], 4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",{attribution:"&copy; OSM &copy; CARTO",maxZoom:18}).addTo(agentMap);

  // Background subscriber circles (faint)
  MAP_DATA.forEach(place => {
    if (!place.lat || !place.lng) return;
    const r = Math.max(4, Math.min(30, Math.sqrt(place.total) * 2.5));
    L.circleMarker([place.lat, place.lng], {
      radius:r, fillColor:"#888", color:"#888", weight:0.3, fillOpacity:0.12, opacity:0.2
    }).addTo(agentMap);
  });

  PAPERS.forEach(p => { agentLayers[p] = L.layerGroup(); });

  AGENT_MAP_DATA.forEach(agent => {
    if (!agent.lat || !agent.lng) return;
    const col = C[agent.paper];
    if (!col) return;
    const icon = L.divIcon({
      html: `<svg width="18" height="18" viewBox="0 0 18 18"><polygon points="9,1 17,9 9,17 1,9" fill="${col}" stroke="#fff" stroke-width="1.5"/></svg>`,
      iconSize:[18,18], iconAnchor:[9,9], className:""
    });
    const m = L.marker([agent.lat, agent.lng], {icon});
    const yr = agent.start ? (agent.end && agent.end !== agent.start ? `${agent.start}\u2013${agent.end}` : `${agent.start}`) : "dates unknown";
    m.bindPopup(`<div class=pt>${agent.name}</div><div class=pr><span>Paper</span><span>${agent.paper}</span></div><div class=pr><span>City</span><span>${agent.city}${agent.state ? ", " + agent.state : ""}</span></div><div class=pr><span>Active</span><span>${yr}</span></div>${agent.addr ? `<div style="margin-top:5px;opacity:.55;font-size:.68rem">${agent.addr}</div>` : ""}`);
    agentLayers[agent.paper].addLayer(m);
  });

  PAPERS.forEach(p => agentLayers[p].addTo(agentMap));
  setTimeout(() => agentMap.invalidateSize(), 100);
}

function toggleAgent(p) {
  agentActive[p] = !agentActive[p];
  document.getElementById("apill-"+p).classList.toggle("off", !agentActive[p]);
  agentActive[p] ? agentLayers[p].addTo(agentMap) : agentMap.removeLayer(agentLayers[p]);
}

// ── Agent Charts ─────────────────────────────────────────────────────
function initAgents() {
  setTimeout(initAgentNetworks, 50);
  if (!AGENT_MAP_DATA.length) {
    ["c-agtline","c-agmulti","c-agtenure","c-agcov"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.parentElement.innerHTML += "<p style='color:#888;font-style:italic;font-size:.8rem'>No agent data available.</p>";
    });
    return;
  }

  // Line chart: agents per year by paper
  mkChart("c-agtline", {
    type:"line",
    data:{
      labels: ALL_YEARS_AGENT,
      datasets: PAPERS.map(p => ({
        label: p,
        data: AGENT_TL[p],
        borderColor: C[p],
        backgroundColor: C[p]+"33",
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.25,
        fill: false
      }))
    },
    options:{
      responsive:true,
      plugins:{legend:{labels:{color:"#5a4a32",usePointStyle:true}}},
      scales:{
        x:{grid:{color:GC},ticks:{color:"#7a6a52",maxTicksLimit:20}},
        y:{beginAtZero:true,grid:{color:GC},ticks:{color:"#7a6a52"},title:{display:true,text:"# Agents",color:"#7a6a52"}}
      }
    }
  });

  // Stacked bar: multi-paper agent cities
  mkChart("c-agmulti", {
    type:"bar",
    data:{
      labels: MULTI_CITY_LABELS,
      datasets: PAPERS.map(p => ({
        label: p,
        data: MULTI_CITY_DATA[p],
        backgroundColor: C[p]+"cc",
        borderWidth: 0
      }))
    },
    options:{
      responsive:true,
      plugins:{legend:{labels:{color:"#5a4a32",usePointStyle:true}}},
      scales:{
        x:{stacked:true,grid:{color:GC},ticks:{color:"#7a6a52"}},
        y:{stacked:true,beginAtZero:true,grid:{color:GC},ticks:{color:"#7a6a52"},title:{display:true,text:"Agent appointments",color:"#7a6a52"}}
      }
    }
  });

  // Doughnut: tenure distribution
  mkChart("c-agtenure", {
    type:"doughnut",
    data:{
      labels:["Single year","1\u20132 years","3\u20135 years","6+ years"],
      datasets:[{
        data: TENURE_BUCKETS,
        backgroundColor:["#c9845a","#4e79a7","#59a14f","#e15759"],
        borderWidth:2,
        borderColor:"#fff"
      }]
    },
    options:{
      responsive:true,
      plugins:{
        legend:{position:"right",labels:{color:"#5a4a32",padding:12}},
        tooltip:{callbacks:{label: ctx => " " + ctx.label + ": " + ctx.raw + " agents"}}
      }
    }
  });

  // Bar: subscriber coverage by agent city
  mkChart("c-agcov", {
    type:"bar",
    data:{
      labels: PAPERS,
      datasets:[{
        label:"% subs in agent cities",
        data: PAPERS.map(p => {
          const fullName = S2F[p];
          const agentCities = new Set(AGENT_MAP_DATA.filter(a=>a.paper===p).map(a=>a.city));
          let total = 0, inAgent = 0;
          MAP_DATA.forEach(pl => {
            const cnt = pl.papers[fullName] || 0;
            total += cnt;
            if (agentCities.has(pl.loc)) inAgent += cnt;
          });
          return total > 0 ? Math.round(inAgent/total*100) : 0;
        }),
        backgroundColor: PAPERS.map(p=>C[p]+"cc"),
        borderWidth:0
      }]
    },
    options:{
      responsive:true,
      plugins:{legend:{display:false}},
      scales:{
        x:{grid:{color:GC},ticks:{color:"#7a6a52"}},
        y:{beginAtZero:true,max:100,grid:{color:GC},ticks:{color:"#7a6a52",callback:v=>v+"%"},title:{display:true,text:"% of subscriptions",color:"#7a6a52"}}
      }
    }
  });
}

// ── Paper Competition Network ─────────────────────────────────────────────────
function initPaperNet() {
  const svg = document.getElementById("svg-paper-net");
  const detail = document.getElementById("paper-net-detail");
  if (!svg) return;
  const W = 480, H = 340, cx = W/2, cy = H/2, R = 110;
  const angles = [Math.PI*1.5, 0, Math.PI*0.5, Math.PI];
  const nx = PAPERS.map((_,i) => cx + R*Math.cos(angles[i]));
  const ny = PAPERS.map((_,i) => cy + R*Math.sin(angles[i]));
  const ns = SVG => (tag,attrs) => { const el = document.createElementNS("http://www.w3.org/2000/svg",tag); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v)); SVG.appendChild(el); return el; };
  const mk = ns(svg);

  const pairs = [
    ["Occident","Israelite"],["Occident","Messenger"],["Occident","Gleaner"],
    ["Israelite","Messenger"],["Israelite","Gleaner"],["Messenger","Gleaner"]
  ];
  pairs.forEach(([p1,p2]) => {
    const key = `${p1}|${p2}`;
    const alt = `${p2}|${p1}`;
    const cities = PAPER_COMPETITION[key] || PAPER_COMPETITION[alt] || [];
    if (!cities.length) return;
    const i1 = PAPERS.indexOf(p1), i2 = PAPERS.indexOf(p2);
    const w = Math.max(1.5, Math.min(10, cities.length * 0.45));
    const mid_x = (nx[i1]+nx[i2])/2, mid_y = (ny[i1]+ny[i2])/2;
    const dx = cx-mid_x, dy = cy-mid_y;
    const ctrl_x = mid_x + dx*0.3, ctrl_y = mid_y + dy*0.3;
    const path = mk("path",{d:`M${nx[i1]},${ny[i1]} Q${ctrl_x},${ctrl_y} ${nx[i2]},${ny[i2]}`,fill:"none",stroke:"#b8a890",opacity:"0.55","stroke-width":w,cursor:"pointer"});
    mk("text",{x:ctrl_x,y:ctrl_y-4,"text-anchor":"middle","font-size":"10","fill":"#7a6a52","pointer-events":"none","font-family":"Georgia,serif"}).textContent = cities.length;
    path.addEventListener("click", () => {
      detail.innerHTML = `<b style="color:#4a3a22">${p1} \u2194 ${p2}</b><br><span style="color:#7a6a52">${cities.length} shared agent cities:</span><br>` +
        cities.map(c=>`<span style="display:inline-block;margin:2px 4px;font-size:.76rem;background:#f0e8d8;padding:2px 6px;border-radius:3px">${c}</span>`).join("");
    });
  });

  PAPERS.forEach((p,i) => {
    const g = document.createElementNS("http://www.w3.org/2000/svg","g");
    svg.appendChild(g);
    const gns = ns(g);
    gns("circle",{cx:nx[i],cy:ny[i],r:28,fill:C[p],opacity:"0.85"});
    const words = p==="Gleaner"?["Weekly","Gleaner"]:p==="Messenger"?["Jewish","Messenger"]:[p];
    words.forEach((w,j) => {
      gns("text",{x:nx[i],y:ny[i]+(j-(words.length-1)/2)*13,"text-anchor":"middle","dominant-baseline":"middle","font-size":words.length>1?"9.5":"11","font-family":"Georgia,serif","fill":"#fff","font-weight":"bold","pointer-events":"none"}).textContent = w;
    });
    const sharedCnt = Object.entries(PAPER_COMPETITION).filter(([k])=>k.includes(p)).reduce((s,[,v])=>s+v.length,0);
    gns("text",{x:nx[i],y:ny[i]+36,"text-anchor":"middle","font-size":"9","fill":"#5a4a32","font-family":"Georgia,serif"}).textContent = `${sharedCnt} shared cities`;
  });

  detail.innerHTML = "<span style=\"color:#9a8a72;font-size:.78rem\">Click an edge to see shared cities</span>";
}

// ── Agent Bipartite Network ───────────────────────────────────────────────────
function initAgentBip() {
  const svg = document.getElementById("svg-agent-bip");
  if (!svg || !AGENT_NET_DATA.length) return;

  const W = 760, H = 520, LX = 150, RX = 610;
  const topAgents = AGENT_NET_DATA.slice(0,15);
  const cityTotals = {};
  topAgents.forEach(a => Object.entries(a.cities).forEach(([c,n]) => { cityTotals[c] = (cityTotals[c]||0)+n; }));
  const cities = Object.entries(cityTotals).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([c])=>c);
  const aY = (i) => 30 + i * (H-60) / Math.max(topAgents.length-1,1);
  const cY = (i) => 30 + i * (H-60) / Math.max(cities.length-1,1);
  svg.innerHTML = "";
  const ns = (tag,attrs,parent) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg",tag);
    Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));
    (parent||svg).appendChild(el); return el;
  };

  topAgents.forEach((agent,ai) => {
    Object.entries(agent.cities).filter(([c])=>cities.includes(c)).forEach(([city,count]) => {
      const ci = cities.indexOf(city);
      const w = Math.max(0.8, Math.min(8, Math.sqrt(count)*1.4));
      const col = C[agent.paper] || "#888";
      const mx = (LX+RX)/2;
      ns("path",{d:`M${LX},${aY(ai)} C${mx},${aY(ai)} ${mx},${cY(ci)} ${RX},${cY(ci)}`,
        fill:"none", stroke:col, "stroke-width":w, opacity:"0.35", "stroke-linecap":"round"});
    });
  });

  topAgents.forEach((agent,i) => {
    const y = aY(i), r = Math.max(5, Math.min(16, Math.sqrt(agent.total) * 1.8));
    ns("circle",{cx:LX,cy:y,r,fill:C[agent.paper]||"#888",opacity:"0.85"});
    const label = agent.agent.replace(/\xa0/g," ");
    ns("text",{x:LX-r-4,y,"text-anchor":"end","dominant-baseline":"middle",
      "font-size":"9","font-family":"Georgia,serif","fill":"#4a3a22"}).textContent = label.length>20?label.slice(0,19)+"\u2026":label;
    ns("text",{x:LX+r+3,y,"dominant-baseline":"middle","font-size":"8","fill":"#7a6a52","font-family":"Georgia,serif"}).textContent = agent.total;
  });

  cities.forEach((city,i) => {
    const y = cY(i), r = Math.max(4, Math.min(14, Math.sqrt(cityTotals[city]) * 1.3));
    ns("circle",{cx:RX,cy:y,r,fill:"#8a7a62",opacity:"0.7"});
    ns("text",{x:RX+r+4,y,"dominant-baseline":"middle","font-size":"9","font-family":"Georgia,serif","fill":"#4a3a22"}).textContent = city;
    ns("text",{x:RX-r-3,y,"text-anchor":"end","dominant-baseline":"middle","font-size":"8","fill":"#7a6a52","font-family":"Georgia,serif"}).textContent = cityTotals[city];
  });

  ns("text",{x:LX,y:10,"text-anchor":"middle","font-size":"10","font-weight":"bold","font-family":"Georgia,serif","fill":"#4a3a22"}).textContent = "Agents";
  ns("text",{x:RX,y:10,"text-anchor":"middle","font-size":"10","font-weight":"bold","font-family":"Georgia,serif","fill":"#4a3a22"}).textContent = "Subscriber Cities";
  const papers = [...new Set(topAgents.map(a=>a.paper))];
  papers.forEach((p,pi) => {
    const lx = W/2 - papers.length*50/2 + pi*50;
    ns("circle",{cx:lx,cy:H-8,r:5,fill:C[p]});
    ns("text",{x:lx+7,y:H-4,"font-size":"9","font-family":"Georgia,serif","fill":"#4a3a22"}).textContent = p;
  });
}

function initAgentNetworks() {
  initPaperNet();
  initAgentBip();
}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Mid-19th Century Jewish Newspaper Subscribers</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Georgia,serif;background:#f5f0e8;color:#2c2416}}
.header{{background:#2c2416;color:#f5f0e8;padding:16px 28px;display:flex;align-items:baseline;gap:16px}}
.header h1{{font-size:1.15rem;font-weight:normal;letter-spacing:.03em}}
.header span{{font-size:.76rem;opacity:.5}}
.nav{{display:flex;background:#3d3020;padding:0 20px;overflow-x:auto}}
.nav button{{background:none;border:none;color:#c9b99a;padding:10px 16px;cursor:pointer;font-family:Georgia,serif;font-size:.82rem;border-bottom:3px solid transparent;white-space:nowrap;transition:color .15s,border-color .15s}}
.nav button.active{{color:#f5f0e8;border-bottom-color:#c9845a}}
.nav button:hover{{color:#f5f0e8}}
.panel{{display:none;padding:18px 24px 28px}}
.panel.active{{display:block}}
#map{{height:560px;border-radius:6px;border:1px solid #c9b99a}}
.map-controls{{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}}
.pill{{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;border:2px solid;cursor:pointer;font-size:.78rem;user-select:none;transition:opacity .2s}}
.pill.off{{opacity:.28}}
.dot{{width:10px;height:10px;border-radius:50%}}
.map-note{{font-size:.72rem;color:#7a6a52;margin-left:auto;font-style:italic}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.box{{background:#fff;border-radius:8px;padding:16px 18px 12px;border:1px solid #ddd0bb}}
.box.wide{{grid-column:1/-1}}
.box h3{{font-size:.86rem;font-weight:normal;color:#4a3a22;margin-bottom:3px}}
.box p{{font-size:.7rem;color:#9a8a72;margin-bottom:10px;line-height:1.4}}
.snote{{font-size:.74rem;color:#7a6a52;font-style:italic;margin-bottom:14px;line-height:1.5}}
.ctrl{{display:flex;gap:12px;align-items:center;margin-bottom:10px;flex-wrap:wrap}}
.ctrl label{{font-size:.8rem;color:#5a4a32}}
.ctrl select{{font-family:Georgia,serif;font-size:.8rem;padding:3px 7px;border:1px solid #c9b99a;border-radius:4px;background:#fffdf8;color:#2c2416}}
.leaflet-popup-content-wrapper{{background:#2c2416;color:#f5f0e8;border-radius:6px;font-family:Georgia,serif;font-size:.8rem}}
.leaflet-popup-tip{{background:#2c2416}}
.pt{{font-size:.9rem;margin-bottom:5px;border-bottom:1px solid #5a4a32;padding-bottom:4px}}
.pr{{display:flex;justify-content:space-between;gap:14px;margin:2px 0}}
.pbw{{background:#3d3020;border-radius:3px;height:5px;margin:1px 0 4px}}
.pb{{height:5px;border-radius:3px}}
</style>
</head>
<body>
<div class="header">
  <h1>Mid-Nineteenth Century Jewish Newspaper Subscribers</h1>
  <span>{subtitle}</span>
</div>
<div class="nav">
  <button class="active" onclick="showPanel('map',this)">Map</button>
  <button onclick="showPanel('monopoly',this)">Monopoly Towns</button>
  <button onclick="showPanel('timeline',this)">Timeline</button>
  <button onclick="showPanel('weekly',this)">Weekly Trends</button>
  <button onclick="showPanel('regions',this)">Regions</button>
  <button onclick="showPanel('states',this)">States</button>
  <button onclick="showPanel('demo',this)">Subscriber Types</button>
  <button onclick="showPanel('flow',this)">Flow</button>
  <button onclick="showPanel('agentmap',this)">Agent Map</button>
  <button onclick="showPanel('agents',this)">Agents</button>
</div>
<div id="panel-map" class="panel active">
  <div class="map-controls">
    <div class="pill" id="pill-Occident" style="border-color:#4e79a7;color:#4e79a7" onclick="togglePaper('Occident')"><div class="dot" style="background:#4e79a7"></div>Occident</div>
    <div class="pill" id="pill-Israelite" style="border-color:#e15759;color:#e15759" onclick="togglePaper('Israelite')"><div class="dot" style="background:#e15759"></div>Israelite</div>
    <div class="pill" id="pill-Messenger" style="border-color:#59a14f;color:#59a14f" onclick="togglePaper('Messenger')"><div class="dot" style="background:#59a14f"></div>Messenger</div>
    <div class="pill" id="pill-Gleaner" style="border-color:#f28e2b;color:#f28e2b" onclick="togglePaper('Gleaner')"><div class="dot" style="background:#f28e2b"></div>Weekly Gleaner</div>
    <span class="map-note">Circle size = subscriber count &middot; Toggle papers &middot; Click for detail</span>
  </div>
  <div class="map-controls" style="margin-top:6px;gap:10px;align-items:center">
    <label style="font-size:.8rem;color:#5a4a32;white-space:nowrap">Filter by year:
      <select id="mapYearSel" onchange="setMapYear(this.value)" style="font-family:Georgia,serif;font-size:.8rem;padding:3px 7px;border:1px solid #c9b99a;border-radius:4px;background:#fffdf8;color:#2c2416;margin-left:4px">
        <option value="">All years</option>
        <option value="1843">1843</option><option value="1844">1844</option>
        <option value="1845">1845</option><option value="1846">1846</option>
        <option value="1847">1847</option><option value="1848">1848</option>
        <option value="1849">1849</option><option value="1850">1850</option>
        <option value="1851">1851</option><option value="1852">1852</option>
        <option value="1853">1853</option><option value="1854">1854</option>
        <option value="1855">1855</option><option value="1856">1856</option>
        <option value="1857">1857</option><option value="1858">1858</option>
        <option value="1859">1859</option><option value="1860">1860</option>
        <option value="1861">1861</option><option value="1862">1862</option>
        <option value="1863">1863</option><option value="1864">1864</option>
        <option value="1865">1865</option><option value="1866">1866</option>
        <option value="1867">1867</option><option value="1868">1868</option>
      </select>
    </label>
    <span id="mapCovNote" style="font-size:.72rem;color:#c9845a;font-style:italic"></span>
    <span class="map-note" style="margin-left:auto">Select a year to filter circles to that year&apos;s subscriptions only</span>
  </div>
  <div id="map"></div>
</div>
<div id="panel-monopoly" class="panel">
  <p class="snote">Places where only one newspaper had any subscribers &mdash; 701 towns out of 952 total. The Israelite dominates (511 towns), reflecting its broad Midwestern reach into smaller communities where no other paper competed. Toggle papers to compare geographic footprints. Grey circles = shared towns (2+ papers) shown for context.</p>
  <div class="map-controls">
    <div class="pill" id="mpill-Occident" style="border-color:#4e79a7;color:#4e79a7" onclick="toggleMono('Occident')"><div class="dot" style="background:#4e79a7"></div>Occident</div>
    <div class="pill" id="mpill-Israelite" style="border-color:#e15759;color:#e15759" onclick="toggleMono('Israelite')"><div class="dot" style="background:#e15759"></div>Israelite</div>
    <div class="pill" id="mpill-Messenger" style="border-color:#59a14f;color:#59a14f" onclick="toggleMono('Messenger')"><div class="dot" style="background:#59a14f"></div>Messenger</div>
    <div class="pill" id="mpill-Gleaner" style="border-color:#f28e2b;color:#f28e2b" onclick="toggleMono('Gleaner')"><div class="dot" style="background:#f28e2b"></div>Weekly Gleaner</div>
    <div class="pill" id="mpill-shared" style="border-color:#888;color:#888" onclick="toggleMono('shared')"><div class="dot" style="background:#aaa"></div>Shared towns</div>
    <span class="map-note">Circle size = subscriber count &middot; Click for detail</span>
  </div>
  <div id="mono-map" style="height:460px;border-radius:6px;border:1px solid #c9b99a;margin-bottom:18px"></div>
  <div class="g2">
    <div class="box"><h3>Monopoly towns by newspaper</h3><p>Number of towns where each paper was the sole subscriber source.</p><canvas id="c-mono-towns" style="max-height:220px"></canvas></div>
    <div class="box"><h3>Monopoly subscriptions by newspaper</h3><p>Total subscription rows in monopoly towns per paper.</p><canvas id="c-mono-subs" style="max-height:220px"></canvas></div>
  </div>
</div>
<div id="panel-timeline" class="panel">
  <p class="snote">Year-level subscriber counts. Toggle <em>normalized</em> to adjust for archival survival rate (raw count &divide; coverage %). Toggle <em>coverage</em> to see what fraction of expected issues have surviving records &mdash; years below 50% are marked and counts should be treated with caution.</p>
  <div class="ctrl" style="margin-bottom:10px;flex-wrap:wrap;gap:14px">
    <label style="font-size:.8rem;color:#5a4a32"><input type="checkbox" id="tlNorm" onchange="updateTimeline()"> Normalize by coverage</label>
    <label style="font-size:.8rem;color:#5a4a32"><input type="checkbox" id="tlCov" onchange="toggleCovChart()"> Show archival coverage chart</label>
    <span style="font-size:.71rem;color:#9a8a72;font-style:italic">Coverage = % of expected weekly/monthly issues represented in subscriber records</span>
  </div>
  <div class="g2">
    <div class="box wide" id="cov-chart-box" style="display:none">
      <h3>Archival issue coverage per paper per year</h3>
      <p>Percentage of expected issues (weekly = 52, monthly = 12) with at least one subscriber record. Bars below 50% indicate sparse archives; treat those year counts as lower bounds.</p>
      <canvas id="c-coverage" style="max-height:170px"></canvas>
    </div>
    <div class="box wide"><h3>Subscribers per year by newspaper</h3><p>Absolute counts. Diamond markers = years with under 50% archival coverage.</p><canvas id="c-timeline" style="max-height:270px"></canvas></div>
    <div class="box"><h3>Proportional share by year</h3><p>Relative balance over time.</p><canvas id="c-stacked" style="max-height:250px"></canvas></div>
    <div class="box"><h3>Individual vs. Business by newspaper</h3><p>Final_Classification field (97.8% complete).</p><canvas id="c-class" style="max-height:250px"></canvas></div>
  </div>
</div>
<div id="panel-weekly" class="panel">
  <p class="snote">New subscriptions per week using the Datetime field. Agent-submitted rows flagged separately when enabled.</p>
  <div class="ctrl">
    <label>From: <select id="wy1" onchange="updateWeekly()"></select></label>
    <label>To: <select id="wy2" onchange="updateWeekly()"></select></label>
    <label><input type="checkbox" id="showAgent" onchange="updateWeekly()"> Show agent batches (dashed)</label>
    <label>Average: <select id="wroll" onchange="updateWeekly()"><option value="1">Raw</option><option value="4" selected>4-week</option><option value="8">8-week</option></select></label>
  </div>
  <div class="box wide"><canvas id="c-weekly" style="max-height:380px"></canvas></div>
</div>
<div id="panel-regions" class="panel">
  <p class="snote">States grouped into six regions. The Occident skews Mid-Atlantic and Southern; the Israelite dominates the Midwest; the Messenger is almost entirely Mid-Atlantic; the Gleaner is exclusively Western.</p>
  <div class="g2">
    <div class="box wide">
      <h3>Subscribers by region over time</h3><p>Select a paper:</p>
      <div class="ctrl"><select id="regionPaper" onchange="updateRegionTime()"><option>Occident</option><option>Israelite</option><option>Messenger</option><option>Gleaner</option></select></div>
      <canvas id="c-regiontime" style="max-height:280px"></canvas>
    </div>
    <div class="box"><h3>Subscribers by region per newspaper</h3><p>Total across all years.</p><canvas id="c-regiontotal" style="max-height:260px"></canvas></div>
    <div class="box"><h3>Regional fingerprint per newspaper</h3><p>Proportional breakdown of each paper geographic base.</p><canvas id="c-regionprop" style="max-height:260px"></canvas></div>
  </div>
</div>
<div id="panel-states" class="panel">
  <p class="snote">Top 25 states by total subscriptions.</p>
  <div class="g2">
    <div class="box wide"><h3>Top 25 states by total subscribers</h3><p>Stacked by newspaper.</p><canvas id="c-states" style="max-height:420px"></canvas></div>
    <div class="box wide"><h3>Multi-paper states: subscriber split</h3><p>Only states where two or more papers had subscribers.</p><canvas id="c-multistates" style="max-height:380px"></canvas></div>
  </div>
</div>
<div id="panel-demo" class="panel">
  <p class="snote">The Subscriber Type field is partially populated. The Occident has the most complete gender data; the Messenger is almost entirely untyped except for Clergy rows.</p>
  <div class="g2">
    <div class="box wide"><h3>Subscriber types per newspaper (typed rows only, as % of typed)</h3><p>Male, Female, Business, Clergy, Synagogue/Org, Military/Political.</p><canvas id="c-type" style="max-height:270px"></canvas></div>
    <div class="box"><h3>Clergy and institutional subscribers over time</h3><p>Synagogue, Organization, Clergy, and Scholar rows per year.</p><canvas id="c-clergy" style="max-height:260px"></canvas></div>
    <div class="box"><h3>Type-field completeness by newspaper</h3><p>How many rows have a Subscriber Type vs. total rows.</p><canvas id="c-typecomp" style="max-height:260px"></canvas></div>
  </div>
</div>
<div id="panel-flow" class="panel">
  <p class="snote">A flow is recorded when a subscriber name appears in paper A before paper B (by first-appearance year), using edited names across the full dataset, not UUID only.</p>
  <div class="g2">
    <div class="box wide"><h3>Total subscriber name flows between papers (all years)</h3><p>Curve thickness proportional to number of names. Numbers shown on flows of 30 or more.</p>
      <svg id="sankey" viewBox="0 0 820 260" style="width:100%;margin-top:6px"></svg>
    </div>
    <div class="box"><h3>Occident subscribers first appearing in other papers, by year</h3><p>The 1857 spike shows the Messenger launch pulling Occident readers.</p><canvas id="c-occflow" style="max-height:255px"></canvas></div>
    <div class="box"><h3>Weekly Gleaner subscribers &mdash; where they went</h3><p>Where Gleaner names next appear after the paper ends.</p><canvas id="c-gleaner" style="max-height:255px"></canvas></div>
  </div>
</div>
<div id="panel-agentmap" class="panel">
  <p class="snote">Newspaper agents collected subscription payments and recruited new readers on behalf of publishers. Diamond markers show agent locations by paper; background circles show subscriber concentrations for geographic context. Use the toggles to isolate individual papers.</p>
  <div class="map-controls">
    <div class="pill" id="apill-Occident" style="border-color:#4e79a7;color:#4e79a7" onclick="toggleAgent('Occident')"><div class="dot" style="background:#4e79a7"></div>Occident</div>
    <div class="pill" id="apill-Israelite" style="border-color:#e15759;color:#e15759" onclick="toggleAgent('Israelite')"><div class="dot" style="background:#e15759"></div>Israelite</div>
    <div class="pill" id="apill-Messenger" style="border-color:#59a14f;color:#59a14f" onclick="toggleAgent('Messenger')"><div class="dot" style="background:#59a14f"></div>Messenger</div>
    <div class="pill" id="apill-Gleaner" style="border-color:#f28e2b;color:#f28e2b" onclick="toggleAgent('Gleaner')"><div class="dot" style="background:#f28e2b"></div>Weekly Gleaner</div>
    <span class="map-note">Diamond = agent &middot; Click for details &middot; Background circles = subscriber counts</span>
  </div>
  <div id="agent-map" style="height:520px;border-radius:6px;border:1px solid #c9b99a;margin-bottom:18px"></div>
</div>
<div id="panel-agents" class="panel">
  <p class="snote">The Weekly Gleaner launched with a blitz of 36 agents in 1857 then rapidly disappeared; The Israelite built steadily to a peak of 59 agents in 1861; The Messenger grew sharply to 38 in 1859. Agent tenure data is available for agents with start and end years recorded.</p>
  <div class="g2">
    <div class="box wide">
      <h3>Active agents per year by newspaper</h3>
      <p>Count of agents with recorded appointments that year.</p>
      <canvas id="c-agtline" style="max-height:260px"></canvas>
    </div>
    <div class="box wide">
      <h3>Top cities with agents from multiple papers</h3>
      <p>Cities where two or more papers placed agents &mdash; showing competitive agent deployment.</p>
      <canvas id="c-agmulti" style="max-height:310px"></canvas>
    </div>
    <div class="box">
      <h3>Agent tenure distribution</h3>
      <p>How many years each agent served (agents with both start and end dates).</p>
      <canvas id="c-agtenure" style="max-height:280px"></canvas>
    </div>
    <div class="box">
      <h3>Subscriber coverage by agent city</h3>
      <p>Percentage of each paper's subscriptions that came from cities where that paper had a named agent.</p>
      <canvas id="c-agcov" style="max-height:280px"></canvas>
    </div>
  </div>
  <div class="g2" style="margin-top:18px">
    <div class="box wide">
      <h3>Paper-competition network: shared agent cities</h3>
      <p>Each paper is a node; edges connect papers that deployed agents in the same city. Edge thickness and label = number of cities where both papers had agents. Click an edge to see the shared cities.</p>
      <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap">
        <svg id="svg-paper-net" viewBox="0 0 480 340" style="width:min(480px,100%);flex-shrink:0"></svg>
        <div id="paper-net-detail" style="font-size:.78rem;color:#4a3a22;flex:1;min-width:160px;padding-top:10px"></div>
      </div>
    </div>
    <div class="box wide">
      <h3>Agent recruitment network: top agents &amp; their subscriber cities</h3>
      <p>Left nodes = top agents by total subscribers recruited (sized by total); right nodes = cities they served (sized by subscribers). Line thickness = subscribers recruited in that city. Color = paper. Hover for details.</p>
      <div style="overflow-x:auto">
        <svg id="svg-agent-bip" style="width:100%;min-width:520px" viewBox="0 0 760 520"></svg>
      </div>
    </div>
  </div>
</div>
<script>
{js_data}
{js_logic}
</script>
</body>
</html>"""


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    # ── Parse arguments ──────────────────────────────────────────────
    # Usage:
    #   python build_visualization.py                          # defaults
    #   python build_visualization.py subscribers.csv         # custom subscriber CSV
    #   python build_visualization.py subscribers.csv out.html
    #   python build_visualization.py subscribers.csv out.html \
    #       "Israelite Agents.csv" "Occident Agents.csv" \
    #       "The Jewish Messenger Agents.csv" "The Weekly Gleaner Agents.csv"
    #
    # Agent CSVs are optional. If not specified, the script will look for the
    # DEFAULT_AGENT_CSVS filenames in the same directory as the subscriber CSV.
    args = sys.argv[1:]
    csv_path = args[0] if len(args) >= 1 else DEFAULT_CSV
    out_path = args[1] if len(args) >= 2 else DEFAULT_OUT

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}")
        print(f"Usage: python build_visualization.py [input.csv] [output.html] [agent csvs...]")
        sys.exit(1)

    # Determine agent CSV paths
    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    if len(args) >= 7:
        # Explicitly provided as args 3-6
        agent_files = {
            "Israelite": args[2],
            "Occident":  args[3],
            "Messenger": args[4],
            "Gleaner":   args[5],
        }
    else:
        # Auto-discover by looking in same directory as subscriber CSV
        agent_files = {}
        for paper, fname in DEFAULT_AGENT_CSVS.items():
            candidate = os.path.join(csv_dir, fname)
            agent_files[paper] = candidate if os.path.exists(candidate) else None

    print(f"Loading {csv_path}...")
    rows = load_csv(csv_path)
    print(f"  {len(rows):,} rows loaded")

    print("Building subscriber data...")
    timeline, all_years = build_timeline(rows)
    paper_totals = {p: sum(1 for r in rows if SHORT.get(r["Newspaper_Name"]) == p) for p in PAPERS}
    type_data = build_type_data(rows)
    type_totals = {p: sum(type_data[p].values()) for p in PAPERS}

    data = {
        "map":           build_map_data(rows),
        "timeline":      timeline,
        "all_years":     all_years,
        "flow":          build_flow(rows),
        "class_data":    build_class_data(rows),
        "region_data":   build_region_data(rows, all_years)[0],
        "region_names":  build_region_data(rows, all_years)[1],
        "weekly":        build_weekly(rows),
        "states":        build_state_data(rows),
        "types":         type_data,
        "clergy":        build_clergy_data(rows, all_years),
        "gleaner_exits": build_gleaner_exits(rows),
        "paper_totals":  paper_totals,
        "type_totals":   type_totals,
        "summary":       build_summary(rows),
    }
    map_data = data["map"]
    mono = build_monopoly_data(map_data)
    data["monopoly"] = mono

    # ── Build agent data ──────────────────────────────────────────────
    found_agents = {p: f for p, f in agent_files.items() if f and os.path.exists(f)}
    if found_agents:
        print(f"Building agent data from {len(found_agents)} agent CSV(s)...")
        for p, f in found_agents.items():
            print(f"  {p}: {f}")
        data["agents"] = build_agent_data(agent_files)
        print(f"  {len(data['agents']['agent_map'])} agent records loaded")
    else:
        print("No agent CSVs found — agent tabs will be empty.")
        print(f"  Place agent CSVs next to {csv_path} with names:")
        for paper, fname in DEFAULT_AGENT_CSVS.items():
            print(f"    {fname}  ({paper})")
        data["agents"] = {}

    # ── Build coverage, place-year, and network data ──────────────────
    print("Building archival coverage and year-filter data...")
    data["coverage"] = build_coverage_data(rows)
    data["place_year"] = build_place_year_data(rows, data["map"])
    net = build_agent_network_data(rows, agent_files)
    data["agent_net"] = net["agent_net"]
    data["paper_competition"] = net["paper_competition"]
    print(f"  Coverage years computed; place-year data for {len(data['place_year'])} places")

    print("Generating HTML...")
    html = build_html(data)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(out_path) // 1024
    print(f"Done! Written to {out_path} ({size_kb} KB)")
    print(f"  {data['summary']['total_rows']:,} rows | {len(data['map'])} places | {len(all_years)} years")


if __name__ == "__main__":
    main()
