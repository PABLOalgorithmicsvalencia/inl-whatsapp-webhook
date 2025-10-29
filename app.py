from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

# ============================================================
#  ✅  BLOQUE 1: VARIABLES DE ENTORNO (Render → Environment)
# ============================================================

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ============================================================
#  ✅  BLOQUE 2: CARGA Y VERIFICACIÓN DE LA BASE DE CONOCIMIENTO
# ============================================================

def load_knowledge_base():
    try:
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            data = f.read()
            print("✅ Archivo de conocimiento cargado correctamente.")
            print("Longitud:", len(data))
            print("Primeras líneas:", data[:500])
            return data
    except Exception as e:
        print("⚠️ Error al cargar knowledge_base.txt:", e)
        return ""

KNOWLEDGE_BASE = load_knowledge_base()

# ============================================================
#  ✅  BLOQUE 3: DIVISIÓN DEL TEXTO EN FRAGMENTOS (para búsquedas)
# ============================================================

def split_kb(text):
    chunks = re.split(r"\n-{3,}\n|^#{1,6}\s|^.+\n=+\n", text, flags=re.MULTILINE)
    chunks = [c.strip() for c in chunks if c.strip()]
    MAX_CHUNK = 1800
    norm = []
    for c in chunks:
        if len(c) <= MAX_CHUNK:
            norm.append(c)
        else:
            paras = re.split(r"\n\s*\n", c)
            buff = ""
            for p in paras:
                if len(buff) + len(p) + 2 <= MAX_CHUNK:
                    buff += (p + "\n\n")
                else:
                    norm.append(buff.strip())
                    buff = p + "\n\n"
            if buff.strip():
                norm.append(buff.strip())
    return norm[:200]

KB_CHUNKS = split_kb(KNOWLEDGE_BASE)
print("Fragmentos de conocimiento cargados:", len(KB_CHUNKS))

# ============================================================
#  ✅  BLOQUE 4: SELECCIÓN DE FRAGMENTOS RELEVANTES
# ============================================================

def top_chunks(query, k=3):
    if not KB_CHUNKS:
        return []
    q = query.lower()
    stop = set("de la los las y e o u un una para por con en del al a que se es son está están".split())
    toks = [t for t in re.split(r"[^a-záéíóúñ0-9]+", q) if t and t not in stop]
    scores = []
    for i, ch in enumerate(KB_CHUNKS):
        c = ch.lower()
        s = 0
        for t in toks:
            if t in c:
                s += 1
        if "curso" in c and ("años" in c or "edad" in c):
            s += 1
        scores.append((s, i))
    scores.sort(reverse=True)
    best = [KB_CHUNKS[i] for s, i in scores[:k] if s > 0]
    if not best:
        best = KB_CHUNKS[:1]
    return best

# ============================================================
#  ✅  BLOQUE 5: TONO Y ESTILO DE RESPUESTA
# ============================================================

SYSTEM_PROMPT = (
    "Eres el asistente oficial de INL Academy / Algorithmics Valencia. "
    "Respondes SIEMPRE en español, profesional, claro y cercano, sin emoticonos. "
    "Nunca inventes datos: apóyate en la base de conocimiento proporcionada. "
    "Prioriza: 1) orientar al curso por edad/nivel, 2) ofrecer horarios, "
    "3) proponer clase de prueba gratuita, 4) recoger datos si procede (nombre, edad, teléfono/email, disponibilidad), "
    "5) CTA concreta. Respuestas breves pero completas, con pasos claros."
)

STYLE_GUIDE = (
    "Estilo: frases cortas, titulares claros cuando aplique, sin tecnicismos innecesarios, "
    "no uses markdown complejo, evita listas con viñetas si no aportan. "
    "Si el usuario pide horarios o edades, cítalos exactamente como aparecen. "
    "Si la pregunta no está en la base, reconoce la limitación y ofrece derivar a un asesor."
)

# ============================================================
#  ✅  BLOQUE 6: GENERACIÓN DE RESPUESTA CON OPENAI
# ============================================================

def generate_ai_response(user_text):
    try:
        snippets = top_chunks(user_text, k=3)
        kb_context = "\n\n---\n\n".join(snippets)
        print("Fragmentos usados (longitud):", len(kb_context))
        print("Texto base usado:", kb_context[:300])

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": "Base de conocimiento:\n" + kb_context},
            {"role": "system", "content": STYLE_GUIDE},
            {"role": "user", "content": user_text}
        ]

        data = {
            "model": "gpt-5",
            "temperature": 0.4,
            "max_tokens": 450,
            "messages": messages
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=30)
        j = response.json()
        out = j["choices"][0]["message"]["content"].strip()
        return out
    except Exception as e:
        print("Error con OpenAI:", e)
        return "Ha ocurrido un error generando la respuesta. ¿Podrías reformular tu pregunta?"

# ============================================================
#  ✅  BLOQUE 7: RECEPCIÓN DE MENSAJES (WHATSAPP)
# ============================================================

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        message = changes["value"]["messages"][0]

        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        if text:
            response_text = generate_ai_response(text)
            send_whatsapp_message(sender, response_text)
    except Exception as e:
        print("Error procesando mensaje:", e)
    return "EVENT_RECEIVED", 200

# ============================================================
#  ✅  BLOQUE 8: ENVÍO DE MENSAJES POR WHATSAPP
# ============================================================

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

# ============================================================
#  ✅  BLOQUE 9: VERIFICACIÓN DEL WEBHOOK
# ============================================================

@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Token inválido", 403

# ============================================================
#  ✅  BLOQUE 10: PÁGINA PRINCIPAL (COMPROBAR SI ESTÁ ACTIVO)
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200

# ============================================================
#  ✅  BLOQUE 11: EJECUCIÓN DEL SERVIDOR
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
