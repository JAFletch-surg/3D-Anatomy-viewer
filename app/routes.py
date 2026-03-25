import os
import uuid
import tempfile
import logging
from datetime import timedelta
from flask import Blueprint, render_template, request, jsonify, current_app, send_from_directory, redirect, url_for, make_response
from werkzeug.utils import secure_filename
from app.model_processor import process_segmentation
from app import database as db
import threading

logger = logging.getLogger(__name__)

main = Blueprint('main', __name__)

processing_status = {}

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}


# --- GCS helpers ---

def get_gcs_bucket():
    """Return GCS bucket name if configured, else None."""
    return os.environ.get('GCS_BUCKET')


def get_storage_client():
    from google.cloud import storage
    return storage.Client()


def gcs_upload_blob(local_path, blob_path):
    """Upload a local file to GCS."""
    bucket_name = get_gcs_bucket()
    if not bucket_name:
        return
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(local_path)
    logger.info(f"Uploaded {local_path} to gs://{bucket_name}/{blob_path}")


def gcs_download_blob(blob_path, local_path):
    """Download a GCS blob to a local file."""
    bucket_name = get_gcs_bucket()
    if not bucket_name:
        return
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
    logger.info(f"Downloaded gs://{bucket_name}/{blob_path} to {local_path}")


def gcs_delete_blob(blob_path):
    """Delete a blob from GCS."""
    bucket_name = get_gcs_bucket()
    if not bucket_name:
        return
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        bucket.blob(blob_path).delete()
    except Exception as e:
        logger.warning(f"Failed to delete gs://{bucket_name}/{blob_path}: {e}")


def gcs_signed_url(blob_path, method="GET", content_type=None, expiration_minutes=60):
    """Generate a v4 signed URL for a GCS blob."""
    bucket_name = get_gcs_bucket()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    kwargs = {
        'version': 'v4',
        'expiration': timedelta(minutes=expiration_minutes),
        'method': method,
    }
    if content_type and method == 'PUT':
        kwargs['content_type'] = content_type

    return blob.generate_signed_url(**kwargs)


def get_file_url(filename):
    """Return a URL for serving a file — signed GCS URL or local path."""
    if get_gcs_bucket() and filename:
        blob_path = f"uploads/{filename}"
        return gcs_signed_url(blob_path, method="GET", expiration_minutes=120)
    return f"/static/uploads/{filename}"


# --- Auth helpers ---

def get_user_id():
    return request.cookies.get('user_id')


def ensure_user_id(response):
    if not request.cookies.get('user_id'):
        response.set_cookie('user_id', str(uuid.uuid4())[:12], max_age=365 * 24 * 3600, httponly=True, samesite='Lax')
    return response


# --- File validation ---

def allowed_nifti(filename):
    name = filename.lower()
    return name.endswith('.nii') or name.endswith('.nii.gz')


def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS


def save_nifti_file(file_obj, case_id, prefix='seg'):
    """Save a NIfTI file locally (and to GCS if configured)."""
    original = file_obj.filename
    ext = '.nii.gz' if original.lower().endswith('.nii.gz') else '.nii'
    safe_name = f"case_{case_id}_{prefix}{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_name)
    file_obj.save(filepath)
    # Also upload to GCS if configured
    if get_gcs_bucket():
        gcs_upload_blob(filepath, f"uploads/{safe_name}")
    return safe_name, filepath


# --- Signed URL endpoint ---

@main.route('/get-upload-url', methods=['POST'])
def get_upload_url():
    """Generate a signed URL for direct browser-to-GCS upload."""
    bucket_name = get_gcs_bucket()
    if not bucket_name:
        return jsonify({'error': 'Cloud storage not configured. Use standard upload.'}), 400

    data = request.get_json()
    filename = data.get('filename', '')
    content_type = data.get('content_type', 'application/octet-stream')
    case_id = data.get('case_id', '')

    if not filename or not case_id:
        return jsonify({'error': 'filename and case_id required'}), 400

    # Build safe blob path
    safe_name = secure_filename(filename)
    blob_path = f"uploads/case_{case_id}_{safe_name}"

    signed_url = gcs_signed_url(blob_path, method="PUT", content_type=content_type, expiration_minutes=15)

    return jsonify({
        'signed_url': signed_url,
        'blob_path': blob_path,
        'filename': f"case_{case_id}_{safe_name}",
    })


