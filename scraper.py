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

def save_matches_to_firebase(matches):
    """Saves a list of matches to Firebase and clears the old ones."""
    if not matches:
        print("No matches found to save.")
        return False
        
    matches_ref = db.collection('matches')
    clear_collection(matches_ref)
    
    for match_data in matches:
        db.collection('matches').add(match_data)
        print(f"Added to Firebase: {match_data.get('homeTeam')} vs {match_data.get('awayTeam')}")
    
    return True

def scrape_odds_agora(driver):
    """Scraper for oddsagora.com.br"""
    print("Attempting to scrape Odds Agora...")
    URL = "https://www.oddsagora.com.br/futebol"
    matches_found = []
    
    driver.get(URL)
    
    try:
        cookie_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler')))
        cookie_button.click()
        print("Odds Agora: Cookie button clicked.")
        time.sleep(5)
    except Exception:
        print("Odds Agora: Could not find or click cookie button.")

    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.odd-event')))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    event_cards = soup.select('div.odd-event')
    print(f"Odds Agora: Found {len(event_cards)} event cards.")

    for card in event_cards[:20]:
        try:
            league = card.select_one('div.odd-event__league span').text.strip()
            home_team = card.select_one('.odd-event__home-team span.team-name').text.strip()
            away_team = card.select_one('.odd-event__away-team span.team-name').text.strip()
            time_str = card.select_one('.odd-event__date span').text.strip()
            date_str = datetime.now().strftime("%Y-%m-%d")

            odds_elements = card.select('.odd-event__odds a')
            if len(odds_elements) < 3: continue

            odds_data = {
                "home": {"value": float(odds_elements[0].select_one('.odd-value').text.strip().replace(',', '.')), "house": odds_elements[0].select_one('.casa-de-aposta img')['alt'].strip()},
                "draw": {"value": float(odds_elements[1].select_one('.odd-value').text.strip().replace(',', '.')), "house": odds_elements[1].select_one('.casa-de-aposta img')['alt'].strip()},
                "away": {"value": float(odds_elements[2].select_one('.odd-value').text.strip().replace(',', '.')), "house": odds_elements[2].select_one('.casa-de-aposta img')['alt'].strip()}
            }

            matches_found.append({
                'homeTeam': home_team, 'awayTeam': away_team, 'league': league,
                'date': date_str, 'time': time_str, 'odds': odds_data,
                'potential': 'Médio', 'analysis': 'Análise automática com base nas odds recolhidas.'
            })
        except Exception:
            continue
            
    return matches_found

def scrape_oddspedia(driver):
    """Scraper for oddspedia.com"""
    print("Attempting to scrape Oddspedia...")
    URL = "https://oddspedia.com/br/futebol"
    matches_found = []
    
    driver.get(URL)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.event-holder')))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    event_cards = soup.select('.event-holder')
    print(f"Oddspedia: Found {len(event_cards)} event cards.")

    for card in event_cards[:20]:
        try:
            league = card.select_one('.league-info .league-name').text.strip()
            teams = card.select('.team-name')
            home_team = teams[0].text.strip()
            away_team = teams[1].text.strip()
            time_str = card.select_one('.game-time').text.strip()
            date_str = datetime.now().strftime("%Y-%m-%d")

            odds_elements = card.select('.odds-item a')
            if len(odds_elements) < 3: continue

            odds_data = {
                "home": {"value": float(odds_elements[0].text.strip()), "house": "Oddspedia"},
                "draw": {"value": float(odds_elements[1].text.strip()), "house": "Oddspedia"},
                "away": {"value": float(odds_elements[2].text.strip()), "house": "Oddspedia"}
            }

            matches_found.append({
                'homeTeam': home_team, 'awayTeam': away_team, 'league': league,
                'date': date_str, 'time': time_str, 'odds': odds_data,
                'potential': 'Médio', 'analysis': 'Análise automática com base nas odds recolhidas.'
            })
        except Exception:
            continue
            
    return matches_found
    
def scrape_checkdaposta(driver):
    """Scraper for checkdaposta.com"""
    print("Attempting to scrape Check Da Posta...")
    URL = "https://www.checkdaposta.com/"
    matches_found = []
    
    driver.get(URL)
    time.sleep(5) # This site needs a bit of time to load content
    
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.card-event')))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    event_cards = soup.select('div.card-event')
    print(f"Check Da Posta: Found {len(event_cards)} event cards.")

    for card in event_cards[:20]:
        try:
            league = card.select_one('.event-details-league-name').text.strip()
            teams = card.select('.event-teams-team-name')
            home_team = teams[0].text.strip()
            away_team = teams[1].text.strip()
            time_str = card.select_one('.event-time-clock').text.strip()
            date_str = datetime.now().strftime("%Y-%m-%d")

            odds_elements = card.select('.best-odd-odd')
            if len(odds_elements) < 3: continue

            odds_data = {
                "home": {"value": float(odds_elements[0].text.strip().replace(',', '.')), "house": "Checkdaposta"},
                "draw": {"value": float(odds_elements[1].text.strip().replace(',', '.')), "house": "Checkdaposta"},
                "away": {"value": float(odds_elements[2].text.strip().replace(',', '.')), "house": "Checkdaposta"}
            }

            matches_found.append({
                'homeTeam': home_team, 'awayTeam': away_team, 'league': league,
                'date': date_str, 'time': time_str, 'odds': odds_data,
                'potential': 'Médio', 'analysis': 'Análise automática com base nas odds recolhidas.'
            })
        except Exception:
            continue
            
    return matches_found

if __name__ == "__main__":
    driver = setup_driver()
    
    # List of scrapers to try in order
    scrapers = [
        scrape_odds_agora,
        scrape_oddspedia,
        scrape_checkdaposta
    ]
    
    all_matches = []
    processed_matches = set()

    for scraper_func in scrapers:
        try:
            matches_from_scraper = scraper_func(driver)
            if matches_from_scraper:
                for match in matches_from_scraper:
                    # Create a unique identifier to avoid duplicates
                    identifier = f"{match['homeTeam'].lower()}-{match['awayTeam'].lower()}"
                    if identifier not in processed_matches:
                        all_matches.append(match)
                        processed_matches.add(identifier)
                print(f"Collected {len(matches_from_scraper)} matches from {scraper_func.__name__}.")
        except Exception as e:
            print(f"Scraper {scraper_func.__name__} failed entirely: {e}")
            continue
            
    if all_matches:
        save_matches_to_firebase(all_matches)
        print(f"Total unique matches saved to Firebase: {len(all_matches)}")
    else:
        print("All scrapers failed or found no matches. No data was saved.")

    driver.quit()
    print("Driver closed.")

