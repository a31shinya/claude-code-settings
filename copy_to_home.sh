#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/home/.claude"
DEST_DIR="${HOME}/.claude"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "コピー元フォルダが存在しません: ${SOURCE_DIR}"
  exit 1
fi

mkdir -p "${DEST_DIR}"

cp -R "${SOURCE_DIR}/." "${DEST_DIR}/"

echo "セットアップが完了しました。"
read -r -p "Enterキーを押して終了します..."
