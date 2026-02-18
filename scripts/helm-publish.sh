#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="${ROOT_DIR}/deploy/helm/data-plane"

CHARTS_REPO_DIR="${CHARTS_REPO_DIR:-}"
CHARTS_REPO_URL="${CHARTS_REPO_URL:-}"
SKIP_PUSH="${SKIP_PUSH:-0}"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required but not found in PATH." >&2
  exit 1
fi

if [[ -z "${CHARTS_REPO_DIR}" ]]; then
  echo "Set CHARTS_REPO_DIR to a local clone of your GitHub Pages charts repo." >&2
  echo "Example: export CHARTS_REPO_DIR=\"$HOME/code/charts\"" >&2
  exit 1
fi

if [[ ! -d "${CHARTS_REPO_DIR}" ]]; then
  echo "CHARTS_REPO_DIR does not exist: ${CHARTS_REPO_DIR}" >&2
  exit 1
fi

if [[ -z "${CHARTS_REPO_URL}" ]]; then
  echo "Set CHARTS_REPO_URL to the public URL (e.g. https://wshands.github.io/charts)." >&2
  exit 1
fi

chart_name="$(awk -F': ' '/^name:/{print $2; exit}' "${CHART_DIR}/Chart.yaml")"
chart_version="$(awk -F': ' '/^version:/{print $2; exit}' "${CHART_DIR}/Chart.yaml")"

if [[ -z "${chart_name}" || -z "${chart_version}" ]]; then
  echo "Failed to read chart name/version from ${CHART_DIR}/Chart.yaml" >&2
  exit 1
fi

echo "Packaging chart ${chart_name} ${chart_version}..."
helm package "${CHART_DIR}" -d "${CHARTS_REPO_DIR}"

echo "Updating repo index..."
helm repo index "${CHARTS_REPO_DIR}" --url "${CHARTS_REPO_URL}"

if [[ -d "${CHARTS_REPO_DIR}/.git" ]]; then
  echo "Committing chart package..."
  git -C "${CHARTS_REPO_DIR}" add .
  git -C "${CHARTS_REPO_DIR}" commit -m "Release ${chart_name} ${chart_version}" || true
  if [[ "${SKIP_PUSH}" != "1" ]]; then
    git -C "${CHARTS_REPO_DIR}" push
  else
    echo "Skipping git push (SKIP_PUSH=1)."
  fi
else
  echo "No git repo detected in ${CHARTS_REPO_DIR}; skipping commit/push."
fi

echo "Done."
