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
    
    # Limpa a coleção antiga
    docs = collection_ref.stream()
    deleted_count = 0
    batch = db.batch()
    for doc in docs:
        batch.delete(doc.reference)
        deleted_count += 1
    batch.commit()
    print(f"Cleared {deleted_count} old documents from the '{collection_name}' collection.")

    # Adiciona os novos documentos com ID único para evitar duplicados
    uploaded_count = 0
    batch = db.batch()
    for record in data:
        # Cria um ID único baseado nos times e na data
        doc_id = f"{record['home_team']}-{record['away_team']}-{record['date']}".replace(" ", "_")
        doc_ref = collection_ref.document(doc_id)
        batch.set(doc_ref, record)
        uploaded_count += 1
    batch.commit()
    print(f"Successfully uploaded {uploaded_count} new documents.")

def parse_match_data_from_json(json_data):
    """Parses the main page JSON (__NEXT_DATA__) to extract all available match data."""
    all_matches = []
    try:
        # Navega pela estrutura complexa do JSON para encontrar os dados dos eventos
        competitions = json_data.get('props', {}).get('pageProps', {}).get('competitions', [])
        
        for competition in competitions:
            league_name = competition.get('name', 'Unknown League')
            events = competition.get('events', [])
            
            for event in events:
                if not event.get('bestOdds') or len(event.get('participants', [])) != 2:
                    continue

                home_team = event['participants'][0]['name']
                away_team = event['participants'][1]['name']
                
                # Formata a data e a hora
                start_time = datetime.fromisoformat(event['startTime'].replace('Z', '+00:00'))
                match_date = start_time.strftime('%Y-%m-%d')
                match_time = start_time.strftime('%H:%M')

                # Extrai as melhores odds para Casa (1), Empate (X) e Visitante (2)
                best_odds = {bo['type']: bo for bo in event['bestOdds']}

                home_odd_data = best_odds.get('1')
                draw_odd_data = best_odds.get('X')
                away_odd_data = best_odds.get('2')

                if home_odd_data and draw_odd_data and away_odd_data:
                    all_matches.append({
                        "date": match_date,
                        "time": match_time,
                        "league": league_name.strip(),
                        "home_team": home_team.strip(),
                        "away_team": away_team.strip(),
                        "home_odd": float(home_odd_data['decimal']),
                        "draw_odd": float(draw_odd_data['decimal']),
                        "away_odd": float(away_odd_data['decimal']),
                        "home_house": home_odd_data.get('bookmaker', 'N/A'),
                        "draw_house": draw_odd_data.get('bookmaker', 'N/A'),
                        "away_house": away_odd_data.get('bookmaker', 'N/A'),
                    })
    except Exception as e:
        print(f"Error while parsing JSON data structure: {e}")
        
    return all_matches

async def scrape_oddschecker():
    """Main function to scrape football odds by parsing the embedded __NEXT_DATA__ JSON."""
    all_scraped_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            print("Navigating to oddschecker football page...")
            await page.goto("https://www.oddschecker.com/football", wait_until="networkidle", timeout=90000)
            print("Page loaded.")

            # Extrai o JSON principal da página
            json_data_element = await page.query_selector('script#__NEXT_DATA__')
            if not json_data_element:
                raise Exception("Could not find the __NEXT_DATA__ script tag.")
                
            json_text = await json_data_element.text_content()
            data = json.loads(json_text)
            
            print("Successfully located and parsed the __NEXT_DATA__ JSON.")
            all_scraped_data = parse_match_data_from_json(data)

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            await page.screenshot(path='debug_error_page.png') # Salva uma imagem para depuração
        finally:
            await browser.close()
            print("Browser closed.")

    # Após a extração, sobe os dados para o Firebase
    if all_scraped_data:
        print(f"\n--- Scraped a total of {len(all_scraped_data)} matches ---")
        if all_scraped_data:
             print("Sample data:", all_scraped_data[0])
        db = initialize_firebase()
        if db:
            upload_to_firestore(db, all_scraped_data, "matches-flashscore")
    else:
        print("\nNo data was scraped. Firebase will not be updated.")

if __name__ == "__main__":
    asyncio.run(scrape_oddschecker())

