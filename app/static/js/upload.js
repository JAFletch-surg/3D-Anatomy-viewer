document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const uploadButton = document.getElementById('uploadButton');
    const progressContainer = document.getElementById('progressContainer');
    const successContainer = document.getElementById('successContainer');
    const errorContainer = document.getElementById('errorContainer');
    const progressBar = document.getElementById('progressBar');
    const progressStatus = document.getElementById('progressStatus');
    const progressPercentage = document.getElementById('progressPercentage');
    const viewerButton = document.getElementById('viewerButton');
    const errorMessage = document.getElementById('errorMessage');
    const retryButton = document.getElementById('retryButton');
    const removeFileButton = document.getElementById('removeFile');

    let statusCheckInterval;

    // File input change handler
    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            handleFileSelection(file);
        }
    });

    // Remove file button
    if (removeFileButton) {
        removeFileButton.addEventListener('click', function() {
            clearFileSelection();
        });
    }

    // Retry button
    if (retryButton) {
        retryButton.addEventListener('click', function() {
            hideAllContainers();
            uploadButton.disabled = false;
        });
    }

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const file = fileInput.files[0];
        if (!file) {
            showError('Please select a file first');
            return;
        }

        await uploadFile(file);
    });

    function handleFileSelection(file) {
        // Validate file
        if (!validateFile(file)) {
            return;
        }

        // Update UI
        fileName.textContent = file.name;
        fileInfo.classList.remove('hidden');
        uploadButton.disabled = false;
        hideAllContainers();
    }

    function validateFile(file) {
        // Check file type
        const allowedTypes = ['.nii', '.nii.gz'];
        const isValidType = allowedTypes.some(type => file.name.toLowerCase().endsWith(type));
        
        if (!isValidType) {
            showError('Invalid file format. Please upload .nii or .nii.gz files only');
            return false;
        }
        
        // Check file size (500MB limit)
        const maxSize = 500 * 1024 * 1024;
        if (file.size > maxSize) {
            showError('File size exceeds 500MB limit');
            return false;
        }
        
        return true;
    }

    function clearFileSelection() {
        fileInput.value = '';
        fileInfo.classList.add('hidden');
        uploadButton.disabled = true;
        hideAllContainers();
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        // Show progress container
        showProgressContainer();
        uploadButton.disabled = true;

        // Reset progress
        updateProgress(0);
        progressStatus.textContent = 'Uploading file...';

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                console.log('Upload successful:', data);
                progressStatus.textContent = 'File uploaded, starting processing...';
                updateProgress(25);
                
                // Start checking processing status
                checkStatus(data.filename);
            } else {
                throw new Error(data.error || 'Upload failed');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showError(error.message);
        }
    }

    function checkStatus(filename) {
        console.log('Starting status check for:', filename);
        clearInterval(statusCheckInterval);
        
        statusCheckInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${filename}`);
                const data = await response.json();
                
                console.log('Status update:', data);

                if (data.status === 'complete') {
                    clearInterval(statusCheckInterval);
                    handleProcessingComplete(data);
                    
                } else if (data.status === 'error') {
                    clearInterval(statusCheckInterval);
                    showError(data.error || 'Processing failed');
                    
                } else if (data.status === 'processing') {
                    // Update progress
                    const progress = data.progress || 50;
                    updateProgress(progress);
                    progressStatus.textContent = data.message || 'Processing file...';
                }
                
            } catch (error) {
                console.error('Status check error:', error);
                clearInterval(statusCheckInterval);
                showError('Error checking processing status');
            }
        }, 1000);
    }

    function handleProcessingComplete(data) {
        console.log('Processing complete:', data);
        
        // Update progress to 100%
        updateProgress(100);
        progressStatus.textContent = 'Processing complete!';
        
        // Wait a moment, then show success
        setTimeout(() => {
            hideAllContainers();
            showSuccessContainer();
            
            // Set the viewer button link
            const viewerLink = viewerButton.querySelector('a');
            if (viewerLink && data.output_file) {
                // Create the correct viewer URL
                const viewerUrl = `/viewer/${data.output_file}`;
                viewerLink.href = viewerUrl;
                console.log('Viewer URL set to:', viewerUrl);
                
                // Show success notification if available
                if (window.showSuccess) {
                    window.showSuccess('3D model generated successfully!');
                }
            } else {
                console.error('No output_file in response or viewerButton not found');
                showError('Model processed but viewer link unavailable');
            }
        }, 1000);
    }

    function updateProgress(percentage) {
        const clampedPercentage = Math.min(Math.max(percentage, 0), 100);
        
        if (progressBar) {
            progressBar.style.width = `${clampedPercentage}%`;
        }
        
        if (progressPercentage) {
            progressPercentage.textContent = `${Math.round(clampedPercentage)}%`;
        }
    }

    function showProgressContainer() {
        hideAllContainers();
        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }
    }

    function showSuccessContainer() {
        hideAllContainers();
        if (successContainer) {
            successContainer.classList.remove('hidden');
        }
    }

    function showErrorContainer() {
        hideAllContainers();
        if (errorContainer) {
            errorContainer.classList.remove('hidden');
        }
    }

    function hideAllContainers() {
        [progressContainer, successContainer, errorContainer].forEach(container => {
            if (container) container.classList.add('hidden');
        });
    }

    function showError(message) {
        console.error('Error:', message);
        
        if (errorMessage) {
            errorMessage.textContent = message;
        }
        
        showErrorContainer();
        uploadButton.disabled = false;
        
        // Show error notification if available
        if (window.showError) {
            window.showError(message);
        }
    }

    // Enhanced drag and drop
    const dropZone = document.querySelector('label');
    
    if (dropZone) {
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        // Highlight drop zone when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        // Handle dropped files
        dropZone.addEventListener('drop', handleDrop, false);
    }

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight(e) {
        dropZone.classList.add('border-blue-500', 'bg-blue-100');
    }

    function unhighlight(e) {
        dropZone.classList.remove('border-blue-500', 'bg-blue-100');
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            const file = files[0];
            fileInput.files = files;
            handleFileSelection(file);
        }
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        if (statusCheckInterval) {
            clearInterval(statusCheckInterval);
        }
    });

    console.log('Upload interface initialized successfully');
});