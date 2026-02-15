# UTrack backend deployment (Oracle Cloud OCI)

Deploy the backend to **Oracle Cloud Infrastructure (OCI)**. The app runs with **PostgreSQL** (or SQLite locally) and supports both **manual install** (Gunicorn + Nginx) and **Docker Compose**.

---

## Prerequisites

1. **OCI compute instance** (e.g. Ubuntu 22.04) with a **public IP**.
2. **Security list / firewall**: open ports **22** (SSH), **80** (HTTP), **443** (HTTPS if SSL on server).
3. **GitHub Secrets** (Settings → Secrets and variables → Actions):
   - `DEPLOY_HOST` – OCI instance public IP (or hostname)
   - `DEPLOY_USER` – SSH user (e.g. `ubuntu`)
   - `DEPLOY_SSH_KEY` – Private key for SSH (full contents)

---

## Bootstrap (once per server)

- **Manual install (Gunicorn + Nginx):** run workflow **Bootstrap Oracle Cloud (OCI) – Manual install**.
- **Docker:** run workflow **Bootstrap Oracle Cloud (OCI) – Docker**.

Then use the deploy workflows for updates.

---

## Deploy

- **Manual stack:** **Deploy to Oracle Cloud (OCI)** (workflow_dispatch).
- **Docker:** **Docker Deploy to Oracle Cloud (OCI)** – runs on push to `deploy/oci` or manual trigger.

On the server, code is pulled from branch **`deploy/oci`**.

---

## Environment variables (production)

| Variable        | Description                                      |
|----------------|--------------------------------------------------|
| `DEPLOY_HOST`  | OCI instance public IP or hostname               |
| `DB_HOST`      | `localhost` (bare metal) or `db` (Docker)       |
| `DB_PORT`      | `5432`                                          |
| `DATABASE_URL` | Full Postgres URL (or set `POSTGRES_*` + `DB_*`) |
| `ALLOWED_HOSTS`| Comma-separated allowed hosts                    |
| `CSRF_TRUSTED_ORIGINS` | e.g. `https://api.yourdomain.com`       |
| `LOCALHOST`    | `False` on production                           |

See `utrack/settings.py` for the full list.
