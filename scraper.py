import asyncio
import os
import json
from datetime import datetime, timedelta

# Instalar playwright e firebase-admin localmente se necessário
# pip install playwright firebase-admin
# playwright install chromium

from playwright.async_api import async_playwright
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.firestore import FieldFilter

# --- CONFIGURAÇÃO ---
# O scraper usará as credenciais do ambiente (GitHub Actions Secret)
try:
    # Tenta usar credenciais do ambiente
    FIREBASE_CREDENTIALS_JSON = os.environ.get('FIREBASE_CREDENTIALS')
    if not FIREBASE_CREDENTIALS_JSON:
        # Se não estiver no ambiente, tenta ler o arquivo local (apenas para debug)
        with open('firebase_credentials.json') as f:
            FIREBASE_CREDENTIALS_JSON = f.read()

    cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase: Inicializado com sucesso.")
except Exception as e:
    print(f"Erro ao inicializar Firebase: {e}")
    db = None

# A coleção onde os dados serão armazenados
COLLECTION_NAME = 'matches-flashscore'
# URL base para raspagem do Oddschecker (Futebol)
BASE_URL = 'https://www.oddschecker.com/futebol'

# --- FUNÇÕES AUXILIARES ---

def is_valid_odd(odd_value):
    """Verifica se a odd é válida (maior que 1.0)"""
    try:
        return float(odd_value) > 1.0
    except (ValueError, TypeError):
        return False

async def fetch_odds(browser, match_url):
    """
    Navega para a página de uma partida e extrai todas as odds disponíveis.
    Retorna: { 'home': [{'value': 2.0, 'house': 'Betano'}...], 'draw': [...], 'away': [...] }
    """
    page = await browser.new_page()
    try:
        await page.goto(match_url, wait_until="domcontentloaded", timeout=60000)
        print(f"    -> Raspando detalhes: {match_url}")

        odds_data = {
            'home': [],
            'draw': [],
            'away': []
        }
        
        # --- LÓGICA DE EXTRAÇÃO REAL (SUBSTITUIR A SIMULAÇÃO) ---
        # ATENÇÃO: A estrutura do site pode mudar. Este seletor é um exemplo e precisa ser validado.
        
        # Espera o contêiner principal das odds carregar
        await page.wait_for_selector('div[data-testid="market-odds-table"]', timeout=30000)
        
        # Pega todas as linhas da tabela de odds
        rows = await page.locator('div[data-testid="market-odds-table"] tr[data-testid^="row-"]').all()

        for row in rows:
            try:
                # Extrai o nome da casa de apostas (geralmente está no 'alt' de uma imagem ou em um texto)
                house_name_locator = row.locator('td:first-child a img')
                house_name = await house_name_locator.get_attribute('alt') if await house_name_locator.count() > 0 else 'Desconhecida'

                # Pega os valores das odds da linha
                odds_locators = row.locator('td[data-testid$="-cell"] button span')
                odds_values_raw = await odds_locators.all_text_contents()
                odds_values = [float(o) for o in odds_values_raw if is_valid_odd(o)]

                # Garante que temos as 3 odds (home, draw, away)
                if len(odds_values) == 3:
                    if is_valid_odd(odds_values[0]):
                        odds_data['home'].append({'value': odds_values[0], 'house': house_name.strip()})
                    if is_valid_odd(odds_values[1]):
                        odds_data['draw'].append({'value': odds_values[1], 'house': house_name.strip()})
                    if is_valid_odd(odds_values[2]):
                        odds_data['away'].append({'value': odds_values[2], 'house': house_name.strip()})
            except Exception as e:
                print(f"      - Erro ao processar uma linha da tabela de odds: {e}")
                continue # Pula para a próxima linha em caso de erro

        # Classifica por valor (Odd mais alta primeiro)
        for key in odds_data:
            odds_data[key].sort(key=lambda x: x['value'], reverse=True)
            
        return odds_data

    except Exception as e:
        print(f"Erro ao raspar detalhes da odd para {match_url}: {e}")
        return None
    finally:
        await page.close()


def select_unique_odds(odds_list):
    """
    Filtra as 3 melhores odds, garantindo que a casa de apostas não se repita.
    O critério de desempate é a odd mais alta.
    """
    unique_odds = []
    used_houses = set()

    for market in ['home', 'draw', 'away']:
        best_odd = None
        
        # Tenta encontrar a melhor odd que ainda não tenha sido usada
        for odd_item in odds_list.get(market, []):
            if odd_item['house'] not in used_houses:
                best_odd = odd_item
                break
        
        # Se encontrou, adiciona e marca a casa como usada
        if best_odd:
            unique_odds.append({
                'market': market, 
                'value': best_odd['value'], 
                'house': best_odd['house']
            })
            used_houses.add(best_odd['house'])
        
        # Se não encontrou uma casa única, pega a melhor disponível (sacrifica a regra para garantir 3 resultados)
        elif odds_list.get(market):
              # Pega a melhor odd, mesmo que a casa se repita (segurança)
              best_odd = odds_list[market][0]
              unique_odds.append({
                  'market': market,
                  'value': best_odd['value'],
                  'house': best_odd['house']
              })
              
    # Retorna os 3 resultados únicos (ou os 3 melhores disponíveis)
    return {item['market']: {'value': item['value'], 'house': item['house']} for item in unique_odds}


