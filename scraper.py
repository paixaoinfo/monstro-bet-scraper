import asyncio
from playwright.async_api import async_playwright
import json
import os
from fractions import Fraction
import firebase_admin
from firebase_admin import credentials, firestore

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
    """
    Initializes the Firebase Admin SDK using credentials from an environment variable.
    """
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

    print(f"Starting upload to '{collection_name}' collection...")
    collection_ref = db.collection(collection_name)

    # Clear the collection
    docs = collection_ref.stream()
    deleted_count = 0
    for doc in docs:
        doc.reference.delete()
        deleted_count += 1
    print(f"Cleared {deleted_count} documents from the collection.")

    # Upload new data
    uploaded_count = 0
    for record in data:
        collection_ref.add(record)
        uploaded_count += 1
    print(f"Successfully uploaded {uploaded_count} new documents.")


async def main():
    """
    Main function to scrape odds from oddschecker.com, save them to a file,
    and upload them to Firebase.
    Note: This scraper targets the main football page of oddschecker.com.
    A more advanced implementation would be required to navigate to and scrape
    all the specific leagues mentioned in the initial project requirements.
    """
    db = initialize_firebase()
    if not db:
        print("Halting execution due to Firebase initialization failure.")
        print("Please ensure the FIREBASE_CREDENTIALS environment variable is set correctly.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        scraped_data = []

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

            match_rows = await page.locator("div.RowWrapper_r6ns4d6").all()
            print(f"Found {len(match_rows)} match rows.")

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
                        scraped_data.append({
                            "home_team": home_team.strip(),
                            "away_team": away_team.strip(),
                            "home_odd": home_odd_dec,
                            "draw_odd": draw_odd_dec,
                            "away_odd": away_odd_dec,
                        })

            if scraped_data:
                file_path = "oddschecker.json" # Corrected filename
                with open(file_path, 'w') as f:
                    json.dump(scraped_data, f, indent=2)
                print(f"\nSuccessfully extracted and saved data for {len(scraped_data)} matches to {file_path}.")
                
                upload_to_firestore(db, scraped_data, "matches-flashscore")
            else:
                print("\nNo data was extracted, so no file was created and nothing was uploaded.")

        except Exception as e:
            print(f"An error occurred: {e}")
            # Screenshots are for debugging and should not be committed.
            # await page.screenshot(path="error_screenshot_oddschecker.png")
            # print("Screenshot saved to error_screenshot_oddschecker.png")

        finally:
            await browser.close()
            print("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())