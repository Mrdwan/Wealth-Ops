FROM python:3.13-slim

# Metadata labels
LABEL org.opencontainers.image.title="Wealth-Ops Dev"
LABEL org.opencontainers.image.description="Development container for Wealth-Ops trading system"
LABEL org.opencontainers.image.source="https://github.com/wealth-ops/wealth-ops"
LABEL project="wealth-ops"

# Install system dependencies (bash required for devcontainer features)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry" \
    POETRY_VERSION="1.8.2" \
    POETRY_VIRTUALENVS_CREATE=false
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Set working directory
WORKDIR /workspaces/wealth-ops

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

USER $USERNAME
