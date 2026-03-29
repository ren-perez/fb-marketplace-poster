import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_CSV = ROOT / "data/bronze/inventory.csv"
PHOTOS_DIR = ROOT / "data/bronze/photos"
OUTPUT_DIR = ROOT / "data/silver/listings_ready"
OUTPUT_FILE = OUTPUT_DIR / "listings_ready.json"

DEALERSHIP_NAME = "Premier Nissan of Fremont"
SALESPERSON_NAME = "Renato Perez"
SALESPERSON_PHONE = "(925) 356-1720"
DEALERSHIP_ADDRESS = "5701 Cushing Parkway, Fremont, CA 94538"
PHOTO_BASE = "https://www.premiernissanoffremont.com/inventoryphotos/16243"
MAX_PHOTOS = 20
DOWNLOAD_TIMEOUT = 10
REQUEST_DELAY = 0.3  # seconds between photo probe requests

TERMINAL_STATUSES = {"posted", "skipped"}


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------

def clean_price(raw: str) -> int | None:
    """Extract the first integer dollar amount from a messy price string."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw.split("OUR")[0].split("$")[-1].split(".")[0])
    if digits:
        return int(digits)
    # fallback: grab any sequence of 4+ digits
    match = re.search(r"\d[\d,]{2,}", raw)
    if match:
        return int(match.group().replace(",", ""))
    return None


def clean_mileage(raw: str) -> int | None:
    """Extract integer mileage from strings like '8,658 mi' or '160 mi'."""
    if not raw:
        return None
    match = re.search(r"[\d,]+", raw)
    if match:
        return int(match.group().replace(",", ""))
    return None


def parse_features(raw: str) -> tuple[str, str]:
    """Return (ext_color, int_color) parsed from the features string."""
    ext_color = ""
    int_color = ""
    if not raw:
        return ext_color, int_color
    for part in raw.split(","):
        part = part.strip()
        if part.startswith("Exterior:"):
            ext_color = part[len("Exterior:"):].strip()
        elif part.startswith("Interior:"):
            int_color = part[len("Interior:"):].strip()
    return ext_color, int_color


def build_description(price: int, mileage: int, ext_color: str) -> str:
    parts = []
    if price:
        parts.append(f"${price:,}")
    if mileage:
        parts.append(f"{mileage:,} mi")
    if ext_color:
        parts.append(ext_color)

    summary = " | ".join(parts)

    lines = [
        summary,
        "",
        f"Vehicle is ready to test drive at {DEALERSHIP_NAME}.",
        f"Reach out to me — {SALESPERSON_NAME} at {SALESPERSON_PHONE}.",
        f"{DEALERSHIP_ADDRESS}",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Photo downloading
# ---------------------------------------------------------------------------

def probe_photo_urls(vin: str) -> list[str]:
    """
    Probe sequential photo URLs for a VIN and return those that exist.
    Pattern: /inventoryphotos/16243/<vin>/ip/<n>.jpg
    """
    found = []
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    for n in range(1, MAX_PHOTOS + 1):
        url = f"{PHOTO_BASE}/{vin.lower()}/ip/{n}.jpg"
        try:
            resp = session.head(url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                found.append(url)
                time.sleep(REQUEST_DELAY)
            elif resp.status_code == 404:
                break  # photos are sequential; stop at first gap
            else:
                break
        except requests.RequestException:
            break

    return found


def download_photos(vin: str, urls: list[str]) -> list[str]:
    """Download photos to data/bronze/photos/<vin>/ and return local paths."""
    dest_dir = PHOTOS_DIR / vin
    dest_dir.mkdir(parents=True, exist_ok=True)

    local_paths = []
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    for i, url in enumerate(urls, start=1):
        dest = dest_dir / f"{i}.jpg"
        if dest.exists():
            local_paths.append(str(dest))
            continue
        try:
            resp = session.get(url, timeout=DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                local_paths.append(str(dest))
                print(f"    ↓ photo {i}: {dest}")
                time.sleep(REQUEST_DELAY)
            else:
                print(f"    ✗ photo {i}: HTTP {resp.status_code}")
        except requests.RequestException as e:
            print(f"    ✗ photo {i}: {e}")

    return local_paths


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def load_existing_queue() -> dict[str, dict]:
    """Return existing queue keyed by VIN, or empty dict."""
    if not OUTPUT_FILE.exists():
        return {}
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {item["vin"]: item for item in data}


def save_queue(queue: dict[str, dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    items = sorted(queue.values(), key=lambda x: x.get("title", ""))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def is_flagged_for_posting(row: dict) -> bool:
    return str(row.get("post", "")).strip().lower() in ("true", "1", "yes")


def validate_row(row: dict) -> list[str]:
    errors = []
    if not row.get("vin"):
        errors.append("missing VIN")
    if not row.get("title"):
        errors.append("missing title")
    if not row.get("price"):
        errors.append("missing price")
    if not row.get("photos"):
        errors.append("no photos")
    return errors


def process_row(row: dict, existing: dict) -> dict | None:
    vin = row.get("vin", "").strip()
    if not vin:
        return None

    # Preserve terminal statuses (posted, skipped) across runs
    if vin in existing and existing[vin].get("status") in TERMINAL_STATUSES:
        print(f"  → {vin}: already {existing[vin]['status']}, skipping")
        return existing[vin]

    errors = validate_row(row)
    if errors:
        print(f"  ✗ {vin}: {', '.join(errors)}")
        return None

    price = clean_price(row["price"])
    mileage = clean_mileage(row["mileage"])
    ext_color, int_color = parse_features(row.get("features", ""))
    description = build_description(price, mileage, ext_color)

    print(f"  → {vin}: {row['title']}")

    # Discover all available photo URLs
    print(f"    Probing photos...")
    photo_urls = probe_photo_urls(vin)
    if not photo_urls:
        # Fall back to the single URL from CSV
        raw_photos = row.get("photos", "")
        photo_urls = [u.split("?")[0] for u in raw_photos.split("|") if u.strip()]
    print(f"    Found {len(photo_urls)} photo(s)")

    # Download
    photo_paths = download_photos(vin, photo_urls)
    if not photo_paths:
        print(f"    ✗ no photos downloaded, skipping")
        return None

    return {
        "vin": vin,
        "stock_number": row.get("stock_number", ""),
        "status": "ready",
        "title": row["title"],
        "year": row.get("year", ""),
        "make": row.get("make", ""),
        "model": row.get("model", ""),
        "trim": row.get("trim", ""),
        "price": price,
        "mileage": mileage,
        "ext_color": ext_color,
        "int_color": int_color,
        "description": description,
        "detail_url": row.get("detail_url", ""),
        "photo_urls": photo_urls,
        "photo_paths": photo_paths,
        "prepared_at": datetime.utcnow().isoformat() + "Z",
    }


def main():
    print("=" * 60)
    print("prepare_marketplace_listings.py")
    print("=" * 60)

    if not os.path.exists(INVENTORY_CSV):
        print(f"✗ {INVENTORY_CSV} not found. Run app/scrape_inventory.py first.")
        return

    existing_queue = load_existing_queue()
    print(f"Loaded {len(existing_queue)} existing queue entries\n")

    with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    flagged = [r for r in rows if is_flagged_for_posting(r)]
    print(f"Inventory rows: {len(rows)}")
    print(f"Flagged for posting (post=true/1): {len(flagged)}\n")

    if not flagged:
        print("No rows flagged. Set post=true in data/bronze/inventory.csv for the vehicles you want to post.")
        return

    new_queue = dict(existing_queue)
    processed = skipped = failed = 0

    for row in flagged:
        result = process_row(row, existing_queue)
        if result:
            new_queue[result["vin"]] = result
            if result["status"] in TERMINAL_STATUSES:
                skipped += 1
            else:
                processed += 1
        else:
            failed += 1

    save_queue(new_queue)

    print()
    print("=" * 60)
    print(f"Done.")
    print(f"  Prepared : {processed}")
    print(f"  Skipped  : {skipped}  (already posted/skipped)")
    print(f"  Failed   : {failed}  (validation or download errors)")
    print(f"  Output   : {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
