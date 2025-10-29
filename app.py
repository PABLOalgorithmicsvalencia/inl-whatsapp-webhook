# app.py
from flask import Flask, request
import requests
import os
from threading import Lock

app = Flask(__name__)

# =============== Variables de entorno ===============
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "inlacademy2025")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "./kb.txt")  # Ruta del archivo de base de conocimiento

# =============== Estado en memoria (simple) ===============
# Para evitar saludar varias veces a la misma persona (se reinicia si el proceso se reinicia)
_seen_users = set()
_seen_lock = Lock()

WELCOME_TEXT = "¡Encantados de saludarte! ¿Podemos ayudarte con algo? 🙂"

# =============== Cargar base de conocimiento ===============
def load_knowledge_base(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
                return txt
    except Exception as e:
        print("⚠️ No se pudo leer la base de conocimiento:", e)
    return ""

knowledge_base = load_knowledge_base(KNOWLEDGE_PATH)
print(f"📚 KB cargada desde {KNOWLEDGE_PATH}. Longitud: {len(knowledge_base)} chars")
print("📚 KB preview:", knowledge_base[:400].replace("\n", " ") + ("..." if len(knowledge_base) > 400 else ""))

# =============== Utilidades WhatsApp ===============
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
        "text": {"body": message}
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print("📤 [WA SEND] status:", resp.status_code, " resp:", resp.text[:600])
    except Exception as e:
        print("❌ Error enviando WhatsApp:", e)

def extract_text_from_incoming(msg: dict) -> str:
    """
    Extrae texto del mensaje entrante de WhatsApp, contemplando texto plano
    y respuestas interactivas (botones, listas).
    """
    # Texto normal
    text = msg.get("text", {}).get("body")
    if text:
        return text

    # Interactivo: botones/listas
    interactive = msg.get("interactive")
    if isinstance(interactive, dict):
        # Button reply
        btn = interactive.get("button_reply")
        if btn and isinstance(btn, dict):
            return btn.get("title") or btn.get("id") or ""

        # List reply
        lst = interactive.get("list_reply")
        if lst and isinstance(lst, dict):
            return lst.get("title") or lst.get("id") or ""

    return ""

# =============== OpenAI: extracción robusta ===============
def extract_text_from_openai(response_json: dict):
    """
    Soporta:
    - Formato nuevo: response["output"] -> items con type='message' y dentro content[] con 'text'
    - Formato antiguo: response["choices"][0]["message"]["content"]
    - Fallback: response["text"] si llega plano
    """
    # 1) Formato nuevo
    out = response_json.get("output")
    if isinstance(out, list):
        for item in out:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if isinstance(c, dict) and isinstance(c.get("text"), str):
                        return c["text"]

    # 2) Formato antiguo
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]

    # 3) Fallback
    if isinstance(response_json.get("text"), str):
        return response_json["text"]

    return None

def generate_ai_response(user_text: str) -> str:
    try:
        kb_fragment = knowledge_base[:12000] if knowledge_base else ""
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        system_prompt = (
            "Eres el asistente oficial de INL Academy / Algorithmics Valencia. "
            "Responde siempre en español, con un tono natural, amable y profesional. "
            "Si el usuario indica una edad o interés, sugiere cursos y horarios adecuados. "
            "Usa la base de conocimiento si aplica; si no está la respuesta, orienta con opciones y ofrece agendar una llamada."
        )
        data = {
            "model": "gpt-5",  # usa "gpt-4o" si no tienes acceso a gpt-5
            "input": (
                f"{system_prompt}\n\n"
                f"--- BASE DE CONOCIMIENTO (texto libre) ---\n{kb_fragment}\n"
                "------------------------------------------\n\n"
                f"Pregunta del usuario: {user_text}\n"
                "Responde de forma clara y práctica."
            ),
            "temperature": 0.5
        }
        resp = requests.post("https://api.openai.com/v1/responses", headers=headers, json=data, timeout=30)
        rj = resp.json()

        text = extract_text_from_openai(rj)
        if text:
            return text.strip()

        print("⚠️ No pude extraer texto de OpenAI. JSON:", str(rj)[:2000])
        return ("Estoy teniendo problemas para procesar la respuesta ahora mismo. "
                "¿Podrías repetir tu consulta con algún detalle extra (por ejemplo, edad y curso de interés)?")
    except Exception as e:
        print("❌ Error con OpenAI:", e)
        return "Ha ocurrido un problema generando la respuesta. Inténtalo de nuevo en un momento, por favor."

# =============== Webhook Meta ===============
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    mode = request.args.get("hub.mode")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado correctamente")
        return challenge, 200
    print("❌ Webhook verificación fallida")
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json(silent=True) or {}
    # Ignorar si no hay estructura esperada
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # Ignorar status updates (no son mensajes de usuario)
        if value.get("statuses"):
            return "OK", 200

        messages = value.get("messages")
        if not messages:
            return "OK", 200

        for msg in messages:
            from_number = msg.get("from")
            if not from_number:
                continue

            text = extract_text_from_incoming(msg).strip()
            if not text:
                # Nada que responder (puede ser media sin caption, etc.)
                continue

            # Saludo SOLO la primera vez para ese número
            first_time = False
            with _seen_lock:
                if from_number not in _seen_users:
                    _seen_users.add(from_number)
                    first_time = True

            if first_time:
                send_whatsapp_message(from_number, WELCOME_TEXT)

            # Respuesta IA
            print("🟢 [IN] Usuario:", from_number, " Texto:", text[:200])
            ai_text = generate_ai_response(text)
            send_whatsapp_message(from_number, ai_text)

        return "EVENT_RECEIVED", 200

    except Exception as e:
        print("❌ Error procesando mensaje:", e)
        return "ERROR", 200

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200

if __name__ == "__main__":
    # Render usa el puerto 10000 por defecto
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
