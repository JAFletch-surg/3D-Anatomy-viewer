import os
import uuid
from flask import Blueprint, render_template, request, jsonify, current_app, send_from_directory, redirect, url_for, make_response
from werkzeug.utils import secure_filename
from app.model_processor import process_segmentation
from app import database as db
import threading

main = Blueprint('main', __name__)

processing_status = {}

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}


def get_user_id():
    return request.cookies.get('user_id')


def ensure_user_id(response):
    if not request.cookies.get('user_id'):
        response.set_cookie('user_id', str(uuid.uuid4())[:12], max_age=365 * 24 * 3600, httponly=True, samesite='Lax')
    return response


def allowed_nifti(filename):
    """Check if filename is a valid NIfTI file (.nii or .nii.gz)."""
    name = filename.lower()
    return name.endswith('.nii') or name.endswith('.nii.gz')


def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS


def save_nifti_file(file_obj, case_id, prefix='seg'):
    """Save a NIfTI file preserving the .nii.gz extension properly."""
    original = file_obj.filename
    # Build a clean filename preserving compound extension
    if original.lower().endswith('.nii.gz'):
        ext = '.nii.gz'
    else:
        ext = '.nii'
    safe_name = f"case_{case_id}_{prefix}{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_name)
    file_obj.save(filepath)
    return safe_name, filepath


# --- Dashboard / Case Library ---

@main.route('/')
def index():
    user_id = get_user_id()
    cases = db.get_cases_for_user(user_id) if user_id else []
    response = make_response(render_template('dashboard.html', cases=cases))
    return ensure_user_id(response)


@main.route('/cases/new', methods=['GET', 'POST'])
def new_case():
    if request.method == 'POST':
        user_id = get_user_id()
        if not user_id:
            return jsonify({'error': 'Session error'}), 400

        title = request.form.get('title', '').strip()
        patient_id = request.form.get('patient_id', '').strip()
        notes = request.form.get('notes', '').strip()

        if not title:
            return jsonify({'error': 'Case title is required'}), 400

        case_id = db.create_case(user_id, title, patient_id, notes)

        # Handle segmentation file upload
        if 'scan_file' in request.files:
            scan_file = request.files['scan_file']
            if scan_file.filename and allowed_nifti(scan_file.filename):
                filename, filepath = save_nifti_file(scan_file, case_id, 'seg')
                db.update_case(case_id, nifti_filename=filename, status='processing')
                processing_status[filename] = {'status': 'processing', 'progress': 0, 'output_file': None}
                thread = threading.Thread(target=process_model, args=(filepath, filename, case_id))
                thread.start()

        # Handle CT scan upload
        if 'ct_file' in request.files:
            ct_file = request.files['ct_file']
            if ct_file.filename and allowed_nifti(ct_file.filename):
                ct_name, _ = save_nifti_file(ct_file, case_id, 'ct')
                db.update_case(case_id, ct_filename=ct_name)

        # Handle video upload
        if 'video_file' in request.files:
            video_file = request.files['video_file']
            if video_file.filename and allowed_video(video_file.filename):
                ext = video_file.filename.rsplit('.', 1)[1].lower()
                video_name = secure_filename(f"case_{case_id}_video.{ext}")
                video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], video_name)
                video_file.save(video_path)
                db.update_case(case_id, video_filename=video_name)

        return redirect(url_for('main.case_detail', case_id=case_id))

    response = make_response(render_template('case_new.html'))
    return ensure_user_id(response)


@main.route('/cases/<case_id>')
def case_detail(case_id):
    case = db.get_case(case_id)
    if not case:
        return redirect(url_for('main.index'))
    response = make_response(render_template('case_detail.html', case=case))
    return ensure_user_id(response)


