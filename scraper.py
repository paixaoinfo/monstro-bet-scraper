import asyncio
from playwright.async_api import async_playwright
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

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
    """Clears a collection and uploads new data using a deterministic document ID."""
    if not db or not data:
        print("Database not initialized or no data to upload.")
        return

    print(f"\n=> SAVING {len(data)} MATCHES TO FIREBASE...")
    collection_ref = db.collection(collection_name)
    
    docs = collection_ref.stream()
    deleted_count = 0
    batch = db.batch()
    for doc in docs:
        batch.delete(doc.reference)
        deleted_count += 1
    if deleted_count > 0:
        batch.commit()
    print(f"Cleared {deleted_count} old documents from the '{collection_name}' collection.")

    uploaded_count = 0
    batch = db.batch()
    for record in data:
        # Create a unique ID based on the match details to prevent duplicates
        doc_id = f"{record['league']}_{record['home_team']}_{record['away_team']}_{record['date']}".replace(" ", "_").replace("/", "-")
        doc_ref = collection_ref.document(doc_id)
        batch.set(doc_ref, record)
        uploaded_count += 1
    batch.commit()
    print(f"Successfully uploaded {uploaded_count} new documents.")

def convert_fractional_to_decimal(fractional_odd):
    """Converts fractional odds string (e.g., '5/2') to decimal format."""
    if not fractional_odd or not isinstance(fractional_odd, str):
        return None
    try:
        if "/" in fractional_odd:
            numerator, denominator = map(int, fractional_odd.split('/'))
            return round(1 + (numerator / denominator), 2)
        elif fractional_odd.upper() == 'EVS':
            return 2.0
        else:
            # Handles cases like '1.5' which are already decimal
            return round(float(fractional_odd), 2)
    except (ValueError, ZeroDivisionError):
        return None

async def scrape_oddschecker():
    """Main function to scrape football odds by parsing the embedded JSON data."""
    all_scraped_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            print("Navigating to oddschecker football page...")
            await page.goto("https://www.oddschecker.com/football", wait_until="domcontentloaded", timeout=90000)
            print("Page loaded.")

            # Handle Geolocation Pop-up by clicking the UK flag
            try:
                uk_button_selector = 'div.showPopup_s19ljh2b a[title="United Kingdom"]'
                await page.wait_for_selector(uk_button_selector, timeout=15000)
                await page.click(uk_button_selector)
                print("Closed geolocation pop-up.")
                await page.wait_for_timeout(3000) # Wait for content to potentially reload
            except Exception:
                print("No geolocation pop-up found or it was already handled.")

            # Extract the JSON data from the script tag
            json_data_element = page.locator('script[data-hypernova-key="footballhomeaccumulator"]').first
            json_text = await json_data_element.text_content()
            
            json_text = json_text.strip().replace("<!--", "").replace("-->", "")
            data = json.loads(json_text)

            # Process the JSON data
            bets = data.get('bets', {}).get('entities', {})
            markets = data.get('markets', {}).get('entities', {})
            subevents = data.get('subevents', {}).get('entities', {})
            best_odds = data.get('bestOdds', {}).get('entities', {})
            events = data.get('events', {}).get('entities', {})

            odds_map = {bet_id: odd_info for bet_id, odd_info in best_odds.items()}

            market_to_bets = {}
            for bet_id, bet_info in bets.items():
                market_id = str(bet_info.get('marketId'))
                if market_id not in market_to_bets:
                    market_to_bets[market_id] = {}
                market_to_bets[market_id][bet_info.get('genericName')] = bet_id

            for subevent_id, subevent_info in subevents.items():
                market_id = None
                for m_id, m_info in markets.items():
                    if str(m_info.get('subeventId')) == subevent_id and m_info.get('marketTemplateId') == 1:
                        market_id = m_id
                        break
                
                if not market_id or market_id not in market_to_bets:
                    continue

                market_bets = market_to_bets.get(market_id, {})
                home_bet_id = market_bets.get('HOME')
                draw_bet_id = market_bets.get('DRAW')
                away_bet_id = market_bets.get('AWAY')

                home_odd_info = odds_map.get(str(home_bet_id))
                draw_odd_info = odds_map.get(str(draw_bet_id))
                away_odd_info = odds_map.get(str(away_bet_id))
                
                event_info = events.get(str(subevent_info.get('eventId')))
                league_name = event_info.get('cardName') if event_info else "Unknown League"

                if all([home_odd_info, draw_odd_info, away_odd_info, event_info]):
                    dt_object = datetime.strptime(subevent_info['startTime'], '%Y-%m-%dT%H:%M:%SZ')
                    all_scraped_data.append({
                        "date": dt_object.strftime('%Y-%m-%d'),
                        "time": dt_object.strftime('%H:%M'),
                        "league": league_name,
                        "home_team": subevent_info['homeTeamName'],
                        "away_team": subevent_info['awayTeamName'],
                        "home_odd": convert_fractional_to_decimal(home_odd_info['fractional']),
                        "draw_odd": convert_fractional_to_decimal(draw_odd_info['fractional']),
                        "away_odd": convert_fractional_to_decimal(away_odd_info['fractional'])
                    })

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            await page.screenshot(path='debug_error_page_final.png')
        finally:
            await browser.close()
            print("Browser closed.")

    if all_scraped_data:
        print(f"\n--- Scraped a total of {len(all_scraped_data)} matches ---")
        if all_scraped_data:
            print("Sample data:", all_scraped_data[:2])
        db = initialize_firebase()
        if db:
            upload_to_firestore(db, all_scraped_data, "matches-flashscore")
    else:
        print("\nNo data was scraped. Firebase will not be updated.")

if __name__ == "__main__":
    asyncio.run(scrape_oddschecker())
