FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       git \
       jq \
       python3 \
       python3-pip \
       python3-venv \
       ripgrep \
       tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
