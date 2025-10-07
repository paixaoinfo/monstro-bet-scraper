import os
import json
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

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

def scrape_odds():
    URL = "https://www.oddsagora.com.br/futebol"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    }
    
    try:
        page = requests.get(URL, headers=headers)
        page.raise_for_status() # Check for request errors
        soup = BeautifulSoup(page.content, 'html.parser')
        print("Successfully fetched the webpage.")

        # Clear existing matches in Firebase to avoid duplicates
        matches_ref = db.collection('matches')
        clear_collection(matches_ref)

        # The structure of the site seems to be a list of events.
        # This selector is more specific and based on recent analysis.
        event_cards = soup.select('div.odd-event')
        print(f"Found {len(event_cards)} event cards.")

        if not event_cards:
            print("No event cards found. The website structure might have changed.")
            return

        for card in event_cards[:20]: # Limit to 20 matches
            try:
                league = card.select_one('div.odd-event__league span').text.strip()
                home_team = card.select_one('.odd-event__home-team span.team-name').text.strip()
                away_team = card.select_one('.odd-event__away-team span.team-name').text.strip()
                
                time_str = card.select_one('.odd-event__date span').text.strip()
                
                # Assume today's date if only time is present
                date_str = datetime.now().strftime("%Y-%m-%d")

                # Find odds and houses
                odds_elements = card.select('.odd-event__odds a')
                if len(odds_elements) < 3:
                    continue

                odds_home_val = float(odds_elements[0].select_one('.odd-value').text.strip())
                odds_draw_val = float(odds_elements[1].select_one('.odd-value').text.strip())
                odds_away_val = float(odds_elements[2].select_one('.odd-value').text.strip())

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

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    scrape_odds()

