# VulHawk hosted guard API
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    GUARD_SCOPE_DIR=/ GUARD_STATE_DIR=/tmp/vulhawk \
    MUBIT_BASE_URL=https://api.mubit.ai/anthropic MUBIT_MODEL=claude-opus-5-5
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY config.py classifier.py local_checks.py guard_hook.py spend.py ./
COPY server ./server
COPY skills ./skills
COPY client ./client
RUN useradd --create-home vulhawk && mkdir -p /tmp/vulhawk && chown vulhawk /tmp/vulhawk
USER vulhawk
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
