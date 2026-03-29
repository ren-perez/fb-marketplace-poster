from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import csv
import time
import re

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BASE = "https://www.premiernissanoffremont.com"
URL = "https://www.premiernissanoffremont.com/searchused.aspx"


def setup_driver():
    """Setup Chrome driver with headless options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def wait_for_vehicles(driver, timeout=20):
    """Wait for vehicle cards to load"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CLASS_NAME, "vehicle-overview"))
        )
        # Extra wait for all content to load
        time.sleep(3)
        return True
    except Exception as e:
        print(f"Timeout waiting for vehicles: {e}")
        return False


def extract_vehicle_info(card_element):
    """Extract all relevant info from a vehicle card element"""
    try:
        # Get the parent vehicle card that contains both overview and images
        try:
            parent_card = card_element.find_element(
                By.XPATH, './ancestor::*[contains(@class, "vehicle-card")]'
            )
            parent_html = parent_card.get_attribute("outerHTML")
        except:
            # Fallback to just the card element if parent not found
            parent_html = card_element.get_attribute("outerHTML")

        soup = BeautifulSoup(parent_html, "html.parser")

        # Year, Make, Model, Trim from vehicle-title
        year = ""
        year_elem = soup.select_one(".vehicle-title__year")
        if year_elem:
            year = year_elem.get_text(strip=True)

        make_model = ""
        make_model_elem = soup.select_one(".vehicle-title__make-model")
        if make_model_elem:
            make_model = make_model_elem.get_text(strip=True)

        trim = ""
        trim_elem = soup.select_one(".vehicle-title__trim")
        if trim_elem:
            trim = trim_elem.get_text(strip=True)

        # Parse make and model from make_model string
        make = ""
        model = ""
        if make_model:
            parts = make_model.strip().split(None, 1)  # Split on first space
            if len(parts) >= 1:
                make = parts[0]
            if len(parts) >= 2:
                model = parts[1]

        # Build full title
        title = f"{year} {make_model} {trim}".strip()

        # VIN
        vin = ""
        vin_elem = soup.select_one(
            ".vehicle-identifiers__vin .vehicle-identifiers__value"
        )
        if vin_elem:
            vin = vin_elem.get_text(strip=True)

        # Stock number
        stock_number = ""
        stock_elem = soup.select_one(
            ".vehicle-identifiers__stock .vehicle-identifiers__value"
        )
        if stock_elem:
            stock_number = stock_elem.get_text(strip=True)

        # Mileage
        mileage = ""
        mileage_elem = soup.select_one(".vehicle-mileage")
        if mileage_elem:
            mileage = mileage_elem.get_text(strip=True)

        # Exterior color
        ext_color = ""
        ext_color_elem = soup.select_one(".vehicle-colors__ext .vehicle-colors__icon")
        if ext_color_elem:
            ext_color = ext_color_elem.get("aria-label", "")

        # Interior color
        int_color = ""
        int_color_elem = soup.select_one(".vehicle-colors__int .vehicle-colors__icon")
        if int_color_elem:
            int_color = int_color_elem.get("aria-label", "")

        # Detail URL
        detail_url = ""
        link_elem = soup.select_one(
            ".vehicle-title a, a.vehicle-dropdown__action--details, a.hero-carousel__item--viewvehicle"
        )
        if link_elem and link_elem.get("href"):
            detail_url = link_elem["href"]
            if detail_url and not detail_url.startswith("http"):
                detail_url = BASE + detail_url

        # Photos - Extract highest resolution from hero-carousel
        photo_urls = []

        # Look for hero-carousel images (these have the best quality)
        # Try multiple selectors
        carousel_imgs = soup.select(
            ".hero-carousel__image, .hero-carousel__background-image"
        )

        if carousel_imgs:
            for img in carousel_imgs[:1]:  # Just get the first one
                srcset = img.get("srcset", "")

                if srcset:
                    # Parse srcset to find highest resolution
                    sources = srcset.split(",")

                    # Extract URL and width, find the highest
                    max_width = 0
                    best_url = None

                    for source in sources:
                        parts = source.strip().split()
                        if len(parts) >= 2:
                            url = parts[0]
                            width_str = parts[1].rstrip("w")
                            try:
                                width = int(width_str)
                                if width > max_width:
                                    max_width = width
                                    best_url = url
                            except:
                                continue

                    if best_url:
                        # Add domain if not present
                        if not best_url.startswith("http"):
                            best_url = BASE + best_url
                        photo_urls.append(best_url)
                        print(
                            f"    → Found image: {best_url[:80]}... (width: {max_width}w)"
                        )

                # Fallback to src if no srcset
                if not photo_urls and img.get("src"):
                    img_url = img.get("src")
                    if not img_url.startswith("http"):
                        img_url = BASE + img_url
                    photo_urls.append(img_url)
                    print(f"    → Found image (from src): {img_url[:80]}...")

        # If still no photos, try looking for any inventory photo
        if not photo_urls:
            img_elems = soup.select(
                'img[src*="inventoryphotos"], img[src*="inventory"]'
            )
            for img in img_elems[:1]:
                img_url = img.get("src")
                if img_url:
                    if not img_url.startswith("http"):
                        img_url = BASE + img_url
                    photo_urls.append(img_url)
                    print(f"    → Found fallback image: {img_url[:80]}...")
                    break

        # Features/colors as features
        features = []
        if ext_color:
            features.append(f"Exterior: {ext_color}")
        if int_color:
            features.append(f"Interior: {int_color}")

        return {
            "vin": vin,
            "stock_number": stock_number,
            "year": year,
            "make": make,
            "model": model,
            "trim": trim,
            "title": title,
            "price": "",  # Will be filled in later from parent card
            "mileage": mileage,
            "features": ", ".join(features),
            "comments": "",
            "detail_url": detail_url,
            "photos": "|".join(photo_urls),
            "post": "",
        }

    except Exception as e:
        print(f"Error extracting vehicle info: {e}")
        import traceback

        traceback.print_exc()
        return None


