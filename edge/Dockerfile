FROM python:3.11-slim

WORKDIR /app

# Install MQTT client + HTTP client
RUN pip install --no-cache-dir paho-mqtt httpx python-dotenv

COPY . .

RUN mkdir -p /app/buffer

# Run both sensor simulator and gateway
CMD ["python", "-m", "edge.pi_gateway"]
