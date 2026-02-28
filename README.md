
# Minerva DPN Worker
Distributed download client for the Minerva Archive project. Volunteers download files and upload them to the central server. This image is alpine based for a small footprint.

Based on [minerva.py](https://gist.github.com/bl791/d14f8d1b27492a17fbbbadc15797cb4b) by [bl791](https://gist.github.com/bl791).


## What it does
1. Polls the Minerva server for download jobs
2. Downloads files using aria2c
3. Uploads completed files back to the server
4. Repeats

The script has been modified from it's original form to wait for the token to be added instead of exiting for convenience. It also has an unofficial patch for handling larger files. 

You will need to copy your token file manually, as the container has no browser for auth.


## Getting a token
You need a Discord auth token to connect.

**Option 1: If you've already used the script locally**
Locate your token at {home directory}/.minerva-dpn/token
 - Windows: %USERPROFILE%/.minerva-dpn/token
 - Linux: ~/.minerva-dpn/token
 - MacOS: ~/.minerva-dpn/token

**Option 2: Obtain locally without extra requirements**
```
python get-token.py
```
A browser window will open for you authenticate to Discord OAuth. It will be saved relative to the script in `.minerva-dpn/token`.


## Docker Compose
By default, docker compose will create a volume to store the token file in. You can choose to change this to a bind mount instead. An example is provided in the docker-compose file.

The token can be placed in via `docker cp` or using SCP. This is an exercise for the user.
```
docker compose up -d
```
Once the container detects the token, it will start working automatically.


## Docker (plain)
If you are not using compose, you can manually build the image locally on your server. Copy the files to a directory on your server, then `cd` to the directory.
This example assumes a bind mount, formatted for Unraid. Your environment may vary.

```
docker build -t senilepenguin/minerva .
docker run -d --name minerva --restart unless-stopped -e MINERVA_SERVER=https://minerva-archive.org -v /mnt/user/appdata/minerva:/root/.minerva-dpn senile/minerva
```

Once again, the token should be placed in the directory manually as the container cannot do auth on it's own. In this example, you would result in `/mnt/user/appdata/minerva/token`.


## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MINERVA_SERVER` | `https://minerva-archive.org` | Server URL. This was a variable in the original script, so it was kept. |