async def run_scraper():
    """Função principal para executar a raspagem de todos os jogos."""
    if not db:
        print("Erro: Firebase não inicializado.")
        return

    print("Iniciando raspagem de Multi-Odds...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            # Acessa a página principal de futebol
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            
            print("Buscando jogos futuros...")
            
            # --- LÓGICA DE EXTRAÇÃO DOS JOGOS (SUBSTITUIR A SIMULAÇÃO) ---
            # ATENÇÃO: Esta é a segunda parte que precisa ser real.
            # O código abaixo deve encontrar os links de todas as partidas na página.
            
            # Exemplo de seletor (precisa ser validado):
            match_links = await page.locator('a[data-testid="match-details-link"]').all()
            
            scraped_matches_info = []
            
            # Limita a 10 jogos para não sobrecarregar em testes
            for link in match_links[:10]:
                try:
                    href = await link.get_attribute('href')
                    full_url = f"https://www.oddschecker.com{href}"
                    
                    # Extrai informações da partida diretamente do link ou de elementos próximos
                    teams_text = await link.inner_text()
                    teams = teams_text.split('\n')
                    home_team, away_team = (teams[0], teams[1]) if len(teams) >= 2 else ('Desconhecido', 'Desconhecido')
                    
                    # A data, hora e liga podem precisar de seletores mais complexos
                    # Aqui usamos um valor padrão para demonstração
                    match_date = datetime.now().strftime("%Y-%m-%d")
                    match_time = '12:00'
                    league = 'Liga Exemplo' # Idealmente, extrair isso da página também

                    scraped_matches_info.append({
                        'homeTeam': home_team,
                        'awayTeam': away_team,
                        'league': league,
                        'date': match_date,
                        'time': match_time,
                        'url': full_url
                    })
                except Exception as e:
                    print(f"Erro ao processar um link de jogo: {e}")
                    continue

            all_scraped_data = []

            for match in scraped_matches_info:
                # Agora o `fetch_odds` usará a URL real
                full_odds_data = await fetch_odds(browser, match['url']) 
                
                if full_odds_data and full_odds_data['home'] and full_odds_data['draw'] and full_odds_data['away']:
                    # 1. Aplica a lógica de Odd Única
                    unique_odds = select_unique_odds(full_odds_data)
                    
                    # 2. Cria o documento a ser salvo
                    document_data = {
                        'home_team': match['homeTeam'],
                        'away_team': match['awayTeam'],
                        'league': match['league'],
                        'date': match['date'],
                        'time': match['time'],
                        'home_odd': unique_odds.get('home', {}).get('value'),
                        'draw_odd': unique_odds.get('draw', {}).get('value'),
                        'away_odd': unique_odds.get('away', {}).get('value'),
                        'home_house': unique_odds.get('home', {}).get('house'),
                        'draw_house': unique_odds.get('draw', {}).get('house'),
                        'away_house': unique_odds.get('away', {}).get('house'),
                        'all_odds_raw': full_odds_data 
                    }
                    all_scraped_data.append(document_data)
            
            if not all_scraped_data:
                print("Nenhum jogo com odds completas foi encontrado para salvar.")
                return

            print(f"=> SALVANDO {len(all_scraped_data)} JOGOS NO FIREBASE...")

            # --- SALVANDO NO FIRESTORE (Upsert) ---
            batch = db.batch()
            collection_ref = db.collection(COLLECTION_NAME)

            for data in all_scraped_data:
                # Cria um ID de documento único para evitar duplicação
                doc_id = f"{data['home_team']}-{data['away_team']}-{data['date']}".replace(" ", "_").replace(":", "_")
                doc_ref = collection_ref.document(doc_id)
                batch.set(doc_ref, data, merge=True) # merge=True atualiza o documento se ele já existir
                
            batch.commit()
            print("Processo de raspagem concluído e dados salvos no Firebase.")


        except Exception as e:
            print(f"Erro crítico durante a raspagem: {e}")
        finally:
            await browser.close()


if __name__ == '__main__':
    if not os.environ.get('FIREBASE_CREDENTIALS'):
        print("Aviso: Usando credenciais de simulação. Substitua pela credencial REAL no GitHub Secrets.")

    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        print("Processo interrompido pelo usuário.")
    except Exception as e:
        print(f"Erro fatal na execução: {e}")
