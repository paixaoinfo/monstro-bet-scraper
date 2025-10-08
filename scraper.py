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
        elif fractional_odd.upper() == 'EVS':
            return 2.0
        else:
            return float(fractional_odd)
    except (ValueError, ZeroDivisionError):
        print(f"Could not convert odd: {fractional_odd}")
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

    print(f"\n=> SAVING {len(data)} MATCHES TO FIREBASE...")
    collection_ref = db.collection(collection_name)
    
    docs = collection_ref.stream()
    deleted_count = 0
    for doc in docs:
        doc.reference.delete()
        deleted_count += 1
    print(f"Cleared {deleted_count} old documents from the '{collection_name}' collection.")

    uploaded_count = 0
    for record in data:
        collection_ref.add(record)
        uploaded_count += 1
    print(f"Successfully uploaded {uploaded_count} new documents.")

async def scrape_oddschecker():
    """Main function to scrape football odds from oddschecker by parsing the embedded JSON data."""
    all_scraped_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            print("Navigating to oddschecker football page...")
            await page.goto("https://www.oddschecker.com/football", wait_until="domcontentloaded", timeout=90000)
            print("Page loaded.")

            try:
                uk_button_selector = 'div.showPopup_s19ljh2b a[title="United Kingdom"]'
                await page.wait_for_selector(uk_button_selector, timeout=10000)
                await page.click(uk_button_selector)
                print("Closed geolocation pop-up.")
                await page.wait_for_timeout(2000)
            except Exception:
                print("No geolocation pop-up found or it was handled.")

            # Extract the JSON data from the script tag
            json_data_element = page.locator('script[data-hypernova-key="footballhomeaccumulator"]').first
            json_text = await json_data_element.text_content()
            
            # Clean the text to get a valid JSON string
            json_text = json_text.strip().replace("<!--", "").replace("-->", "")
            data = json.loads(json_text)

            # Process the JSON data
            bets = data.get('bets', {}).get('entities', {})
            markets = data.get('markets', {}).get('entities', {})
            subevents = data.get('subevents', {}).get('entities', {})
            best_odds = data.get('bestOdds', {}).get('entities', {})

            # Create a mapping from betId to odds for faster lookup
            odds_map = {bet_id: odd_info for bet_id, odd_info in best_odds.items()}

            # Create a mapping from marketId to bets
            market_to_bets = {}
            for bet_id, bet_info in bets.items():
                market_id = str(bet_info.get('marketId'))
                if market_id not in market_to_bets:
                    market_to_bets[market_id] = {}
                market_to_bets[market_id][bet_info.get('genericName')] = bet_id

            # Reconstruct match data
            for subevent_id, subevent_info in subevents.items():
                # Find the corresponding market (Match Result, marketTemplateId: 1)
                market_id = None
                for m_id, m_info in markets.items():
                    if str(m_info.get('subeventId')) == subevent_id and m_info.get('marketTemplateId') == 1:
                        market_id = m_id
                        break
                
                if not market_id or market_id not in market_to_bets:
                    continue

                market_bets = market_to_bets[market_id]
                home_bet_id = market_bets.get('HOME')
                draw_bet_id = market_bets.get('DRAW')
                away_bet_id = market_bets.get('AWAY')

                home_odd_info = odds_map.get(home_bet_id)
                draw_odd_info = odds_map.get(draw_bet_id)
                away_odd_info = odds_map.get(away_bet_id)

                if home_odd_info and draw_odd_info and away_odd_info:
                    all_scraped_data.append({
                        "date": datetime.strptime(subevent_info['startTime'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d'),
                        "time": datetime.strptime(subevent_info['startTime'], '%Y-%m-%dT%H:%M:%SZ').strftime('%H:%M'),
                        "league": data['events']['entities'][str(subevent_info['eventId'])]['cardName'],
                        "home_team": subevent_info['homeTeamName'],
                        "away_team": subevent_info['awayTeamName'],
                        "home_odd": convert_fractional_to_decimal(home_odd_info['fractional']),
                        "draw_odd": convert_fractional_to_decimal(draw_odd_info['fractional']),
                        "away_odd": convert_fractional_to_decimal(away_odd_info['fractional'])
                    })

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            await page.screenshot(path='debug_error_page.png')
        finally:
            await browser.close()
            print("Browser closed.")

    # After scraping, upload to Firebase
    if all_scraped_data:
        print(f"\n--- Scraped a total of {len(all_scraped_data)} matches ---")
        print("Sample data:", all_scraped_data[:2])
        db = initialize_firebase()
        if db:
            upload_to_firestore(db, all_scraped_data, "matches-flashscore")
    else:
        print("\nNo data was scraped. Firebase will not be updated.")

if __name__ == "__main__":
    asyncio.run(scrape_oddschecker())