@main.route('/cases/<case_id>/upload-complete', methods=['POST'])
def upload_complete(case_id):
    """Called after frontend uploads directly to GCS."""
    case = db.get_case(case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404

    data = request.get_json()
    blob_path = data.get('blob_path', '')
    file_type = data.get('file_type', '')
    filename = data.get('filename', '')

    if not blob_path or not file_type:
        return jsonify({'error': 'blob_path and file_type required'}), 400

    if file_type == 'scan':
        db.update_case(case_id, nifti_filename=filename, status='processing')
        processing_status[filename] = {'status': 'processing', 'progress': 0, 'output_file': None}
        thread = threading.Thread(target=process_model_from_gcs, args=(blob_path, filename, case_id))
        thread.start()
    elif file_type == 'ct':
        db.update_case(case_id, ct_filename=filename)
    elif file_type == 'video':
        db.update_case(case_id, video_filename=filename)

    return jsonify({'success': True})


def process_model_from_gcs(blob_path, filename, case_id):
    """Download NIfTI from GCS, process to GLB, upload GLB back to GCS."""
    try:
        # Download to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            local_nifti = os.path.join(tmpdir, filename)
            gcs_download_blob(blob_path, local_nifti)

            # Process
            output_file = process_segmentation(local_nifti)
            output_basename = os.path.basename(output_file)

            # Upload GLB to GCS
            gcs_upload_blob(output_file, f"uploads/{output_basename}")

            # Also copy to local uploads for serving (fallback)
            local_dest = os.path.join(os.environ.get('UPLOAD_FOLDER', 'app/static/uploads'), output_basename)
            if not os.path.exists(local_dest):
                import shutil
                shutil.copy2(output_file, local_dest)

        processing_status[filename] = {
            'status': 'complete',
            'progress': 100,
            'output_file': output_basename
        }
        db.update_case(case_id, glb_filename=output_basename, status='complete')

    except Exception as e:
        logger.error(f"GCS processing error: {e}")
        processing_status[filename] = {
            'status': 'error',
            'progress': 0,
            'error': str(e)
        }
        db.update_case(case_id, status='error')


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

        # Accept both JSON and form data
        if request.is_json:
            data = request.get_json()
            title = data.get('title', '').strip()
            patient_id = data.get('patient_id', '').strip()
            notes = data.get('notes', '').strip()
        else:
            title = request.form.get('title', '').strip()
            patient_id = request.form.get('patient_id', '').strip()
            notes = request.form.get('notes', '').strip()

        if not title:
            return jsonify({'error': 'Case title is required'}), 400

        case_id = db.create_case(user_id, title, patient_id, notes)

        # If JSON request, return case_id for JS upload flow
        if request.is_json:
            return jsonify({'success': True, 'case_id': case_id})

        # Legacy form submit with files (for local dev / small files)
        if 'scan_file' in request.files:
            scan_file = request.files['scan_file']
            if scan_file.filename and allowed_nifti(scan_file.filename):
                filename, filepath = save_nifti_file(scan_file, case_id, 'seg')
                db.update_case(case_id, nifti_filename=filename, status='processing')
                processing_status[filename] = {'status': 'processing', 'progress': 0, 'output_file': None}
                thread = threading.Thread(target=process_model, args=(filepath, filename, case_id))
                thread.start()

        if 'ct_file' in request.files:
            ct_file = request.files['ct_file']
            if ct_file.filename and allowed_nifti(ct_file.filename):
                ct_name, _ = save_nifti_file(ct_file, case_id, 'ct')
                db.update_case(case_id, ct_filename=ct_name)

        if 'video_file' in request.files:
            video_file = request.files['video_file']
            if video_file.filename and allowed_video(video_file.filename):
                ext = video_file.filename.rsplit('.', 1)[1].lower()
                video_name = secure_filename(f"case_{case_id}_video.{ext}")
                video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], video_name)
                video_file.save(video_path)
                if get_gcs_bucket():
                    gcs_upload_blob(video_path, f"uploads/{video_name}")
                db.update_case(case_id, video_filename=video_name)

        return redirect(url_for('main.case_detail', case_id=case_id))

    response = make_response(render_template('case_new.html', gcs_enabled=bool(get_gcs_bucket())))
    return ensure_user_id(response)


