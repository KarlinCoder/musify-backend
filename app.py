# app.py
from flask import Flask
from flask_cors import CORS
from routes.download import download_song_bp
from routes.download_album import download_album_bp
import os

# Inicializar Flask
app = Flask(__name__)
CORS(app)

app.register_blueprint(download_song_bp, url_prefix='/download-song')
app.register_blueprint(download_album_bp, url_prefix='/download-album')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)