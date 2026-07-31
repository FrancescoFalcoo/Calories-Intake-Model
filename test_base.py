# test_main.py

def test_import_main():
    # Verifica che il file main.py esista e non abbia errori di sintassi
    import main
    assert True

def test_calorimetro_exists():
    # Verifica che la funzione 'Calorimetro' sia effettivamente definita in main.py
    from main import Calorimetro
    assert callable(Calorimetro)

def test_totalizzatore_exists():
    # Verifica che la funzione 'Totalizzatore' sia effettivamente definita in main.py
    from main import Totalizzatore
    assert callable(Totalizzatore)
   