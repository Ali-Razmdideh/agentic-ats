# syntax=docker/dockerfile:1.6
ARG PYTHON_VERSION=3.12

# ---------- builder ----------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /src

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Create the runtime virtualenv up front and install into it.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml MANIFEST.in README.md LICENSE ./
COPY ats ./ats

RUN pip install --upgrade pip \
 && pip install .

# ---------- runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    ATS_DB_PATH=/data/ats.db \
    ATS_INBOX_DIR=/data/inbox

# Node.js is required by the bundled Claude Code CLI that the SDK shells out to.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --create-home --uid 1000 ats \
 && mkdir -p /data \
 && chown -R ats:ats /data

COPY --from=builder /opt/venv /opt/venv

USER ats
WORKDIR /home/ats
VOLUME ["/data"]

ENTRYPOINT ["/usr/bin/tini", "--", "python", "-u", "-m", "ats.cli"]
CMD ["--help"]
