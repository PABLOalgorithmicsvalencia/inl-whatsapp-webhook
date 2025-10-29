from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "inlacademy2025"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification failed", 403
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
