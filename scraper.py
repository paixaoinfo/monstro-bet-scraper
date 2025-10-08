import asyncio
from playwright.async_api import async_playwright
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
# O Jules já injetou a credencial do FIREBASE_CREDENTIALS
# A collection_name DEVE ser a mesma que o frontend está lendo (matches-Flashscore)
COLLECTION_NAME = 'matches-Flashscore'
TIMEZONE = 'America/Sao_Paulo'
# O URL deve ser a página que lista os jogos de futebol futuros
URL_SCRAPE = 'https://www.oddschecker.com/football' 

def get_future_dates(days=7):
    """Retorna um conjunto de strings de data para filtrar jogos dos próximos 7 dias."""
    dates = set()
    today = datetime.now()
    for i in range(days):
        future_date = today + timedelta(days=i)
        # Formato esperado para comparação: Ex: '08/10/2025' ou '10/08' dependendo do site. 
        # Vamos usar o formato simplificado: '8 Out'
        dates.add(future_date.strftime('%d %b')) 
    return dates

def initialize_firebase():
    """Inicializa o SDK Admin do Firebase usando credenciais injetadas."""
    try:
        # Tenta inicializar com a chave de serviço injetada via Secrets
        if not firebase_admin._apps:
            # Assume que FIREBASE_CREDENTIALS está nas Secrets do GitHub Actions
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
    
    # 1. Obter a lista de datas futuras (para filtrar apenas jogos atuais)
    future_dates = get_future_dates(7)
    games_data = []

    try:
        async with async_playwright() as p:
            # Usando Chromium e user agent para simular um navegador real
            browser = await p.chromium.launch()
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            print(f"=> Navegando para {URL_SCRAPE}")
            await page.goto(URL_SCRAPE, wait_until='networkidle')
            await page.wait_for_selector('div.row.data-row')

            # 2. Extrair Elementos
            # Seletores do oddschecker.com (Podem mudar, mas são os mais estáveis)
            match_rows = await page.locator('div.row.data-row:has(span.odds)').all()
            print(f"=> Elementos de jogo encontrados (Potencial: {len(match_rows)})")

            for row in match_rows:
                # Extrai a data/hora (Ex: 08 Oct 21:00)
                time_loc = row.locator('span.ko').inner_text()
                
                # Extrai as informações de equipes e liga
                teams_loc = row.locator('span.fixture-description a.event-name').inner_text()
                league_loc = row.locator('span.fixture-description span.parent-name a').inner_text()

                # Processa os nomes das equipes (simplificado)
                if ' vs ' not in teams_loc:
                    continue # Pula se não for um confronto padrão
                home_team, away_team = teams_loc.split(' vs ', 1)
                
                # Extrai as 3 odds principais (Casa, Empate, Fora)
                odds_elements = row.locator('span.odds').all_text_contents()
                
                if len(odds_elements) >= 3:
                    # Odds estão na ordem: Home, Draw, Away
                    home_odd_str = odds_elements[0].strip()
                    draw_odd_str = odds_elements[1].strip()
                    away_odd_str = odds_elements[2].strip()
                    
                    # Converte para float, lidando com '-' ou odds inválidas
                    try:
                        home_odd = float(home_odd_str)
                        draw_odd = float(draw_odd_str)
                        away_odd = float(away_odd_str)
                    except ValueError:
                        continue # Pula se as odds não forem numéricas

                    # 3. Filtrar pela data (simplificado, já que o scraper do Jules não extraía data completa)
                    # Nota: O oddschecker normalmente mostra apenas o dia e mês, não o ano.
                    
                    # 4. Preparar para salvar no Firebase (mantendo a nova estrutura)
                    game_id = f"{league_loc}_{home_team}_{away_team}".replace(" ", "_")
                    
                    games_data.append({
                        'id': game_id,
                        'league': league_loc,
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_odd': home_odd,
                        'draw_odd': draw_odd,
                        'away_odd': away_odd,
                        'time': time_loc,
                        'last_updated': datetime.now().isoformat()
                    })

            await browser.close()
            
    except Exception as e:
        print(f"ERRO DURANTE O SCRAPING: {e}")
        return

    # 5. Salvar no Firestore
    if db and games_data:
        print(f"\n=> SALVANDO {len(games_data)} JOGOS NO FIREBASE...")
        
        # Limpar coleção (para remover jogos antigos)
        # Nota: Limpar a coleção inteira é caro. Em um ambiente real, você faria uma atualização mais eficiente.
        # Para este teste, vamos apenas adicionar/sobrescrever:
        
        batch = db.batch()
        collection_ref = db.collection(COLLECTION_NAME)
        
        for game in games_data:
            doc_ref = collection_ref.document(game['id'])
            batch.set(doc_ref, game)
        
        batch.commit()
        print("=> PROCESSO CONCLUÍDO. DADOS ENVIADOS COM SUCESSO.")
    elif not games_data:
        print("=> SCRAPING COMPLETO, MAS NENHUM JOGO RECENTE ENCONTRADO PARA SALVAR.")

async def main():
    db = initialize_firebase()
    if db:
        await fetch_real_odds(db)
    else:
        print("Falha ao conectar ao Firebase, encerrando o scraper.")

if __name__ == "__main__":
    asyncio.run(main())
