import os
from flask import Blueprint, render_template, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from app.model_processor import process_segmentation
import threading

main = Blueprint('main', __name__)


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
        
        
        processing_status[filename] = {
            'status': 'processing',
            'progress': 0,
            'output_file': None
        }
        
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

# File serving routes to fix 404 errors
@main.route('/static/uploads/<filename>')
def serve_uploaded_file(filename):
    """Serve uploaded and generated files from the upload folder"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main.route('/models/<filename>')
def serve_model_file(filename):
    """Alternative route for serving model files"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# Debug routes for troubleshooting
@main.route('/test')
def test():
    return "Flask app is working! Routes are good."

@main.route('/debug')
def debug():
    import os
    template_dir = os.path.join(current_app.root_path, 'templates')
    static_dir = os.path.join(current_app.root_path, 'static')
    upload_dir = current_app.config['UPLOAD_FOLDER']
    
    template_files = os.listdir(template_dir) if os.path.exists(template_dir) else "Directory not found"
    static_files = os.listdir(static_dir) if os.path.exists(static_dir) else "Directory not found"
    upload_files = os.listdir(upload_dir) if os.path.exists(upload_dir) else "Directory not found"
    
    return f"""
    <h3>Debug Info:</h3>
    <p><strong>App root:</strong> {current_app.root_path}</p>
    <p><strong>Template dir:</strong> {template_dir}</p>
    <p><strong>Template files:</strong> {template_files}</p>
    <p><strong>Static dir:</strong> {static_dir}</p>
    <p><strong>Static files:</strong> {static_files}</p>
    <p><strong>Upload dir:</strong> {upload_dir}</p>
    <p><strong>Upload files:</strong> {upload_files}</p>
    """

@main.route('/debug-processing')
def debug_processing():
    """Show current processing status for all files"""
    return jsonify(processing_status)

@main.route('/check-upload-folder')
def check_upload_folder():
    """Check what files exist in the upload folder"""
    import os
    folder = current_app.config['UPLOAD_FOLDER']
    files = os.listdir(folder) if os.path.exists(folder) else []
    return f"Upload folder: {folder}<br>Files: {files}"


@main.route('/health')
def health_check():
    return {'status': 'healthy'}, 200