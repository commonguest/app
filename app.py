import os
import base64
import json
import socket
from io import BytesIO
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# Image & OSINT Libraries
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from duckduckgo_search import DDGS
import whois

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


# ==========================================
# EXIF & METADATA EXTRACTION MODULE
# ==========================================
def convert_to_degrees(value):
    """Helper to convert GPS coordinates to decimal degrees."""
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None

def extract_image_exif(image_bytes):
    """Extracts raw EXIF metadata and GPS coordinates from uploaded image."""
    exif_summary = {
        "has_exif": False,
        "camera_info": {},
        "gps_coordinates": None,
        "date_taken": None
    }
    
    try:
        img = Image.open(BytesIO(image_bytes))
        exif_data = img._getexif()
        
        if not exif_data:
            return exif_summary

        exif_summary["has_exif"] = True
        raw_tags = {}
        
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            raw_tags[tag] = value

        # 1. Camera & Timestamp Info
        if "Make" in raw_tags or "Model" in raw_tags:
            exif_summary["camera_info"] = {
                "make": str(raw_tags.get("Make", "Unknown")),
                "model": str(raw_tags.get("Model", "Unknown")),
                "software": str(raw_tags.get("Software", "Unknown"))
            }
        
        exif_summary["date_taken"] = str(raw_tags.get("DateTimeOriginal", raw_tags.get("DateTime", "Unknown")))

        # 2. Extract GPS IFD
        gps_info = {}
        if "GPSInfo" in raw_tags:
            for key in raw_tags["GPSInfo"].keys():
                sub_tag = GPSTAGS.get(key, key)
                gps_info[sub_tag] = raw_tags["GPSInfo"][key]

            lat = gps_info.get("GPSLatitude")
            lat_ref = gps_info.get("GPSLatitudeRef")
            lon = gps_info.get("GPSLongitude")
            lon_ref = gps_info.get("GPSLongitudeRef")

            if lat and lon and lat_ref and lon_ref:
                lat_deg = convert_to_degrees(lat)
                lon_deg = convert_to_degrees(lon)
                
                if lat_ref != "N":
                    lat_deg = -lat_deg
                if lon_ref != "E":
                    lon_deg = -lon_deg

                exif_summary["gps_coordinates"] = {
                    "latitude": lat_deg,
                    "longitude": lon_deg,
                    "google_maps_url": f"https://www.google.com/maps?q={lat_deg},{lon_deg}"
                }

    except Exception as e:
        exif_summary["error"] = f"Failed to parse metadata: {str(e)}"

    return exif_summary


# ==========================================
# DOMAIN & WEB OSINT MODULE
# ==========================================
def perform_osint_lookup(query):
    """Performs WHOIS and public records search."""
    osint_data = {"domain_info": None, "network_info": None, "public_records": []}
    clean_query = query.strip().replace("https://", "").replace("http://", "").split("/")[0]

    if "." in clean_query and " " not in clean_query:
        try:
            domain_details = whois.whois(clean_query)
            osint_data["domain_info"] = {
                "registrar": domain_details.registrar,
                "creation_date": str(domain_details.creation_date),
                "org": domain_details.org,
                "emails": domain_details.emails
            }
        except Exception:
            pass

        try:
            osint_data["network_info"] = {"resolved_ip": socket.gethostbyname(clean_query)}
        except Exception:
            pass

    return osint_data


# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('app.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_text = request.form.get('message', '').strip()
    image_files = request.files.getlist('images')

    if not user_text and not image_files:
        return jsonify({"error": "No message or image provided."}), 400

    exif_results = []
    user_content = []

    # 1. Process Images for Visual Analysis & EXIF Metadata
    for img_file in image_files:
        if img_file and img_file.filename != '':
            image_bytes = img_file.read()
            mime_type = img_file.content_type or 'image/jpeg'
            
            # Extract EXIF metadata
            metadata = extract_image_exif(image_bytes)
            exif_results.append({"filename": img_file.filename, "metadata": metadata})

            # Base64 encode for Vision Model
            base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_encoded}"}
            })

    if user_text:
        user_content.append({"type": "text", "text": user_text})

    # 2. Check for Domain/Text OSINT Triggers
    osint_data = None
    if user_text and any(k in user_text.lower() for k in ["whois", "domain", "lookup", "investigate"]):
        osint_data = perform_osint_lookup(user_text)

    # 3. System Instructions for Visual GEOINT & Metadata Analysis
    system_instruction = (
        "You are an OSINT and GEOINT (Geographic Intelligence) analysis AI.\n"
        "1. If image EXIF metadata contains GPS coordinates, report the exact coordinates and map links.\n"
        "2. Conduct visual GEOINT on images: inspect landforms, architecture, street signage, license plate styles, electrical pole designs, and vegetation to deduce the location.\n"
        "3. Present findings structured cleanly under headings like **EXIF Metadata**, **Visual Indicators**, and **Probable Location**."
    )

    if exif_results:
        system_instruction += f"\n\n[EXTRACTED EXIF METADATA]\n{json.dumps(exif_results, indent=2)}\n[END METADATA]"
    if osint_data:
        system_instruction += f"\n\n[DOMAIN OSINT DATA]\n{json.dumps(osint_data, indent=2)}\n[END OSINT DATA]"

    api_messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=api_messages,
            max_tokens=1500,
            temperature=0.2
        )
        reply = response.choices[0].message.content

        return jsonify({
            "reply": reply,
            "exif_data": exif_results,
            "osint_data": osint_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
