# Publishing the Docker image to GHCR

The image is built and pushed to [GitHub Container Registry](https://github.com/mathematicalmaker/zoho2gcal/pkgs/container/zoho2gcal) by the workflow in `.github/workflows/docker-publish.yml`.

## What happens automatically

### On every push to `main`

The workflow runs and pushes:

- **`ghcr.io/mathematicalmaker/zoho2gcal:latest`** — updated on every push to main
- **`ghcr.io/mathematicalmaker/zoho2gcal:main`** — same as above, branch name
- **`ghcr.io/mathematicalmaker/zoho2gcal:<short-sha>`** — e.g. `sha-a1b2c3d` for that commit

No action needed. Push to `main` and wait for the workflow to finish; then `docker pull ghcr.io/mathematicalmaker/zoho2gcal:latest` will get the new build.

---

## Creating a release (versioned tags)

To publish an image for a specific version (e.g. `v1.0.0`), create a **GitHub Release**. The workflow runs when a release is **published** and pushes semver tags.

### Steps

1. **Tag the commit you want to release**  
   Either create the tag locally and push:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
   Or create the tag in the GitHub UI when you create the release (step 2).

2. **Create the release on GitHub**  
   - Repo → **Releases** → **Draft a new release** (or **Create a new release**).
   - **Choose a tag:** pick the tag you pushed (e.g. `v1.0.0`) or create it here (e.g. type `v1.0.0` and choose “Create new tag”).
   - **Release title:** e.g. `v1.0.0` or `Release 1.0.0`.
   - **Description:** optional; add release notes.
   - Click **Publish release** (not “Save draft”).

3. **Workflow runs**  
   When the release is published, the Docker workflow runs and pushes:
   - **`ghcr.io/mathematicalmaker/zoho2gcal:v1.0.0`** — full version
   - **`ghcr.io/mathematicalmaker/zoho2gcal:1.0`** — major.minor (so `1.0.1` would also update `1.0`)

Users can then pull a specific version, e.g.:

```bash
docker pull ghcr.io/mathematicalmaker/zoho2gcal:v1.0.0
```

### Summary

| Trigger              | Tags pushed                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| Push to `main`       | `latest`, `main`, `sha-<short>`                                            |
| Publish release      | `v1.0.0` (or whatever the release tag), `1.0` (major.minor from that tag)  |

The first time you push to `main`, the workflow will build and push; after that, the image is available under the repo’s **Packages** (same page as the link above).