def extract_price_from_parent(card_element):
    """Extract price from the parent vehicle card element"""
    try:
        # Get the parent vehicle-card__body or vehicle-card element
        parent = card_element.find_element(
            By.XPATH, './ancestor::*[contains(@class, "vehicle-card")]'
        )
        if parent:
            parent_html = parent.get_attribute("outerHTML")
            soup = BeautifulSoup(parent_html, "html.parser")

            # Look for price in various possible locations
            price_selectors = [
                ".vehicle-pricing__value",
                ".pricing-value",
                ".vehicle-price",
                '[class*="price-value"]',
                '[class*="pricing"]',
            ]

            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    if price_text and (
                        "$" in price_text or price_text.replace(",", "").isdigit()
                    ):
                        return price_text
    except:
        pass

    return ""


def click_next_page(driver):
    """Try to click the next page button"""
    try:
        # Look for the "Next" pagination link that is NOT disabled
        next_buttons = driver.find_elements(By.CSS_SELECTOR, ".pagination__item--next")

        for next_button in next_buttons:
            # Check if the parent li is not disabled
            if "disabled" not in next_button.get_attribute("class"):
                # Find the link inside and click it
                link = next_button.find_element(By.CSS_SELECTOR, "a")
                if link:
                    # Scroll into view
                    driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    time.sleep(0.5)

                    # Click using JavaScript to avoid any click interception
                    driver.execute_script("arguments[0].click();", link)
                    print("  → Clicked Next button, waiting for page to load...")

                    # Wait for the page to reload - wait for stale element
                    time.sleep(2)

                    # Wait for new vehicles to load
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CLASS_NAME, "vehicle-overview")
                            )
                        )
                        time.sleep(2)  # Extra wait for all content
                    except:
                        pass

                    return True
    except Exception as e:
        print(f"  → Could not find or click Next button: {e}")

    return False


