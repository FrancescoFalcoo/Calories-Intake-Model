#!/usr/bin/env bash         #dice che deve essere eseguito con bash quando si fa la richiesta. 
#è un commento finto (col !), per il codice è un commento, ma per il sistema operativo no! lo legge e sa che deve usare bash per eseguire questo script


if [ $# -lt 2 ]; then                                                         #almeno 2 ('-lt 2' è less than 2) argomenti ($#) devono essere presenti, nome e quantità: se sbagli ti dice come si usa!
  echo "Uso: $0 <nome_o_barcode> <quantità_grammi> [data_YYYY-MM-DD]"
  echo "Esempio: $0 \"mela\" 150"                                             # $0 è il nome del file eseguito
  echo "Esempio con data: $0 \"8000500310427\" 100 \"2026-08-04\""
  exit 1                                                                      #exit 1 significa errore
fi

NOME="$1"                                                                             #prendi primo e secondoargomento e mettili nelle variabili NOME e QUANTITA
QUANTITA="$2"
# Se il terzo argomento è vuoto, usa la data odierna in formato YYYY-MM-DD, altrimenti usa il terzo argomento dato da utente come data            
DATA="${3:-$(date +%F)}"                                                              # '+%F' dice la data odierna, è lo stesso di '+%Y-%m-%d', ma più corto

URL="https://europe-west8-contacalorie-503715.cloudfunctions.net/calories-intake-function"

echo "Invio pasto: '${NOME}' (${QUANTITA}g) per il giorno ${DATA}..."

curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "{\"nome\": \"${NOME}\", \"quantità\": ${QUANTITA}, \"data\": \"${DATA}\"}" | jq . || echo ""