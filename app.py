import os
import base64
import json
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# LangChain Search Engines
from duckduckgo_search import DDGS
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import Tool

app = Flask(__name__)

# Payload limits up to 32MB for handling up to 10 high-res images
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

api_key = os.environ.get("OPENAI_API_KEY")
serpapi_key = os.environ.get("SERPAPI_API_KEY")
client = OpenAI(api_key=api_key)


# ==========================================
# ADVANCED SEARCH ENGINE & IMAGE FINDER
# ==========================================
def perform_image_and_product_search(query):
    """
    Searches for live web images, stock photography, shopping URLs, and absolute web links.
    """
    search_results = {
        "images": [],
        "shopping_urls": [],
        "stock_urls": [],
        "web_urls": []
    }

    # 1. DuckDuckGo Image & Web Search (Free, no key required)
    try:
        with DDGS() as ddgs:
            # Fetch Images
            img_results = list(ddgs.images(keywords=query, max_results=6))
            for img in img_results:
                search_results["images"].append({
                    "title": img.get("title", ""),
                    "image_url": img.get("image", ""),
                    "source_url": img.get("url", "")
                })

            # Fetch Web & Shopping Links
            text_results = list(ddgs.text(keywords=query, max_results=6))
            for res in text_results:
                url = res.get("href", "")
                title = res.get("title", "")
                body = res.get("body", "").lower()

                # Categorize into Shopping, Stock, or Web URLs
                if any(k in url.lower() or k in body for k in ["shop", "buy", "store", "amazon", "ebay", "etsy", "price"]):
                    search_results["shopping_urls"].append({"title": title, "url": url})
                elif any(k in url.lower() or k in body for k in ["shutterstock", "getty", "unsplash", "stock", "freepik", "adobe"]):
                    search_results["stock_urls"].append({"title": title, "url": url})
                else:
                    search_results["web_urls"].append({"title": title, "url": url})
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")

    # 2. SerpApi Google Images/Shopping (Optional backup if key is available)
    if serpapi_key:
        try:
            from serpapi import GoogleSearch
            # Google Images
            params = {"engine": "google_images", "q": query, "api_key": serpapi_key, "num": 5}
            serp_img = GoogleSearch(params).get_dict().get("images_results", [])
            for item in serp_img:
                search_results["images"].append({
                    "title": item.get("title", ""),
                    "image_url": item.get("original", ""),
                    "source_url": item.get("link", "")
                })

            # Google Shopping
            shop_params = {"engine": "google_shopping", "q": query, "api_key": serpapi_key, "num": 4}
            serp_shop = GoogleSearch(shop_params).get_dict().get("shopping_results", [])
            for item in serp_shop:
                search_results["shopping_urls"].append({
                    "title": item.get("title", "Shop Item"),
                    "url": item.get("link", "")
                })
        except Exception as e:
            print(f"SerpApi error: {e}")

    return search_results


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

    # 1. Detect if the user wants images, stock photos, or product recommendations
    search_data = None
    query_lower = user_text.lower()
    triggers = ["show me", "picture of", "photo of", "image of", "find me", "buy", "stock photo", "where to get", "look like"]

    if user_text and any(trigger in query_lower for trigger in triggers):
        search_data = perform_image_and_product_search(user_text)

    # 2. System Instructions
    system_instruction = (
        "You are an exceptionally intelligent, concise, and direct AI assistant.\n"
        "1. When asked for pictures, photos, shopping options, or stock links, acknowledge the query directly and summarize what you found.\n"
        "2. Cross-reference provided search data to suggest absolute URLs for shopping, stock photos, and official web references.\n"
        "3. Always output active markdown links `[Title](URL)` for all suggested links."
    )

    if search_data:
        system_instruction += f"\n\n[LIVE SEARCH & IMAGE DATA FOUND]\n{json.dumps(search_data, indent=2)}\n[END SEARCH DATA]"

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

        return jsonify({
            "reply": reply,
            "found_media": search_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
