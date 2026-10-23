# Minimal pytest-only image used as the untrusted-code sandbox.
# The backend runs this image with: no network, no capabilities, nobody user,
# 256MB RAM, 64 PIDs, 0.5 CPU and a hard 5-second deadline.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace

RUN pip install --no-cache-dir pytest==8.3.5 \
    && mkdir -p /workspace \
    && chmod 755 /workspace

WORKDIR /workspace

CMD ["python", "-m", "pytest", "--version"]
