#!/usr/bin/env bash
set -euo pipefail

# Stop all Python-related processes for the current user
USER_NAME="$(whoami)"

echo "Stopping Python processes for user: ${USER_NAME}"

# Collect PIDs where the command name is python or python3
mapfile -t PIDS_COMM < <(ps -u "${USER_NAME}" -o pid=,comm= | awk '$2 ~ /^python(3)?$/ {print $1}')

# Collect PIDs where the full command line contains explicit python interpreter paths or words with boundaries
mapfile -t PIDS_ARGS < <(ps -u "${USER_NAME}" -o pid=,args= | awk '$0 ~ /(^|[[:space:]]|\/)(python3?)([[:space:]]|$|\/)/ {print $1}')

# Merge and deduplicate PIDs
declare -A SEEN
PIDS=()
for pid in "${PIDS_COMM[@]:-}"; do
  if [[ -n "${pid}" && -z "${SEEN[$pid]:-}" ]]; then
    SEEN[$pid]=1
    PIDS+=("${pid}")
  fi
done
for pid in "${PIDS_ARGS[@]:-}"; do
  if [[ -n "${pid}" && -z "${SEEN[$pid]:-}" ]]; then
    SEEN[$pid]=1
    PIDS+=("${pid}")
  fi
done

if [[ ${#PIDS[@]} -eq 0 ]]; then
  echo "No Python processes found for user ${USER_NAME}."
  exit 0
fi

echo "Found ${#PIDS[@]} Python process(es): ${PIDS[*]}"
echo "Details:"
ps -fp "$(IFS=,; echo "${PIDS[*]}")" || true

echo "Sending SIGTERM to Python processes..."
kill -TERM "${PIDS[@]}" || true

# Wait up to 10 seconds for graceful shutdown
for i in {1..20}; do
  sleep 0.5
  # Re-check which of the original PIDs still exist
  read -r -a REMAINING < <(ps -o pid= -p "$(IFS=,; echo "${PIDS[*]}")")
  if [[ ${#REMAINING[@]} -eq 0 ]]; then
    echo "All Python processes stopped gracefully."
    exit 0
  fi
done

echo "Force killing remaining processes: ${REMAINING[*]}"
kill -KILL "${REMAINING[@]}" || true

echo "Done."