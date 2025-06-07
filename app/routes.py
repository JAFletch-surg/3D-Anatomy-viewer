import os
from flask import Blueprint, render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app.model_processor import process_segmentation
import threading

main = Blueprint('main', __name__)

# Track processing status
processing_status = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'nii', 'gz'}

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Initialize processing status
        processing_status[filename] = {
            'status': 'processing',
            'progress': 0,
            'output_file': None
        }
        
        # Start processing in background
        thread = threading.Thread(target=process_model, args=(filepath, filename))
        thread.start()
        
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename
        })
    
    return jsonify({'error': 'Invalid file type'}), 400

def process_model(filepath, filename):
    try:
        output_file = process_segmentation(filepath)
        processing_status[filename] = {
            'status': 'complete',
            'progress': 100,
            'output_file': os.path.basename(output_file)
        }
    except Exception as e:
        processing_status[filename] = {
            'status': 'error',
            'progress': 0,
            'error': str(e)
        }

@main.route('/status/<filename>')
def get_status(filename):
    return jsonify(processing_status.get(filename, {'status': 'not_found'}))

@main.route('/viewer/<filename>')
def viewer(filename):
    return render_template('viewer.html', model_filename=filename)

# app/model_processor.py
import os
from app.test_mesh import extract_transformed_mesh

def process_segmentation(filepath):
    """Wrapper for the segmentation processing function"""
    try:
        output_path = extract_transformed_mesh(filepath)
        return output_path
    except Exception as e:
        raise Exception(f"Error processing segmentation: {str(e)}")