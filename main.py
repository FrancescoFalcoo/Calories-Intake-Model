#librerie che abbiamo dato a requirements
from flask import Flask, request    
import requests
import re                                           #confronto per capire se chiedo un cibo o un codice a barre
import os                                           #serve per prendere la chiave API di USDA dai secrets e passarla alla funzione search_usda
from google.cloud import firestore

#dpbbiamo inizializzare l'oggetto applicazione Flask e il client per il database
db = firestore.Client(project="contacalorie-503715", database="calories-table")     #il comando dell'SDK di Google che crea il "gestore" della connessione a Firestore. Quando l'app girerà su GCP, questa riga si collegherà in automatico al tuo database.

#dobbiamo creare il punto di ingresso per le richieste HTTP

def Calorimetro(request):                   #Inserendo request tra le parentesi, diciamo a Python di accettare i dati che Google Cloud invia automaticamente quando riceve una chiamata HTTP
    if request.method != 'POST':            #accettiamo solo POST
        return {"errore": "Metodo non consentito, usa una richiesta POST"}, 405
    
    #estrazione variabili da richiesta del client e preparazione parametri di richesta

    richiesta_utente = request.get_json()   #Manderemo un json con i dati per richiedere del cibo. È un dizionario con i campi nome e quantità
    
    pasto = richiesta_utente["nome"]        #Dal dizionario estratto dal json, prendiamo i valori che ci interessano dai relativi campi
    peso = richiesta_utente["quantità"]
    data = richiesta_utente["data"]

    # ROUTER: È un codice a barre (solo numeri) o testo?
    if re.match(r'^\d{8,14}$', pasto):                  #se input_utente è un codice a barre (solo numeri, da 8 a 14 cifre) allora cerchiamo su OpenFoodFacts, altrimenti cerchiamo su USDA
        nutrienti = search_openfoodfacts(pasto)
    else:
        nutrienti = search_usda(pasto)

    if not nutrienti or not isinstance(nutrienti, dict) or "calorie" not in nutrienti:      #controllo di sicurezza: se la funzione di ricerca non ha trovato il cibo, ritorniamo un errore al client
        return {"errore": f"Prodotto non trovato o dati incompleti per: {pasto}"}, 404

    #normalizziamo i valori in base al peso che abbiamo 
    true_cal = (nutrienti["calorie"] * peso)/100
    true_carb = (nutrienti["carboidrati"] * peso)/100
    true_sugar = (nutrienti["zuccheri"] * peso)/100
    true_fibre = (nutrienti["fibre"] * peso)/100
    true_sodio = (nutrienti["sodio"] * peso)/100
    true_potassio = (nutrienti["potassio"] * peso)/100
    true_saturi = (nutrienti["grassi_saturi"] * peso)/100
    true_pro = (nutrienti["proteine"] * peso)/100
    true_fat = (nutrienti["grassi"] * peso)/100


    #adesso mettiamo tutto nel nostro database,
    dati_pasto= {                               #vuole raggruppato tutto in un dizionario
    "1_nome" : nutrienti["nome_cibo"],          #nome chiave tra virgolette per non confondersi con le variabili, : non =, separati da virgole
    "2_peso" : peso,
    "3_kcal" : true_cal,
    "4_carboidrati" : true_carb,
    "5_zuccheri" :true_sugar, 
    "6_fibre" : true_fibre,
    "7_proteine" : true_pro,
    "8_grassi" : true_fat,
    "9_grassi_saturi" : true_saturi,
    "a_sodio" : true_sodio,
    "b_potassio" : true_potassio,
    }

    nome_documento = f"{nutrienti['nome_cibo']}_{peso}g"
    db.collection(data).document(nome_documento).set(dati_pasto)              #firestore è dinamico, se la collection pasti non c'è la crea, altrimenti si limita ad aggiungere. pure se dovessi cancellare i dati questo codice continuerebbe a funzionare!

    #risposta al client che quello che chiesto è stato salvato
    return ({"stato": "successo"},200)               #restituiamo la stringa successo e il codice 200


