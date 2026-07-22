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

# Payload limits up to 32MB for handling up to 10 high-res images
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

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
            description="Searches live web facts and current events."
        ))
    except Exception:
        pass

    try:
        wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=1000))
        tools.append(Tool(
            name="Wikipedia_Knowledge_Base",
            func=wiki.run,
            description="Useful for historical, scientific, and technical facts."
        ))
    except Exception:
        pass

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        tools.append(Tool(
            name="Tavily_AI_Search",
            func=TavilySearchResults(k=3).run,
            description="Factual deep web search optimized for AI."
        ))
    except Exception:
        pass

    try:
        from langchain_community.utilities import SerpAPIWrapper
        serp_tool = SerpAPIWrapper()
        tools.append(Tool(
            name="SerpApi_Google_Search",
            func=serp_tool.run,
            description="Searches Google results using SerpApi."
        ))
    except Exception:
        pass

    return tools

search_tools = create_multi_search_tools()


# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('app.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_text = request.form.get('message', '').strip()
    image_files = request.files.getlist('images')  # Handles up to 10 images

    if not user_text and not image_files:
        return jsonify({"error": "No message or image provided."}), 400

    if len(image_files) > 10:
        return jsonify({"error": "Maximum of 10 images allowed per request."}), 400

    # 1. Fetch web search context if query text exists
    fetched_context = ""
    if user_text and search_tools:
        try:
            for tool in search_tools:
                result = tool.func(user_text)
                if result:
                    fetched_context += f"\n--- Source ({tool.name}) ---\n{result}\n"
        except Exception as e:
            fetched_context = f"Search tool issue: {str(e)}"

    # 2. System Instructions
    system_instruction = (
        "You are an exceptionally intelligent, concise, and direct AI assistant powered by gpt-4.1-mini.\n"
        "1. When provided with image(s), IMMEDIATELY solve, answer, or analyze their content directly. Do NOT describe what the images look like.\n"
        "2. Cross-reference all fetched search data below to ensure maximum accuracy."
    )

    if fetched_context:
        system_instruction += f"\n\n[FETCHED MULTI-SOURCE SEARCH CONTEXT]\n{fetched_context}\n[END CONTEXT]"

    # 3. Construct OpenAI user payload
    user_content = []

    if user_text:
        user_content.append({"type": "text", "text": user_text})
    elif image_files:
        user_content.append({"type": "text", "text": "Directly solve or answer whatever is shown in the provided image(s)."})

    # Convert up to 10 uploaded image files to Base64
    for img_file in image_files:
        if img_file and img_file.filename != '':
            image_bytes = img_file.read()
            mime_type = img_file.content_type or 'image/jpeg'
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

    # 4. Request response from OpenAI
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
