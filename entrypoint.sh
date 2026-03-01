#!/bin/sh
# Entrypoint wrapper - waits for token file before starting worker

TOKEN_FILE="/root/.minerva-dpn/token"
SCRIPT_URL='https://minerva-archive.org/worker/download'

echo "Minerva DPN Worker - Container Entrypoint"
echo "=========================================="


echo "Obtaining script from $SCRIPT_URL"
wget $SCRIPT_URL -O /app/minerva.py -q
sleep 5

# Extract version from the downloaded script
VERSION=$(grep "^VERSION = " /app/minerva.py | sed "s/VERSION = '\(.*\)'/\1/")
echo "Running version: $VERSION"
echo ""

if [ ! -f "$TOKEN_FILE" ]; then
    echo ""
    echo "No token found at $TOKEN_FILE"
    echo "Waiting for token file to be created..."
    echo "   Use the 'get-token.py' script on your host machine to obtain your Discord token file."
	echo "   One obtained, copy it to your BIND or VOLUME mapping as a 'token' file."
    echo ""
	echo "Once detected, operations will automatically continue."
    while [ ! -f "$TOKEN_FILE" ]; do
        sleep 5
    done
    echo "Token found! Starting worker..."
fi

echo "Note: Due to the limitations of this minimal container, progress bars will not render."
echo "Other messages, such as acquiring jobs, completion notifications, and errors will still display."

# Run the official script with any passed arguments
exec python /app/minerva.py "$@"