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

# A coleção onde os dados serão armazenados (já corrigida no frontend)
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
        await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
        print(f"   -> Raspando detalhes: {match_url}")

        # Seletor para encontrar as melhores odds por mercado de várias casas
        # Foca no mercado 1X2 (Resultado Final)
        odds_data = {
            'home': [],
            'draw': [],
            'away': []
        }
        
        # O seletor abaixo é um exemplo genérico que precisa de ser ajustado ao HTML atual do site.
        # Estamos a simular uma raspagem robusta de múltiplas colunas/linhas
        odds_table = await page.locator('div[data-testid="market-odds-table"]').nth(0).all_text_contents()
        
        # Simulação de Extração (Como não podemos raspar em tempo real, usamos um mock para a estrutura)
        # O Jules implementaria aqui o código Playwright/BeautifulSoup para extrair as 3 colunas e N linhas.
        
        # Dados simulados para demonstrar a estrutura Multi-Odds
        odds_simuladas = {
            'Betano': [2.12, 4.00, 3.10],
            'Stake': [2.05, 3.80, 3.15],
            'Bet365': [2.10, 3.90, 3.00]
        }
        
        for house_name, values in odds_simuladas.items():
            if is_valid_odd(values[0]):
                odds_data['home'].append({'value': values[0], 'house': house_name})
            if is_valid_odd(values[1]):
                odds_data['draw'].append({'value': values[1], 'house': house_name})
            if is_valid_odd(values[2]):
                odds_data['away'].append({'value': values[2], 'house': house_name})
                
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
        for odd_item in odds_list[market]:
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
        elif odds_list[market]:
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
            # Acessa o Oddschecker para Futebol (exige raspagem de seletores complexos)
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            
            # SIMULAÇÃO: Encontrando links de partidas futuras (O Jules faria isso com seletores)
            print("Buscando jogos futuros...")
            
            # Filtro de data: apenas jogos de hoje (08/10) até 7 dias no futuro
            today_str = datetime.now().strftime("%Y-%m-%d")
            seven_days_later_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

            # MOCK de dados brutos que seriam raspados do Oddschecker
            # O URL abaixo seria o link para a página de detalhe da Odd
            mock_matches = [
                {'homeTeam': 'Orlando City SC', 'awayTeam': 'Vancouver Whitecaps FC', 'league': 'USA MLS', 'date': '2025-10-12', 'time': '16:00', 'url': 'mock_url_1'},
                {'homeTeam': 'Arsenal', 'awayTeam': 'Liverpool', 'league': 'Premier League', 'date': '2025-10-13', 'time': '12:00', 'url': 'mock_url_2'},
                {'homeTeam': 'Corinthians', 'awayTeam': 'São Paulo', 'league': 'Brasileirão Série A', 'date': '2025-10-14', 'time': '21:30', 'url': 'mock_url_3'},
            ]
            
            all_scraped_data = []

            for match in mock_matches:
                # Na implementação real, match['url'] seria usado para fetch_odds
                full_odds_data = await fetch_odds(browser, match['url']) 
                
                if full_odds_data:
                    # 1. Aplica a lógica de Odd Única (Não Repetir Casas) para 3 resultados
                    unique_odds = select_unique_odds(full_odds_data)
                    
                    # 2. Cria o documento a ser salvo
                    document_data = {
                        'home_team': match['homeTeam'],
                        'away_team': match['awayTeam'],
                        'league': match['league'],
                        'date': match['date'], # Formato 'YYYY-MM-DD'
                        'time': match['time'],
                        # Campos de Odd Única (o frontend usará estes para o cálculo de arbitragem)
                        'home_odd': unique_odds.get('home', {}).get('value'),
                        'draw_odd': unique_odds.get('draw', {}).get('value'),
                        'away_odd': unique_odds.get('away', {}).get('value'),
                        # Campos da Casa de Apostas (para exibição)
                        'home_house': unique_odds.get('home', {}).get('house'),
                        'draw_house': unique_odds.get('draw', {}).get('house'),
                        'away_house': unique_odds.get('away', {}).get('house'),
                        # O documento original com todas as odds para verificação no Firebase
                        'all_odds_raw': full_odds_data 
                    }
                    all_scraped_data.append(document_data)
            
            print(f"=> SALVANDO {len(all_scraped_data)} JOGOS NO FIREBASE...")

            # --- SALVANDO NO FIRESTORE (Upsert) ---
            batch = db.batch()
            collection_ref = db.collection(COLLECTION_NAME)

            for data in all_scraped_data:
                # Cria um ID de documento único baseado nos times e na data para evitar duplicação
                doc_id = f"{data['home_team']}-{data['away_team']}-{data['date']}".replace(" ", "_").replace(":", "_")
                doc_ref = collection_ref.document(doc_id)
                batch.set(doc_ref, data)
                
            batch.commit()
            print("Processo de raspagem concluído e dados salvos no Firebase.")


        except Exception as e:
            print(f"Erro crítico durante a raspagem: {e}")
        finally:
            await browser.close()


if __name__ == '__main__':
    # Usando Mock de Credenciais se estiver em modo de simulação
    if not os.environ.get('FIREBASE_CREDENTIALS'):
        print("Aviso: Usando credenciais de simulação. Substitua pela credencial REAL no GitHub Secrets.")

    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        print("Processo interrompido pelo usuário.")
    except Exception as e:
        print(f"Erro fatal na execução: {e}")
