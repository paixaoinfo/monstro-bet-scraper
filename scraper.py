import asyncio
from playwright.async_api import async_playwright
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

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

    # Adiciona os novos documentos com ID único
    uploaded_count = 0
    batch = db.batch()
    for record in data:
        doc_id = f"{record['home_team']}-{record['away_team']}-{record['date']}".replace(" ", "_").replace("/", "-")
        doc_ref = collection_ref.document(doc_id)
        batch.set(doc_ref, record)
        uploaded_count += 1
    batch.commit()
    print(f"Successfully uploaded {uploaded_count} new documents.")

def parse_date_header(header_text):
    """Parses date headers like 'Today', 'Tomorrow', or 'Sunday, 13 Oct' into a YYYY-MM-DD string."""
    header_text = header_text.lower()
    today = datetime.now()
    if 'today' in header_text:
        return today.strftime('%Y-%m-%d')
    if 'tomorrow' in header_text:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        # Tenta extrair datas como "Sun 13 Oct"
        date_part = header_text.split(', ')[-1]
        # Adiciona o ano corrente para o parse
        parsed_date = datetime.strptime(f"{date_part} {today.year}", '%a %d %b %Y')
        return parsed_date.strftime('%Y-%m-%d')
    except ValueError:
        return today.strftime('%Y-%m-%d') # Fallback para o dia de hoje

async def scrape_oddschecker():
    """Main function to scrape football odds by interacting with the page."""
    all_scraped_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            print("Navigating to oddschecker football page...")
            await page.goto("https://www.oddschecker.com/football", wait_until="networkidle", timeout=90000)
            print("Page loaded.")
            
            # Espera pelo contentor principal dos jogos
            await page.wait_for_selector('div#oddsTableContainer', timeout=20000)
            print("Main odds container loaded.")

            # Itera pelos dias disponíveis (até 7 dias no futuro)
            for i in range(7):
                await page.wait_for_timeout(2000) # Pausa para garantir que o conteúdo do dia carregou
                
                date_header_el = await page.query_selector('h2.title')
                date_header = await date_header_el.inner_text() if date_header_el else 'Today'
                current_date_str = parse_date_header(date_header)
                print(f"\n--- Scraping day {i+1}: {date_header} ({current_date_str}) ---")

                # Extrai os dados dos jogos para o dia atual
                match_rows = await page.locator('div.relative.h-full.w-full').all()
                print(f"Found {len(match_rows)} match rows to process for this day.")

                for row in match_rows:
                    try:
                        home_team_el = await row.query_selector('p.text-black.truncate')
                        away_team_el = await row.query_selector('p.text-black.truncate >> nth=1')
                        
                        # Validação para garantir que estamos a olhar para uma linha de jogo real
                        if not all([home_team_el, away_team_el]):
                           continue

                        home_team = await home_team_el.inner_text()
                        away_team = await away_team_el.inner_text()
                        
                        time_el = await row.query_selector('div.text-xs.text-black')
                        match_time = await time_el.inner_text() if time_el else 'N/A'
                        
                        league_el = await row.query_selector('p.text-gray-dark.truncate')
                        league_name = await league_el.inner_text() if league_el else 'Unknown League'

                        odds_elements = await row.locator('div.odds-button-best-odds').all()
                        
                        if len(odds_elements) == 3:
                            home_odd = await odds_elements[0].inner_text()
                            draw_odd = await odds_elements[1].inner_text()
                            away_odd = await odds_elements[2].inner_text()

                            home_house = (await odds_elements[0].query_selector('img')).get_attribute('alt')
                            draw_house = (await odds_elements[1].query_selector('img')).get_attribute('alt')
                            away_house = (await odds_elements[2].query_selector('img')).get_attribute('alt')

                            all_scraped_data.append({
                                "date": current_date_str,
                                "time": match_time.strip(),
                                "league": league_name.strip(),
                                "home_team": home_team.strip(),
                                "away_team": away_team.strip(),
                                "home_odd": float(home_odd),
                                "draw_odd": float(draw_odd),
                                "away_odd": float(away_odd),
                                "home_house": await home_house,
                                "draw_house": await draw_house,
                                "away_house": await away_house,
                            })
                    except Exception:
                        continue
                
                # Clica no botão para ir para o próximo dia
                next_day_button = page.locator('button[aria-label="Next Day"]')
                if not await next_day_button.is_enabled():
                    print("Next day button is not enabled. Ending scrape.")
                    break
                await next_day_button.click()

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            await page.screenshot(path='debug_error_page.png')
        finally:
            await browser.close()
            print("Browser closed.")

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

