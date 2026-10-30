# Use a lightweight Python image based on Linux.
FROM python:3.12-slim

# Set the working directory inside the container.
WORKDIR /app

# Prevent Python from creating unnecessary bytecode files.
ENV PYTHONDONTWRITEBYTECODE=1

# Display Python logs immediately without output buffering.
ENV PYTHONUNBUFFERED=1

# Configure the persistent JSON data file location.
ENV KV_DATA_FILE=/data/kv_data.json

# Configure the operation log file location.
ENV KV_LOG_FILE=/data/kv_operations.log

# Check for modified records every two seconds.
ENV KV_SAVE_INTERVAL=2

# Configure the HTTP server port.
ENV PORT=8080

# Copy the dependency file before the application code.
# This allows Docker to cache dependency installation.
COPY requirements.txt ./

# Install packages without retaining the pip download cache.
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy the asynchronous Key-Value Store application.
COPY app.py ./

# Create a directory for persistent data and logs.
# A named Docker volume will be mounted here at runtime.
RUN mkdir -p /data

# Document the HTTP port used by the application.
EXPOSE 8080

# Start the asynchronous HTTP server.
CMD ["python", "app.py"]