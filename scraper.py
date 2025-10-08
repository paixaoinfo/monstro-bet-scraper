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
        doc_id = f"{record['home_team']}-{record['away_team']}-{record['date']}".replace(" ", "_").replace("/", "-")
        doc_ref = collection_ref.document(doc_id)
        batch.set(doc_ref, record)
        uploaded_count += 1
    batch.commit()
    print(f"Successfully uploaded {uploaded_count} new documents.")

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

            # Tenta fechar o pop-up de geolocalização se ele aparecer
            try:
                popup_close_button = page.locator('button:has-text("Accept All")')
                await popup_close_button.click(timeout=10000)
                print("Accepted cookies.")
            except Exception:
                print("Cookie consent button not found or already handled.")

            # Expande todas as ligas para garantir que os jogos fiquem visíveis no HTML
            accordions = await page.locator('div[data-testid="accordion-header"]').all()
            print(f"Found {len(accordions)} league accordions. Expanding all...")
            for accordion in accordions:
                try:
                    await accordion.click()
                    await page.wait_for_timeout(200) # Pequena pausa para a animação
                except Exception:
                    continue # Ignora se o clique falhar por algum motivo

            print("Finished expanding accordions.")

            # Extrai os dados dos jogos visíveis
            match_rows = await page.locator('div[data-testid^="match-row-"]').all()
            print(f"Found {len(match_rows)} match rows to process.")

            for row in match_rows:
                try:
                    home_team = await row.locator('[data-testid="participant-1-name"]').inner_text()
                    away_team = await row.locator('[data-testid="participant-2-name"]').inner_text()
                    
                    date_time_str = await row.locator('[data-testid="status-or-time"]').inner_text()
                    # A data precisa ser construída a partir do contexto da página, assumimos hoje para simplificar
                    # Uma implementação mais robusta buscaria o cabeçalho da data
                    match_date = datetime.now().strftime('%Y-%m-%d')
                    match_time = date_time_str if ':' in date_time_str else 'N/A'

                    league_element = row.locator('xpath=./ancestor::div[contains(@data-testid, "competition-")]//h2')
                    league_name = await league_element.inner_text() if await league_element.count() > 0 else 'Unknown League'

                    odds_elements = await row.locator('[data-testid$="-best-odds"]').all()
                    
                    if len(odds_elements) == 3:
                        home_odd = await odds_elements[0].inner_text()
                        draw_odd = await odds_elements[1].inner_text()
                        away_odd = await odds_elements[2].inner_text()

                        # Nomes das casas de aposta estão geralmente num elemento filho
                        home_house = await odds_elements[0].locator('img').get_attribute('alt')
                        draw_house = await odds_elements[1].locator('img').get_attribute('alt')
                        away_house = await odds_elements[2].locator('img').get_attribute('alt')

                        all_scraped_data.append({
                            "date": match_date,
                            "time": match_time.strip(),
                            "league": league_name.strip(),
                            "home_team": home_team.strip(),
                            "away_team": away_team.strip(),
                            "home_odd": float(home_odd),
                            "draw_odd": float(draw_odd),
                            "away_odd": float(away_odd),
                            "home_house": home_house.strip(),
                            "draw_house": draw_house.strip(),
                            "away_house": away_house.strip(),
                        })
                except Exception as e:
                    # print(f"Could not process a match row: {e}")
                    continue

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

