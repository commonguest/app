import os
import base64
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

# LangChain Multi-Tool Search Agent Setup
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import Tool

app = Flask(__name__)

# Payloads up to 32MB for chat memory and high-res pasted images
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

# Setup OpenAI API Key
api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


# ==========================================
# MULTI-TOOL SEARCH ENGINE SETUP
# ==========================================
def create_multi_search_tools():
    """Initializes multiple search and retrieval tools."""
    tools = []

    # Tool 1: General Web Search (DuckDuckGo Text)
    try:
        ddg_tool = DuckDuckGoSearchRun()
        tools.append(Tool(
            name="Web_Search_General",
            func=ddg_tool.run,
            description="Searches the live web for recent news, facts, current events, and live data."
        ))
    except Exception:
        pass

    # Tool 2: Deep Encyclopedia Search (Wikipedia)
    try:
        wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=1000))
        tools.append(Tool(
            name="Wikipedia_Knowledge_Base",
            func=wiki.run,
            description="Useful for looking up detailed historical, scientific, geographical, and technical facts."
        ))
    except Exception:
        pass

    # ---> PUT YOUR NEW CODE HERE <---
    # Tool 3: Tavily AI Search (requires TAVILY_API_KEY in Render Environment)
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        tools.append(Tool(
            name="Tavily_AI_Search",
            func=TavilySearchResults(k=3).run,
            description="Factual deep web search optimized for AI context."
        ))
    except Exception:
        pass

    # Tool 4: SerpApi Google Search (requires SERPAPI_API_KEY in Render Environment)
    try:
        from langchain_community.utilities import SerpAPIWrapper
        serp_tool = SerpAPIWrapper()
        tools.append(Tool(
            name="SerpApi_Google_Search",
            func=serp_tool.run,
            description="Searches live Google results using SerpApi for accurate, real-time web facts."
        ))
    except Exception:
        pass

    return tools

# Initialize Agent Tools
search_tools = create_multi_search_tools()


# ==========================================
# CHAT UI
# ==========================================
@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>GPT-4.1-Mini Deep Search Assistant</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 30px auto; padding: 0 20px; color: #333; }
                #chat-box { border: 1px solid #e1e1e1; height: 500px; overflow-y: auto; padding: 20px; border-radius: 12px; margin-bottom: 15px; background: #fafafa; }
                .message { margin-bottom: 20px; }
                .user { font-weight: bold; color: #0066cc; }
                .assistant { color: #111; background: #ffffff; padding: 14px 18px; border-radius: 8px; border: 1px solid #e0e0e0; margin-top: 5px; white-space: pre-wrap; line-height: 1.5; }
                .preview-img { max-width: 250px; display: block; margin-top: 8px; border-radius: 6px; border: 1px solid #ccc; }
                .controls { display: flex; gap: 10px; align-items: center; }
                input[type="text"] { flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }
                button { padding: 12px 18px; background: #0066cc; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
                button:hover { background: #0052a5; }
                #image-preview-container { margin-bottom: 10px; display: none; align-items: center; gap: 10px; }
                .clear-btn { background: #666; }
                .clear-btn:hover { background: #444; }
                .search-toggle { display: flex; align-items: center; gap: 6px; font-size: 0.9em; margin-bottom: 10px; font-weight: 500; }
            </style>
        </head>
        <body>
            <h2>GPT-4.1-Mini Assistant (Vision + Multi-Source Search Engine)</h2>
            
            <div class="search-toggle">
                <input type="checkbox" id="web-search-check" checked>
                <label for="web-search-check">Enable Multi-Source Web Fetching (Queries multiple tools behind the scenes)</label>
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


# ==========================================
# CHAT ENDPOINT WITH AGENT & VISION
# ==========================================
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    if not data or 'messages' not in data:
        return jsonify({"error": "Invalid request"}), 400

    messages = data.get('messages', [])
    enable_web_search = data.get('enable_web_search', True)

    # 1. Extract query for multi-source search
    last_user_message = messages[-1]['content']
    search_query = ""
    
    if isinstance(last_user_message, list):
        for item in last_user_message:
            if item.get('type') == 'text':
                search_query += item.get('text', '') + " "
    elif isinstance(last_user_message, str):
        search_query = last_user_message

    # 2. Gather context from Multi-Search Tools if search is enabled
    fetched_context = ""
    if enable_web_search and search_query.strip() and len(search_tools) > 0:
        try:
            # Query web search and knowledge bases in parallel/sequence
            for tool in search_tools:
                result = tool.func(search_query.strip())
                if result:
                    fetched_context += f"\n--- Source ({tool.name}) ---\n{result}\n"
        except Exception as e:
            fetched_context = f"Search tools encountered an issue: {str(e)}"

    # 3. System Instruction
    system_instruction = {
        "role": "system",
        "content": (
            "You are an exceptionally intelligent, concise, and direct AI assistant powered by gpt-4.1-mini. "
            "1. When provided with an image, IMMEDIATELY solve, answer, or analyze its content directly. Do NOT describe what the image looks like.\n"
            "2. Cross-reference all fetched search data below to ensure maximum accuracy before answering.\n"
            "3. Maintain full conversation context using history provided."
        )
    }

    if fetched_context:
        system_instruction["content"] += f"\n\n[FETCHED MULTI-SOURCE SEARCH CONTEXT]\n{fetched_context}\n[END CONTEXT]"

    api_messages = [system_instruction] + messages

    try:
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
