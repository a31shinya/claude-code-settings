#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/project"

read -r -p "コピー先フォルダのパスを入力してください: " DEST_DIR

if [[ ! -d "${DEST_DIR}" ]]; then
  echo "指定されたパスは存在しません: ${DEST_DIR}"
  exit 1
fi

cp -R "${SOURCE_DIR}/." "${DEST_DIR}/"

echo "セットアップが完了しました。"
read -r -p "Enterキーを押して終了します..."
