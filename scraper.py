import os
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Initialize Firebase
try:
    cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
    cred = credentials.Certificate(cred_json)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    exit()

def clear_collection(collection_ref, batch_size=50):
    """Deletes all documents in a collection in batches."""
    docs = collection_ref.limit(batch_size).stream()
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    if deleted >= batch_size:
        return clear_collection(collection_ref, batch_size)
    print("Matches collection cleared.")

def setup_driver():
    """Sets up the Selenium WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

def scrape_odds():
    URL = "https://www.oddsagora.com.br/futebol"
    driver = setup_driver()
    
    try:
        driver.get(URL)
        print("Successfully fetched the webpage with Selenium.")

        # Wait for the cookie button and click it
        try:
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler'))
            )
            cookie_button.click()
            print("Cookie button clicked.")
            time.sleep(5) # Wait for the page to reload/settle
        except Exception as e:
            print(f"Could not find or click cookie button: {e}")
            # Continue anyway, it might not be present

        # Wait for the main content to be present
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.odd-event'))
        )
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        matches_ref = db.collection('matches')
        clear_collection(matches_ref)

        event_cards = soup.select('div.odd-event')
        print(f"Found {len(event_cards)} event cards.")

        if not event_cards:
            print("No event cards found after waiting.")
            return

        for card in event_cards[:20]:
            try:
                league = card.select_one('div.odd-event__league span').text.strip()
                home_team = card.select_one('.odd-event__home-team span.team-name').text.strip()
                away_team = card.select_one('.odd-event__away-team span.team-name').text.strip()
                time_str = card.select_one('.odd-event__date span').text.strip()
                date_str = datetime.now().strftime("%Y-%m-%d")

                odds_elements = card.select('.odd-event__odds a')
                if len(odds_elements) < 3:
                    continue

                odds_home_val = float(odds_elements[0].select_one('.odd-value').text.strip().replace(',', '.'))
                odds_draw_val = float(odds_elements[1].select_one('.odd-value').text.strip().replace(',', '.'))
                odds_away_val = float(odds_elements[2].select_one('.odd-value').text.strip().replace(',', '.'))

                house_home = odds_elements[0].select_one('.casa-de-aposta img')['alt'].strip()
                house_draw = odds_elements[1].select_one('.casa-de-aposta img')['alt'].strip()
                house_away = odds_elements[2].select_one('.casa-de-aposta img')['alt'].strip()

                odds_data = {
                    "home": {"value": odds_home_val, "house": house_home},
                    "draw": {"value": odds_draw_val, "house": house_draw},
                    "away": {"value": odds_away_val, "house": house_away}
                }

                match_data = {
                    'homeTeam': home_team,
                    'awayTeam': away_team,
                    'league': league,
                    'date': date_str,
                    'time': time_str,
                    'odds': odds_data,
                    'potential': 'Médio',
                    'analysis': 'Análise automática com base nas odds recolhidas.'
                }
                
                db.collection('matches').add(match_data)
                print(f"Added to Firebase: {home_team} vs {away_team}")

            except Exception as e:
                print(f"Error processing a single match card: {e}")
                continue

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        driver.quit()
        print("Driver closed.")

if __name__ == "__main__":
    scrape_odds()

