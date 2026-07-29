#librerie che abbiamo dato a requirements
from flask import Flask, request    
import requests
from google.cloud import firestore

#dpbbiamo inizializzare l'oggetto applicazione Flask e il client per il database
db = firestore.Client(project="contacalorie-503715", database="calories-table")     #il comando dell'SDK di Google che crea il "gestore" della connessione a Firestore. Quando l'app girerà su GCP, questa riga si collegherà in automatico al tuo database.

#dobbiamo creare il punto di ingresso per le richieste HTTP

def Calorimetro(request):               #Inserendo request tra le parentesi, diciamo a Python di accettare i dati che Google Cloud invia automaticamente quando riceve una chiamata HTTP
    if request.method != 'POST':            #accettiamo solo POST
        return {"errore": "Metodo non consentito, usa una richiesta POST"}, 405
    
    #estrazione variabili da richiesta del client e preparazione parametri di richesta

    richiesta_utente = request.get_json()   #Manderemo un json con i dati per richiedere del cibo. È un dizionario con i campi nome e quantità
    
    pasto = richiesta_utente["nome"]        #Dal dizionario estratto dal json, prendiamo i valori che ci interessano dai relativi campi
    peso = richiesta_utente["quantità"]

    
    url = "https://world.openfoodfacts.org/cgi/search.pl"   #URL del sito che ci darà le calorie in risposta
    parametri = {                                           #parametri richiesti da documentazione
    "search_terms": pasto,          #nome del cibo da cercare, prenderà il contenuto della variabile
    "search_simple": 1,             
    "action": "process",
    "json": 1                       #Non mandarmi una pagina web HTML, mandami i dati puliti in formato JSON
    }

    #mandiamo la richiesta HTTP GET
    # CREIAMO LA NOSTRA CARTA D'IDENTITÀ (User-Agent)
    intestazioni = {
        "User-Agent": "ContaCalorieApp/1.0 - Progetto di test"
    }
    
    # Mandiamo la richiesta HTTP GET includendo l'intestazione
    interrogazione = requests.get(url, params=parametri, headers=intestazioni)

    # AGGIUNTA EXTRA SICUREZZA: Controlliamo se la richiesta è andata a buon fine prima di leggere il JSON
    if interrogazione.status_code != 200:
        return {"errore": f"OpenFoodFacts ha risposto con errore {interrogazione.status_code}"}, 500

    risposta = interrogazione.json()                              #convertiamola in un dizionario, usiamo il metodo .json 

    nutrienti = risposta["products"][0]["nutriments"]       #ci salviamo tutti i nutrienti insieme, poi con solo un accesso prendiamo i 4 campi da nutrient, non ogni volta entrare dentro 4 dizionari!
    calorie = nutrienti["energy-kcal_100g"]
    carbo = nutrienti["carbohydrates_100g"]
    protein = nutrienti["proteins_100g"]
    fat = nutrienti["fat_100g"]

    #normalizziamo i valori in base al peso che abbiamo 
    true_cal = (calorie * peso)/100
    true_carb = (carbo * peso)/100
    true_pro = (protein * peso)/100
    true_fat = (fat * peso)/100

    #adesso mettiamo tutto nel nostro database,
    dati_pasto= {                           #vuole raggruppato tutto in un dizionario
    "1_nome" : pasto,                         #nome chiave tra virgolette per non confondersi con le variabili, : non =, separati da virgole
    "2_peso" : peso,
    "3_kcal" : true_cal,
    "4_carbohydrates" : true_carb,
    "5_proteins" : true_pro,
    "6_fats" : true_fat

    }

    nome_documento = f"{pasto}_{peso}g"
    db.collection("pasti").document(nome_documento).set(dati_pasto)
    #firestore è dinamico, se la collection pasti non c'è la crea, altrimenti si limita ad aggiungere. pure se dovessi cancellare i dati questo codice continuerebbe a funzionare!

    #risposta al client che quello che chiesto è stato salvato
    return ({"stato": "successo"},200)               #restituiamo la stringa successo e il codice 200