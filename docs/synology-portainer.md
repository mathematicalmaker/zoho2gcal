# Running z2g on Synology NAS with Portainer

These steps get z2g running in Docker on a Synology NAS using Portainer. Try them first; once they work for you, we can fold a short version into the main README.

## Prerequisites

- Synology NAS with Docker package installed.
- Portainer (as a Docker container or via Package Center / Docker Compose).
- The z2g image available (see “Get the image” below).
- A shared folder for z2g data (e.g. `docker/zoho2gcal`). We’ll call the path on the NAS **`/volume1/docker/zoho2gcal`**; adjust if your volume or folder name differs.

---

## 1. Get the image

You need the `zoho2gcal` image on the NAS. Two options.

**Option A – Build on your PC and push to Docker Hub**

On a machine with the repo and Docker:

```bash
cd /path/to/zoho2gcal
docker build -t YOUR_DOCKERHUB_USER/zoho2gcal:latest .
docker push YOUR_DOCKERHUB_USER/zoho2gcal:latest
```

In Portainer: **Images** → **Pull** → image: `YOUR_DOCKERHUB_USER/zoho2gcal:latest`.

**Option B – Build in Portainer from Git**

In Portainer: **Images** → **Build a new image**:

- **URL**: `https://github.com/mathematicalmaker/zoho2gcal.git`
- **Dockerfile path**: `Dockerfile` (or leave default)
- **Image name**: `zoho2gcal:latest`

Build and wait until the image appears.

---

## 2. Create the data folder on the NAS

On the Synology, create a folder for z2g data (e.g. `docker/zoho2gcal` via File Station or Control Panel → Shared Folder). You can leave it **empty**—the container will create `.env`, `secrets/`, and `secrets/private.env` from built-in examples on first run. Example files (`.env.example`, `secrets/private.env.example`) are also copied for reference.

The only file you must add before verify: your **Google client secret JSON** from GCP. Upload it as `secrets/google_client_secret.json` (create the `secrets` subfolder if needed). Or run the container once; it will create `secrets/`, then add `google_client_secret.json` and run again.

---

## 3. Run verify (no cron yet)

In Portainer:

1. **Containers** → **Add container**.
2. **Name**: e.g. `z2g`.
3. **Image**: `zoho2gcal:latest` (or `YOUR_DOCKERHUB_USER/zoho2gcal:latest`).
4. **Restart policy**: `Unless stopped` (or `No` if you prefer to start it manually).
5. **Advanced container settings**:
   - **Volumes** → **Bind**:
     - **Container**: `/data` (first column)
     - **Host**: `/volume1/docker/zoho2gcal` (or your path; second column)
   - **Env**: Do **not** set `Z2G_CRON_ENABLED` yet (no other env needed; `DATA_DIR` defaults to `/data`).
6. Do **not** set a custom command (leave empty so the image runs its default: `z2g verify`).
7. Deploy the container.

Check **Logs**. You should see either “Config OK. Zoho and Google connections and scopes verified.” or errors about missing env/files. Fix any missing env or file errors (edit `.env` and `secrets/private.env` in File Station, re-upload `secrets/google_client_secret.json` if needed), then run the container again until verify succeeds. If verify reports that `ZOHO_CALENDAR_UID` and `GOOGLE_CALENDAR_ID` are not set, that’s expected for now; set them after the next steps.

---

## 4. Complete setup (Zoho + Google)

You need to run a few one-off z2g commands with the **same** data volume. In Portainer you can do that by running a **new** container with the same bind mount and a **command** override, or by using the **Console** of an existing container.

**Zoho refresh token**

1. In Zoho API Console (Self Client) generate a one-time code.
2. In Portainer: **Containers** → **Add container** (temporary).
   - **Image**: same `zoho2gcal:latest`.
   - **Volumes**: same bind (Container `/data`, Host `/volume1/docker/zoho2gcal`).
   - **Command**: `zoho-exchange-code --code YOUR_CODE` (replace `YOUR_CODE` with the code).
3. Deploy and check **Logs** for the line `ZOHO_REFRESH_TOKEN=...`.
4. Add that line to **`secrets/private.env`** on the NAS (edit in File Station).

