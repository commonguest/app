import os
import base64
from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file (for local development)
load_dotenv()

app = Flask(__name__)

# Fallback secret key for sessions
app.secret_key = os.getenv("FLASK_SECRET_KEY", "temporary-secret-key-change-this")

# Load OpenAI API key
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    # Notice: In production, render will pass environment variables automatically
    print("WARNING: OPENAI_API_KEY is not set!")

client = OpenAI(api_key=api_key)

@app.route("/")
def home():

    # Using render_template correctly loads templates/app.html
    return render_template("app.html")

@app.route("/chat", methods=["POST"])
def chat():

    try:
        user_text = request.form.get("message", "")
        uploaded_image = request.files.get("image")

        content = []

        if user_text:
            content.append({
                "type": "text",
                "text": user_text
            })

        if uploaded_image:
            image_bytes = uploaded_image.read()
            encoded = base64.b64encode(image_bytes).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{uploaded_image.content_type};base64,{encoded}"
                }
            })

        if "history" not in session:
            session["history"] = []

        session["history"].append({
            "role": "user",
            "content": content
        })

        # Updated model to standard gpt-4o-mini (supports vision & chat)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=session["history"]
        )

        reply = response.choices[0].message.content

        session["history"].append({
            "role": "assistant",
            "content": reply
        })

        session.modified = True

        return jsonify({"reply": reply})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"reply": "ERROR: " + str(e)})

@app.route("/clear", methods=["POST"])
def clear():

    session.clear()
    return jsonify({"reply": "Chat cleared"})

if __name__ == "__main__":
    print("Server running...")
    app.run(host="0.0.0.0", port=5000, debug=True)