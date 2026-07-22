import os
import base64
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# LangChain Multi-Tool Search Engine Setup
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import Tool

app = Flask(__name__)

# Allow payloads up to 32MB for high-res images
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

    try:
        ddg_tool = DuckDuckGoSearchRun()
        tools.append(Tool(
            name="Web_Search_General",
            func=ddg_tool.run,
            description="Searches the live web for recent news, facts, current events, and live data."
        ))
    except Exception:
        pass

    try:
        wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=1000))
        tools.append(Tool(
            name="Wikipedia_Knowledge_Base",
            func=wiki.run,
            description="Useful for looking up detailed historical, scientific, geographical, and technical facts."
        ))
    except Exception:
        pass

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        tools.append(Tool(
            name="Tavily_AI_Search",
            func=TavilySearchResults(k=3).run,
            description="Factual deep web search optimized for AI context."
        ))
    except Exception:
        pass

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
# UI ROUTE
# ==========================================
@app.route('/')
def index():
    # Renders app.html from your /templates folder
    return render_template('app.html')


# ==========================================
# CHAT ENDPOINT
# ==========================================
@app.route('/chat', methods=['POST'])
def chat():
    # Read text and image from FormData
    user_text = request.form.get('message', '').strip()
    image_file = request.files.get('image')

    if not user_text and not image_file:
        return jsonify({"error": "No message or image provided."}), 400

    # 1. Fetch search context if query text is provided
    fetched_context = ""
    if user_text and search_tools:
        try:
            for tool in search_tools:
                result = tool.func(user_text)
                if result:
                    fetched_context += f"\n--- Source ({tool.name}) ---\n{result}\n"
        except Exception as e:
            fetched_context = f"Search tool issue: {str(e)}"

    # 2. Build system instructions
    system_instruction = (
        "You are an exceptionally intelligent, concise, and direct AI assistant powered by gpt-4.1-mini.\n"
        "1. When provided with an image, IMMEDIATELY solve, answer, or analyze its content directly. Do NOT describe what the image looks like.\n"
        "2. Cross-reference all fetched search data below to ensure maximum accuracy before answering."
    )

    if fetched_context:
        system_instruction += f"\n\n[FETCHED MULTI-SOURCE SEARCH CONTEXT]\n{fetched_context}\n[END CONTEXT]"

    # 3. Construct user message content block for OpenAI Vision
    user_content = []
    
    if user_text:
        user_content.append({"type": "text", "text": user_text})
    elif image_file:
        user_content.append({"type": "text", "text": "Directly solve or answer whatever is shown in this image."})

    # Convert uploaded file to base64 Data URL if present
    if image_file:
        image_bytes = image_file.read()
        mime_type = image_file.content_type or 'image/jpeg'
        base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
        image_url = f"data:{mime_type};base64,{base64_encoded}"
        
        user_content.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

    api_messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content}
    ]

    # 4. Call OpenAI API
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
