"""Neighbourhood centroids from OpenStreetMap Nominatim.

Builds data/reference/neighbourhood_centroids.csv (name, lat, lon, source,
is_proxy), data/reference/pois.csv and data/reference/roads.csv (OSM road
geometry from the Overpass API, cached in overpass_cache.json)
for every neighbourhood the model knows, plus any extra names in the raw
data. Raw Nominatim responses are cached in
data/reference/nominatim_cache.json so each query is sent at most once.

Usage policy (https://operations.osmfoundation.org/policies/nominatim/):
max 1 request/s, an identifying User-Agent, results cached.
Data (c) OpenStreetMap contributors, ODbL 1.0.

Run: python -m data_pipeline.geocode
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

REF_DIR = Path("data/reference")
CACHE_PATH = REF_DIR / "nominatim_cache.json"
OUT_PATH = REF_DIR / "neighbourhood_centroids.csv"
LOOKUP_PATH = Path("ml/models/v20261107-appD/location_lookup.json")
RAW_PATH = Path("data/raw/nairobi_rentals_enriched_v4.csv")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "KodiWise/0.1 (Nairobi rent research; https://github.com/bmitigoa/kodiwise)"
MIN_INTERVAL_S = 1.1

# Nairobi County, generous bounding box (lat, lon).
NAIROBI_BBOX = (-1.45, -1.15, 36.64, 37.11)

# Place objects that represent an area (preferred over roads/POIs).
AREA_TYPES = {"suburb", "neighbourhood", "quarter", "residential", "village",
              "hamlet", "city_district", "borough", "locality", "town"}

# Names where a road or POI hit is likely to be wrong: accept area objects only.
STRICT_NAMES = {"Kahawa", "Kahawa West", "Kahawa Wendani", "Riverside",
                "Garden Estate", "Spring Valley", "Pipeline"}

# Extra query spellings tried after "<name>, Nairobi, Kenya".
ALT_QUERIES = {
    "Upperhill": ["Upper Hill, Nairobi, Kenya", "Upper Hill, Kenya", "Upperhill, Kenya"],
    "Pipeline": ["Pipeline, Embakasi, Nairobi, Kenya"],
    # In the data "Kahawa" is mostly Kahawa Sukari / Kahawa Maziwa listings.
    "Kahawa": ["Kahawa Sukari, Kenya", "Kahawa, Kenya"],
    # OSM places Kahawa Wendani just across the county line (Ruiru, Kiambu).
    "Kahawa Wendani": ["Kahawa Wendani, Kenya"],
    "Riverside": ["Riverside Drive, Nairobi, Kenya", "Riverside, Westlands, Nairobi, Kenya"],
}

NOT_PLACES = {"Unknown"}

# Names whose first area hit is a large administrative boundary whose centre
# is not where people live: pin the specific OSM suburb object instead.
PINNED = {
    "Langata": 6065491374,    # place/suburb along Langata Road (admin centre is in the National Park)
    "Westlands": 30121815,    # place/suburb at the Westlands roundabout (commercial core)
}

# Names with no suburb-level OSM object: an agreed proxy point built from
# specific OSM objects in the cached responses (query, osm ids, reason).
PROXIES = {
    "Kahawa": {
        "query": "Kahawa Sukari, Kenya",
        "osm_ids": [1948520302],
        "reason": ("listings are mostly Kahawa Sukari/Maziwa; no suburb object exists, "
                   "Kahawa Sukari junction on Thika Road used as proxy"),
    },
    "Riverside": {
        "query": "Riverside Drive, Nairobi, Kenya",
        "osm_ids": [552376627, 680549029, 553071363, 680541964],
        "reason": ("listings are Riverside Drive (Westlands); OSM has it only as roads "
                   "(the Riverside suburb object is a different estate in Viwandani); "
                   "mean of the Riverside Drive way centres used as proxy"),
    },
}


def known_names() -> list[str]:
    lookup = json.loads(LOOKUP_PATH.read_text())
    names = {k for k in lookup if k not in ("__global__",)}
    if RAW_PATH.exists():
        names |= set(pd.read_csv(RAW_PATH, usecols=["location_std"]).location_std.dropna())
    return sorted(names - NOT_PLACES)


class Nominatim:
    def __init__(self) -> None:
        self.cache: dict = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
        self._last = 0.0

    def search(self, query: str) -> list[dict]:
        if query in self.cache:
            return self.cache[query]
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        params = urllib.parse.urlencode({
            "q": query, "format": "jsonv2", "countrycodes": "ke",
            "limit": 10, "addressdetails": 1,
        })
        req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            results = json.load(resp)
        self._last = time.monotonic()
        self.cache[query] = results
        CACHE_PATH.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False), encoding="utf-8")
        return results


def in_nairobi(r: dict) -> bool:
    lat, lon = float(r["lat"]), float(r["lon"])
    lat_lo, lat_hi, lon_lo, lon_hi = NAIROBI_BBOX
    return lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi


def is_area(r: dict) -> bool:
    """An OSM object that represents an area/neighbourhood (not a road,
    building or POI): a place node, an administrative boundary, or a
    residential-landuse estate."""
    cat, typ = r.get("category"), r.get("type")
    return ((cat == "place" and typ in AREA_TYPES)
            or (cat == "boundary" and typ == "administrative")
            or (cat == "landuse" and typ == "residential"))


def pick(name: str, results: list[dict]) -> tuple[dict | None, str]:
    """Best result for a neighbourhood, plus a note. Area objects first;
    strict names never fall back to roads/POIs."""
    inside = [r for r in results if in_nairobi(r)]
    areas = [r for r in inside if is_area(r)]
    if areas:
        # Prefer an exact name match, then Nominatim's own ranking.
        exact = [r for r in areas if r.get("name", "").lower() == name.lower()]
        return (exact or areas)[0], "area object"
    if name in STRICT_NAMES:
        return None, "NO suburb-level object found"
    if inside:
        r = inside[0]
        return r, f"non-area fallback ({r.get('category')}/{r.get('type')}) - check"
    return None, "nothing inside Nairobi"


def proxy_row(nom: "Nominatim", name: str, today: str) -> dict:
    spec = PROXIES[name]
    hits = [r for r in nom.search(spec["query"]) if int(r["osm_id"]) in spec["osm_ids"]]
    if len(hits) != len(spec["osm_ids"]):
        raise RuntimeError(f"proxy objects for {name} not all found in Nominatim results")
    lat = sum(float(r["lat"]) for r in hits) / len(hits)
    lon = sum(float(r["lon"]) for r in hits) / len(hits)
    objs = ",".join(f"{r['osm_type']}/{r['osm_id']}" for r in hits)
    kinds = sorted({f"{r.get('category')}/{r.get('type')}" for r in hits})
    return {
        "name": name, "lat": round(lat, 6), "lon": round(lon, 6),
        "source": (f"proxy: OSM Nominatim {objs} ({'+'.join(kinds)}) q='{spec['query']}' {today}; "
                   f"{spec['reason']}"),
        "is_proxy": True,
        "osm_name": hits[0].get("display_name", ""),
        "note": "proxy",
    }


def geocode_all() -> pd.DataFrame:
    nom = Nominatim()
    rows = []
    today = date.today().isoformat()
    for name in known_names():
        if name in PROXIES:
            rows.append(proxy_row(nom, name, today))
            continue
        queries = [f"{name}, Nairobi, Kenya"] + ALT_QUERIES.get(name, [])
        if name in PINNED:
            hit = [r for r in nom.search(queries[0]) if int(r["osm_id"]) == PINNED[name]]
            if not hit:
                raise RuntimeError(f"pinned OSM object for {name} not found")
            r = hit[0]
            rows.append({
                "name": name, "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
                "source": (f"OSM Nominatim {r['osm_type']}/{r['osm_id']} ({r.get('category')}/{r.get('type')}) "
                           f"q='{queries[0]}' {today}"),
                "is_proxy": False, "osm_name": r.get("display_name", ""), "note": "pinned",
            })
            continue
        chosen, note, used = None, "no results", queries[0]
        for q in queries:
            r, n = pick(name, nom.search(q))
            if r is not None and (chosen is None or (is_area(r) and not is_area(chosen))):
                chosen, note, used = r, n, q
            if chosen is not None and is_area(chosen):
                break
            if chosen is None:
                note, used = n, q
        rows.append({
            "name": name,
            "lat": round(float(chosen["lat"]), 6) if chosen else None,
            "lon": round(float(chosen["lon"]), 6) if chosen else None,
            "source": (f"OSM Nominatim {chosen['osm_type']}/{chosen['osm_id']} "
                       f"({chosen.get('category')}/{chosen.get('type')}) q='{used}' {today}") if chosen else "",
            "is_proxy": False,
            "osm_name": chosen.get("display_name", "") if chosen else "",
            "note": note,
        })
    return pd.DataFrame(rows)




# ---------------------------------------------------------------------------
# Reference points and roads for the distance features (data/reference/).
# ---------------------------------------------------------------------------

POIS_PATH = REF_DIR / "pois.csv"
ROADS_PATH = REF_DIR / "roads.csv"
OVERPASS_CACHE = REF_DIR / "overpass_cache.json"

# name -> (Nominatim query, OSM id) ; Westlands/Upperhill reuse the approved
# neighbourhood points so "distance to Westlands" means the same place.
POI_OBJECTS = {
    "cbd": ("Nairobi General Post Office, Kenyatta Avenue, Nairobi, Kenya", 1537504486),
    "jkia": ("Jomo Kenyatta International Airport, Nairobi, Kenya", 11951583),
}
POI_FROM_CENTROIDS = {"westlands": "Westlands", "upperhill": "Upperhill"}

# Overpass cache key -> exact way name kept (drops slip roads etc.)
ROADS = {"thika_rd": ("thika", "Thika Road"), "mombasa_rd": ("mombasa", "Mombasa Road")}


def build_reference() -> None:
    nom = Nominatim()
    today = date.today().isoformat()
    rows = []
    for key, (query, osm_id) in POI_OBJECTS.items():
        hit = [r for r in nom.search(query) if int(r["osm_id"]) == osm_id]
        if not hit:
            raise RuntimeError(f"POI {key}: OSM object {osm_id} not in results for {query!r}")
        r = hit[0]
        rows.append({"poi": key, "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
                     "source": f"OSM Nominatim {r['osm_type']}/{r['osm_id']} ({r.get('category')}/{r.get('type')}) q='{query}' {today}"})
    cents = pd.read_csv(OUT_PATH).set_index("name")
    for key, name in POI_FROM_CENTROIDS.items():
        rows.append({"poi": key, "lat": cents.loc[name, "lat"], "lon": cents.loc[name, "lon"],
                     "source": f"neighbourhood centroid '{name}' ({cents.loc[name, 'source']})"})
    pd.DataFrame(rows).to_csv(POIS_PATH, index=False)

    cache = json.loads(OVERPASS_CACHE.read_text(encoding="utf-8"))
    road_rows = []
    for road, (cache_key, way_name) in ROADS.items():
        entry = cache[cache_key]
        for el in entry["result"]["elements"]:
            if el.get("tags", {}).get("name") != way_name:
                continue
            for i, g in enumerate(el.get("geometry", [])):
                road_rows.append({"road": road, "way_id": el["id"], "seq": i,
                                  "lat": round(g["lat"], 6), "lon": round(g["lon"], 6)})
    pd.DataFrame(road_rows).to_csv(ROADS_PATH, index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    print(pd.DataFrame(road_rows).groupby("road").agg(ways=("way_id", "nunique"), points=("seq", "size")))


def main() -> None:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    df = geocode_all()
    if df["lat"].isna().any():
        raise RuntimeError(f"unresolved neighbourhoods: {df.loc[df['lat'].isna(), 'name'].tolist()}")
    df[["name", "lat", "lon", "source", "is_proxy"]].to_csv(OUT_PATH, index=False)
    print(df.to_string(index=False))
    build_reference()


if __name__ == "__main__":
    main()
