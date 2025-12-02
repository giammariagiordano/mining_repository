import google.generativeai as genai

# --- INCOLLA QUI LA TUA API KEY ---
api_key = "AIzaSyDgr58CvWoYH-B10ugQwHAGv3IhMQuDQSg"
# ----------------------------------

genai.configure(api_key=api_key)

print("Consultando Google per i modelli disponibili per questa chiave...")

try:
    found_any = False
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            found_any = True
            print(f"- {m.name}")
    
    if not found_any:
        print("NESSUN modello trovato. La chiave potrebbe non essere valida o abilitata.")
        
except Exception as e:
    print(f"Errore: {e}")

print("\nCOSA FARE ORA:")
print("Copia una delle stringhe qui sopra (es. 'models/gemini-1.5-flash') e usala ESATTAMENTE così nel tuo codice.")