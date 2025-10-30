from flask import Flask, request
import requests
import os

app = Flask(__name__)

# =========================
# VARIABLES DE ENTORNO
# =========================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
KB_PATH = "./kb.txt"  # nombre del archivo en tu repo

# =========================
# 1. CARGAR BASE DE CONOCIMIENTO
# =========================
def load_kb():
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            text = f.read()
        print(f"[KB] Base de conocimiento cargada. Longitud: {len(text)} chars")
        return text
    except Exception as e:
        print(f"[KB] No se pudo cargar kb.txt: {e}")
        return ""

KB_TEXT = load_kb()

# dividir en trozos para buscar mejor
def chunk_text(text, max_len=900):
    parts = []
    current = []
    count = 0
    for line in text.splitlines():
        l = line.strip()
        if not l:
            continue
        if count + len(l) > max_len:
            parts.append("\n".join(current))
            current = [l]
            count = len(l)
        else:
            current.append(l)
            count += len(l)
    if current:
        parts.append("\n".join(current))
    return parts

KB_CHUNKS = chunk_text(KB_TEXT, max_len=900)
print(f"[KB] Generados {len(KB_CHUNKS)} trozos para buscar.")

# =========================
# 2. BUSCAR TROZOS RELEVANTES
# =========================
def find_relevant_chunks(user_text, top_k=3):
    user_lower = user_text.lower()
    scored = []
    for ch in KB_CHUNKS:
        ch_low = ch.lower()
        score = 0
        # palabras típicas que preguntan los padres
        keywords = [
            "algorithmics", "roblox", "unity", "python", "valencia", "l’eliana",
            "horario", "precios", "permanencia", "matrícula", "curso", "años",
            "clase de prueba", "sábados", "miércoles", "jueves", "viernes"
        ]
        for kw in keywords:
            if kw in user_lower and kw in ch_low:
                score += 2
        # coincidencia directa de palabras del usuario
        for w in user_lower.split():
            if w and w in ch_low:
                score += 1
        if score > 0:
            scored.append((score, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]

# =========================
# 3. WEBHOOK VERIFICACIÓN
# =========================
@app.route("/webhook", methods=["GET"])
def verify_token():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Token inválido", 403

# =========================
# 4. WEBHOOK MENSAJES
# =========================
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        message = value["messages"][0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        print(f"[IN] Usuario: {sender} Texto: {text}")

        if not text:
            send_whatsapp_message(sender, "No he podido leer tu mensaje. ¿Lo puedes repetir?")
            return "EVENT_RECEIVED", 200

        # generar respuesta
        answer = generate_ai_response(text)
        print(f"[OUT] Respuesta generada: {answer}")
        send_whatsapp_message(sender, answer)

    except Exception as e:
        print("Error procesando mensaje:", e)
    return "EVENT_RECEIVED", 200

# =========================
# 5. GENERAR RESPUESTA CON OPENAI
# =========================
def generate_ai_response(user_text):
    # 5.1 detectar si pide agente humano
    human_triggers = [
        "hablar con una persona",
        "hablar con un agente",
        "me llamáis",
        "que me llamen",
        "llamadme",
        "llamame",
        "asesor",
        "atención humana",
        "atencion humana",
        "quiero hablar con alguien"
    ]
    for trig in human_triggers:
        if trig in user_text.lower():
            return ("Perfecto, te pasamos con un asesor humano. "
                    "¿Nos indicas tu nombre y un teléfono de contacto (si no es este) "
                    "y el horario en el que te podemos llamar?")

    # 5.2 buscar en la base de conocimiento
    relevant = find_relevant_chunks(user_text, top_k=3)
    kb_part = "\n\n".join(relevant) if relevant else KB_TEXT[:1600]

    system_prompt = (
        "Eres el asistente oficial de INL Academy y Algorithmics Valencia.\n"
        "Hablas SIEMPRE en español sencillo, tono cercano y profesional, como un amigo progresista "
        "en quien se puede confiar a los hijos.\n"
        "Respondes de forma breve pero completa, sin tecnicismos innecesarios.\n"
        "SIEMPRE das opción de clase de prueba gratuita y de hablar con un asesor humano.\n"
        "Si te preguntan por algo fuera de esta información, dices que lo pasas al equipo humano.\n"
        "No inventes horarios que no estén en el texto.\n"
        "Texto de conocimiento a usar a continuación:\n"
        f"{kb_part}\n"
    )

    # modelo responses no acepta temperature: la quitamos
    payload = {
        "model": "gpt-5",  # o "gpt-4o"
        "input": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        "max_output_tokens": 450
    }

    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.post("https://api.openai.com/v1/responses",
                             headers=headers, json=payload, timeout=20)
        data = resp.json()
        # nuevo formato
        if "output" in data:
            for item in data["output"]:
                if item.get("type") == "message":
                    parts = item.get("content", [])
                    if parts and parts[0].get("type") == "output_text":
                        return parts[0].get("text", "").strip()
        # compatibilidad antigua
        if "choices" in data:
            return data["choices"][0]["message"]["content"].strip()
        print("No pude extraer texto de OpenAI. JSON:", data)
        return "He recibido tu mensaje pero no he podido preparar la respuesta completa. ¿Quieres que te pase con un asesor?"
    except Exception as e:
        print("Error con OpenAI:", e)
        return "Ahora mismo no puedo generar la respuesta completa. ¿Te paso con un asesor humano?"

# =========================
# 6. ENVIAR MENSAJE WHATSAPP
# =========================
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
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        print("[WA SEND] status:", r.status_code, "resp:", r.text[:200])
    except Exception as e:
        print("Error enviando mensaje WA:", e)

# =========================
# 7. HOME
# =========================
@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Chatbot activo ✅", 200

if __name__ == "__main__":
    # en local
    app.run(host="0.0.0.0", port=10000)
