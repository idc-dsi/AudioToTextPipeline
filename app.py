from flask import Flask, redirect, url_for, render_template, request, session, jsonify, Response
from flask_oauthlib.client import OAuth
from flask_cors import CORS
from flask_compress import Compress
from azure.storage.blob import BlobServiceClient
from urllib.parse import unquote
from werkzeug.middleware.proxy_fix import ProxyFix
from static.py.video_indexer import VideoIndexer
from dotenv import load_dotenv
import os
import sys
import jwt
import logging
import requests
import warnings
import nltk
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# Load environment variables from .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Configure persistent directory for NLTK data
nltk_data_path = os.getenv('NLTK_DATA', '/opt/render/project/.render/nltk_data')
if not os.path.exists(nltk_data_path):
    os.makedirs(nltk_data_path)

# Set NLTK data path to use the persistent directory
nltk.data.path.append(nltk_data_path)

# Download required NLTK packages if not already present
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', download_dir=nltk_data_path)

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', download_dir=nltk_data_path)

# Ignore warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Flask App Initialization
app = Flask(__name__)
Compress(app)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
app.logger = logging.getLogger(__name__)
CORS(app)

# Set up logging to stdout
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)

# Create a formatter to format the log messages (optional)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
app.logger.addHandler(handler)

# OAuth Setup
oauth = OAuth(app)
azure = oauth.remote_app(
    'azure',
    consumer_key=os.getenv('AZURE_CLIENT_ID', 'your_client_id'),  # Replace with your Azure AD Application ID
    consumer_secret=os.getenv('AZURE_CLIENT_SECRET', 'your_client_secret'),  # Replace with your Azure AD Client Secret
    request_token_params={'scope': 'openid email profile'},
    base_url='https://graph.microsoft.com/v1.0/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'your_tenant_id')}/oauth2/v2.0/token",  # Replace TENANT_ID
    authorize_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'your_tenant_id')}/oauth2/v2.0/authorize"  # Replace TENANT_ID
)

# Azure Blob Storage Setup
storage_account_name = os.getenv('AZURE_STORAGE_ACCOUNT_NAME', 'your_storage_account_name')
storage_account_key = os.getenv('AZURE_STORAGE_ACCOUNT_KEY', 'your_storage_account_key')
container_name = "dsi-nlp-models"
blob_folder = "alignment_model"
local_model_dir = "./alignment_model_local"
connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING', 'your_connection_string')

# Create the BlobServiceClient object
blob_service_client = BlobServiceClient.from_connection_string(connection_string)

# Function to download files from a specific blob folder
def download_blob_file(blob_client, download_path):
    with open(download_path, "wb") as download_file:
        download_file.write(blob_client.download_blob().readall())

# Lazy download the model files if not already present
def download_model_files():
    if not os.path.exists(local_model_dir):
        os.makedirs(local_model_dir)

    # List of files to download
    files_to_download = [
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json"
    ]

    # Download each file from Blob Storage if not already downloaded
    for file_name in files_to_download:
        download_path = os.path.join(local_model_dir, file_name)
        if not os.path.exists(download_path):
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=f"{blob_folder}/{file_name}")
            download_blob_file(blob_client, download_path)
            print(f"Downloaded {file_name} to {download_path}")
        else:
            print(f"{file_name} already exists in {local_model_dir}, skipping download.")

# Lazy load the model and tokenizer
tokenizer = None
model = None

def load_model_and_tokenizer():
    global tokenizer, model
    # Download model files if not already present
    download_model_files()

    # Load the model and tokenizer if not already loaded
    if tokenizer is None or model is None:
        tokenizer = AutoTokenizer.from_pretrained(local_model_dir, local_files_only=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(local_model_dir, local_files_only=True)
        print("Model and tokenizer loaded successfully.")

@app.route('/')
def index():
    anonymous = request.args.get('anonymous', 0)
    logged_in = session.get('logged_in', False)
    return render_template('index.html', anonymous=anonymous, logged_in=logged_in)

@app.route('/login')
def login():
    callback_url = url_for('authorized', _external=True, _scheme='https')
    #return azure.authorize(callback=callback_url)
    #Localhost
    return azure.authorize(url_for('authorized', _external=True))

@app.route('/login/authorized')
def authorized():
    response = azure.authorized_response()
    if response is None or response.get('access_token') is None:
        return 'Access Denied: Reason=%s\nError=%s' % (
            request.args['error_reason'],
            request.args['error_description']
        )

    session['azure_token'] = (response['access_token'], '')

    id_token = response.get('id_token')
    if id_token:
        # Decode the ID token
        decoded_token = jwt.decode(id_token, options={"verify_signature": False})

        # Extract the 'name'
        user_name = decoded_token.get('name')
        if user_name:
            session['username'] = user_name

    # Add the 'logged_in' query parameter to indicate successful login
    callback_url = url_for('index', logged_in=True, _scheme='https')
    #return redirect(callback_url)
    #for local host
    return redirect(url_for('index', logged_in=True))


@app.route('/load_model', methods=['POST'])
# Ensure that the model is downloaded and loaded only when needed
def load_model():
    try:
        # Call the function that loads the model and tokenizer
        load_model_and_tokenizer()
        return jsonify({'message': 'Model and tokenizer successfully loaded.'}), 200
    except Exception as e:
        # If there's an error during loading, catch it and return an error message
        return jsonify({'message': f'Error loading model: {str(e)}'}), 500



@app.route('/translate', methods=['POST'])
def translate():
    # Ensure that the model is downloaded and loaded only when needed
    load_model_and_tokenizer()

    data = request.get_json()
    text = data.get('text')

    if "\n\n" in text or "\n" in text:
        sentences = [s for s in text.splitlines() if s.strip()]
        formatted_output = []
        for sentence in sentences:
            inputs = tokenizer(sentence, return_tensors="pt", truncation=True, padding=True)
            generated_ids = model.generate(**inputs, num_beams=4, max_length=1024)
            translated_sentence = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)
            formatted_output.append(' '.join(translated_sentence))
        
        translated_text = '\n'.join(formatted_output)

    else:
        sentences = nltk.sent_tokenize(text)
        inputs = tokenizer(sentences, return_tensors="pt", truncation=True, padding=True)
        generated_ids = model.generate(**inputs, num_beams=4, max_length=1024)
        translated_sentences = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)
        translated_text = ' '.join(translated_sentences)
    
    return jsonify({'translated_text': translated_text})

