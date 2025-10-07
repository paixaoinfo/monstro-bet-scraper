import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import random
import requests

# --- CONFIGURAÇÃO ---
ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
# AGORA VAMOS BUSCAR TODOS OS JOGOS DE FUTEBOL E FILTRAR DEPOIS
API_URL = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=br&markets=h2h&apiKey={ODDS_API_KEY}"

# LIGAS QUE QUEREMOS MANTER
DESIRED_LEAGUES = [
    'soccer_epl', # Premier League
    'soccer_uefa_champions_league', # Champions League
    'soccer_brazil_campeonato_brasileiro_serie_a' # Brasileirão
]

ANALYSIS_TEMPLATES = {
    "classic": ["Clássico de grande rivalidade. A tensão pode levar a um cenário imprevisível e com potencial para viradas.", "Jogo onde a camisa pesa. A tradição fala mais alto e o fator emocional será decisivo."],
    "technical": ["Duelo de duas equipas muito organizadas taticamente. A que errar menos provavelmente sairá com a vitória.", "Partida que promete ser um xadrez tático. A estratégia dos treinadores será fundamental."],
    "balanced": ["Confronto muito equilibrado. O fator casa pode ser o diferencial para o resultado final.", "Partida sem um favorito claro. Detalhes podem definir o vencedor."]
}

# --- INICIALIZAÇÃO DO FIREBASE ---
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

# --- FUNÇÕES AUXILIARES ---
def clear_collection(collection_ref):
    docs = collection_ref.stream()
    for doc in docs:
        doc.reference.delete()
    print("Coleção 'matches' limpa.")

def generate_smart_analysis(home_team, away_team):
    classic_teams = ["Real Madrid", "Barcelona", "Liverpool", "Manchester United", "Flamengo", "Palmeiras", "Corinthians", "São Paulo", "River Plate", "Boca Juniors", "Benfica", "FC Porto"]
    if home_team in classic_teams and away_team in classic_teams:
        return random.choice(ANALYSIS_TEMPLATES["classic"])
    return random.choice(ANALYSIS_TEMPLATES["balanced"])

# --- FUNÇÃO PRINCIPAL DO ROBÔ ---
def fetch_real_odds():
    print(f"A buscar odds da API: {API_URL.replace(ODDS_API_KEY, '***')}")
    
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        games = response.json()
        
        if not games:
            print("Nenhum jogo encontrado na resposta da API.")
            return

        print(f"Encontrados {len(games)} jogos na API. A filtrar pelas ligas desejadas...")
        
        matches_ref = db.collection('matches')
        clear_collection(matches_ref)

        for game in games:
            # FILTRA APENAS OS JOGOS DAS LIGAS QUE QUEREMOS
            if game.get('sport_key') not in DESIRED_LEAGUES:
                continue

            try:
                home_team = game.get('home_team')
                away_team = game.get('away_team')
                commence_time = game.get('commence_time')
                
                dt_object = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                game_date = dt_object.strftime("%Y-%m-%d")
                game_time = dt_object.strftime("%H:%M")

                best_odds = {"home": {"value": 0, "house": "N/A"}, "draw": {"value": 0, "house": "N/A"}, "away": {"value": 0, "house": "N/A"}}

                for bookmaker in game.get('bookmakers', []):
                    market = next((m for m in bookmaker.get('markets', []) if m['key'] == 'h2h'), None)
                    if market:
                        for outcome in market.get('outcomes', []):
                            price = outcome['price']
                            if outcome['name'] == home_team and price > best_odds['home']['value']:
                                best_odds['home'] = {'value': price, 'house': bookmaker['title']}
                            elif outcome['name'] == 'Draw' and price > best_odds['draw']['value']:
                                best_odds['draw'] = {'value': price, 'house': bookmaker['title']}
                            elif outcome['name'] == away_team and price > best_odds['away']['value']:
                                best_odds['away'] = {'value': price, 'house': bookmaker['title']}
                
                if best_odds['home']['value'] == 0:
                    continue

                analysis_text = generate_smart_analysis(home_team, away_team)

                match_data = {
                    'homeTeam': home_team,
                    'awayTeam': away_team,
                    'league': game.get('sport_title'),
                    'date': game_date,
                    'time': game_time,
                    'odds': best_odds,
                    'potential': random.choice(['Médio', 'Alto']),
                    'analysis': analysis_text
                }
                
                db.collection('matches').add(match_data)
                print(f"Adicionado à base de dados: {home_team} vs {away_team}")

            except Exception as e:
                print(f"Erro ao processar um jogo: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"Falha na ligação à Odds API: {e}")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    fetch_real_odds()
    print("Processo do robô concluído.")

