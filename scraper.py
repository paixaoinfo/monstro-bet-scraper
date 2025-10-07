import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import random

# --- CONFIGURAÇÃO ---
BETTING_HOUSES = ['Betano', 'Bet365', 'Sportingbet', 'KTO', 'VaideBet', 'Esportes da Sorte']

# Lista interna de jogos futuros realistas, com datas relativas ao dia da execução
# O robô irá escolher a partir daqui.
INTERNAL_MATCH_LIST = [
    {"league": "Brasileirão Série A", "homeTeam": "Flamengo", "awayTeam": "Corinthians", "type": "classic", "days_from_now": 0},
    {"league": "Brasileirão Série A", "homeTeam": "Palmeiras", "awayTeam": "São Paulo", "type": "classic", "days_from_now": 0},
    {"league": "Liga dos Campeões", "homeTeam": "Real Madrid", "awayTeam": "Liverpool", "type": "classic", "days_from_now": 1},
    {"league": "Liga dos Campeões", "homeTeam": "Bayern Munique", "awayTeam": "Manchester City", "type": "technical", "days_from_now": 1},
    {"league": "Premier League", "homeTeam": "Arsenal", "awayTeam": "Tottenham", "type": "classic", "days_from_now": 2},
    {"league": "Premier League", "homeTeam": "Chelsea", "awayTeam": "Manchester United", "type": "classic", "days_from_now": 2},
    {"league": "La Liga", "homeTeam": "Barcelona", "awayTeam": "Atlético de Madrid", "type": "technical", "days_from_now": 3},
    {"league": "Copa Libertadores", "homeTeam": "Boca Juniors", "awayTeam": "Fluminense", "type": "classic", "days_from_now": 4},
    {"league": "Copa Libertadores", "homeTeam": "River Plate", "awayTeam": "Internacional", "type": "technical", "days_from_now": 4},
    {"league": "Serie A (Itália)", "homeTeam": "Inter de Milão", "awayTeam": "AC Milan", "type": "classic", "days_from_now": 5},
    {"league": "Bundesliga", "homeTeam": "Borussia Dortmund", "awayTeam": "Bayer Leverkusen", "type": "goals", "days_from_now": 5},
    {"league": "Liga Portugal", "homeTeam": "Benfica", "awayTeam": "Sporting CP", "type": "classic", "days_from_now": 6},
    {"league": "Brasileirão Série A", "homeTeam": "Grêmio", "awayTeam": "Atlético-MG", "type": "balanced", "days_from_now": 6},
    {"league": "Eliminatórias Copa do Mundo", "homeTeam": "Brasil", "awayTeam": "Uruguai", "type": "classic", "days_from_now": 7},
    {"league": "Eliminatórias Copa do Mundo", "homeTeam": "Argentina", "awayTeam": "Chile", "type": "classic", "days_from_now": 7},
]

ANALYSIS_TEMPLATES = {
    "classic": ["Clássico de grande rivalidade. A tensão pode levar a um cenário imprevisível e com potencial para viradas.", "Jogo onde a camisa pesa. A tradição fala mais alto e o fator emocional será decisivo."],
    "technical": ["Duelo de duas equipas muito organizadas taticamente. A que errar menos provavelmente sairá com a vitória.", "Partida que promete ser um xadrez tático. A estratégia dos treinadores será fundamental."],
    "goals": ["Jogo com potencial para muitos golos. Ambas as equipas têm ataques poderosos e defesas que costumam ceder espaços.", "A tendência é de uma partida aberta, com golos dos dois lados."],
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
    """Apaga todos os documentos numa coleção."""
    docs = collection_ref.stream()
    for doc in docs:
        doc.reference.delete()
    print("Coleção 'matches' limpa.")

def generate_realistic_odds():
    """Gera odds simuladas de forma realista."""
    prob_home = random.uniform(0.15, 0.65)
    prob_draw = random.uniform(0.20, 0.35)
    prob_away = 1.0 - prob_home - prob_draw
    
    if prob_away < 0.1:
        prob_away = 0.1; total = prob_home + prob_draw + prob_away
        prob_home, prob_draw, prob_away = prob_home/total, prob_draw/total, prob_away/total

    margin = 0.95
    return {
        "home": {"value": round(max(1.2, 1/prob_home * margin), 2), "house": random.choice(BETTING_HOUSES)},
        "draw": {"value": round(max(3.0, 1/prob_draw * margin), 2), "house": random.choice(BETTING_HOUSES)},
        "away": {"value": round(max(1.2, 1/prob_away * margin), 2), "house": random.choice(BETTING_HOUSES)}
    }

# --- FUNÇÃO PRINCIPAL DO ROBÔ ---
def process_internal_matches():
    """Processa a lista interna de jogos, gera odds e guarda na base de dados."""
    print("A iniciar o processo com a lista de jogos interna.")
    matches_ref = db.collection('matches')
    clear_collection(matches_ref)

    num_matches_to_show = random.randint(7, 12)
    selected_matches = random.sample(INTERNAL_MATCH_LIST, num_matches_to_show)
    print(f"A processar {len(selected_matches)} jogos selecionados.")

    for match_template in selected_matches:
        try:
            match_date = datetime.now() + timedelta(days=match_template['days_from_now'])
            match_hour = random.randint(16, 22)
            match_minute = random.choice([0, 15, 30, 45])
            
            match_type = match_template.get("type", "balanced")
            analysis_text = random.choice(ANALYSIS_TEMPLATES[match_type])

            match_data = {
                'homeTeam': match_template['homeTeam'],
                'awayTeam': match_template['awayTeam'],
                'league': match_template['league'],
                'date': match_date.strftime("%Y-%m-%d"),
                'time': f"{match_hour:02d}:{match_minute:02d}",
                'odds': generate_realistic_odds(),
                'potential': random.choice(['Médio', 'Alto']),
                'analysis': analysis_text
            }
            
            db.collection('matches').add(match_data)
            print(f"Adicionado à base de dados: {match_data['homeTeam']} vs {match_data['awayTeam']}")

        except Exception as e:
            print(f"Erro ao processar o jogo {match_template['homeTeam']}: {e}")
            continue
    
    print(f"Processo concluído. {len(selected_matches)} jogos foram adicionados à base de dados.")

if __name__ == "__main__":
    process_internal_matches()

