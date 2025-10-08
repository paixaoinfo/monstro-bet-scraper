import asyncio
from playwright.async_api import async_playwright
import json
import os
import re
from fractions import Fraction
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import locale

def convert_fractional_to_decimal(fractional_odd):
    """Converts fractional odds string (e.g., '5/2') to decimal format."""
    try:
        if "/" in fractional_odd:
            numerator, denominator = map(int, fractional_odd.split('/'))
            return round(1 + (numerator / denominator), 2)
        else:
            if fractional_odd.upper() == 'EVS':
                return 2.0
            return float(fractional_odd)
    except (ValueError, ZeroDivisionError):
        return None

def initialize_firebase():
    """Initializes the Firebase Admin SDK using credentials from an environment variable."""
    try:
        cred_json_str = os.environ.get('FIREBASE_CREDENTIALS')
        if not cred_json_str:
            print("FIREBASE_CREDENTIALS environment variable not set.")
            return None
        cred_json = json.loads(cred_json_str)
        cred = credentials.Certificate(cred_json)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully.")
        return firestore.client()
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        return None

def upload_to_firestore(db, data, collection_name):
    """Clears a collection and uploads new data."""
    if not db or not data:
        print("Database not initialized or no data to upload.")
        return
    print(f"\nStarting upload to '{collection_name}' collection...")
    collection_ref = db.collection(collection_name)

    docs = collection_ref.stream()
    deleted_count = 0
    for doc in docs:
        doc.reference.delete()
        deleted_count += 1
    print(f"Cleared {deleted_count} documents from the collection.")

    uploaded_count = 0
    for record in data:
        collection_ref.add(record)
        uploaded_count += 1
    print(f"Successfully uploaded {uploaded_count} new documents.")

def parse_date_string(date_text):
    """Parses various date string formats from oddschecker, handling year changeover."""
    try:
        locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    except locale.Error:
        print("Warning: Could not set locale to en_US.UTF-8. Date parsing may fail.")

    current_date = datetime.now()
    if date_text.lower() == 'today':
        return current_date
    if date_text.lower() == 'tomorrow':
        return current_date + timedelta(days=1)

    cleaned_date_text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text).replace(',', '')

    try:
        parsed_date = datetime.strptime(f"{cleaned_date_text} {current_date.year}", '%A %d %B %Y')
    except ValueError:
        try:
            parsed_date = datetime.strptime(f"{cleaned_date_text} {current_date.year}", '%a %d %b %Y')
        except ValueError:
            print(f"CRITICAL: Could not parse date: {date_text}")
            return None

    if parsed_date.month < current_date.month:
        return parsed_date.replace(year=current_date.year + 1)
    else:
        return parsed_date

async def main():
    db = initialize_firebase()
    if not db:
        print("Halting execution due to Firebase initialization failure.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_scraped_data = []

        try:
            target_url = "https://www.oddschecker.com/football"
            print(f"Navigating to {target_url}")
            await page.goto(target_url, timeout=90000)
            print("Page loaded.")

            try:
                close_button_selector = "span.PopupCloseIcon_pb1x1zx"
                await page.wait_for_selector(close_button_selector, timeout=15000)
                await page.click(close_button_selector)
                print("Closed the region selection pop-up.")
                await page.wait_for_timeout(2000)
            except Exception:
                print("Region pop-up not found or already handled.")

            for i in range(7):
                await page.wait_for_timeout(2000)

                date_text_element = page.locator("p.DateWrapper_d7psjzv")
                await date_text_element.wait_for(state="visible", timeout=10000)
                date_text = await date_text_element.inner_text()

                scrape_date = parse_date_string(date_text)

                if not scrape_date:
                    print(f"Skipping day {i+1} due to unparsable date.")
                    continue

                formatted_date = scrape_date.strftime('%Y-%m-%d')
                print(f"\n--- Scraping day {i+1}/7: {date_text} ({formatted_date}) ---")

                league_containers = await page.locator("article.CardWrapper_c1m7xrb5").all()
                print(f"Found {len(league_containers)} league containers for this day.")

                for league_card in league_containers:
                    league_name = await league_card.locator(".AccordionText_a13j5kn0").inner_text()

                    match_rows = await league_card.locator("div.RowWrapper_r6ns4d6").all()

                    for row in match_rows:
                        team_name_elements = await row.locator("div.TeamWrapper_tedwdbv p").all()
                        odds_buttons = await row.locator("button.bestOddsButton_b3gzcta").all()

                        if len(team_name_elements) == 2 and len(odds_buttons) == 3:
                            home_team = await team_name_elements[0].inner_text()
                            away_team = await team_name_elements[1].inner_text()
                            home_odd_frac = await odds_buttons[0].inner_text()
                            draw_odd_frac = await odds_buttons[1].inner_text()
                            away_odd_frac = await odds_buttons[2].inner_text()

                            home_odd_dec = convert_fractional_to_decimal(home_odd_frac)
                            draw_odd_dec = convert_fractional_to_decimal(draw_odd_frac)
                            away_odd_dec = convert_fractional_to_decimal(away_odd_frac)

                            if all([home_team, away_team, home_odd_dec, draw_odd_dec, away_odd_dec]):
                                all_scraped_data.append({
                                    "date": formatted_date,
                                    "league": league_name.strip(),
                                    "home_team": home_team.strip(),
                                    "away_team": away_team.strip(),
                                    "home_odd": home_odd_dec,
                                    "draw_odd": draw_odd_dec,
                                    "away_odd": away_odd_dec,
                                })
                
                next_day_button = page.locator('button.ArrowButton_a1t2hqrk:has(.ArrowRight_aiogb61)')
                if await next_day_button.is_disabled():
                    print("Next day button is disabled. Ending scrape.")
                    break
                await next_day_button.click()

            # --- VERIFICATION AND UPLOAD ---
            if all_scraped_data:
                today = datetime.now().date()
                print(f"\n--- Filtering Data ---")
                print(f"Total matches scraped before filtering: {len(all_scraped_data)}")

                future_matches = [
                    match for match in all_scraped_data
                    if datetime.strptime(match['date'], '%Y-%m-%d').date() >= today
                ]

                print(f"Total matches after filtering for current/future dates: {len(future_matches)}")

                if not future_matches:
                    print("\nVerification Log: No future matches found after filtering. The database will not be updated.")
                else:
                    dates = [match['date'] for match in future_matches]
                    min_date = min(dates)
                    max_date = max(dates)

                    # Save to local file for verification
                    file_path = "oddschecker.json"
                    with open(file_path, 'w') as f:
                        json.dump(future_matches, f, indent=2)
                    print(f"Saved {len(future_matches)} matches to {file_path} for verification.")

                    print("\n--- Verification Log ---")
                    print(f"Total matches for upload: {len(future_matches)}")
                    print(f"Earliest match date: {min_date}")
                    print(f"Latest match date: {max_date}")
                    print("------------------------")
                    upload_to_firestore(db, future_matches, "matches-flashscore")
            else:
                print("\nNo data was extracted across the 7-day period.")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            await browser.close()
            print("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())