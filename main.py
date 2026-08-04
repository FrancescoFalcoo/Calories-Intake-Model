#librerie che abbiamo dato a requirements
from flask import Flask, request    
import requests
import re                                           #confronto per capire se chiedo un cibo o un codice a barre
import os                                           #serve per prendere la chiave API di USDA dai secrets e passarla alla funzione search_usda
from google.cloud import firestore
from firebase_functions import firestore_fn
from APIrequests import search_openfoodfacts, search_usda   #divisione del codice in due file per chiarezza, importiamo le funzioni di ricerca da APIrequests.py 

#libreie e funzione per logging
import time
import json

def log_json(severity, message, **kwargs):          #**wkargs dice che oltre i primi due argomenti, gliene possiamo passare un altro numero arbitrario se vogliamo
    print(json.dumps({"severity": severity, "message": message, **kwargs}))         #diventa un unico dizionario, che poi viene convertito in JSON e stampato sul log di GCP. GCP lo leggerà e lo formatterà in automatico


#dobbiamo creare il punto di ingresso per le richieste HTTP

def Calorimetro(request):                   #Inserendo request tra le parentesi, diciamo a Python di accettare i dati che Google Cloud invia automaticamente quando riceve una chiamata HTTP
    start_time= time.time()

    #dobbiamo inizializzar il client per il database
    db = firestore.Client(project="contacalorie-503715", database="calories-table")     #il comando dell'SDK di Google che crea il "gestore" della connessione a Firestore. Quando l'app girerà su GCP, questa riga si collegherà in automatico al tuo database.

    if request.method != 'POST':            #accettiamo solo POST
        return {"errore": "Metodo non consentito, usa una richiesta POST"}, 405
    
    #estrazione variabili da richiesta del client e preparazione parametri di richesta

    richiesta_utente = request.get_json()   #Manderemo un json con i dati per richiedere del cibo. È un dizionario con i campi nome e quantità
    
    pasto = richiesta_utente["nome"]        #Dal dizionario estratto dal json, prendiamo i valori che ci interessano dai relativi campi
    peso = richiesta_utente["quantità"]
    data = richiesta_utente["data"]

    if not pasto or not peso or not data:               #controllo di sicurezza: se il client non ha mandato tutti i dati, ritorniamo un errore al client
        log_json("ERROR", "richiesta invalida, specificare 'nome' cibo, 'quantità' in cui si è consumato e 'data' del giorno di consumo", event_type="invalid_request")
        return {"errore":"richiesta invalida, specificare 'nome' cibo, 'quantità' in cui si è consumato e 'data' del giorno di consumo", }



    # ROUTER: È un codice a barre (solo numeri) o testo?
    if re.match(r'^\d{8,14}$', pasto):                  #se input_utente è un codice a barre (solo numeri, da 8 a 14 cifre) allora cerchiamo su OpenFoodFacts, altrimenti cerchiamo su USDA
        nutrienti = search_openfoodfacts(pasto, "barcode")
    else:
        nutrienti = search_usda(pasto)

    if not nutrienti or not isinstance(nutrienti, dict) or "calorie" not in nutrienti:      #controllo di sicurezza: se la funzione di ricerca non ha trovato il cibo, ritorniamo un errore al client
        log_json("ERROR", f"Prodotto non trovato o dati incompleti per: {pasto}", event_type="invalid_product", cibo=pasto, status_code=404)
        return {"errore": f"Prodotto '{pasto}' non trovato"}, 404                           #bisogna SEMPRE dare una risposta con questo formato ad una HTTP function

    #normalizziamo i valori in base al peso che abbiamo 
    true_cal = round((nutrienti["calorie"] * peso)/100, 2)
    true_carb = round((nutrienti["carboidrati"] * peso)/100, 2)
    true_sugar = round((nutrienti["zuccheri"] * peso)/100, 2)
    true_fibre = round((nutrienti["fibre"] * peso)/100, 2)
    true_sodio = round((nutrienti["sodio"] * peso)/100, 2)
    true_potassio = round((nutrienti["potassio"] * peso)/100, 2)
    true_saturi = round((nutrienti["grassi_saturi"] * peso)/100, 2)
    true_pro = round((nutrienti["proteine"] * peso)/100, 2)
    true_fat = round((nutrienti["grassi"] * peso)/100, 2)


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

    latency= round(((time.time()-start_time)*1000),2)
    log_json("INFO", f"prodotto '{pasto}' inserito col successo nel database in {latency} ms", event_type="product_saved", latency=latency, cibo=nutrienti["nome_cibo"])

    return ({"stato": "successo"},200)                    #restituiamo la stringa successo per mostrarlo subito al terminale lato client



