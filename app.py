import os, json, requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

GRAPH_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

# ========= Helpers =========

def send_whatsapp_text(to, text):
    """Envía texto simple dentro de la ventana de 24 h."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4000]}
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(GRAPH_URL, headers=headers, json=payload, timeout=20)
    return r.status_code, r.text

def call_openai(messages):
    """Llama a OpenAI con un sistema que guía al bot para INL/Algorithmics."""
    import requests
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "gpt-4o-mini",
        "temperature": 0.3,
        "messages": messages,
        "max_tokens": 350
    }
    resp = requests.post(url, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

SYSTEM_PROMPT = (
    "Eres el asistente de INL Academy / Algorithmics Valencia. "
    "Objetivo: responder con claridad, y si procede, recoger datos para agendar una clase de prueba GRATIS "
    "(nombre del alumno, edad, curso de interés, disponibilidad, teléfono/email). "
    "Si preguntan por cursos, explica en breve: programación (Python, Java, C/C++, Web/JS, Unity/Unreal), "
    "ofimática/profesional (Excel, Adobe, etc.). "
    "Si detectas intención de reserva, guía en 3 pasos y ofrece link: https://es.alg.academy/clases-prueba "
    "(indicar centro Valencia). "
    "Estilo: cercano, profesional, respuestas cortas, con pasos claros. No inventes precios si no los sabes."
)

WELCOME_FALLBACK = (
    "¡Hola! Soy el asistente de INL Academy. ¿Buscas información de cursos o quieres agendar "
    "una clase de prueba gratuita? Puedo ayudarte :)"
)

# ========= Webhook =========

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Verificación
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Token inválido", 403

    # Mensajes entrantes
    data = request.get_json(silent=True) or {}
    try:
        changes = data["entry"][0]["changes"][0]["value"]
    except Exception:
        return "ok", 200  # no es un evento de mensaje

    # Asegurar que hay mensajes
    if "messages" not in changes:
        return "ok", 200

    msg = changes["messages"][0]
    from_id = msg.get("from")  # teléfono del usuario
    text_in = ""

    # Tipos: text, button, interactive, etc.
    if msg.get("type") == "text":
        text_in = msg["text"]["body"]
    elif msg.get("type") == "button":
        text_in = msg["button"]["text"]
    elif msg.get("type") == "interactive":
        interactive = msg["interactive"]
        if interactive.get("type") == "list_reply":
            text_in = interactive["list_reply"]["title"]
        elif interactive.get("type") == "button_reply":
            text_in = interactive["button_reply"]["title"]
    else:
        text_in = "."

    # Construir contexto para la IA
    user_prompt = text_in.strip() if text_in else "Usuario envió un evento sin texto."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    # Llamar a OpenAI y responder
    try:
        ai_reply = call_openai(messages)
        if not ai_reply or ai_reply.isspace():
            ai_reply = WELCOME_FALLBACK
    except Exception:
        ai_reply = WELCOME_FALLBACK

    # Enviar respuesta por WhatsApp
    try:
        send_whatsapp_text(from_id, ai_reply)
    except Exception:
        pass

    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def health():
    return "OK", 200