@main.route('/cases/<case_id>/delete', methods=['POST'])
def delete_case(case_id):
    case = db.get_case(case_id)
    if case:
        for fname in [case.get('nifti_filename'), case.get('glb_filename'),
                       case.get('ct_filename'), case.get('video_filename')]:
            if fname:
                fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
                if os.path.exists(fpath):
                    os.remove(fpath)
        db.delete_case(case_id)
    return redirect(url_for('main.index'))


@main.route('/cases/<case_id>/upload-video', methods=['POST'])
def upload_video(case_id):
    case = db.get_case(case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    if 'video_file' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    video_file = request.files['video_file']
    if not video_file.filename or not allowed_video(video_file.filename):
        return jsonify({'error': 'Invalid video format. Use MP4, WebM, MOV, or AVI'}), 400
    ext = video_file.filename.rsplit('.', 1)[1].lower()
    video_name = secure_filename(f"case_{case_id}_video.{ext}")
    video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], video_name)
    video_file.save(video_path)
    db.update_case(case_id, video_filename=video_name)
    return jsonify({'success': True, 'filename': video_name})


@main.route('/cases/<case_id>/upload-scan', methods=['POST'])
def upload_scan(case_id):
    case = db.get_case(case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    if 'scan_file' not in request.files:
        return jsonify({'error': 'No scan file'}), 400
    scan_file = request.files['scan_file']
    if not scan_file.filename or not allowed_nifti(scan_file.filename):
        return jsonify({'error': 'Invalid file. Use .nii or .nii.gz'}), 400
    filename, filepath = save_nifti_file(scan_file, case_id, 'seg')
    db.update_case(case_id, nifti_filename=filename, status='processing')
    processing_status[filename] = {'status': 'processing', 'progress': 0, 'output_file': None}
    thread = threading.Thread(target=process_model, args=(filepath, filename, case_id))
    thread.start()
    return jsonify({'success': True, 'filename': filename})


@main.route('/cases/<case_id>/upload-ct', methods=['POST'])
def upload_ct(case_id):
    case = db.get_case(case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    if 'ct_file' not in request.files:
        return jsonify({'error': 'No CT file'}), 400
    ct_file = request.files['ct_file']
    if not ct_file.filename or not allowed_nifti(ct_file.filename):
        return jsonify({'error': 'Invalid file. Use .nii or .nii.gz'}), 400
    ct_name, _ = save_nifti_file(ct_file, case_id, 'ct')
    db.update_case(case_id, ct_filename=ct_name)
    return jsonify({'success': True, 'filename': ct_name})


# --- Legacy upload endpoint ---

@main.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_nifti(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        processing_status[filename] = {'status': 'processing', 'progress': 0, 'output_file': None}
        thread = threading.Thread(target=process_model, args=(filepath, filename, None))
        thread.start()
        return jsonify({'message': 'File uploaded successfully', 'filename': filename})
    return jsonify({'error': 'Invalid file type. Use .nii or .nii.gz'}), 400


def process_model(filepath, filename, case_id=None):
    try:
        output_file = process_segmentation(filepath)
        output_basename = os.path.basename(output_file)
        processing_status[filename] = {
            'status': 'complete',
            'progress': 100,
            'output_file': output_basename
        }
        if case_id:
            db.update_case(case_id, glb_filename=output_basename, status='complete')
    except Exception as e:
        processing_status[filename] = {
            'status': 'error',
            'progress': 0,
            'error': str(e)
        }
        if case_id:
            db.update_case(case_id, status='error')


@main.route('/status/<filename>')
def get_status(filename):
    return jsonify(processing_status.get(filename, {'status': 'not_found'}))


@main.route('/viewer/<filename>')
def viewer(filename):
    return render_template('viewer.html', model_filename=filename)


@main.route('/ct-viewer/<filename>')
def ct_viewer(filename):
    return render_template('ct_viewer.html', ct_filename=filename)


@main.route('/static/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@main.route('/models/<filename>')
def serve_model_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@main.route('/health')
def health_check():
    return {'status': 'healthy'}, 200
