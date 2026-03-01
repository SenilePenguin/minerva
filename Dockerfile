FROM python:3.13-alpine

# Install apk dependencies
RUN apk add --no-cache aria2 ca-certificates curl

# Install Python dependencies
RUN pip install httpx rich click --no-cache-dir

# Setup directories and files. Deletes temp files in case it's been a while and they are stale/no longer assigned.
WORKDIR /app
RUN rm /root/.minerva-dpn/tmp
RUN wget https://minerva-archive.org/worker/download -O minerva.py

# Copy entrypoint wrapper
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create state directory
RUN mkdir -p /root/.minerva-dpn

ENTRYPOINT ["/entrypoint.sh"]
CMD ["run", "-c", "5", "-b", "20"]
