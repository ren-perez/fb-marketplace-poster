# FB Marketplace Poster

Semi-automated assistant for posting dealership inventory to Facebook Marketplace. Handles all data prep and browser automation — you do the final review and click Post.

---

## Pipeline

```
inventory.csv
      │
      ▼
app/scrape_inventory.py        ← scrapes live dealership site → writes inventory.csv
      │
      ▼
app/prepare_marketplace_listings.py   ← cleans data, downloads photos → writes listings_ready.json
      │
      ▼
app/listing_copier.py          ← generates a click-to-copy HTML page from the queue
      │
      ▼
app/marketplace_poster.py      ← fills FB form, pauses for your review → you click Post
      │
      ▼
listings_ready.json        ← queue updated with posted/skipped/failed + timestamp
```

---

## Scripts

### `app/scrape_inventory.py`
Scrapes `premiernissanoffremont.com/searchused.aspx` using Selenium (headless Chrome). Paginates through all result pages and extracts one row per vehicle.

**Output:** `inventory.csv`

**Fields extracted:**
- `vin`, `stock_number`, `year`, `make`, `model`, `trim`, `title`
- `price` — raw string from the page (dirty, cleaned downstream)
- `mileage` — raw string from the page (dirty, cleaned downstream)
- `features` — exterior and interior color
- `detail_url` — link to the vehicle detail page
- `photos` — pipe-delimited photo URLs (one per vehicle from the carousel)
- `post` — empty by default; **you set this to `true`** for vehicles to post

---

### `app/prepare_marketplace_listings.py`
Reads `inventory.csv`, processes only rows where `post = true`, and builds the posting queue.

**Input:** `inventory.csv`
**Output:** `data/silver/listings_ready/listings_ready.json`
**Photos:** `data/bronze/photos/<vin>/1.jpg`, `2.jpg`, …

**What it does:**

1. **Filter** — skips rows where `post` is not `true`/`1`/`yes`, or where VIN, title, price, or photos are missing
2. **Clean price** — `"$15,981OUR PRICEClick To Call..."` → `15981`
3. **Clean mileage** — `"8,658 mi"` → `8658`
4. **Parse colors** — splits `"Exterior: Deep Blue Pearl, Interior: Black"` into separate fields
5. **Discover photos** — probes `HEAD /inventoryphotos/16243/<vin>/ip/1.jpg`, `2.jpg`, … up to 20, stops at first 404
6. **Download photos** — saves to `data/bronze/photos/<vin>/`, skips files already on disk
7. **Generate description** — builds a clean Marketplace-formatted description from the cleaned fields
8. **Write queue** — each entry has a `status` field; existing `posted`/`skipped` entries are preserved across re-runs

**Queue entry shape:**
```json
{
  "vin": "1N4AZ1BV4RC556421",
  "status": "ready",
  "title": "2024 Nissan Leaf S",
  "year": "2024", "make": "Nissan", "model": "Leaf", "trim": "S",
  "price": 15981,
  "mileage": 8658,
  "ext_color": "Deep Blue Pearl",
  "int_color": "Black",
  "description": "...",
  "detail_url": "https://...",
  "photo_urls": ["https://..."],
  "photo_paths": ["data/bronze/photos/1N4AZ1BV4RC556421/1.jpg"],
  "prepared_at": "2026-03-29T00:00:00Z"
}
```

**Listing statuses:**

| Status | Meaning |
|---|---|
| `ready` | Prepared, waiting to be posted |
| `in_progress` | Browser open right now |
| `posted` | You clicked Post, marked done |
| `skipped` | Deliberately skipped |
| `failed` | Error during automation or form fill |

---

### `app/listing_copier.py`
Generates a standalone HTML page from the queue so you can copy each field individually into Facebook Marketplace by hand.

**Input:** `data/silver/listings_ready/listings_ready.json`
**Output:** `data/silver/listings_copier.html`

