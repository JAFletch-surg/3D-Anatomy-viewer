from app import create_app

# Create the app instance at module level (needed for gunicorn)
app = create_app()

if __name__ == '__main__':
    import os
    # Get port from environment variable (Docker/cloud platforms set this)
    port = int(os.environ.get('PORT', 5000))
    # Bind to all interfaces (0.0.0.0) so Docker can access it
    app.run(host='0.0.0.0', port=port, debug=False)