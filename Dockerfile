FROM python:3.12-slim

ARG USER_NAME=google-proxy
ARG UID=1001

RUN useradd --uid ${UID} --create-home --shell /bin/bash ${USER_NAME}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/usr/local -r requirements.txt

# Copy application source
COPY app/ ./app/

# Persistent storage for internal token mappings lives here.
# Override DATA_DIR if you want a different path inside the container.
RUN mkdir -p /app/data

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    TOKENS_FILE=tokens.json

EXPOSE 9000

# Non-root user for security
RUN chown -R ${USER_NAME}:${USER_NAME} /app
USER ${USER_NAME}

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "9000", \
     "--proxy-headers"]
