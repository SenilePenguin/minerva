FROM python:3.13-alpine

# Install aria2c for faster multi-connection downloads
RUN apk add --no-cache aria2

# Install Python dependencies
RUN pip install httpx rich click --no-cache-dir

# Copy script
COPY minerva.py /app/minerva.py
WORKDIR /app

# Create state directory
RUN mkdir -p /root/.minerva-dpn

ENTRYPOINT ["python", "minerva.py"]
CMD ["run", "-c", "5", "-b", "20", "--wait"]
