FROM python:3.11-slim

WORKDIR /app

# Install Icarus Verilog for RTL compilation and simulation
RUN apt-get update \
    && apt-get install -y --no-install-recommends iverilog \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app ./app
COPY frontend ./frontend

# Runtime configuration
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.api.server:app --host 0.0.0.0 --port ${PORT}"]
