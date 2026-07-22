import os
import tempfile
import base64
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 1. ALLOW BIGGER PAYLOADS (Prevents 413 errors when pasting large images)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# 2. SAFE UPLOAD DIRECTORY (Uses Render's writable /tmp folder)
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'app_uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# 3. ROUTE TO SERVE YOUR FRONTEND PAGE
@app.route('/')
def index():
    # Simple UI with upload input and clipboard paste listener
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Image Upload App</title>
            <style>
                body { font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; text-align: center; }
                .drop-zone { border: 2px dashed #ccc; padding: 40px; border-radius: 8px; margin-top: 20px; cursor: pointer; }
                .drop-zone:hover { border-color: #888; }
                img { max-width: 100%; height: auto; margin-top: 20px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <h2>Upload or Paste an Image</h2>
            <p>Click below to choose a file, drag & drop, or press <b>Ctrl+V / Cmd+V</b> to paste.</p>

            <div class="drop-zone" id="drop-zone">
                <input type="file" id="file-input" accept="image/*" style="display: none;">
                <p>Click or drag image here</p>
            </div>

            <div id="result"></div>

            <script>
                const fileInput = document.getElementById('file-input');
                const dropZone = document.getElementById('drop-zone');
                const resultDiv = document.getElementById('result');

                // Click box to trigger file select
                dropZone.addEventListener('click', () => fileInput.click());

                // Handle file input selection
                fileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        uploadFile(e.target.files[0]);
                    }
                });

                // Handle Clipboard Paste (Ctrl+V or Cmd+V)
                document.addEventListener('paste', (event) => {
                    const items = (event.clipboardData || window.clipboardData).items;
                    for (const item of items) {
                        if (item.type.indexOf('image') !== -1) {
                            const blob = item.getAsFile();
                            uploadFile(blob);
                            break;
                        }
                    }
                });

                // Send image to backend via relative URL '/upload'
                async function uploadFile(file) {
                    const formData = new FormData();
                    formData.append('file', file, file.name || 'pasted_image.png');

                    resultDiv.innerHTML = '<p>Uploading...</p>';

                    try {
                        const response = await fetch('/upload', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await response.json();

                        if (response.ok) {
                            resultDiv.innerHTML = `
                                <p style="color: green;"><b>Success!</b> Saved to ${data.path}</p>
                                <img src="${data.preview_url}" alt="Uploaded image" />
                            `;
                        } else {
                            resultDiv.innerHTML = `<p style="color: red;">Error: ${data.error}</p>`;
                        }
                    } catch (err) {
                        resultDiv.innerHTML = `<p style="color: red;">Upload failed. Check console for details.</p>`;
                        console.error('Upload Error:', err);
                    }
                }
            </script>
        </body>
        </html>
    ''')


# 4. ROUTE TO HANDLE FILE UPLOADS AND PASTED IMAGES
@app.route('/upload', methods=['POST'])
def upload():
    # Handle File or Pasted Image via FormData
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Save file safely to /tmp directory
            file.save(filepath)

            # Generate base64 string so frontend can immediately render preview
            file.seek(0)
            encoded_img = base64.b64encode(file.read()).decode('utf-8')
            preview_url = f"data:image/png;base64,{encoded_img}"

            return jsonify({
                "status": "success",
                "filename": filename,
                "path": filepath,
                "preview_url": preview_url
            })

    return jsonify({"error": "No file received"}), 400


# 5. START APP
if __name__ == '__main__':
    # Render assigns its own PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
