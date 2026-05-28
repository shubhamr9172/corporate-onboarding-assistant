# Developer Onboarding: Code Setup & Environment Configuration Guide

Welcome to the engineering team! This guide will help you configure your local development environment, set up version control, install required packages, and run projects locally.

## 1. Prerequisites & Tool Installation
Ensure your local machine has the primary toolchains installed. If you do not have administrative rights to install these, use the **MakeMeAdmin** / **Privileges** tool to temporarily elevate your permissions.

- **Git**: Ensure Git is installed (`git --version`).
- **Docker & Docker Compose**: Essential for containerized local services (databases, caches).
- **Python / Node.js**: Install the version specified in the project's codebase guidelines.

---

## 2. Git & SSH Key Configuration
All source code repositories are hosted on the corporate GitHub organization (`github.com/corporate-org`). Direct HTTPS password authentication is disabled; you must authenticate using SSH.

### A. Generating an SSH Key
If you do not have an SSH key, generate a new one:
```bash
ssh-keygen -t ed25519 -C "your.email@corporate.com"
```
Press Enter to accept the default file path and set a secure passphrase.

### B. Registering with GitHub
1. Copy the public key to your clipboard:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
2. Log in to GitHub -> **Settings** -> **SSH and GPG keys** -> **New SSH Key**.
3. Paste the key and save.
4. Test your connection:
   ```bash
   ssh -T git@github.com
   ```

---

## 3. Cloning and Setting Up a Python Repository
For most core services (including our onboarding assistants and backend services), follow these setup steps:

### A. Clone the Repository
```bash
git clone git@github.com:corporate-org/corporate-onboarding-assistant.git
cd corporate-onboarding-assistant
```

### B. Environment Variables (`.env`)
Projects rely on `.env` files for configuration. Never commit `.env` files to git.
1. Copy the template:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in the required API keys (e.g., `GOOGLE_API_KEY`, `REDIS_HOST`, etc.). You can request development API keys from your Tech Lead.

### C. Creating a Virtual Environment
We use virtual environments to isolate python dependencies.
```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### D. Installing Dependencies
Upgrade pip and install the package requirements:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Running Infrastructure Services Locally
Many services rely on Redis (for caching/rate limiting) or databases.
Start the local development services using Docker Compose:
```bash
docker-compose up -d
```
Verify the containers are running:
```bash
docker ps
```

---

## 5. Development Standards & Commands
Before pushing code changes to a branch, verify compliance with our standards:

- **Linting & Code Style**: We enforce PEP8 compliance using `flake8` or `black`.
  ```bash
  black .
  ```
- **Running Tests**: Run the pytest suite before pushing to make sure no regressions are introduced:
  ```bash
  pytest
  ```
- **Local Dev Servers**: For Streamlit frontend projects:
  ```bash
  streamlit run app.py
  ```