**Zoho calendar UID**

1. Add container again (or reuse a temporary one) with same image and volume.
2. **Command**: `list-zoho-calendars`.
3. Check logs, note the UID you want, set `ZOHO_CALENDAR_UID=...` in **`secrets/private.env`**.

**Google token (manual OAuth)**

1. Add container with same image and volume.
2. **Command**: `google-auth --manual`.
3. Enable **Interactive** and **TTY** (if Portainer offers them for this run).
4. Open the URL from the logs in a browser, authorize, then copy the **full redirect URL** from the address bar and paste it into the container’s console when prompted. The container will write **`secrets/google_token.json`** into the data folder.
5. If you can’t use interactive mode easily: start a container with command `sleep 3600`, open **Console**, then run:  
   `/app/.venv/bin/z2g google-auth --manual`  
   and paste the redirect URL when prompted.

**Google calendar ID**

1. Add container with same image and volume.
2. **Command**: `list-google-calendars`.
3. From logs, set `GOOGLE_CALENDAR_ID=...` in **`secrets/private.env`**.

**Verify again**

Run the main container again (same as in step 3). Logs should show “Config OK. Zoho and Google connections and scopes verified.” If it warns that calendar IDs are not set, make sure both `ZOHO_CALENDAR_UID` and `GOOGLE_CALENDAR_ID` are in `secrets/private.env` and try again.

---

## 5. Enable scheduled sync (cron)

When verify succeeds and both calendar IDs are set:

1. In Portainer, **Containers** → select your **z2g** container → **Duplicate/Edit** (or edit the container).
2. Under **Env**, add:
   - `Z2G_CRON_ENABLED` = `1`
3. **Redeploy** (recreate) the container.

The entrypoint will create **`crontab`** in the data folder from an example (sync every 15 minutes) if it doesn’t exist. The container will keep running and supercronic will run `z2g run` on that schedule.

To change the schedule: edit **`zoho2gcal/crontab`** on the NAS (e.g. via File Station). The file is in the repo as `docker/crontab.example`; the container copies it to `/data/crontab` on first run.

To **stop** scheduled sync: remove the env var `Z2G_CRON_ENABLED` (or set it to `0`) and recreate the container. It will fall back to “run verify and exit” on start.

---

## 6. Optional: Docker Compose stack in Portainer

If you prefer a stack (docker-compose), in Portainer: **Stacks** → **Add stack** (e.g. name `z2g`), then use the following. Adjust the host path if yours is different.

```yaml
services:
  z2g:
    image: zoho2gcal:latest
    container_name: z2g
    restart: unless-stopped
    environment:
      - Z2G_CRON_ENABLED=1
    volumes:
      - /volume1/docker/zoho2gcal:/data
```

- For **verify-only** (no cron), omit the `Z2G_CRON_ENABLED` line or set it to `0`.
- Replace `zoho2gcal:latest` with `YOUR_DOCKERHUB_USER/zoho2gcal:latest` if you use Docker Hub.

Deploy the stack. One-off commands (list-zoho-calendars, google-auth --manual, etc.) still need to be run via a separate container or console, as in step 4, using the same volume path.

---

## Troubleshooting

- **Verify fails with “Missing env”**  
  Ensure `.env` and `secrets/private.env` exist and that paths in `.env` point to `./secrets/...`. Check that the container’s volume mount is correct (container path `/data`).

- **Verify fails with “File not found: GOOGLE_CLIENT_SECRET_JSON”**  
  Ensure `secrets/google_client_secret.json` exists in the data folder and `.env` has `GOOGLE_CLIENT_SECRET_JSON=./secrets/google_client_secret.json`.

- **Sync fails after enabling cron**  
  Sync/run require `ZOHO_CALENDAR_UID` and `GOOGLE_CALENDAR_ID`. Set both in `secrets/private.env` and run verify again.

- **Path on Synology**  
  Shared folders are often under `/volume1/<SharedFolderName>`. Use **File Station** or **Control Panel** → **Shared Folder** to see the exact path, or use the path you use for other Docker bind mounts in Portainer.

Once this works for you, we can add a short “Synology / Portainer” subsection to the main README that points to this doc or inlines the essentials.
