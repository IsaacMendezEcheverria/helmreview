#!/usr/bin/env bash
# Instala helm en las imágenes python:*-slim de Cloud Build. Uso: source .cloudbuild/install-helm.sh
set -euo pipefail
HELM_VERSION="${HELM_VERSION:-v3.16.2}"
apt-get update -qq && apt-get install -y -qq curl ca-certificates > /dev/null
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" | tar xz -C /tmp
mv /tmp/linux-amd64/helm /usr/local/bin/helm
helm version --short
