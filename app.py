from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Variables de entorno (Render → Settings → Environment)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Webhook de verificación (GET) ---
@app.route("/webhook", methods=["GET"])
def verify_token():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403

# --- Webhook de recepción (POST) ---
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json(silent=True) or {}
    try:
        entry = (data.get("entry") or [{}])[0]
        changes = (entry.get("changes") or [{}])[0]
        value = changes.get("value") or {}

        # WhatsApp envía muchos tipos de eventos; solo seguimos si hay "messages"
        messages = value.get("messages")
        if not messages:
            return "EVENT_IGNORED", 200

        msg = messages[0]
        sender = msg.get("from")
        text = (msg.get("text") or {}).get("body", "")

        if sender and text:
            reply = generate_ai_response(text)
            send_whatsapp_message(sender, reply)

    except Exception as e:
        print(f"[Webhook Error] {e}")

    return "EVENT_RECEIVED", 200

# --- IA: OpenAI ---
def generate_ai_response(user_text: str) -> str:
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-5",  # si no tienes gpt-5, cambia a "gpt-4o"
            "input": (
                "Eres un asistente de Algorithmics Valencia. "
                "Responde de forma clara, útil y amable. "
                f"Usuario: {user_text}"
            )
        }
        r = requests.post("https://api.openai.com/v1/responses",
                          headers=headers, json=payload, timeout=25)
        j = r.json()

        # Preferir output_text si existe; luego caídas controladas
        if isinstance(j, dict):
            if "output_text" in j and j["output_text"]:
                return j["output_text"].strip()
            if "output" in j and j["output"]:
                # salida estructurada del endpoint responses
                try:
                    return j["output"][0]["content"][0]["text"].strip()
                except Exception:
                    pass
            if "choices" in j and j["choices"]:
                # compatibilidad con /chat/completions
                return j["choices"][0]["message"]["content"].strip()

        print("[OpenAI] Respuesta no esperada:", j)
        return "Ahora mismo no puedo responder, ¿puedes reformular tu pregunta?"

    except Exception as e:
        print(f"[OpenAI Error] {e}")
        return "He tenido un problema generando la respuesta. Intentémoslo de nuevo."

# --- Envío de WhatsApp ---
def send_whatsapp_message(to: str, message: str):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message[:4000]}  # límite prudente
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        print("[WA SEND]", resp.status_code, resp.text)
    except Exception as e:
        print("[WA Error] Enviando mensaje:", e)

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200
