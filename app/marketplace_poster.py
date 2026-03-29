"""
marketplace_poster.py

Loads one listing at a time from listings_ready.json, opens Facebook Marketplace
vehicle creation form, fills every field it can, uploads photos, then PAUSES for
your manual review before you click Post yourself.

Usage:
    python marketplace_poster.py            # process next ready listing
    python marketplace_poster.py --vin XYZ  # process a specific VIN

Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT / "data/silver/listings_ready/listings_ready.json"
PROFILE_DIR = ROOT / "chrome-profile"   # persistent login lives here

FB_VEHICLE_URL = "https://www.facebook.com/marketplace/create/vehicle"

# Human-pace delays (seconds)
DELAY_SHORT = (0.3, 0.7)
DELAY_MEDIUM = (0.8, 1.5)
DELAY_LONG = (1.5, 3.0)


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        print(f"✗ Queue file not found: {QUEUE_FILE}")
        print("  Run prepare_marketplace_listings.py first.")
        sys.exit(1)
    with open(QUEUE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list[dict]) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def find_listing(queue: list[dict], vin: str | None) -> tuple[int, dict] | None:
    if vin:
        for i, item in enumerate(queue):
            if item["vin"] == vin:
                return i, item
        print(f"✗ VIN {vin} not found in queue.")
        return None
    for i, item in enumerate(queue):
        if item.get("status") == "ready":
            return i, item
    return None


def update_status(queue: list[dict], idx: int, status: str, **kwargs) -> None:
    queue[idx]["status"] = status
    queue[idx]["updated_at"] = datetime.utcnow().isoformat() + "Z"
    for k, v in kwargs.items():
        queue[idx][k] = v
    save_queue(queue)


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def human_delay(range_: tuple[float, float]) -> None:
    time.sleep(random.uniform(*range_))


def human_type(page, selector: str, text: str, clear_first: bool = True) -> bool:
    """Type into a field with human-like pacing. Returns True if successful."""
    try:
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=5000)
        if clear_first:
            locator.triple_click()
            human_delay(DELAY_SHORT)
        locator.type(text, delay=random.randint(40, 100))
        human_delay(DELAY_SHORT)
        return True
    except Exception as e:
        print(f"    ⚠ could not type into {selector!r}: {e}")
        return False


def human_fill(page, selector: str, text: str) -> bool:
    """fill() is faster for plain inputs (no key events needed)."""
    try:
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=5000)
        locator.fill(str(text))
        human_delay(DELAY_SHORT)
        return True
    except Exception as e:
        print(f"    ⚠ could not fill {selector!r}: {e}")
        return False


def select_option_by_label(page, label_text: str, value: str) -> bool:
    """Click a labeled dropdown and pick the matching option."""
    try:
        # Try aria-label first
        combo = page.get_by_role("combobox", name=label_text)
        combo.wait_for(state="visible", timeout=5000)
        combo.select_option(label=value)
        human_delay(DELAY_SHORT)
        return True
    except Exception:
        pass
    try:
        # Fallback: click the element, then click the option text
        page.get_by_label(label_text).first.click()
        human_delay(DELAY_SHORT)
        page.get_by_role("option", name=value).first.click()
        human_delay(DELAY_SHORT)
        return True
    except Exception as e:
        print(f"    ⚠ could not select '{value}' in '{label_text}': {e}")
        return False


# ---------------------------------------------------------------------------
# Form filling
# ---------------------------------------------------------------------------

def upload_photos(page, photo_paths: list[str]) -> int:
    """Attach local photo files. Returns number uploaded."""
    existing = [p for p in photo_paths if Path(p).exists()]
    if not existing:
        print("    ⚠ no local photo files found")
        return 0

    try:
        # Facebook uses a hidden file input; set_input_files works reliably
        file_input = page.locator('input[type="file"][accept*="image"]').first
        file_input.wait_for(state="attached", timeout=8000)
        file_input.set_input_files(existing)
        human_delay(DELAY_LONG)
        print(f"    ✓ uploaded {len(existing)} photo(s)")
        return len(existing)
    except Exception as e:
        print(f"    ⚠ photo upload failed: {e}")
        return 0


def fill_vehicle_form(page, listing: dict) -> dict[str, bool]:
    """
    Fill the Marketplace vehicle form fields.
    Returns a dict of field → success for the review summary.
    """
    results = {}
    human_delay(DELAY_LONG)  # let the form settle

    # --- Photos ---
    print("  Uploading photos...")
    n = upload_photos(page, listing.get("photo_paths", []))
    results["photos"] = n > 0

    human_delay(DELAY_MEDIUM)

    # --- Price ---
    print("  Filling price...")
    price = listing.get("price")
    if price:
        results["price"] = (
            human_fill(page, 'input[aria-label="Price"]', str(price))
            or human_fill(page, 'input[placeholder*="rice"]', str(price))
        )
    else:
        results["price"] = False

    # --- Vehicle Year ---
    print("  Filling year...")
    year = listing.get("year", "")
    if year:
        results["year"] = (
            human_fill(page, 'input[aria-label="Year"]', str(year))
            or select_option_by_label(page, "Year", str(year))
        )
    else:
        results["year"] = False

    human_delay(DELAY_SHORT)

    # --- Make ---
    print("  Filling make...")
    make = listing.get("make", "")
    if make:
        results["make"] = (
            select_option_by_label(page, "Make", make)
            or human_fill(page, 'input[aria-label="Make"]', make)
        )
        human_delay(DELAY_MEDIUM)  # model dropdown may reload
    else:
        results["make"] = False

    # --- Model ---
    print("  Filling model...")
    model = listing.get("model", "")
    if model:
        results["model"] = (
            select_option_by_label(page, "Model", model)
            or human_fill(page, 'input[aria-label="Model"]', model)
        )
        human_delay(DELAY_MEDIUM)
    else:
        results["model"] = False

    # --- Trim ---
    print("  Filling trim...")
    trim = listing.get("trim", "")
    if trim:
        results["trim"] = (
            human_fill(page, 'input[aria-label="Trim"]', trim)
            or human_fill(page, 'input[aria-label="Trim level"]', trim)
        )
    else:
        results["trim"] = False

    # --- Mileage ---
    print("  Filling mileage...")
    mileage = listing.get("mileage")
    if mileage:
        results["mileage"] = (
            human_fill(page, 'input[aria-label="Mileage"]', str(mileage))
            or human_fill(page, 'input[placeholder*="ileage"]', str(mileage))
        )
    else:
        results["mileage"] = False

    # --- Description ---
    print("  Filling description...")
    description = listing.get("description", "")
    if description:
        results["description"] = (
            human_type(page, 'textarea[aria-label="Description"]', description)
            or human_type(page, 'div[aria-label="Description"]', description)
        )
    else:
        results["description"] = False

    return results


# ---------------------------------------------------------------------------
# Review prompt
# ---------------------------------------------------------------------------

def print_listing_summary(listing: dict, field_results: dict[str, bool]) -> None:
    print()
    print("=" * 60)
    print("LISTING READY FOR REVIEW")
    print("=" * 60)
    print(f"  VIN    : {listing['vin']}")
    print(f"  Title  : {listing['title']}")
    print(f"  Price  : ${listing.get('price', '?'):,}" if listing.get("price") else "  Price  : ?")
    print(f"  Miles  : {listing.get('mileage', '?'):,}" if listing.get("mileage") else "  Miles  : ?")
    print(f"  Photos : {len(listing.get('photo_paths', []))}")
    print()
    print("  Field fill results:")
    for field, ok in field_results.items():
        icon = "✓" if ok else "⚠"
        print(f"    {icon} {field}")
    print()
    print("  Review the form in the browser window.")
    print("  Fix anything that didn't fill correctly.")
    print("  When ready, choose:")
    print("    [Enter]  → mark as posted  (after you click Post)")
    print("    [s]      → skip this listing")
    print("    [f]      → mark as failed  (broken form / not posted)")
    print("=" * 60)


def prompt_result() -> str:
    while True:
        answer = input("  Your choice: ").strip().lower()
        if answer in ("", "s", "f"):
            return answer
        print("  Please press Enter, s, or f.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def launch_browser(headless: bool = False):
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = sync_playwright().start()
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR.resolve()),
        headless=headless,
        channel="chromium",   # use bundled Chromium; change to "chrome" for system Chrome
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
        no_viewport=True,
        slow_mo=100,
    )
    return p, context


def run(vin: str | None = None) -> None:
    queue = load_queue()
    result = find_listing(queue, vin)

    if result is None:
        if vin:
            print(f"VIN {vin} not found.")
        else:
            print("No listings with status 'ready' found in queue.")
            ready_count = sum(1 for x in queue if x.get("status") == "ready")
            print(f"Queue summary:")
            for status in ("ready", "posted", "skipped", "failed", "in_progress"):
                n = sum(1 for x in queue if x.get("status") == status)
                if n:
                    print(f"  {status:15} {n}")
        return

    idx, listing = result
    print()
    print(f"Next listing: {listing['title']}  ({listing['vin']})")
    print(f"  Price  : ${listing.get('price', '?'):,}" if listing.get("price") else f"  Price  : ?")
    print(f"  Photos : {len(listing.get('photo_paths', []))} local file(s)")
    print()

    go = input("Open browser and fill form? [Y/n] ").strip().lower()
    if go == "n":
        print("Aborted.")
        return

    update_status(queue, idx, "in_progress")

    print()
    print("Launching browser...")
    print("  Profile stored in:", PROFILE_DIR.resolve())
    print("  Log in to Facebook once — it will stay logged in for future runs.")
    print()

    p, context = launch_browser()
    page = context.new_page()

    try:
        print(f"Navigating to {FB_VEHICLE_URL} ...")
        page.goto(FB_VEHICLE_URL, wait_until="domcontentloaded", timeout=30000)
        human_delay(DELAY_LONG)

        # Quick check: are we logged in?
        if "login" in page.url.lower() or page.query_selector('[data-testid="royal_login_button"]'):
            print()
            print("⚠  Facebook login required.")
            print("   Please log in manually in the browser window, then press Enter here.")
            input("   [Enter to continue after login] ")
            page.goto(FB_VEHICLE_URL, wait_until="domcontentloaded", timeout=30000)
            human_delay(DELAY_LONG)

        print("Filling form...")
        field_results = fill_vehicle_form(page, listing)

        print_listing_summary(listing, field_results)
        choice = prompt_result()

        if choice == "":
            update_status(queue, idx, "posted", posted_at=datetime.utcnow().isoformat() + "Z")
            print(f"  ✓ Marked as posted.")
        elif choice == "s":
            update_status(queue, idx, "skipped")
            print(f"  → Marked as skipped.")
        elif choice == "f":
            note = input("  Optional failure note: ").strip()
            update_status(queue, idx, "failed", failure_note=note or None)
            print(f"  ✗ Marked as failed.")

    except KeyboardInterrupt:
        print("\n  Interrupted — marking as ready again.")
        update_status(queue, idx, "ready")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        update_status(queue, idx, "failed", failure_note=str(e))
        raise
    finally:
        input("\n  Press Enter to close the browser...")
        context.close()
        p.stop()

    # Offer to continue with next
    print()
    remaining = sum(1 for x in queue if x.get("status") == "ready")
    if remaining:
        print(f"  {remaining} listing(s) still ready.")
        again = input("  Process next listing now? [y/N] ").strip().lower()
        if again == "y":
            run()
    else:
        print("  Queue is empty — all listings processed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post one Marketplace vehicle listing at a time.")
    parser.add_argument("--vin", help="Target a specific VIN instead of the next ready listing.")
    args = parser.parse_args()
    run(vin=args.vin)
