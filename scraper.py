import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import random

# --- CONFIGURAÇÃO ---
BETTING_HOUSES = ['Betano', 'Bet365', 'Sportingbet', 'KTO', 'VaideBet', 'Esportes da Sorte']

# Lista interna de jogos futuros, agora mais precisa e variada.
INTERNAL_MATCH_LIST = [
    {"league": "Liga dos Campeões", "homeTeam": "Real Madrid", "awayTeam": "Bayern Munique", "type": "classic"},
    {"league": "Liga dos Campeões", "homeTeam": "Manchester City", "awayTeam": "PSG", "type": "technical"},
    {"league": "Premier League", "homeTeam": "Liverpool", "awayTeam": "Manchester United", "type": "classic"},
    {"league": "Premier League", "homeTeam": "Arsenal", "awayTeam": "Chelsea", "type": "classic"},
    {"league": "La Liga", "homeTeam": "Barcelona", "awayTeam": "Atlético de Madrid", "type": "technical"},
    {"league": "Brasileirão Série A", "homeTeam": "Flamengo", "awayTeam": "Palmeiras", "type": "classic"},
    {"league": "Brasileirão Série A", "homeTeam": "Corinthians", "awayTeam": "São Paulo", "type": "classic"},
    {"league": "Brasileirão Série A", "homeTeam": "Santos", "awayTeam": "Vasco da Gama", "type": "balanced"},
    {"league": "Copa Libertadores", "homeTeam": "River Plate", "awayTeam": "Boca Juniors", "type": "classic"},
    {"league": "Copa Libertadores", "homeTeam": "Fluminense", "awayTeam": "Internacional", "type": "technical"},
    {"league": "Serie A (Itália)", "homeTeam": "Inter de Milão", "awayTeam": "Juventus", "type": "classic"},
    {"league": "Bundesliga", "homeTeam": "Borussia Dortmund", "awayTeam": "RB Leipzig", "type": "goals"},
    {"league": "Liga Portugal", "homeTeam": "Benfica", "awayTeam": "FC Porto", "type": "classic"},
    {"league": "Brasileirão Série A", "homeTeam": "Grêmio", "awayTeam": "Atlético-MG", "type": "balanced"},
    {"league": "Eliminatórias Copa do Mundo", "homeTeam": "Brasil", "awayTeam": "Argentina", "type": "classic"},
    {"league": "Eliminatórias Copa do Mundo", "homeTeam": "Portugal", "awayTeam": "Itália", "type": "technical"},
]

# Nova lista de análises de cenário
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
        prob_away = 0.1
        total = prob_home + prob_draw + prob_away
        prob_home, prob_draw, prob_away = prob_home/total, prob_draw/total, prob_away/total

    margin = 0.95 # Margem de 5% da casa
    odd_home = 1 / prob_home * margin
    odd_draw = 1 / prob_draw * margin
    odd_away = 1 / prob_away * margin
    
    return {
        "home": {"value": round(max(1.2, odd_home), 2), "house": random.choice(BETTING_HOUSES)},
        "draw": {"value": round(max(3.0, odd_draw), 2), "house": random.choice(BETTING_HOUSES)},
        "away": {"value": round(max(1.2, odd_away), 2), "house": random.choice(BETTING_HOUSES)}
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

    for i, match_template in enumerate(selected_matches):
        try:
            future_date = datetime.now() + timedelta(days=i)
            match_hour = random.randint(16, 22)
            match_minute = random.choice([0, 15, 30, 45])
            
            # Escolhe uma análise aleatória com base no tipo de jogo
            match_type = match_template.get("type", "balanced")
            analysis_text = random.choice(ANALYSIS_TEMPLATES[match_type])

            match_data = {
                'homeTeam': match_template['homeTeam'],
                'awayTeam': match_template['awayTeam'],
                'league': match_template['league'],
                'date': future_date.strftime("%Y-%m-%d"),
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

