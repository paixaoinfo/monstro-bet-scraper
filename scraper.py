import asyncio
from playwright.async_api import async_playwright
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import firebase_admin
import json
import os
import re

# --- CONFIGURAÇÃO ---
COLLECTION_NAME = 'matches-Flashscore'
# URL da página de futebol futuro no oddschecker (geralmente a melhor para raspagem)
URL_SCRAPE = 'https://www.oddschecker.com/football' 

def initialize_firebase():
    """Inicializa o SDK Admin do Firebase usando credenciais injetadas."""
    try:
        if not firebase_admin._apps:
            cred_json = os.environ.get("FIREBASE_CREDENTIALS")
            if not cred_json:
                print("ERRO: FIREBASE_CREDENTIALS não encontrada.")
                return None
            
            cred = credentials.Certificate(json.loads(cred_json))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"ERRO DE INICIALIZAÇÃO DO FIREBASE: {e}")
        return None

def clean_odd_value(odd_str):
    """Limpa e converte string de odd (pode ser '-' ou 'EVS') para float."""
    odd_str = odd_str.strip()
    if not odd_str or odd_str in ('-', 'EVS'):
        return 0.0
    try:
        return float(odd_str)
    except ValueError:
        return 0.0

async def fetch_and_save_odds(db):
    """Executa o web scraping, extrai os dados e salva no Firestore."""
    
    games_data = []
    today = datetime.now().date()

    try:
        async with async_playwright() as p:
            # Lança o navegador Chromium
            browser = await p.chromium.launch()
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            print(f"=> Navegando para {URL_SCRAPE}")
            await page.goto(URL_SCRAPE, wait_until='networkidle', timeout=60000)
            
            # 1. Espera pelo elemento que contém todos os jogos.
            await page.wait_for_selector('div.data-row-container', timeout=30000)

            # 2. Extrai as linhas de jogos
            match_rows = await page.locator('div.data-row').all()
            print(f"=> Encontrados {len(match_rows)} elementos potenciais para processamento.")

            for row in match_rows:
                try:
                    # Extração da Liga e Times
                    league_element = await row.locator('span.fixture-description span.parent-name a').first.inner_text()
                    teams_element = await row.locator('span.fixture-description a.event-name').first.inner_text()
                    
                    # Extração da data/hora (Ex: '08 Oct', '21:00')
                    time_data = await row.locator('span.ko').inner_text()
                    date_data_str = await row.locator('div.ko-date').inner_text()

                    # Processamento Simples de Data para Filtragem
                    match_datetime = None
                    try:
                        # Tenta converter para um objeto datetime para saber se é futuro
                        date_with_year = f"{date_data_str} {today.year}"
                        match_datetime = datetime.strptime(date_with_year, '%d %b %Y').date()
                    except ValueError:
                        # Se falhar, tenta um formato mais longo
                        try:
                            date_with_year = f"{date_data_str} {today.year}"
                            match_datetime = datetime.strptime(date_with_year, '%a %d %b %Y').date()
                        except ValueError:
                             pass

                    # Filtro de Data: Ignora jogos que já passaram (Obrigatório)
                    if match_datetime and match_datetime < today:
                        continue 

                    # Processa os nomes das equipes (home vs away)
                    if ' vs ' not in teams_element:
                        continue 
                    home_team, away_team = teams_element.split(' vs ', 1)
                    
                    # Extração das Odds (os 3 primeiros valores de span.odds)
                    odds_elements = await row.locator('div.odds-container span.odds').all_text_contents()
                    
                    if len(odds_elements) >= 3:
                        home_odd = clean_odd_value(odds_elements[0])
                        draw_odd = clean_odd_value(odds_elements[1])
                        away_odd = clean_odd_value(odds_elements[2])
                        
                        # Verifica se as odds são válidas (maior que 1.0 para Home/Away)
                        if home_odd <= 1.0 or away_odd <= 1.0:
                            continue

                        # Geração de ID Único
                        game_id = re.sub(r'\W+', '', f"{league_element}_{home_team}_{away_team}_{date_data_str}").lower()
                        
                        games_data.append({
                            'id': game_id,
                            'league': league_element,
                            'home_team': home_team,
                            'away_team': away_team,
                            'home_odd': home_odd,
                            'draw_odd': draw_odd,
                            'away_odd': away_odd,
                            'time': time_data,
                            'date': match_datetime.isoformat() if match_datetime else None, # Formato ISO para o Frontend ler facilmente
                            'last_updated': datetime.now().isoformat()
                        })

                except Exception as e:
                    # Logs de erro de linha para debug (opcional, mas ajuda)
                    # print(f"Erro ao processar linha: {e}")
                    continue 

            await browser.close()
            
    except Exception as e:
        print(f"ERRO CRÍTICO NO SCRAPING: {e}")
        return

    # 3. Salvar no Firestore
    if db and games_data:
        print(f"\n=> SALVANDO {len(games_data)} JOGOS NO FIREBASE...")
        
        # Salvar novos dados
        batch = db.batch()
        collection_ref = db.collection(COLLECTION_NAME)
        
        # Salvar novos dados
        batch = db.batch()
        for game in games_data:
            doc_ref = collection_ref.document(game['id'])
            batch.set(doc_ref, game)
        
        batch.commit()
        print("=> PROCESSO CONCLUÍDO. DADOS ENVIADOS COM SUCESSO.")
    elif not games_data:
        print(f"=> SCRAPING COMPLETO. 0 JOGOS ENCONTRADOS PARA SALVAR.")

async def main():
    db = initialize_firebase()
    if db:
        await fetch_and_save_odds(db)
    else:
        print("Falha ao conectar ao Firebase, encerrando o scraper.")

if __name__ == "__main__":
    asyncio.run(main())
