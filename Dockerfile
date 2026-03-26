FROM python:3.10-slim

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1

# 1. Install pip dependencies first (using requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy only setup.py and the LGTV/ package directory to install the CLI command
# This avoids re-installing if only webui.py or static/ files change
COPY setup.py .
COPY LGTV/ LGTV/
RUN pip install --no-cache-dir .

# 3. Copy the rest of the application files
COPY webui.py .
COPY static/ static/
COPY templates/ templates/

# Create config directory for persistence
RUN mkdir -p /etc/lgtv

# Expose the port the app runs on
EXPOSE 8000

# Run the application
CMD ["python", "webui.py"]
