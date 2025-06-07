# CME Anatomy Viewer

A Flask-based web application for viewing 3D anatomical models from medical segmentation files.

## Features

- Upload and process NIfTI (.nii/.nii.gz) segmentation files
- Real-time progress tracking for file upload and processing
- Interactive 3D viewer with intuitive controls
- Responsive design that works on both desktop and mobile devices
- Support for multiple segmentation labels with distinct colors

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Modern web browser with WebGL support

## Installation

1. Clone the repository:
```bash
git clone [your-repository-url]
cd CME-anatomy-viewer
```

2. Create and activate a virtual environment:
```bash
# On macOS/Linux:
python3 -m venv venv
source venv/bin/activate

# On Windows:
python -m venv venv
.\venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the application:
```bash
python run.py
```

2. Open a web browser and navigate to `http://localhost:5000`

3. Upload a NIfTI segmentation file using the upload interface

4. Wait for the processing to complete

5. Click the "View 3D Model" button to interact with your 3D model

## Viewer Controls

- Left click + drag: Rotate the model
- Right click + drag: Pan the view
- Scroll wheel: Zoom in/out
- Double click: Reset camera position

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── model_processor.py
│   ├── test_mesh.py
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   ├── js/
│   │   │   ├── upload.js
│   │   │   └── viewer.js
│   │   ├── models/
│   │   └── uploads/
│   └── templates/
│       ├── base.html
│       ├── index.html
│       └── viewer.html
├── requirements.txt
└── run.py
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.