import os
import json
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

def scrape_odds():
    # NOTA: Este é um URL de exemplo. Os alvos de web scraping podem mudar frequentemente.
    # Este URL é para demonstração e pode precisar de ser atualizado.
    URL = "https://www.oddsagora.com.br/futebol/hoje"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        page = requests.get(URL, headers=headers)
        soup = BeautifulSoup(page.content, 'html.parser')

        # Limpar os jogos existentes no Firebase para evitar duplicados
        matches_ref = db.collection('matches')
        docs = matches_ref.stream()
        for doc in docs:
            doc.reference.delete()

        # Encontrar os contentores dos jogos (este seletor é um exemplo e provavelmente precisará de ser atualizado)
        match_elements = soup.select('.card-evento') # Este seletor é hipotético

        for match_elem in match_elements[:15]: # Limitar a 15 jogos para este exemplo
            try:
                home_team = match_elem.select_one('.equipe-casa').text.strip()
                away_team = match_elem.select_one('.equipe-visitante').text.strip()
                league = match_elem.select_one('.card-evento__competicao').text.strip()
                match_time_raw = match_elem.select_one('.card-evento__horario').text.strip()
                
                # Limpeza básica de dados
                match_time = match_time_raw.split(' ')[-1]
                match_date = "2025-10-07" # Data de exemplo

                odds_elems = match_elem.select('.odd-container') # Seletor hipotético
                
                # Estrutura de exemplo para as odds, já que a estrutura real é complexa
                odds_data = {
                    "home": {"value": float(odds_elems[0].text.strip()), "house": "Casa A"},
                    "draw": {"value": float(odds_elems[1].text.strip()), "house": "Casa B"},
                    "away": {"value": float(odds_elems[2].text.strip()), "house": "Casa C"}
                }

                match_data = {
                    'homeTeam': home_team,
                    'awayTeam': away_team,
                    'league': league,
                    'date': match_date,
                    'time': match_time,
                    'odds': odds_data,
                    'potential': 'Médio', # Potencial por defeito
                    'analysis': 'Análise automática com base nas odds.'
                }
                
                # Adicionar ao Firebase
                db.collection('matches').add(match_data)
                print(f"Adicionado: {home_team} vs {away_team}")

            except Exception as e:
                print(f"Erro ao processar um jogo: {e}")
                continue

    except Exception as e:
        print(f"Erro ao obter a página principal: {e}")

if __name__ == "__main__":
    scrape_odds()

