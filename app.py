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
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", "./kb.txt")

# =============== Estado en memoria ===============
_seen_users = set()
_seen_lock = Lock()

WELCOME_TEXT = "¡Encantados de saludarte! ¿Podemos ayudarte con algo? 🙂"

# =============== Cargar base de conocimiento ===============
def load_knowledge_base(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        print("⚠️ No se pudo leer la base de conocimiento:", e)
    return ""

knowledge_base = load_knowledge_base(KNOWLEDGE_PATH)
print(f"📚 KB cargada desde {KNOWLEDGE_PATH}. Longitud: {len(knowledge_base)} chars")
print("📚 KB preview:", knowledge_base[:400].replace("\n", " ") + ("..." if len(knowledge_base) > 400 else ""))

# =============== WhatsApp helpers ===============
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
        print("📤 [WA SEND] status:", resp.status_code, " resp:", resp.text[:400])
    except Exception as e:
        print("❌ Error enviando WhatsApp:", e)

def extract_text_from_incoming(msg: dict) -> str:
    # Texto normal
    txt = msg.get("text", {}).get("body")
    if txt:
        return txt

    # Interactivo
    interactive = msg.get("interactive")
    if isinstance(interactive, dict):
        btn = interactive.get("button_reply")
        if btn:
            return btn.get("title") or btn.get("id") or ""
        lst = interactive.get("list_reply")
        if lst:
            return lst.get("title") or lst.get("id") or ""

    return ""

# =============== OpenAI helpers ===============
def extract_text_from_openai(rj: dict):
    # Formato nuevo
    out = rj.get("output")
    if isinstance(out, list):
        for item in out:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if isinstance(c, dict) and c.get("text"):
                        return c["text"]
    # Formato antiguo
    choices = rj.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        if isinstance(msg, dict) and msg.get("content"):
            return msg["content"]
    # Fallback
    if isinstance(rj.get("text"), str):
        return rj["text"]
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
            "Responde siempre en español, con tono amable y profesional. "
            "Si el usuario dice la edad del niño/a, sugiere el curso y el horario más cercano. "
            "Si no tienes la info exacta, ofrece clase de prueba y teléfonos."
        )

        data = {
            "model": "gpt-5",   # cambia a gpt-4o si lo prefieres
            "input": (
                f"{system_prompt}\n\n"
                f"--- BASE DE CONOCIMIENTO ---\n{kb_fragment}\n"
                f"-----------------------------\n"
                f"Pregunta del usuario: {user_text}\n"
                "Responde de forma clara, breve y práctica."
            )
            # IMPORTANTE: no ponemos 'temperature' porque tu modelo no lo soporta
        }

        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=data,
            timeout=30
        )
        rj = resp.json()

        text = extract_text_from_openai(rj)
        if text:
            return text.strip()

        print("⚠️ No pude extraer texto de OpenAI. JSON:", str(rj)[:1500])
        return "He recibido tu mensaje, pero no he podido generar la respuesta ahora mismo. ¿Puedes reformularlo?"

    except Exception as e:
        print("❌ Error con OpenAI:", e)
        return "Ha ocurrido un problema generando la respuesta. Inténtalo en un momento, por favor."

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
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # Ignorar estados
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
                continue

            # Saludo solo primera vez
            first_time = False
            with _seen_lock:
                if from_number not in _seen_users:
                    _seen_users.add(from_number)
                    first_time = True

            print("🟢 [IN] Usuario:", from_number, " Texto:", text[:200])

            if first_time:
                send_whatsapp_message(from_number, WELCOME_TEXT)

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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