def search_openfoodfacts(codice):
    
    url = f"https://world.openfoodfacts.org/api/v2/product/{codice}.json"           #URL del sito che ci darà le calorie in risposta, da API

    parametri = {                                           #parametri richiesti da documentazione
        "search_terms": codice,                             #nome del cibo da cercare, prenderà il contenuto della variabile
        "search_simple": 1,             
        "action": "process",
        "json": 1                                           #Non mandarmi una pagina web HTML, mandami i dati puliti in formato JSON
        }
           
    intestazioni = {                                        # CREIAMO LA NOSTRA CARTA D'IDENTITÀ (User-Agent)
            "User-Agent": "ContaCalorieApp/1.0 - Progetto di test"
        }
        
    # Mandiamo la richiesta HTTP GET 
    interrogazione = requests.get(url, params=parametri, headers=intestazioni)
    
    if interrogazione.status_code != 200:
        return None
    
    risposta = interrogazione.json()                                #convertiamola in un dizionario, usiamo il metodo .json 

    if risposta.get("status") != 1 or not risposta.get("product"):
        return None

    prodotto = risposta["product"]                                  #cambio formattazione per altra porta dell'API
    cibo = prodotto.get("nutriments", {})
    
    calorie = 0.0                                                   #inizializzazione a zero(Evita il NameError se un macro manca)
    carbo = 0.0
    sugar = 0.0
    fibra = 0.0
    protein = 0.0
    fat = 0.0
    saturi = 0.0
    sodio = 0.0
    potassio = 0.0

    sodio_converted = cibo.get("sodium_100g") * 1000 if cibo.get("sodium_100g") is not None else 0                  #da milligrammi a grammi + controllo che non sia vuoto
    potassio_converted = cibo.get("potassium_100g") * 1000 if cibo.get("potassium_100g") is not None else 0

    nutrienti = {                                                           #impacchettiamo qui, nel main facciamo solo la normalizzazione 
    "nome_cibo": prodotto.get("product_name", f"Prodotto_{codice}"),        #prendiamo il nome del cibo trovato, lo useremo per la risposta al client
    "calorie": float(cibo.get("energy-kcal_100g", 0.0)),                    #grazie alla get controlliamo che il campo esista, se non esiste mettiamo 0.0
    "carboidrati": float(cibo.get("carbohydrates_100g", 0.0)),              #qui è necessario il controllo perche lo mettono gli utenti, quindi non è detto che ci sia sempre
    "zuccheri": float(cibo.get("sugars_100g", 0.0)),
    "fibre": float(cibo.get("fiber_100g", 0.0)),
    "proteine": float(cibo.get("proteins_100g", 0.0)),
    "grassi": float(cibo.get("fat_100g", 0.0)),
    "grassi_saturi": float(cibo.get("saturated-fat_100g", 0.0)),
    "sodio": sodio_converted,
    "potassio": potassio_converted
    }

    return nutrienti


def search_usda(cibo):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"    #URL del sito della seconda API che ci darà le calorie in risposta
    USDA_key=os.environ.get("CHIAVE_USDA")                  #prendiamo la chiave API dai secrets, che abbiamo passato come variabile d'ambiente alla funzione cloud
    parametri = {
         "api_key": USDA_key,                               #inseriamo la chiave API dai secrets
         "query": cibo,
         "pageSize": 1,                                     #quanti risultati vogliamo, 1 solo per semplicità
         "dataType": ["Foundation", "SR Legacy"]            #tipi di dati che vogliamo, escludiamo i cibi dei supermercati, solo i cibi "ufficiali" del governo
    }

    interrogazione = requests.get(url, params=parametri)
    
    if interrogazione.status_code != 200:
        return None
    
    risposta = interrogazione.json()                        #Conversione in dizionario/JSON Python
    
    # 2. CONTROLLO E FALLBACK CORRETTO: la lista "foods" è vuota?
    if not risposta.get("foods"):
        return search_openfoodfacts(cibo)                   #chiamata di emergenza: se non trova il cibo su USDA, lo cerchiamo su OpenFoodFacts
    

    cibo = risposta["foods"][0]                             #Prendiamo il primo risultato della lista di cibi trovati

    nome_cibo = cibo["description"]                         #Prendiamo il nome del cibo trovato, lo useremo per la risposta al client

    calorie = 0.0                                           #inizializzazione a zero(Evita il NameError se un macro manca)
    carbo = 0.0
    sugar = 0.0
    fibra = 0.0
    protein = 0.0
    fat = 0.0
    saturi = 0.0
    sodio = 0.0
    potassio = 0.0

    for i in cibo["foodNutrients"]:                         #ciclo for per scorrere tutti i nutrienti del cibo trovato. In Python "i" non è per forza un numero, ma si adatta! qui i è una struct
        if i["nutrientId"] == 1008:                 
            calorie = i["value"]
        elif i["nutrientId"] == 1005:
            carbo = i["value"]
        elif i["nutrientId"] == 2000:
            sugar = i["value"]
        elif i["nutrientId"] == 1079: 
            fibra = i["value"]
        elif i["nutrientId"] == 1003:
            protein = i["value"]
        elif i["nutrientId"] == 1004: 
            fat = i["value"]
        elif i["nutrientId"] == 1258: 
            saturi = i["value"]
        elif i["nutrientId"] == 1093: 
            sodio = i["value"]
        elif i["nutrientId"] == 1092:
            potassio = i["value"]

    nutrienti = {                                           #impacchettiamo qui, nel main facciamo solo la normalizzazione
        "nome_cibo": nome_cibo,
        "calorie": calorie,
        "carboidrati": carbo,
        "zuccheri": sugar,
        "fibre": fibra,
        "proteine": protein,
        "grassi": fat,
        "grassi_saturi": saturi,
        "sodio": sodio,
        "potassio": potassio
    }

    return nutrienti
