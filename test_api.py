import google.generativeai as genai

# Pon tu clave entre las comillas
MI_API_KEY = "AIzaSyD3F_lfAFvMPI5sg6V99rf3cUVNOOSU6DE" 

genai.configure(api_key=MI_API_KEY)

try:
    print("Conectando con Google...")
    # Intentamos listar los modelos disponibles
    modelos = list(genai.list_models())
    print("✅ ¡La API Key funciona perfectamente!")
    print(f"Tienes acceso a {len(modelos)} modelos, incluyendo la familia Gemini.")
except Exception as e:
    print(f"❌ Error: La API Key no es válida, está caducada o hay un problema de red.")
    print(f"Detalle del error: {e}")