@app.route('/upload', methods=['POST'])
def handle_upload():
    print("Entered /upload route")
    if 'file' not in request.files:
        print("No file part")
        return redirect(request.url)
    video_file = request.files['file']
    if video_file.filename == '':
        print("No selected file")
        return redirect(request.url)
    if video_file:
        print(video_file)
        try:
            indexer = VideoIndexer(
                subscription_key=os.getenv('VIDEO_INDEXER_SUBSCRIPTION_KEY', 'your_subscription_key'),
                account_id=os.getenv('VIDEO_INDEXER_ACCOUNT_ID', 'your_account_id'),
                location=os.getenv('VIDEO_INDEXER_LOCATION', 'your_location')
            )
            video_id = indexer.upload_video_and_get_indexed(video_file)
            return {'message': 'Video uploaded and processing started', 'videoId': video_id}, 200
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500
    else:
        return {'error': 'No file uploaded'}, 400

@app.route('/results/<video_id>', methods=['GET'])
def get_results(video_id):
    indexer = VideoIndexer(
        subscription_key=os.getenv('VIDEO_INDEXER_SUBSCRIPTION_KEY', 'your_subscription_key'),
        account_id=os.getenv('VIDEO_INDEXER_ACCOUNT_ID', 'your_account_id'),
        location=os.getenv('VIDEO_INDEXER_LOCATION', 'your_location')
    )
    try:
        results = indexer.get_video_index(video_id)
        processing_status = results.get('state', 'Processing')

        if processing_status.lower() in ['processed', 'indexed']:
            return {'results': results, 'processingComplete': True}, 200
        else:
            return {'processingComplete': False}, 202
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}, 500

@app.route('/list_files', methods=['GET'])
def list_files():
    return render_template('list_files.html')

@app.route('/list_videos', methods=['GET'])
def list_videos():
    indexer = VideoIndexer(
        subscription_key=os.getenv('VIDEO_INDEXER_SUBSCRIPTION_KEY', 'your_subscription_key'),
        account_id=os.getenv('VIDEO_INDEXER_ACCOUNT_ID', 'your_account_id'),
        location=os.getenv('VIDEO_INDEXER_LOCATION', 'your_location')
    )
    videos = indexer.list_videos()
    video_list = [{"name": video["name"], "id": video["id"]} for video in videos]
    return jsonify(video_list)

@app.route('/get_captions/<video_id>', methods=['GET'])
def get_captions(video_id):
    indexer = VideoIndexer(
        subscription_key=os.getenv('VIDEO_INDEXER_SUBSCRIPTION_KEY', 'your_subscription_key'),
        account_id=os.getenv('VIDEO_INDEXER_ACCOUNT_ID', 'your_account_id'),
        location=os.getenv('VIDEO_INDEXER_LOCATION', 'your_location')
    )
    try:
        captions = indexer.get_video_captions(video_id)
        return captions, 200
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}, 500

@app.route('/test_captions/<video_id>', methods=['GET'])
def test_captions(video_id):
    indexer = VideoIndexer(
        subscription_key=os.getenv('VIDEO_INDEXER_SUBSCRIPTION_KEY', 'your_subscription_key'),
        account_id=os.getenv('VIDEO_INDEXER_ACCOUNT_ID', 'your_account_id'),
        location=os.getenv('VIDEO_INDEXER_LOCATION', 'your_location')
    )
    try:
        captions = indexer.get_video_captions(video_id)
        return Response(captions, mimetype='text/plain; charset=utf-8')
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}, 500

@azure.tokengetter
def get_azure_oauth_token():
    return session.get('azure_token')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
