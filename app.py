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
seen_users = set()
seen_lock = Lock()

# aquí guardamos en qué área está cada número: {"34697xxxx":"A"}
user_context = {}
user_context_lock = Lock()

WELCOME_TEXT = (
    "¡Encantados de saludarte! Soy el asistente de INL Academy y Algorithmics Valencia. "
    "¿Podemos ayudarte con algo? 🙂"
)

AREA_MENU = (
    "Para ayudarte mejor, dime sobre qué necesitas info:\n"
    "A. Algorithmics (programación e informática para niños y jóvenes 5–17)\n"
    "B. Clases de repaso escolar o universitario\n"
    "C. Cursos de informática y programación para adultos\n"
    "D. Otra consulta\n"
    "Puedes responder con la letra o escribiendo la opción."
)

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
        print("📤 [WA SEND]", resp.status_code, resp.text[:400])
    except Exception as e:
        print("❌ Error enviando WhatsApp:", e)

def extract_text_from_incoming(msg: dict) -> str:
    txt = msg.get("text", {}).get("body")
    if txt:
        return txt
    interactive = msg.get("interactive")
    if isinstance(interactive, dict):
        btn = interactive.get("button_reply")
        if btn:
            return btn.get("title") or btn.get("id") or ""
        lst = interactive.get("list_reply")
        if lst:
            return lst.get("title") or lst.get("id") or ""
    return ""

# =============== Detección de área ===============
def detect_area(user_text: str) -> str | None:
    t = user_text.lower()

    # Si el usuario pone la letra
    if t.strip() in ["a", "algoritmics", "algorithmics", "algo", "algorithmics valencia"]:
        return "A"
    if t.strip() in ["b", "repaso", "clases de repaso", "refuerzo", "academia"]:
        return "B"
    if t.strip() in ["c", "adultos", "informatica", "informática", "curso de excel", "curso de word", "curso de diseño"]:
        return "C"
    if t.strip() in ["d", "otra", "otras", "otra consulta", "facturacion", "facturación"]:
        return "D"

    # Por contenido
    # A) Algorithmics: niño, hija, hijo, edad, roblox, unity, programación, 10 años...
    if any(x in t for x in ["mi hijo", "mi hija", "tiene 5", "tiene 6", "tiene 7", "tiene 8", "tiene 9", "tiene 10",
                            "tiene 11", "tiene 12", "tiene 13", "tiene 14", "tiene 15", "tiene 16", "tiene 17",
                            "roblox", "unity", "unreal", "programación para niños", "curso de programación para niños",
                            "clases de programación", "algorithmics"]):
        return "A"

    # B) Repaso
    if any(x in t for x in ["repaso", "secundaria", "eso", "bachiller", "bachillerato",
                            "mates", "matemáticas", "lengua", "fisica", "quimica", "selectivo", "selectividad",
                            "universidad", "universitario", "aprobar"]):
        return "B"

    # C) Adultos
    if any(x in t for x in ["quiero aprender excel", "curso de excel", "ofimática", "ofimatica", "para el trabajo",
                            "soy adulto", "soy mayor", "tengo 30", "tengo 40", "tengo 50", "para mi empresa",
                            "curso de wordpress", "curso de diseño", "curso de python", "curso de programación"]):
        return "C"

    return None

# =============== OpenAI helpers ===============
def extract_text_from_openai(rj: dict):
    out = rj.get("output")
    if isinstance(out, list):
        for item in out:
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if isinstance(c, dict) and c.get("text"):
                        return c["text"]
    choices = rj.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        if isinstance(msg, dict) and msg.get("content"):
            return msg["content"]
    if isinstance(rj.get("text"), str):
        return rj["text"]
    return None

def generate_ai_response(user_text: str, area: str | None) -> str:
    try:
        kb_fragment = knowledge_base[:12000] if knowledge_base else ""

        # Construimos el "contexto" según el área
        if area == "A":
            area_instr = "El usuario está preguntando por ALGORITHMICS (niños y jóvenes 5–17). Usa SOLO la parte de Algorithmics."
        elif area == "B":
            area_instr = "El usuario está preguntando por CLASES DE REPASO ESCOLAR o UNIVERSITARIO. Usa SOLO la parte de repaso."
        elif area == "C":
            area_instr = "El usuario está preguntando por CURSOS DE INFORMÁTICA / PROGRAMACIÓN / DISEÑO PARA ADULTOS. Usa SOLO esa parte."
        elif area == "D":
            area_instr = "El usuario tiene una consulta general (facturación, administración, otras). Responde con los datos generales."
        else:
            # no detectado: mostramos menú
            return AREA_MENU

        system_prompt = (
            "Eres el asistente oficial de INL Academy y Algorithmics Valencia. "
            "Tu tarea es responder solo con la información del área que corresponda. "
            "Si hay horarios en el conocimiento, ofrécelos. Si no hay precio, no lo inventes. "
            "Si el usuario quiere clase de prueba, pídele nombre, edad y teléfono. "
            f"{area_instr}"
        )

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-5",
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Base de conocimiento:\n{kb_fragment}"},
                {"role": "user", "content": user_text}
            ]
        }

        resp = requests.post("https://api.openai.com/v1/responses",
                             headers=headers, json=data, timeout=30)
        rj = resp.json()
        text = extract_text_from_openai(rj)
        if text:
            return text.strip()

        print("⚠️ No pude extraer texto de OpenAI:", str(rj)[:1200])
        return "He recibido tu mensaje, pero no he podido generar la respuesta ahora mismo."

    except Exception as e:
        print("❌ Error con OpenAI:", e)
        return "Ha ocurrido un problema generando la respuesta. Intenta formularlo de otra forma."

# =============== Webhook Meta ===============
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    mode = request.args.get("hub.mode")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json(silent=True) or {}
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # ignorar estados
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

            # saludo solo 1 vez
            with seen_lock:
                first_time = from_number not in seen_users
                if first_time:
                    seen_users.add(from_number)

            if first_time:
                send_whatsapp_message(from_number, WELCOME_TEXT)

            # 1) vemos si ya tenemos área guardada
            with user_context_lock:
                area = user_context.get(from_number)

            # 2) si no hay área guardada, intentamos detectar por el texto
            if not area:
                detected = detect_area(text)
                if detected:
                    with user_context_lock:
                        user_context[from_number] = detected
                    area = detected
                else:
                    # no se detecta → mostramos menú y no seguimos
                    send_whatsapp_message(from_number, AREA_MENU)
                    continue

            # 3) ya tenemos área → generamos respuesta
            ai_text = generate_ai_response(text, area)
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
