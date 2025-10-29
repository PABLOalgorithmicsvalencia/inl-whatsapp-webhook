from flask import Flask, request
import requests
import os

# --- Versión actual del bot ---
VERSION = "INL Chatbot v1.3 (29/10/2025 19:45)"
print(f"🚀 Iniciando {VERSION}")

app = Flask(__name__)

# --- Variables de entorno (Render → Environment) ---
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# --- Webhook de verificación (paso inicial con Meta) ---
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        print("✅ Webhook verificado correctamente.")
        return challenge
    print("❌ Token de verificación incorrecto.")
    return "Token inválido", 403


# --- Webhook para recibir mensajes de WhatsApp ---
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            print("[WEBHOOK] No hay mensajes en el payload.")
            return "EVENT_RECEIVED", 200

        msg = messages[0]
        sender = msg.get("from")
        mtype = msg.get("type")

        # Extraer texto del mensaje según el tipo
        text = ""
        if mtype == "text":
            text = msg.get("text", {}).get("body", "")
        elif mtype == "interactive":
            interactive = msg.get("interactive", {})
            text = interactive.get("button_reply", {}).get("title") or \
                   interactive.get("list_reply", {}).get("title") or ""
        elif mtype == "button":
            text = msg.get("button", {}).get("text", "")
        else:
            text = msg.get("text", {}).get("body", "") or ""

        print(f"[WEBHOOK] from={sender} type={mtype} text='{text}'")

        if not sender:
            print("[WEBHOOK] No se encontró el remitente del mensaje.")
            return "EVENT_RECEIVED", 200

        if text:
            ai_response = generate_ai_response(text)
            print(f"[AI RESPONSE] {ai_response}")
            send_whatsapp_message(sender, ai_response)
        else:
            # Si el mensaje no tiene texto interpretable
            fallback = ("Puedo ayudarte a reservar una clase de prueba GRATIS o darte información de nuestros cursos. "
                        "Por ejemplo, escribe: 'Quiero clase de prueba' o 'Cuéntame sobre los cursos'.")
            send_whatsapp_message(sender, fallback)

    except Exception as e:
        print(f"[ERROR] Procesando mensaje: {e}")
        send_whatsapp_message(
            value.get("contacts", [{}])[0].get("wa_id", sender or ""),
            "⚠️ Ha ocurrido un error temporal. Escribe 'hola' o 'ayuda' para continuar."
        )

    return "EVENT_RECEIVED", 200


# --- Generar respuesta con OpenAI ---
def generate_ai_response(user_text):
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "gpt-4o-mini",  # más estable y rápido
            "input": f"Eres un asistente de Algorithmics Valencia. Da respuestas útiles, amables y breves. "
                     f"El usuario dice: {user_text}"
        }

        response = requests.post("https://api.openai.com/v1/responses", headers=headers, json=data)
        response_json = response.json()

        if "output" in response_json:
            return response_json["output"][0]["content"][0]["text"]
        elif "choices" in response_json:
            return response_json["choices"][0]["message"]["content"]
        else:
            print(f"[AI WARNING] Respuesta inesperada: {response_json}")
            return "Disculpa, estoy procesando mucha información. Intenta repetirlo en unos segundos."
    except Exception as e:
        print(f"[AI ERROR] {e}")
        return "Disculpa, ha ocurrido un error con el sistema. Intenta de nuevo en un momento."


# --- Enviar mensaje de texto por WhatsApp ---
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
        print(f"[WA SEND] → {to}: {message[:120]}...")
        response = requests.post(url, headers=headers, json=payload)
        print(f"[WA STATUS] {response.status_code} {response.text}")
    except Exception as e:
        print(f"[WA ERROR] {e}")


# --- Página principal ---
@app.route("/", methods=["GET"])
def home():
    return f"✅ WhatsApp Chatbot activo ({VERSION})", 200


# --- Iniciar servidor Flask ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
