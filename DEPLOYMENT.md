# Deployment
Docker/Render: `render.yaml` uses the Dockerfile, health check `/_stcore/health`, port from `$PORT` (default 8501).
Steps: push this folder to a Git repo, create a Render Web Service from the repo (Docker runtime). It is not deployed until the service shows healthy; this package has not been deployed anywhere.
Local container check: `docker build -t inspector . && docker run -p 8501:8501 inspector`, then open http://localhost:8501/_stcore/health (expects `ok`). Docker was not available where this was built, so the image is untested.