def Totalizzatore(event, context=None):                     #funzione che si attiva ogni volta che un documento viene aggiunto o rimosso da una collection, e calcola il totale dei nutrienti della collection
    start_time = time.time()                    

    db = firestore.Client(project="contacalorie-503715", database="calories-table")     #il comando dell'SDK di Google che crea il "gestore" della connessione a Firestore. Quando l'app girerà su GCP, questa riga si collegherà in automatico al tuo database.

    # Trasformiamo l'indirizzo grezzo di Google in un oggetto Firestore
    # str(context.resource) finisce sempre con ".../documents/pasti/yogurt_200g"
    path_relativo = str(context.resource).split("/documents/")[-1]
    doc_ref = db.document(path_relativo)

    if doc_ref.id == "TOTALE":                                                          #si attiva ogni volta che un nuovo documento viene tolto/messo in una collection, quindi anche quando viene messo TOTALE! Evitiamo loop
        log_json("INFO", "Scrittura su TOTALE ignorata (loop prevention)", event_type="loop_prevention")        
        return

    collezione_ref = doc_ref.parent                 #lui ci passa il riferimento al documento, ma noi vogliamo la collection, quindi prendiamo il parent del documento, cioè la collezione a cui appartiene il documento "padre", che ha scatenato l'evento
     
    tot_calorie = 0.0
    tot_carboidrati = 0.0
    tot_zuccheri = 0.0
    tot_fibre = 0.0
    tot_proteine = 0.0
    tot_grassi = 0.0
    tot_grassi_saturi = 0.0
    tot_sodio = 0.0
    tot_potassio = 0.0 

    #Estrazione dei dati dalla collection e somma dei valori
    for cibo in collezione_ref.stream():                    #scorriamo tutti i documenti della collection tramite stream che è più efficiente di get se dobbiammo prendere tutti i cibi di una giornata
        cibo_diz = cibo.to_dict()                           #convertiamo il cibo corrente in un dizionario Python così possiamo accedere ai campi con le chiavi
        if cibo_diz.get("1_nome") != "TOTALE":              #ovviamente non vogliamo sommare il documento TOTALE, altrimenti avremmo un loop infinito
            tot_calorie += cibo_diz.get("3_kcal", 0)
            tot_carboidrati += cibo_diz.get("4_carboidrati", 0)
            tot_zuccheri += cibo_diz.get("5_zuccheri", 0)
            tot_fibre += cibo_diz.get("6_fibre", 0)
            tot_proteine += cibo_diz.get("7_proteine", 0)
            tot_grassi += cibo_diz.get("8_grassi", 0)
            tot_grassi_saturi += cibo_diz.get("9_grassi_saturi", 0)
            tot_sodio += cibo_diz.get("a_sodio", 0)
            tot_potassio += cibo_diz.get("b_potassio", 0)

    #Creazione/Upgrade di TOTALE                                         
    totale_ref = collezione_ref.document("TOTALE")          #creiamo riferimento al documento TOTALE, per come funziona Firestore, se non esiste lo crea, altrimenti lo aggiorna
    totale_ref.set({                                        #setta i valori del documento TOTALE con i valori
        "1_nome": "TOTALE",
        "2_peso": 0.0,
        "3_kcal": round(tot_calorie, 2),
        "4_carboidrati": round(tot_carboidrati, 2),
        "5_zuccheri": round(tot_zuccheri, 2),
        "6_fibre": round(tot_fibre, 2),
        "7_proteine": round(tot_proteine, 2),
        "8_grassi": round(tot_grassi, 2),
        "9_grassi_saturi": round(tot_grassi_saturi, 2),
        "a_sodio": round(tot_sodio, 2),
        "b_potassio": round(tot_potassio, 2),
    }, merge=True)                                          #merge=True significa che se il documento esiste già, aggiorna solo i campi che gli passiamo, senza cancellare gli altri campi che potrebbero esserci

    latency = round((time.time() - start_time) * 1000, 2)              
    log_json("INFO", f"Documento TOTALE aggiornato con successo nella collezione pasti in {latency} ms", event_type="TOT_update", collection=collezione_ref.id, latency=latency)
    return