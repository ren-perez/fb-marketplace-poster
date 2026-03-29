"""
listing_copier.py

Generates a standalone HTML page from listings_ready.json.
Each vehicle shows clickable fields — click to copy the value to clipboard.

Usage:
    python app/listing_copier.py
    python app/listing_copier.py --open   # also opens the page in your browser

Output:
    data/silver/listings_copier.html
"""

import argparse
import json
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT / "data/silver/listings_ready/listings_ready.json"
OUTPUT_HTML = ROOT / "data/silver/listings_copier.html"

SALESPERSON_NAME = "Renato Perez"
DEALERSHIP_NAME = "Premier Nissan of Fremont"
DEALERSHIP_ADDRESS = "5701 Cushing Parkway, Fremont, CA 94538"


def build_description(listing: dict) -> str:
    year = listing.get("year", "")
    make = listing.get("make", "")
    model = listing.get("model", "")
    trim = listing.get("trim", "")
    price = listing.get("price")
    mileage = listing.get("mileage")

    title_line = " ".join(p for p in [year, make, model, trim] if p)
    price_line = f"${price:,}" if price else ""
    miles_line = f"{mileage:,} miles" if mileage else ""

    parts = [title_line, price_line, miles_line, ""]
    parts += [
        "Vehicle is available and ready for a test drive. "
        "Just let me know what is a good date and time for you to come in.",
        "",
        SALESPERSON_NAME,
        DEALERSHIP_NAME,
        DEALERSHIP_ADDRESS,
    ]

    return "\n".join(p for p in parts if p is not None)