**What it does:**

- Shows every listing as a card with clickable fields: **Year, Make, Model, Price, Miles, Description, Photos folder**
- Click any field → value is copied to clipboard → "Copied!" flash confirms it
- Description is generated in the standard format:
  ```
  Year Make Model Trim
  Price
  Miles

  Vehicle is available and ready for a test drive. Just let me know what is a good date and time for you to come in.

  Renato Perez
  Premier Nissan of Fremont
  5701 Cushing Parkway, Fremont, CA 94538
  ```
- Re-run anytime after preparing new listings to refresh the page

**Usage:**
```bash
python app/listing_copier.py          # generate HTML
python app/listing_copier.py --open   # generate and open in browser
```

---

### `app/marketplace_poster.py`
Opens the Facebook Marketplace vehicle creation form and fills it using the queue data. Stops before submitting for your review.

**Input:** `data/silver/listings_ready/listings_ready.json`
**Browser profile:** `chrome-profile/` (persistent — log in once, stays logged in)

**What it does:**

1. Picks the next `ready` listing from the queue (or `--vin XYZ` for a specific one)
2. Marks it `in_progress` before opening the browser (crash-safe)
3. Launches Chromium with the persistent profile
4. Navigates to `facebook.com/marketplace/create/vehicle`
5. Fills form fields with human-paced typing and randomized delays:
   - Photos (file upload)
   - Price, Year, Make, Model, Trim, Mileage, Description
6. Prints a summary of which fields filled successfully
7. **Pauses — you review the form in the browser, fix anything, then choose:**
   - `Enter` → mark `posted`
   - `s` → mark `skipped`
   - `f` → mark `failed` (with optional note)
8. Saves updated status to the queue
9. Offers to continue with the next listing

---

## Data layout

```
app/
  scrape_inventory.py
  prepare_marketplace_listings.py
  listing_copier.py
  marketplace_poster.py
data/
  bronze/
    photos/<vin>/          ← downloaded vehicle photos (1.jpg, 2.jpg, ...)
  silver/
    listings_ready/
      listings_ready.json  ← posting queue (source of truth)
    listings_copier.html   ← click-to-copy page (generated by listing_copier.py)
chrome-profile/            ← persistent Chromium login session
inventory.csv              ← live inventory (edit to set post=true)
```

---

## Setup

```bash
pip install selenium beautifulsoup4 requests playwright
playwright install chromium
```

Chrome/chromedriver required for `scrape_inventory.py`.

---

## Usage

```bash
# 1. Scrape latest inventory
python app/scrape_inventory.py

# 2. Open inventory.csv, set post=true on vehicles you want to queue

# 3. Download photos and build the posting queue
python app/prepare_marketplace_listings.py

# 4. Open the click-to-copy page to manually fill FB Marketplace fields
python app/listing_copier.py --open

# 5. (Optional) Use automation to fill the form instead
python app/marketplace_poster.py

# Target a specific VIN
python app/marketplace_poster.py --vin 1N4AZ1BV4RC556421
```

---

## What is automated vs manual

| Automated | Manual |
|---|---|
| Inventory scraping | Setting `post=true` in CSV |
| Price and mileage cleaning | Final Post click |
| Description generation | Fixing fields the automation missed |
| Photo discovery and download | Captcha / unexpected modals |
| Browser launch and navigation | Account health monitoring |
| Form filling | |
| Queue state tracking | |

---

## Important notes

- **One listing at a time.** The script processes one vehicle per run by design.
- **Human-paced automation.** Randomized delays between actions. Do not remove them.
- **No brute-force login.** The persistent profile keeps you logged in. If a login page appears, log in manually — the script will wait.
- **Meta's UI changes often.** If a field fails to fill, fix it manually before clicking Post. The script degrades gracefully rather than erroring out.
- **Daily cap.** Avoid posting large batches in one session. Marketplace can temporarily limit accounts that post too fast.
