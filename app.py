from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ------------------------------------------------------------
# VARIABLES DE ENTORNO (definidas en Render → Environment)
# ------------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------------
# CARGA DE BASE DE CONOCIMIENTO LOCAL
# ------------------------------------------------------------
KNOWLEDGE_BASE_PATH = "knowledge_base.txt"
knowledge_base = ""

try:
    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
        knowledge_base = f.read()
        print("✅ Archivo de conocimiento cargado correctamente.")
        print(f"Longitud: {len(knowledge_base)} caracteres")
except Exception as e:
    print(f"⚠️ No se pudo cargar la base de conocimiento: {e}")

# ------------------------------------------------------------
# MENSAJE DE BIENVENIDA AUTOMÁTICO
# ------------------------------------------------------------
SEEN_SENDERS = set()
INTRO_MESSAGE = (
    "¡Encantados de saludarte! 😊 ¿Podemos ayudarte con algo?"
)

# ------------------------------------------------------------
# WEBHOOK DE VERIFICACIÓN
# ------------------------------------------------------------
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Token inválido", 403

# ------------------------------------------------------------
# WEBHOOK DE RECEPCIÓN DE MENSAJES
# ------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        message = changes["value"]["messages"][0]

        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        if not text:
            return "EVENT_RECEIVED", 200

        # Saludo automático si es la primera vez que escribe
        if sender not in SEEN_SENDERS:
            send_whatsapp_message(sender, INTRO_MESSAGE)
            SEEN_SENDERS.add(sender)

        # Generar respuesta con IA
        response_text = generate_ai_response(text)
        send_whatsapp_message(sender, response_text)

    except Exception as e:
        print(f"❌ Error procesando mensaje: {e}")

    return "EVENT_RECEIVED", 200

# ------------------------------------------------------------
# FUNCIÓN: Generar respuesta con OpenAI
# ------------------------------------------------------------
def generate_ai_response(user_text):
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-5",  # o gpt-4o si no tienes gpt-5
            "input": (
                f"Eres el asistente oficial de INL Academy / Algorithmics Valencia. "
                f"Utiliza el siguiente conocimiento para responder de forma natural, útil y amable. "
                f"Base de conocimiento:\n{knowledge_base}\n\n"
                f"Pregunta del usuario: {user_text}"
            )
        }

        response = requests.post("https://api.openai.com/v1/responses", headers=headers, json=data)
        response_json = response.json()

        # --- Manejo del nuevo formato (output) ---
        if "output" in response_json and len(response_json["output"]) > 0:
            try:
                return response_json["output"][0]["content"][0]["text"]
            except Exception:
                pass

        # --- Compatibilidad con el formato antiguo (choices) ---
        if "choices" in response_json and len(response_json["choices"]) > 0:
            try:
                return response_json["choices"][0]["message"]["content"]
            except Exception:
                pass

        # --- Si falla, mostramos el error recibido ---
        return f"No se pudo procesar la respuesta de OpenAI. Respuesta: {response_json}"

    except Exception as e:
        print(f"❌ Error con OpenAI: {e}")
        return "Ha ocurrido un problema generando la respuesta, inténtalo de nuevo en unos instantes."

# ------------------------------------------------------------
# FUNCIÓN: Enviar mensaje de WhatsApp
# ------------------------------------------------------------
def send_whatsapp_message(to, message):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"✅ Mensaje enviado a {to}: {response.status_code}")
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")

# ------------------------------------------------------------
# HOME PAGE
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200

# ------------------------------------------------------------
# EJECUCIÓN
# ------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Iniciando servicio INL Academy Chatbot...")
    app.run(host="0.0.0.0", port=10000)
