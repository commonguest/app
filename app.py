import os
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
from duckduckgo_search import DDGS

app = Flask(__name__)

# Make sure OPENAI_API_KEY is configured in Render Environment Variables
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Payloads up to 32MB for memory and high-res pasted images
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024


def perform_web_search(query, max_results=3):
    """Fetches real-time web search results using DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "No search results found."
            
            formatted_results = []
            for r in results:
                formatted_results.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}\nURL: {r.get('href')}\n")
            return "\n---\n".join(formatted_results)
    except Exception as e:
        return f"Web search error: {str(e)}"


# CHAT UI WITH WEB SEARCH + VISION + MEMORY
@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>GPT-4.1-Mini Assistant</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 750px; margin: 30px auto; padding: 0 20px; color: #333; }
                #chat-box { border: 1px solid #e1e1e1; height: 500px; overflow-y: auto; padding: 20px; border-radius: 12px; margin-bottom: 15px; background: #fafafa; }
                .message { margin-bottom: 20px; }
                .user { font-weight: bold; color: #0066cc; }
                .assistant { color: #111; background: #ffffff; padding: 12px 16px; border-radius: 8px; border: 1px solid #e0e0e0; margin-top: 5px; white-space: pre-wrap; line-height: 1.5; }
                .preview-img { max-width: 250px; display: block; margin-top: 8px; border-radius: 6px; border: 1px solid #ccc; }
                .controls { display: flex; gap: 10px; align-items: center; }
                input[type="text"] { flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }
                button { padding: 12px 18px; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
                button:hover { background: #0052a5; }
                #image-preview-container { margin-bottom: 10px; display: none; align-items: center; gap: 10px; }
                .clear-btn { background: #666; }
                .clear-btn:hover { background: #444; }
                .search-toggle { display: flex; align-items: center; gap: 6px; font-size: 0.9em; margin-bottom: 10px; }
            </style>
        </head>
        <body>
            <h2>GPT-4.1-Mini Assistant (Vision + Web Search)</h2>
            
            <div class="search-toggle">
                <input type="checkbox" id="web-search-check" checked>
                <label for="web-search-check">Enable Web Search (fetches real-time internet data)</label>
            </div>

            <div id="chat-box"></div>

            <div id="image-preview-container">
                <span id="preview-label" style="font-size: 0.9em; color: #555;">Image Attached!</span>
                <button type="button" onclick="clearImage()" style="background: #dc3545; padding: 4px 10px; font-size: 0.8em;">Remove</button>
            </div>

            <div class="controls">
                <input type="file" id="file-input" accept="image/*" style="display: none;">
                <button type="button" onclick="document.getElementById('file-input').click()" title="Upload Image">📎</button>
                <input type="text" id="user-input" placeholder="Type or paste (Ctrl+V) an image here...">
                <button type="button" onclick="sendMessage()">Send</button>
                <button type="button" class="clear-btn" onclick="clearChat()">Clear History</button>
            </div>

            <script>
                let chatHistory = []; 
                let currentBase64Image = null;

                const fileInput = document.getElementById('file-input');
                const userInput = document.getElementById('user-input');
                const previewContainer = document.getElementById('image-preview-container');
                const chatBox = document.getElementById('chat-box');
                const webSearchCheck = document.getElementById('web-search-check');

                fileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) processFile(e.target.files[0]);
                });

                document.addEventListener('paste', (event) => {
                    const items = (event.clipboardData || window.clipboardData).items;
                    for (const item of items) {
                        if (item.type.indexOf('image') !== -1) {
                            processFile(item.getAsFile());
                            break;
                        }
                    }
                });

                function processFile(file) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        currentBase64Image = e.target.result;
                        previewContainer.style.display = 'flex';
                    };
                    reader.readAsDataURL(file);
                }

                function clearImage() {
                    currentBase64Image = null;
                    fileInput.value = '';
                    previewContainer.style.display = 'none';
                }
                
                function clearChat() {
                    chatHistory = [];
                    chatBox.innerHTML = '';
                    clearImage();
                }

                async function sendMessage() {
                    const text = userInput.value.trim();
                    if (!text && !currentBase64Image) return;

                    let userHtml = `<div class="message"><span class="user">You:</span> ${text}`;
                    if (currentBase64Image) userHtml += `<img src="${currentBase64Image}" class="preview-img">`;
                    userHtml += `</div>`;
                    chatBox.innerHTML += userHtml;

                    let userContent = [];
                    
                    if (text) {
                        userContent.push({ type: "text", text: text });
                    } else if (currentBase64Image) {
                        userContent.push({ type: "text", text: "Directly solve or answer whatever is shown in this image." });
                    }

                    if (currentBase64Image) {
                        userContent.push({ type: "image_url", image_url: { url: currentBase64Image } });
                    }

                    chatHistory.push({ role: "user", content: userContent });

                    userInput.value = '';
                    clearImage();
                    chatBox.scrollTop = chatBox.scrollHeight;

                    try {
                        const response = await fetch('/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                messages: chatHistory,
                                enable_web_search: webSearchCheck.checked
                            })
                        });
                        const data = await response.json();

                        if (response.ok) {
                            chatBox.innerHTML += `<div class="message"><div class="assistant"><b>AI:</b> ${data.reply}</div></div>`;
                            chatHistory.push({ role: "assistant", content: data.reply });
                        } else {
                            chatBox.innerHTML += `<div class="message" style="color:red;">Error: ${data.error}</div>`;
                            chatHistory.pop();
                        }
                    } catch (err) {
                        chatBox.innerHTML += `<div class="message" style="color:red;">Failed to send message.</div>`;
                        chatHistory.pop();
                    }
                    chatBox.scrollTop = chatBox.scrollHeight;
                }

                userInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') sendMessage();
                });
            </script>
        </body>
        </html>
    ''')


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    if not data or 'messages' not in data:
        return jsonify({"error": "Invalid request"}), 400

    messages = data.get('messages', [])
    enable_web_search = data.get('enable_web_search', True)

    # 1. Extract query for search context
    last_user_message = messages[-1]['content']
    search_query = ""
    
    if isinstance(last_user_message, list):
        for item in last_user_message:
            if item.get('type') == 'text':
                search_query += item.get('text', '') + " "
    elif isinstance(last_user_message, str):
        search_query = last_user_message

    # 2. Perform live web fetch
    search_context = ""
    if enable_web_search and search_query.strip():
        search_results = perform_web_search(search_query.strip())
        search_context = f"\n\n[LIVE WEB SEARCH RESULTS FOR: '{search_query.strip()}']\n{search_results}\n[END SEARCH RESULTS]\n"

    # 3. System Instruction
    system_instruction = {
        "role": "system",
        "content": (
            "You are an exceptionally intelligent, concise, and direct AI assistant powered by gpt-4.1-mini. "
            "1. When provided with an image, IMMEDIATELY solve, answer, or analyze its content. Do NOT describe what the image looks like. Give the final answer directly.\n"
            "2. You are provided with live search results when available. Use them to provide up-to-date, accurate answers.\n"
            "3. If asked about previous topics, photos, or text in the conversation, refer back to the conversation history provided."
        )
    }

    if search_context:
        system_instruction["content"] += f"\nRelevant context from web search:\n{search_context}"

    api_messages = [system_instruction] + messages

    try:
        # Calls model gpt-4.1-mini
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=api_messages,
            max_tokens=1200,
            temperature=0.2
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
