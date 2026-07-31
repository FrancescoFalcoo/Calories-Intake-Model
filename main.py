#librerie che abbiamo dato a requirements
from flask import Flask, request    
import requests
import re                                           #confronto per capire se chiedo un cibo o un codice a barre
import os                                           #serve per prendere la chiave API di USDA dai secrets e passarla alla funzione search_usda
from google.cloud import firestore
from firebase_functions import firestore_fn
from APIrequests import search_openfoodfacts, search_usda   #divisione del codice in due file per chiarezza, importiamo le funzioni di ricerca da APIrequests.py 

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
    return ({"stato": "successo"},200)                  #restituiamo la stringa successo e il codice 200




def Totalizzatore(event):

    if event.params["id_cibo"] == "TOTALE":                 #si attiva ogni volta che un nuovo documento viene tolto/messo in una collection, quindi anche quando viene messo TOTALE! Evitiamo loop
        return
     
    tot_calorie = 0.0
    tot_carboidrati = 0.0
    tot_zuccheri = 0.0
    tot_fibre = 0.0
    tot_proteine = 0.0
    tot_grassi = 0.0
    tot_grassi_saturi = 0.0
    tot_sodio = 0.0
    tot_potassio = 0.0 

    db = firestore.Client(project="contacalorie-503715", database="calories-table")     #il comando dell'SDK di Google che crea il "gestore" della connessione a Firestore. Quando l'app girerà su GCP, questa riga si collegherà in automatico al tuo database.

    tabella_ref = (
        event.data.after.reference                      #dalla variabile evento che ci passa Google Cloud, prendiamo il riferimento al documento che è stato modificato. 
        if event.data.after                             #Se l'evento è una cancellazione, 'after' non esiste, quindi prendiamo 'before'.
            else event.data.before.reference                            
    )

    collezione_ref = tabella_ref.parent                 #lui ci passa il riferimento al documento, ma noi vogliamo la collection, quindi prendiamo il parent del documento, cioè la collezione a cui appartiene il documento "padre", che ha scatenato l'evento

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
        "3_kcal": tot_calorie,
        "4_carboidrati": tot_carboidrati,
        "5_zuccheri": tot_zuccheri,
        "6_fibre": tot_fibre,
        "7_proteine": tot_proteine,
        "8_grassi": tot_grassi,
        "9_grassi_saturi": tot_grassi_saturi,
        "a_sodio": tot_sodio,
        "b_potassio": tot_potassio,
    }, merge=True)                                          #merge=True significa che se il documento esiste già, aggiorna solo i campi che gli passiamo, senza cancellare gli altri campi che potrebbero esserci

    print(f"Documento TOTALE aggiornato con successo nella collezione pasti!")
    return