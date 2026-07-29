from unittest.mock import patch, MagicMock

# 1. Blocchiamo la connessione reale a Firestore prima di importare il main, 
# altrimenti Python cerca di collegarsi a Google Cloud e va in errore in locale!
with patch("google.cloud.firestore.Client"):
    from main import Calorimetro

def test_metodo_sbagliato():
    """Testa che la funzione rifiuti tutto ciò che non è una POST [source: 2]"""
    mock_request = MagicMock()
    mock_request.method = 'GET'
    
    risposta, codice = Calorimetro(mock_request)
    assert codice == 405
    assert "errore" in risposta

@patch("main.requests.get")
def test_calorimetro_successo(mock_get):
    """Testa che il calcolo delle calorie e il salvataggio simulato funzionino"""
    # Simuliamo la risposta del sito OpenFoodFacts [source: 2]
    mock_api_response = MagicMock()
    mock_api_response.status_code = 200
    mock_api_response.json.return_value = {
        "products": [{
            "nutriments": {
                "energy-kcal_100g": 52,
                "carbohydrates_100g": 14,
                "proteins_100g": 0.3,
                "fat_100g": 0.2
            }
        }]
    }
    mock_get.return_value = mock_api_response

    # Simuliamo una richiesta POST dell'utente con una mela da 150g [source: 2]
    mock_request = MagicMock()
    mock_request.method = 'POST'
    mock_request.get_json.return_value = {
        "nome": "mela",
        "quantità": 150
    }

    # Eseguiamo la funzione
    risposta, codice = Calorimetro(mock_request)

    # Controlliamo che ritorni successo e codice 200 [source: 2]
    assert codice == 200
    assert risposta == {"stato": "successo"}