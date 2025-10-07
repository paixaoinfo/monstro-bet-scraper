import os
import json
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import random

# --- CONFIGURAÇÃO ---
# Lista de casas de aposta para simulação
BETTING_HOUSES = ['Betano', 'Bet365', 'Sportingbet', 'KTO', 'VaideBet', 'Esportes da Sorte']
# API Gratuita para obter jogos reais (https://www.thesportsdb.com/api.php)
SPORTS_API_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=" 

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
def clear_collection(collection_ref, batch_size=50):
    """Apaga todos os documentos numa coleção em lotes."""
    docs = collection_ref.limit(batch_size).stream()
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    if deleted >= batch_size:
        return clear_collection(collection_ref, batch_size)
    print("Coleção 'matches' limpa.")

def generate_realistic_odds():
    """Gera odds simuladas de forma realista."""
    # Gera uma probabilidade base para cada resultado
    prob_home = random.uniform(0.1, 0.7)
    prob_draw = random.uniform(0.1, 0.4)
    prob_away = 1.0 - prob_home - prob_draw

    # Garante que a probabilidade away não é negativa se as outras forem altas
    if prob_away < 0.05:
        prob_away = 0.05
        total = prob_home + prob_draw + prob_away
        prob_home /= total
        prob_draw /= total
        prob_away /= total

    # Converte probabilidades em odds com uma pequena margem para a casa
    odd_home = 1 / prob_home * 0.95
    odd_draw = 1 / prob_draw * 0.95
    odd_away = 1 / prob_away * 0.95
    
    return {
        "home": {"value": round(max(1.1, odd_home), 2), "house": random.choice(BETTING_HOUSES)},
        "draw": {"value": round(max(2.0, odd_draw), 2), "house": random.choice(BETTING_HOUSES)},
        "away": {"value": round(max(1.1, odd_away), 2), "house": random.choice(BETTING_HOUSES)}
    }

# --- FUNÇÃO PRINCIPAL DO ROBÔ ---
def fetch_real_matches_and_simulate_odds():
    """Busca jogos reais de uma API estável e simula as odds."""
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    api_url_today = f"{SPORTS_API_URL}{today_str}"
    
    print(f"A buscar jogos para o dia de hoje a partir de: {api_url_today}")
    
    try:
        response = requests.get(api_url_today)
        response.raise_for_status() # Verifica se houve erros no pedido
        data = response.json()
        
        # A API retorna 'None' se não houver eventos, por isso tratamos isso
        events = data.get('events')
        if not events:
            print("Nenhum evento encontrado para hoje nesta API.")
            return

        print(f"Encontrados {len(events)} eventos.")
        
        matches_ref = db.collection('matches')
        clear_collection(matches_ref)

        for event in events:
            # Filtra apenas por eventos de Futebol (Soccer)
            if event.get('strSport') != 'Soccer':
                continue

            try:
                # Extrai os dados do jogo real
                home_team = event.get('strHomeTeam')
                away_team = event.get('strAwayTeam')
                league = event.get('strLeague')
                event_time_str = event.get('strTime')
                event_date_str = event.get('dateEvent')

                # Validação básica para garantir que temos os dados mínimos
                if not all([home_team, away_team, league, event_time_str, event_date_str]):
                    continue

                # Gera as odds simuladas para este jogo real
                simulated_odds = generate_realistic_odds()
                
                match_data = {
                    'homeTeam': home_team,
                    'awayTeam': away_team,
                    'league': league,
                    'date': event_date_str,
                    'time': event_time_str[:5], # Pega apenas HH:MM
                    'odds': simulated_odds,
                    'potential': random.choice(['Médio', 'Alto']), # Potencial aleatório
                    'analysis': 'Análise automática com base em dados de jogos reais e odds simuladas.'
                }
                
                # Guarda na base de dados
                db.collection('matches').add(match_data)
                print(f"Adicionado à base de dados: {home_team} vs {away_team}")

            except Exception as e:
                print(f"Erro ao processar um evento: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"Falha na ligação à API de desporto: {e}")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    fetch_real_matches_and_simulate_odds()
    print("Processo do robô concluído.")

