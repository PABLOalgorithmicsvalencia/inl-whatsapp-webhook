{\rtf1\ansi\ansicpg1252\cocoartf2820
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 from flask import Flask, request\
\
app = Flask(__name__)\
\
VERIFY_TOKEN = "inlacademy2025"\
\
@app.route("/webhook", methods=["GET", "POST"])\
def webhook():\
    if request.method == "GET":\
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:\
            return request.args.get("hub.challenge"), 200\
        return "Verification failed", 403\
    return "ok", 200\
\
if __name__ == "__main__":\
    app.run(host="0.0.0.0", port=5000)}