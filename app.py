from flask import Flask, request, jsonify
from openai import OpenAI
import os

# Inicializa Flask
app = Flask(__name__)

# Inicializa cliente de OpenAI (asegúrate de tener la variable en Render)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Ruta raíz para comprobar que el servidor está activo
@app.route("/", methods=["GET"])
def home():
    return "INL WhatsApp Webhook funcionando correctamente ✅"

# Ruta del webhook de WhatsApp
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("=== MENSAJE RECIBIDO ===")
        print(data)

        # Verificamos que el cuerpo contenga mensajes
        if data and "entry" in data:
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for message in messages:
                        sender = message["from"]
                        text = message["text"]["body"] if "text" in message else ""
                        print(f"Mensaje de {sender}: {text}")

                        # Generar respuesta con OpenAI
                        if text:
                            respuesta = generar_respuesta(text)
                            enviar_respuesta_whatsapp(sender, respuesta)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Error en webhook:", e)
        return jsonify({"error": str(e)}), 500


# Genera una respuesta sencilla usando OpenAI
def generar_respuesta(mensaje):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un asistente amable de Algorithmics School Valencia."},
                {"role": "user", "content": mensaje}
            ]
        )
        respuesta = completion.choices[0].message.content
        print(f"Respuesta generada: {respuesta}")
        return respuesta
    except Exception as e:
        print("Error generando respuesta:", e)
        return "Ha ocurrido un error procesando tu mensaje."


# Envía una respuesta de texto al número de WhatsApp del usuario
def enviar_respuesta_whatsapp(destinatario, mensaje):
    import requests
    import json

    try:
        token = os.getenv("WHATSAPP_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

        if not token or not phone_number_id:
            print("⚠️ Faltan variables de entorno WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID")
            return

        url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        body = {
            "messaging_product": "whatsapp",
            "to": destinatario,
            "type": "text",
            "text": {"body": mensaje}
        }

        response = requests.post(url, headers=headers, data=json.dumps(body))
        print("Respuesta enviada a WhatsApp:", response.status_code, response.text)

    except Exception as e:
        print("Error enviando respuesta:", e)


# Puerto para Render (usa variable de entorno PORT)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
