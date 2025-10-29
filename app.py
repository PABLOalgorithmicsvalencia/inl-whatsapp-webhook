from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Variables de entorno (Render → Environment)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Webhook de verificación
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Token inválido", 403


# Webhook de recepción de mensajes
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()

    try:
        # Verificar si hay un mensaje entrante
        entry = data["entry"][0]
        changes = entry["changes"][0]
        message = changes["value"]["messages"][0]

        sender = message["from"]  # número del usuario
        text = message.get("text", {}).get("body", "")

        if text:
            response_text = generate_ai_response(text)
            send_whatsapp_message(sender, response_text)

    except Exception as e:
        print(f"Error procesando mensaje: {e}")

    return "EVENT_RECEIVED", 200


# Función para generar respuesta con OpenAI
def generate_ai_response(user_text):
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-5",  # puedes poner gpt-4o si no tienes gpt-5
            "input": f"Eres un asistente de Algorithmics Valencia y das respuestas claras, útiles y amables. El usuario ha dicho: {user_text}"
        }

        response = requests.post("https://api.openai.com/v1/responses", headers=headers, json=data)
        response_json = response.json()

        # Extraer texto de la respuesta
        if "output" in response_json:
            return response_json["output"][0]["content"][0]["text"]
        elif "choices" in response_json:  # compatibilidad con versiones anteriores
            return response_json["choices"][0]["message"]["content"]
        else:
            return "Lo siento, no entendí tu mensaje."
    except Exception as e:
        print(f"Error con OpenAI: {e}")
        return "Ha ocurrido un error generando la respuesta."


# Enviar mensaje de WhatsApp
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
        print("Mensaje enviado:", response.status_code, response.text)
    except Exception as e:
        print("Error enviando mensaje:", e)


@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