def scrape_all():
    """Scrape all vehicles from all pages"""
    driver = setup_driver()
    all_vehicles = []
    seen_vins = set()  # Track VINs to avoid duplicates

    try:
        print("Opening website...")
        driver.get(URL)

        page = 1

        while True:
            print(f"\nScraping page {page}...")

            # Wait for vehicles to load
            if not wait_for_vehicles(driver):
                print("No vehicles found or timeout")
                break

            # Scroll down the page to trigger lazy loading of all vehicles
            print("  → Scrolling to load all vehicles...")
            last_height = driver.execute_script("return document.body.scrollHeight")

            # Scroll in increments to trigger lazy loading
            for i in range(5):  # Scroll 5 times
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)  # Wait for content to load

                # Check if we've reached the bottom
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Scroll back to top
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # Find all unique vehicle-overview elements (one per vehicle)
            vehicle_cards = driver.find_elements(By.CSS_SELECTOR, ".vehicle-overview")

            if not vehicle_cards:
                print("No vehicle cards found on page")
                break

            print(f"Found {len(vehicle_cards)} vehicle cards")

            # Extract info from each card
            vehicles_on_page = 0
            for i, card in enumerate(vehicle_cards):
                try:
                    vehicle_info = extract_vehicle_info(card)
                    if vehicle_info and vehicle_info["vin"]:
                        # Skip duplicates based on VIN
                        if vehicle_info["vin"] in seen_vins:
                            continue

                        # Try to get price from parent element
                        price = extract_price_from_parent(card)
                        if price:
                            vehicle_info["price"] = price

                        seen_vins.add(vehicle_info["vin"])
                        all_vehicles.append(vehicle_info)
                        vehicles_on_page += 1
                        print(
                            f"  ✓ Vehicle {vehicles_on_page}: {vehicle_info['title']} (VIN: {vehicle_info['vin']})"
                        )
                    elif vehicle_info and vehicle_info["title"]:
                        # If no VIN but has title, check if we should still add it
                        price = extract_price_from_parent(card)
                        if price:
                            vehicle_info["price"] = price

                        all_vehicles.append(vehicle_info)
                        vehicles_on_page += 1
                        print(
                            f"  ✓ Vehicle {vehicles_on_page}: {vehicle_info['title']} (No VIN)"
                        )
                except Exception as e:
                    print(f"  ✗ Error on card {i+1}: {e}")

            print(f"✓ Page {page}: Extracted {vehicles_on_page} unique vehicles")
            print(f"  Total so far: {len(all_vehicles)} vehicles")

            # Try to go to next page
            if not click_next_page(driver):
                print("No more pages or couldn't find next button")
                break

            page += 1

            # Safety limit
            if page > 50:
                print("Reached page limit (50)")
                break

    finally:
        driver.quit()

    return all_vehicles


def save_csv(vehicles, filename=None):
    """Save vehicles to CSV file"""
    if filename is None:
        filename = ROOT / "data/bronze/inventory.csv"
        filename.parent.mkdir(parents=True, exist_ok=True)
    if not vehicles:
        print("No vehicles to save!")
        return

    fieldnames = [
        "vin",
        "stock_number",
        "year",
        "make",
        "model",
        "trim",
        "title",
        "price",
        "mileage",
        "features",
        "comments",
        "detail_url",
        "photos",
        "post",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(vehicles)

    print(f"\n✓ Saved {len(vehicles)} vehicles to {filename}")


if __name__ == "__main__":
    print("Starting HTML inventory scrape...")
    print("=" * 50)
    print("\nNote: This scraper uses Selenium to render JavaScript.")
    print("Make sure you have Chrome and chromedriver installed.\n")

    vehicles = scrape_all()

    if vehicles:
        save_csv(vehicles)
        print("\n" + "=" * 50)
        print("Scraping complete!")
        print(f"Total vehicles: {len(vehicles)}")

        # Show sample
        if vehicles:
            print("\nSample (first vehicle):")
            print(f"  VIN: {vehicles[0]['vin']}")
            print(f"  Title: {vehicles[0]['title']}")
            print(f"  Price: {vehicles[0]['price']}")
            print(f"  Mileage: {vehicles[0]['mileage']}")
    else:
        print("\n⚠ No vehicles found. The website structure may have changed.")
