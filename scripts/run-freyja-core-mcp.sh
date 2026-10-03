#!/bin/zsh
set -euo pipefail

repo_root="/Users/freyja/freyja-os"
export PYTHONPATH="${repo_root}/src:${repo_root}"
export FREYJA_CORE_MCP_HOST="100.115.228.56"
export FREYJA_CORE_MCP_PORT="8766"

# Keep runtime credentials outside the repository and LaunchAgent plist.
secret_env_file="${FREYJA_CORE_MCP_ENV_FILE:-${HOME}/.config/freyja-os/core-mcp.env}"
if [[ -r "${secret_env_file}" ]]; then
  set -a
  source "${secret_env_file}"
  set +a
fi

exec "${repo_root}/.venv/bin/python" "${repo_root}/scripts/freyja-core-mcp-server.py"