def esc(text: str) -> str:
    """HTML-escape for embedding in attributes/text."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def js_str(text: str) -> str:
    """Escape for embedding inside a JS template literal."""
    return str(text).replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def build_html(listings: list[dict]) -> str:
    cards_html = []

    for listing in listings:
        status = listing.get("status", "")
        year = listing.get("year", "")
        make = listing.get("make", "")
        model = listing.get("model", "")
        trim = listing.get("trim", "")
        price = listing.get("price")
        mileage = listing.get("mileage")
        vin = listing.get("vin", "")
        photo_paths = listing.get("photo_paths", [])
        description = build_description(listing)

        price_str = f"${price:,}" if price else "—"
        miles_str = f"{mileage:,}" if mileage else "—"
        title_str = " ".join(p for p in [year, make, model, trim] if p)

        photos_dir = str(Path(photo_paths[0]).parent) if photo_paths else "—"
        photo_count = len(photo_paths)

        status_badge = {
            "ready": '<span class="badge badge-ready">Ready</span>',
            "posted": '<span class="badge badge-posted">Posted</span>',
            "skipped": '<span class="badge badge-skipped">Skipped</span>',
            "failed": '<span class="badge badge-failed">Failed</span>',
            "in_progress": '<span class="badge badge-progress">In Progress</span>',
        }.get(status, f'<span class="badge">{esc(status)}</span>')

        def field_row(label: str, value: str, multiline: bool = False) -> str:
            safe_val = js_str(value)
            if multiline:
                return f"""
            <div class="field-row">
              <span class="field-label">{esc(label)}</span>
              <button class="copy-btn multiline" onclick="copyText(`{safe_val}`, this)" title="Click to copy">
                <pre class="field-value">{esc(value)}</pre>
                <span class="copied-toast">Copied!</span>
              </button>
            </div>"""
            else:
                return f"""
            <div class="field-row">
              <span class="field-label">{esc(label)}</span>
              <button class="copy-btn" onclick="copyText(`{safe_val}`, this)" title="Click to copy">
                <span class="field-value">{esc(value)}</span>
                <span class="copied-toast">Copied!</span>
              </button>
            </div>"""

        rows = "".join([
            field_row("Year", year),
            field_row("Make", make),
            field_row("Model", model),
            field_row("Price", price_str),
            field_row("Miles", miles_str),
            field_row("Description", description, multiline=True),
        ])

        cards_html.append(f"""
    <div class="card">
      <div class="card-header">
        <div class="card-title">{esc(title_str)}</div>
        <div class="card-meta">
          {status_badge}
          <span class="vin">VIN: {esc(vin)}</span>
          <span class="photos">{photo_count} photo(s)</span>
        </div>
      </div>
      <div class="fields">{rows}</div>
      <div class="photos-path">
        <span class="field-label">Photos folder</span>
        <button class="copy-btn" onclick="copyText(`{js_str(photos_dir)}`, this)" title="Click to copy path">
          <span class="field-value path">{esc(photos_dir)}</span>
          <span class="copied-toast">Copied!</span>
        </button>
      </div>
    </div>""")

    cards = "\n".join(cards_html) if cards_html else "<p class='empty'>No listings found.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FB Marketplace Listing Copier</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5;
    color: #1c1e21;
    padding: 24px 16px;
  }}

  h1 {{
    font-size: 1.4rem;
    font-weight: 700;
    margin-bottom: 20px;
    color: #1877f2;
  }}

  .card {{
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.12);
    margin-bottom: 20px;
    overflow: hidden;
  }}

  .card-header {{
    padding: 14px 18px;
    background: #f7f8fa;
    border-bottom: 1px solid #e4e6eb;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }}

  .card-title {{
    font-weight: 700;
    font-size: 1.05rem;
    flex: 1;
  }}

  .card-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }}

  .badge {{
    font-size: .72rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    background: #e4e6eb;
    color: #444;
  }}
  .badge-ready    {{ background: #d4edda; color: #155724; }}
  .badge-posted   {{ background: #cce5ff; color: #004085; }}
  .badge-skipped  {{ background: #fff3cd; color: #856404; }}
  .badge-failed   {{ background: #f8d7da; color: #721c24; }}
  .badge-progress {{ background: #e2d9f3; color: #432874; }}

  .vin, .photos {{
    font-size: .75rem;
    color: #65676b;
  }}

  .fields {{
    padding: 12px 18px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}

  .field-row, .photos-path {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }}

  .photos-path {{
    padding: 10px 18px 14px;
    border-top: 1px solid #f0f2f5;
  }}

  .field-label {{
    width: 76px;
    min-width: 76px;
    font-size: .78rem;
    font-weight: 600;
    color: #65676b;
    padding-top: 6px;
    text-transform: uppercase;
    letter-spacing: .03em;
  }}

  .copy-btn {{
    position: relative;
    background: #f0f2f5;
    border: 1.5px solid transparent;
    border-radius: 8px;
    padding: 5px 10px;
    cursor: pointer;
    text-align: left;
    flex: 1;
    transition: background .15s, border-color .15s;
    outline: none;
  }}

  .copy-btn:hover {{
    background: #e7f0fd;
    border-color: #1877f2;
  }}

  .copy-btn:active {{
    background: #d0e4ff;
  }}

  .copy-btn.multiline {{
    padding: 6px 10px;
  }}

  .field-value {{
    font-size: .9rem;
    color: #1c1e21;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: block;
  }}

  .copy-btn.multiline .field-value {{
    white-space: pre-wrap;
    font-family: inherit;
    font-size: .88rem;
    line-height: 1.5;
  }}

  .field-value.path {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: .8rem;
    color: #444;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 600px;
    display: block;
  }}

  .copied-toast {{
    position: absolute;
    top: 50%;
    right: 10px;
    transform: translateY(-50%);
    background: #1877f2;
    color: #fff;
    font-size: .72rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 6px;
    opacity: 0;
    pointer-events: none;
    transition: opacity .2s;
  }}

  .copy-btn.multiline .copied-toast {{
    top: 8px;
    transform: none;
  }}

  .copy-btn.flashed .copied-toast {{
    opacity: 1;
  }}

  .empty {{
    text-align: center;
    color: #65676b;
    padding: 40px;
  }}
</style>
</head>
<body>
<h1>FB Marketplace — Listing Copier</h1>
{cards}
<script>
function copyText(text, btn) {{
  navigator.clipboard.writeText(text).then(() => {{
    btn.classList.add('flashed');
    setTimeout(() => btn.classList.remove('flashed'), 1400);
  }}).catch(() => {{
    // fallback for older browsers
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.classList.add('flashed');
    setTimeout(() => btn.classList.remove('flashed'), 1400);
  }});
}}
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate listing copier HTML page.")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser after generating.")
    args = parser.parse_args()

    if not QUEUE_FILE.exists():
        print(f"✗ Queue file not found: {QUEUE_FILE}")
        print("  Run prepare_marketplace_listings.py first.")
        return

    with open(QUEUE_FILE, encoding="utf-8") as f:
        listings = json.load(f)

    # Show all statuses, most recent first
    listings = sorted(listings, key=lambda x: x.get("prepared_at", ""), reverse=True)

    html = build_html(listings)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")

    print(f"Generated: {OUTPUT_HTML}")
    print(f"  {len(listings)} listing(s) included")

    if args.open:
        webbrowser.open(OUTPUT_HTML.as_uri())
        print("  Opened in browser.")
    else:
        print(f"  Open in browser: {OUTPUT_HTML.as_uri()}")


if __name__ == "__main__":
    main()
