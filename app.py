import os
import base64
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

# Make sure your OPENAI_API_KEY is set in Render's Environment Variables!
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 1. ALLOW BIGGER PAYLOADS (Pasted image Base64 data can be large)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit


# 2. CHAT UI WITH IMAGE UPLOAD & PASTE SUPPORT
@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>AI Vision Chat</title>
            <style>
                body { font-family: sans-serif; max-width: 700px; margin: 30px auto; padding: 0 20px; }
                #chat-box { border: 1px solid #ccc; height: 400px; overflow-y: auto; padding: 15px; border-radius: 8px; margin-bottom: 15px; background: #f9f9f9; }
                .message { margin-bottom: 15px; }
                .user { font-weight: bold; color: #0066cc; }
                .assistant { color: #222; background: #fff; padding: 10px; border-radius: 6px; border: 1px solid #ddd; }
                .preview-img { max-width: 200px; display: block; margin-top: 5px; border-radius: 4px; }
                .controls { display: flex; gap: 10px; align-items: center; }
                input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; }
                button { padding: 10px 15px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
                #image-preview-container { margin-bottom: 10px; display: none; align-items: center; gap: 10px; }
            </style>
        </head>
        <body>
            <h2>AI Chat (Text + Image Support)</h2>
            <div id="chat-box"></div>

            <div id="image-preview-container">
                <span id="preview-label" style="font-size: 0.9em; color: #555;">Image Attached!</span>
                <button type="button" onclick="clearImage()" style="background: red; padding: 2px 8px; font-size: 0.8em;">Remove</button>
            </div>

            <div class="controls">
                <input type="file" id="file-input" accept="image/*" style="display: none;">
                <button type="button" onclick="document.getElementById('file-input').click()">📎 Upload</button>
                <input type="text" id="user-input" placeholder="Type a message or press Ctrl+V / Cmd+V to paste an image...">
                <button type="button" onclick="sendMessage()">Send</button>
            </div>

            <script>
                let currentBase64Image = null;

                const fileInput = document.getElementById('file-input');
                const userInput = document.getElementById('user-input');
                const previewContainer = document.getElementById('image-preview-container');

                // 1. Handle File Upload via Button
                fileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        processFile(e.target.files[0]);
                    }
                });

                // 2. Handle Paste Event (Ctrl+V / Cmd+V)
                document.addEventListener('paste', (event) => {
                    const items = (event.clipboardData || window.clipboardData).items;
                    for (const item of items) {
                        if (item.type.indexOf('image') !== -1) {
                            const blob = item.getAsFile();
                            processFile(blob);
                            break;
                        }
                    }
                });

                // Convert image file/blob to Base64
                function processFile(file) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        currentBase64Image = e.target.result; // Full data URL (data:image/png;base64,...)
                        previewContainer.style.display = 'flex';
                    };
                    reader.readAsDataURL(file);
                }

                function clearImage() {
                    currentBase64Image = null;
                    fileInput.value = '';
                    previewContainer.style.display = 'none';
                }

                // 3. Send Message to Backend
                async function sendMessage() {
                    const text = userInput.value.trim();
                    if (!text && !currentBase64Image) return;

                    const chatBox = document.getElementById('chat-box');

                    // Add user message to UI
                    let userHtml = `<div class="message"><span class="user">You:</span> ${text}`;
                    if (currentBase64Image) {
                        userHtml += `<img src="${currentBase64Image}" class="preview-img">`;
                    }
                    userHtml += `</div>`;
                    chatBox.innerHTML += userHtml;

                    // Clear inputs
                    const payload = { message: text, image_data: currentBase64Image };
                    userInput.value = '';
                    clearImage();
                    chatBox.scrollTop = chatBox.scrollHeight;

                    // Call backend /chat
                    try {
                        const response = await fetch('/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        const data = await response.json();

                        if (response.ok) {
                            chatBox.innerHTML += `<div class="message"><div class="assistant"><b>AI:</b> ${data.reply}</div></div>`;
                        } else {
                            chatBox.innerHTML += `<div class="message" style="color:red;">Error: ${data.error}</div>`;
                        }
                    } catch (err) {
                        chatBox.innerHTML += `<div class="message" style="color:red;">Failed to send message.</div>`;
                    }
                    chatBox.scrollTop = chatBox.scrollHeight;
                }

                // Allow pressing Enter to send
                userInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') sendMessage();
                });
            </script>
        </body>
        </html>
    ''')


# 3. OPENAI VISION CHAT ENDPOINT
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    user_text = data.get('message', '')
    image_data = data.get('image_data')  # Base64 string

    # Construct content payload for OpenAI
    content = []
    
    if user_text:
        content.append({"type": "text", "text": user_text})
    elif image_data:
        # Default prompt if user uploads an image without text
        content.append({"type": "text", "text": "What is in this image?"})

    if image_data:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": image_data  # Pass base64 data URL directly to OpenAI
            }
        })

    try:
        # Use gpt-4o which natively handles both text and images
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            max_tokens=500
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 4. START APP
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
