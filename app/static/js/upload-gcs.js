/**
 * GCS Signed URL upload utility.
 * If the server has GCS configured, uploads go directly to GCS.
 * Otherwise falls back to standard FormData upload to Flask.
 */

async function uploadFileToCase(file, caseId, fileType, onProgress) {
    // fileType: 'scan', 'ct', or 'video'
    // First, try the signed URL path
    try {
        const urlRes = await fetch('/get-upload-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: file.name,
                content_type: file.type || 'application/octet-stream',
                case_id: caseId,
            })
        });

        if (urlRes.ok) {
            const { signed_url, blob_path, filename } = await urlRes.json();

            // Upload directly to GCS using XMLHttpRequest for progress
            await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open('PUT', signed_url);
                xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');

                xhr.upload.onprogress = function(e) {
                    if (e.lengthComputable && onProgress) {
                        onProgress(Math.round((e.loaded / e.total) * 90)); // 0-90% for upload
                    }
                };

                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve();
                    } else {
                        reject(new Error('GCS upload failed: ' + xhr.status));
                    }
                };
                xhr.onerror = () => reject(new Error('Network error during upload'));
                xhr.send(file);
            });

            if (onProgress) onProgress(95);

            // Notify Flask that upload is complete
            const notifyRes = await fetch('/cases/' + caseId + '/upload-complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ blob_path, file_type: fileType, filename })
            });

            const result = await notifyRes.json();
            if (onProgress) onProgress(100);
            return result;
        }
    } catch (e) {
        console.log('Signed URL not available, falling back to direct upload:', e.message);
    }

    // Fallback: standard FormData upload to Flask
    const formData = new FormData();
    const fieldMap = { scan: 'scan_file', ct: 'ct_file', video: 'video_file' };
    formData.append(fieldMap[fileType] || fileType, file);

    const urlMap = {
        scan: '/cases/' + caseId + '/upload-scan',
        ct: '/cases/' + caseId + '/upload-ct',
        video: '/cases/' + caseId + '/upload-video',
    };

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', urlMap[fileType]);

        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable && onProgress) {
                onProgress(Math.round((e.loaded / e.total) * 100));
            }
        };

        xhr.onload = function() {
            try {
                const data = JSON.parse(xhr.responseText);
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(data);
                } else {
                    reject(new Error(data.error || 'Upload failed'));
                }
            } catch {
                reject(new Error('Upload failed: ' + xhr.status));
            }
        };
        xhr.onerror = () => reject(new Error('Network error'));
        xhr.send(formData);
    });
}

// Export for use in templates
window.uploadFileToCase = uploadFileToCase;
