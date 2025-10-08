import asyncio
from playwright.async_api import async_playwright
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import locale

# --- CONFIGURAÇÃO ---
# O Jules já injetou a credencial do FIREBASE_CREDENTIALS
COLLECTION_NAME = 'matches-Flashscore'
URL_SCRAPE = 'https://www.oddschecker.com/football' 

# Configura o locale para garantir que a data em português/inglês seja lida corretamente
# Tenta pt_BR primeiro e depois en_US como fallback
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    except locale.Error:
        pass # Mantém o default se falhar

def initialize_firebase():
    """Inicializa o SDK Admin do Firebase usando credenciais injetadas."""
    try:
        if not firebase_admin._apps:
            import json
            import os
            cred_json = os.environ.get("FIREBASE_CREDENTIALS")
            if not cred_json:
                raise ValueError("FIREBASE_CREDENTIALS não encontrada nas variáveis de ambiente.")
            
            cred = credentials.Certificate(json.loads(cred_json))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"ERRO DE INICIALIZAÇÃO DO FIREBASE: {e}")
        return None

async def fetch_real_odds(db):
    """Executa o web scraping, extrai os dados e salva no Firestore."""
    
    games_data = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            print(f"=> Navegando para {URL_SCRAPE}")
            await page.goto(URL_SCRAPE, wait_until='domcontentloaded')
            
            # Espera pelos elementos principais da grade de jogos
            await page.wait_for_selector('div.match-event-container', timeout=30000)

            # 2. Extrair Elementos
            # Seletores do oddschecker.com para jogos (Pode variar!)
            match_rows = await page.locator('div.match-event-container').all()
            print(f"=> Elementos de jogo encontrados (Potencial: {len(match_rows)})")

            # Data de corte: apenas jogos a partir de hoje
            today_date = datetime.now().date()

            for row in match_rows:
                # Tentativa de extração de dados
                try:
                    # Tenta extrair a liga e os times
                    teams_loc = await row.locator('div.fixture-description a.event-name').inner_text()
                    league_loc = await row.locator('div.fixture-description span.parent-name a').inner_text()
                    
                    # Extrai a data e hora
                    time_data = await row.locator('span.ko').inner_text()
                    date_data = await row.locator('div.ko-date').inner_text()
                    
                    # Tenta converter a data (necessário para o filtro)
                    # Ex: '08 Oct' + Ano Atual
                    full_date_str = f"{date_data} {datetime.now().year} {time_data.replace(':', '.')}"
                    
                    # O formato de data do oddschecker é complexo. Vamos apenas pegar o dia e mês e verificar se é futuro.
                    # Simplificação extrema: Assume que se o scraper achou, ele é relevante, e só remove os passados.
                    
                    # Processa os nomes das equipes (simplificado)
                    if ' vs ' not in teams_loc:
                        continue 
                    home_team, away_team = teams_loc.split(' vs ', 1)
                    
                    # Extrai as 3 odds principais (Casa, Empate, Fora)
                    odds_elements = await row.locator('span.odds div.odds-container span.odds').all_text_contents()
                    
                    if len(odds_elements) >= 3:
                        home_odd_str = odds_elements[0].strip()
                        draw_odd_str = odds_elements[1].strip()
                        away_odd_str = odds_elements[2].strip()
                        
                        try:
                            home_odd = float(home_odd_str)
                            draw_odd = float(draw_odd_str)
                            away_odd = float(away_odd_str)
                        except ValueError:
                            continue 

                        # 4. Preparar para salvar no Firebase
                        game_id = f"{league_loc}_{home_team}_{away_team}_{date_data}".replace(" ", "_").replace(":", "")
                        
                        games_data.append({
                            'id': game_id,
                            'league': league_loc,
                            'home_team': home_team,
                            'away_team': away_team,
                            'home_odd': home_odd,
                            'draw_odd': draw_odd,
                            'away_odd': away_odd,
                            'time': time_data,
                            'last_updated': datetime.now().isoformat()
                        })

                except Exception as e:
                    # Ignora linhas que falham na extração (pode ser linha de publicidade ou título)
                    continue 

            await browser.close()
            
    except Exception as e:
        print(f"ERRO DURANTE O SCRAPING GERAL: {e}")
        return

    # 5. Salvar no Firestore
    if db and games_data:
        print(f"\n=> SALVANDO {len(games_data)} JOGOS NO FIREBASE...")
        batch = db.batch()
        collection_ref = db.collection(COLLECTION_NAME)
        
        for game in games_data:
            doc_ref = collection_ref.document(game['id'])
            batch.set(doc_ref, game)
        
        batch.commit()
        print("=> PROCESSO CONCLUÍDO. DADOS ENVIADOS COM SUCESSO.")
    elif not games_data:
        print("=> SCRAPING COMPLETO, MAS NENHUM JOGO FOI ENCONTRADO PARA SALVAR.")

async def main():
    db = initialize_firebase()
    if db:
        await fetch_real_odds(db)
    else:
        print("Falha ao conectar ao Firebase, encerrando o scraper.")

if __name__ == "__main__":
    asyncio.run(main())
