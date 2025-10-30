import os
from flask import Flask, request, jsonify
from openai import OpenAI

# Inicialización del cliente OpenAI (usa tu propia clave en variable de entorno)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Archivo de conocimiento
KNOWLEDGE_FILE = "knowledge_base.txt"

def load_knowledge():
    """Carga el contenido del archivo de conocimiento completo"""
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return "No se encontró el archivo de conocimiento."

knowledge_base = load_knowledge()

# Mensaje de sistema base: define el tono y las reglas
SYSTEM_PROMPT = f"""
Eres el asistente oficial de Algorithmics School Valencia, parte de INL Academy.

Tu función es ayudar a padres y alumnos a conocer los cursos, precios, horarios y funcionamiento de la escuela. 
Siempre debes usar un tono cercano, amable, informativo y claro — nunca comercial ni frío.

REGLAS DE CONVERSACIÓN:
1. Si el usuario pide hablar con un humano o un agente, responde exactamente:
   "Perfecto, te pasamos con un asesor humano. ¿Nos indicas tu nombre y un teléfono de contacto (si no es este) y el horario en el que te podemos llamar?"
   Si ya dio sus datos, responde: "Gracias, lo pasamos al equipo ahora mismo."

2. Si el usuario menciona “no encuentro mi curso”, “no lo veo”, “no está en la lista”, “soy un colegio”, “soy una empresa” o lleva 3 interacciones sin resolver su duda,
   también debes ofrecer contacto con un asesor humano.

3. Si se menciona “PDF”, “dossier”, “ficha del curso” o similar, responde con el enlace del PDF correspondiente si está en la base de conocimiento.

4. Si el usuario no deja claro el área de interés, ofrece opciones de categorías:
   - Programación e informática (desde 5 años)
   - Diseño y videojuegos
   - Robótica
   - Desarrollo web y Python

5. Nunca inventes cursos ni precios. Solo usa la información incluida en el conocimiento cargado.

6. Usa el tono de voz Algorithmics: habla como un amigo progresista, de forma sencilla, optimista y cercana. 
   Ejemplo: “Tu hijo aprenderá…” en lugar de “los alumnos aprenderán”.

7. Si el usuario pide información general, explica brevemente lo que es Algorithmics y su filosofía, y ofrece consultar los cursos adecuados según edad o interés.

BASE DE CONOCIMIENTO:
{knowledge_base}
"""

@app.route("/chat", methods=["POST"])
def chat():
    """Endpoint principal del chatbot"""
    user_message = request.json.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No se recibió mensaje."}), 400

    try:
        # Llamada al modelo
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.6,
            max_tokens=800,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response.choices[0].message.content.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({"status": "Chatbot de Algorithmics activo"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
