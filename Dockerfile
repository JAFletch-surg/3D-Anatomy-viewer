# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (this helps with Docker caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Create necessary directories
RUN mkdir -p app/static/uploads app/static/models

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Set environment variables
ENV FLASK_APP=run.py
ENV PYTHONPATH=/app
ENV SECRET_KEY=production-secret-key-change-this
ENV PORT=8080

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "run:app"]