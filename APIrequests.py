from flask import Flask, request    
import requests
import re                                           #confronto per capire se chiedo un cibo o un codice a barre
import os                                           #serve per prendere la chiave API di USDA dai secrets e passarla alla funzione search_usda
from google.cloud import firestore
#libreie e funzione per logging
import time
import json



def log_json(severity, message, **kwargs):                                          #**wkargs dice che oltre i primi due argomenti, gliene possiamo passare un altro numero arbitrario se vogliamo
    print(json.dumps({"severity": severity, "message": message, **kwargs}))         #diventa un unico dizionario, che poi viene convertito in JSON e stampato sul log di GCP. GCP lo leggerà e lo formatterà in automatico



def search_openfoodfacts(codice, tipo):
    start_time = time.time()                    # Inizio del timer per misurare il tempo di esecuzione della funzione (secondi dal 1 gen 1970)

    if tipo == "barcode":
        url = f"https://world.openfoodfacts.org/api/v2/product/{codice}.json"           #URL del sito che ci darà le calorie in risposta se usiamo il codice a barre, da API
    elif tipo == "text":
        url = "https://world.openfoodfacts.org/cgi/search.pl"                           #URL del sito che ci darà le calorie in risposta se è nome prodotto in caso di fallimento di USDA

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
    interrogazione = requests.get(url, params=parametri, headers=intestazioni, timeout=7.0)         #conviene sempre mettere il timeout
    
    if interrogazione.status_code != 200 and tipo=="barcode":
        log_json("ERROR", f"Chiamata a OpenFoodFacts fallita con codice {interrogazione.status_code}", event_type="failed_API_call", API="OpenFoodFacts", nome=codice, status_code=interrogazione.status_code)
        return None
    elif interrogazione.status_code != 200 and tipo=="text":
        log_json("ERROR", f"chiamada di riserva a OpenFoodFacts fallita con codice {interrogazione.status_code}", event_type="failed_fallback_API_call",nome=codice, status_code=interrogazione.status_code)
        return None
    
    risposta = interrogazione.json()                                #convertiamola in un dizionario, usiamo il metodo .json 

    if risposta.get("status") != 1 or not risposta.get("product"):
        return None

    latency = round((time.time() - start_time) * 1000, 2)              #tempo di esecuzione della funzione in millisecondi, arrotondato alle 2 cifra
    if tipo == "barcode":
        log_json("INFO", f"Chiamata a OpenFoodFacts completata con successo in {latency} ms", event_type="latency_API_call", nome=codice, latency=latency)
    elif tipo == "text":
        log_json("INFO", f"Chiamata di riserva a OpenFoodFacts completata con successo in {latency} ms", event_type="latency_fallback_API_call", nome=codice, latency=latency)

    prodotto = risposta["product"]                                  #cambio formattazione per altra porta dell'API
    cibo = prodotto.get("nutriments", {})
    
    calorie = 0.0                                                   #inizializzazione a zero (Evita il NameError se un macro manca)
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
    start_time = time.time()                    # Inizio del timer per misurare il tempo di esecuzione della funzione (secondi dal 1 gen 1970)

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"    #URL del sito della seconda API che ci darà le calorie in risposta
    USDA_key=os.environ.get("CHIAVE_USDA")                  #prendiamo la chiave API dai secrets, che abbiamo passato come variabile d'ambiente alla funzione cloud
    parametri = {
         "api_key": USDA_key,                               #inseriamo la chiave API dai secrets
         "query": cibo,
         "pageSize": 1,                                     #quanti risultati vogliamo, 1 solo per semplicità
         "dataType": ["Foundation", "SR Legacy"]            #tipi di dati che vogliamo, escludiamo i cibi dei supermercati, solo i cibi "ufficiali" del governo
    }

    interrogazione = requests.get(url, params=parametri, timeout=7.0)             
    
    if interrogazione.status_code != 200:
        log_json("ERROR", f"Chiamata a USDA fallita con codice {interrogazione.status_code}", event_type="failed_API_call", nome=cibo, API="USDA", status_code=interrogazione.status_code)
        return None
    
    risposta = interrogazione.json()                            #Conversione in dizionario/JSON Python
    
    # 2. CONTROLLO E FALLBACK CORRETTO: la lista "foods" è vuota?
    if not risposta.get("foods"):
        log_json("WARNING", f"prodotto assente su USA, chiiamata di riserva ad OpenFoodFacts", event_type="USDA_to_OFF_fallback", nome=cibo)
        return search_openfoodfacts(cibo, "text")               #chiamata di emergenza: se non trova il cibo su USDA, lo cerchiamo su OpenFoodFacts
    
    latency = round((time.time() - start_time) * 1000, 2)                               #tempo di esecuzione della funzione in millisecondi, arrotondato alle 2 cifra
    log_json("INFO", f"Chiamata a USDA completata con successo in {latency} ms", event_type="latency_API_call", nome=cibo, latency=latency)

    prodotto = risposta["foods"][0]                             #Prendiamo il primo risultato della lista di cibi trovati

    nome_cibo = prodotto["description"]                         #Prendiamo il nome del cibo trovato, lo useremo per la risposta al client

    calorie = 0.0                                               #inizializzazione a zero (Evita il NameError se un macro manca)
    carbo = 0.0
    sugar = 0.0
    fibra = 0.0
    protein = 0.0
    fat = 0.0
    saturi = 0.0
    sodio = 0.0
    potassio = 0.0

    for i in prodotto["foodNutrients"]:                         #ciclo for per scorrere tutti i nutrienti del cibo trovato. In Python "i" non è per forza un numero, ma si adatta! qui i è una struct
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

    nutrienti = {                                               #impacchettiamo qui, nel main facciamo solo la normalizzazione
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