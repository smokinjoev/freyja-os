#!/usr/bin/env bash
set -euo pipefail

repo_dir="${REPO_DIR:-/home/joe/freyja-os}"
compose_file="${COMPOSE_FILE:-deploy/compose/open-webui/compose.yaml}"
env_file="${ENV_FILE:-deploy/compose/open-webui/.env}"
project_name="${PROJECT_NAME:-freyja-open-webui-atlas}"
output_dir="${1:-logs/open-webui-diagnostics/atlas-state-$(date -u +%Y%m%dT%H%M%SZ)}"
backup_data="${BACKUP_OPEN_WEBUI_DATA:-0}"

mkdir -p "$output_dir"

redact() {
  sed -E 's/^([^#=]*(KEY|TOKEN|SECRET|PASSWORD|COOKIE|AUTH)[^=]*)=.*/\1=<redacted>/I'
}

write_command() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    "$@"
  } >"$output_dir/$name" 2>&1 || true
}

cd "$repo_dir"

{
  printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'hostname=%s\n' "$(hostname)"
  printf 'repo_dir=%s\n' "$repo_dir"
  printf 'compose_file=%s\n' "$compose_file"
  printf 'env_file=%s\n' "$env_file"
  printf 'project_name=%s\n' "$project_name"
} >"$output_dir/collector-metadata.txt"

if [ -f "$env_file" ]; then
  redact <"$env_file" >"$output_dir/env.redacted"
fi

cp "$compose_file" "$output_dir/compose.yaml" 2>/dev/null || true
cp deploy/compose/open-webui/model-proxy.py "$output_dir/model-proxy.py" 2>/dev/null || true
cp deploy/compose/open-webui/README.md "$output_dir/README.md" 2>/dev/null || true

if [ -f "$env_file" ]; then
  write_command compose-config docker compose --env-file "$env_file" -f "$compose_file" config
  redact <"$output_dir/compose-config" >"$output_dir/compose-config.redacted" || true
fi

write_command docker-ps docker ps --filter "name=${project_name}" --no-trunc
write_command docker-images docker images --digests --no-trunc

docker ps -a --filter "name=${project_name}" --format '{{.Names}}' | while IFS= read -r container; do
  [ -n "$container" ] || continue
  safe_name="${container//[^A-Za-z0-9_.-]/_}"
  write_command "inspect-${safe_name}.json" docker inspect "$container"
  write_command "logs-${safe_name}.txt" docker logs --timestamps --tail 1000 "$container"
done

write_command open-webui-version curl -fsS --max-time 10 http://127.0.0.1:3001/api/version
write_command open-webui-config curl -fsS --max-time 10 http://127.0.0.1:3001/api/config

if [ "$backup_data" = "1" ]; then
  volume_name="${VOLUME_NAME:-${project_name}_open-webui}"
  backup_path="$output_dir/open-webui-data-volume.tgz"
  docker run --rm \
    -v "${volume_name}:/source:ro" \
    -v "$(pwd)/${output_dir}:/backup" \
    alpine:3.20 \
    tar -czf "/backup/$(basename "$backup_path")" -C /source .
  printf '%s\n' "$backup_path" >"$output_dir/data-backup-path.txt"
fi

printf 'Open WebUI state captured under %s\n' "$output_dir"
