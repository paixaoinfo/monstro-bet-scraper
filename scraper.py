import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import random
import requests

# --- CONFIGURAÇÃO ---
BETTING_HOUSES = ['Betano', 'Bet365', 'Sportingbet', 'KTO', 'VaideBet', 'Esportes da Sorte']
SPORTS_API_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d="

# Lista de análises de cenário
ANALYSIS_TEMPLATES = {
    "classic": [
        "Clássico de grande rivalidade. A tensão do jogo pode levar a um cenário imprevisível e com potencial para viradas.",
        "Jogo onde a camisa pesa. A tradição das equipas fala mais alto e o fator emocional será decisivo.",
        "Confronto histórico. Espera-se um jogo muito disputado, onde um golo pode mudar toda a dinâmica da partida."
    ],
    "technical": [
        "Duelo de duas equipas muito organizadas taticamente. A que errar menos provavelmente sairá com a vitória.",
        "Partida que promete ser um xadrez tático. A estratégia dos treinadores será fundamental para o resultado.",
        "Confronto entre equipas de alta qualidade técnica. O brilho individual de um jogador pode decidir o jogo."
    ],
    "goals": [
        "Jogo com potencial para muitos golos. Ambas as equipas têm ataques poderosos e defesas que costumam ceder espaços.",
        "A tendência é de uma partida aberta. As duas equipas preferem atacar a defender, o que promete um placar movimentado.",
        "Esperam-se golos dos dois lados. É um confronto entre duas filosofias de jogo ofensivas."
    ],
    "balanced": [
        "Confronto muito equilibrado. O fator casa pode ser o diferencial para o resultado final.",
        "Partida sem um favorito claro. Detalhes como uma bola parada ou um erro individual podem definir o vencedor.",
        "Jogo de forças equivalentes. A equipa que conseguir impor o seu ritmo de jogo terá mais chances de vencer."
    ]
}

# Palavras-chave para identificar tipos de jogos
CLASSIC_TEAMS = ["Real Madrid", "Barcelona", "Liverpool", "Manchester United", "Flamengo", "Palmeiras", "Corinthians", "São Paulo", "River Plate", "Boca Juniors", "Benfica", "FC Porto", "Brasil", "Argentina"]
TECHNICAL_LEAGUES = ["Champions League", "Premier League", "La Liga", "Serie A"]

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

def generate_realistic_odds():
    prob_home = random.uniform(0.15, 0.65)
    prob_draw = random.uniform(0.20, 0.35)
    prob_away = 1.0 - prob_home - prob_draw
    
    if prob_away < 0.1:
        prob_away = 0.1
        total = prob_home + prob_draw + prob_away
        prob_home, prob_draw, prob_away = prob_home/total, prob_draw/total, prob_away/total

    margin = 0.95
    odd_home = 1 / prob_home * margin
    odd_draw = 1 / prob_draw * margin
    odd_away = 1 / prob_away * margin
    
    return {
        "home": {"value": round(max(1.2, odd_home), 2), "house": random.choice(BETTING_HOUSES)},
        "draw": {"value": round(max(3.0, odd_draw), 2), "house": random.choice(BETTING_HOUSES)},
        "away": {"value": round(max(1.2, odd_away), 2), "house": random.choice(BETTING_HOUSES)}
    }

def generate_smart_analysis(home_team, away_team, league):
    """Gera uma análise inteligente com base nas equipas e na liga."""
    if any(team in home_team for team in CLASSIC_TEAMS) and any(team in away_team for team in CLASSIC_TEAMS):
        return random.choice(ANALYSIS_TEMPLATES["classic"])
    if any(l in league for l in TECHNICAL_LEAGUES):
        return random.choice(ANALYSIS_TEMPLATES["technical"])
    if "Bundesliga" in league:
        return random.choice(ANALYSIS_TEMPLATES["goals"])
    return random.choice(ANALYSIS_TEMPLATES["balanced"])


# --- FUNÇÃO PRINCIPAL DO ROBÔ ---
def fetch_real_matches_and_simulate_odds():
    print("A iniciar o processo para buscar jogos reais e simular odds.")
    
    all_events = []
    # Busca jogos para os próximos 5 dias
    for i in range(5):
        date_to_fetch = datetime.now() + timedelta(days=i)
        date_str = date_to_fetch.strftime("%Y-%m-%d")
        api_url = f"{SPORTS_API_URL}{date_str}"
        
        print(f"A buscar jogos para o dia: {date_str}")
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            events = data.get('events')
            if events:
                all_events.extend(events)
        except requests.exceptions.RequestException as e:
            print(f"Falha na ligação à API para o dia {date_str}: {e}")
            continue

    if not all_events:
        print("Nenhum evento encontrado nos próximos dias. A terminar.")
        return

    print(f"Total de {len(all_events)} eventos encontrados.")
    
    matches_ref = db.collection('matches')
    clear_collection(matches_ref)

    for event in all_events:
        if event.get('strSport') != 'Soccer':
            continue

        try:
            home_team = event.get('strHomeTeam')
            away_team = event.get('strAwayTeam')
            league = event.get('strLeague')
            event_time_str = event.get('strTime')
            event_date_str = event.get('dateEvent')

            if not all([home_team, away_team, league, event_time_str, event_date_str]):
                continue

            analysis_text = generate_smart_analysis(home_team, away_team, league)

            match_data = {
                'homeTeam': home_team,
                'awayTeam': away_team,
                'league': league,
                'date': event_date_str,
                'time': event_time_str[:5],
                'odds': generate_realistic_odds(),
                'potential': random.choice(['Médio', 'Alto']),
                'analysis': analysis_text
            }
            
            db.collection('matches').add(match_data)
            print(f"Adicionado à base de dados: {match_data['homeTeam']} vs {match_data['awayTeam']}")

        except Exception as e:
            print(f"Erro ao processar o evento {event.get('strEvent')}: {e}")
            continue
    
    print("Processo do robô concluído.")

if __name__ == "__main__":
    fetch_real_matches_and_simulate_odds()

