# Use a lightweight Python Linux Image
FROM python:3.13-alpine

# Set the working directory inside the container
WORKDIR /app

# Configure Python and Flask for Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0

# Copy and install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the key-value store application
COPY app/ ./app/

# Document the port used by the Flask server
EXPOSE 8080

# Start the application automatically
CMD ["python", "app/server.py"]