@main.route('/cases/<case_id>')
def case_detail(case_id):
    case = db.get_case(case_id)
    if not case:
        return redirect(url_for('main.index'))
    # Generate signed URLs for file serving if GCS enabled
    file_urls = {}
    if get_gcs_bucket():
        for key in ['glb_filename', 'ct_filename', 'nifti_filename', 'video_filename', 'thumbnail']:
            fname = case.get(key)
            if fname:
                file_urls[key] = get_file_url(fname)
    response = make_response(render_template('case_detail.html', case=case, file_urls=file_urls, gcs_enabled=bool(get_gcs_bucket())))
    return ensure_user_id(response)


@main.route('/cases/<case_id>/delete', methods=['POST'])
def delete_case(case_id):
    case = db.get_case(case_id)
    if case:
        for fname in [case.get('nifti_filename'), case.get('glb_filename'),
                       case.get('ct_filename'), case.get('video_filename'), case.get('thumbnail')]:
            if fname:
                # Delete local
                fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
                if os.path.exists(fpath):
                    os.remove(fpath)
                # Delete from GCS
                gcs_delete_blob(f"uploads/{fname}")
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
        return jsonify({'error': 'Invalid video format'}), 400
    ext = video_file.filename.rsplit('.', 1)[1].lower()
    video_name = secure_filename(f"case_{case_id}_video.{ext}")
    video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], video_name)
    video_file.save(video_path)
    if get_gcs_bucket():
        gcs_upload_blob(video_path, f"uploads/{video_name}")
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


@main.route('/cases/<case_id>/save-thumbnail', methods=['POST'])
def save_thumbnail(case_id):
    case = db.get_case(case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    if 'thumbnail' not in request.files:
        return jsonify({'error': 'No thumbnail'}), 400
    thumb = request.files['thumbnail']
    thumb_name = f"case_{case_id}_thumb.png"
    thumb_path = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_name)
    thumb.save(thumb_path)
    if get_gcs_bucket():
        gcs_upload_blob(thumb_path, f"uploads/{thumb_name}")
    db.update_case(case_id, thumbnail=thumb_name)
    return jsonify({'success': True})


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
            # Upload GLB to GCS if configured
            if get_gcs_bucket():
                gcs_upload_blob(output_file, f"uploads/{output_basename}")
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
    case_id = ''
    case = None
    if filename.startswith('case_'):
        case_id = filename.replace('case_', '').split('_')[0]
        case = db.get_case(case_id)
    file_url = get_file_url(filename) if get_gcs_bucket() else f"/static/uploads/{filename}"
    return render_template('viewer.html', model_filename=filename, case_id=case_id, case=case, file_url=file_url)


@main.route('/ct-viewer/<filename>')
def ct_viewer(filename):
    seg_filename = ''
    case = None
    if filename.startswith('case_'):
        case_id = filename.replace('case_', '').split('_')[0]
        case = db.get_case(case_id)
        if case and case.get('nifti_filename'):
            seg_filename = case['nifti_filename']
    ct_url = get_file_url(filename) if get_gcs_bucket() else f"/static/uploads/{filename}"
    seg_url = get_file_url(seg_filename) if (get_gcs_bucket() and seg_filename) else (f"/static/uploads/{seg_filename}" if seg_filename else '')
    return render_template('ct_viewer.html', ct_filename=filename, seg_filename=seg_filename, case=case, ct_url=ct_url, seg_url=seg_url)


@main.route('/split/<case_id>')
def split_view(case_id):
    case = db.get_case(case_id)
    if not case:
        return redirect(url_for('main.index'))
    mode = request.args.get('mode', 'ct-3d')
    return render_template('split_view.html', case=case, mode=mode)


# --- File serving (local fallback + GCS signed URL redirect) ---

@main.route('/static/uploads/<filename>')
def serve_uploaded_file(filename):
    if get_gcs_bucket():
        # Redirect to signed GCS URL
        signed = get_file_url(filename)
        return redirect(signed)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@main.route('/models/<filename>')
def serve_model_file(filename):
    if get_gcs_bucket():
        signed = get_file_url(filename)
        return redirect(signed)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@main.route('/health')
def health_check():
    return {'status': 'healthy', 'gcs': bool(get_gcs_bucket())}, 200
