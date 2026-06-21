#!/usr/bin/env bash
# Windows Task Scheduler wrapper — collect daily analytics
# Called by: wsl.exe -u mfayech bash /home/mfayech/Github/channelos.ia/scripts/wts-collect.sh
set -euo pipefail
REPO=/home/mfayech/Github/channelos.ia
LOG="$REPO/logs/collect.log"
SCHED_LOG="$REPO/logs/scheduler.log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wts-collect: start" >> "$SCHED_LOG"

# Wait up to 60 s for Docker Desktop to be ready after wake
for i in $(seq 1 10); do
  docker info > /dev/null 2>&1 && break
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] waiting for Docker ($i/10)..." >> "$SCHED_LOG"
  sleep 6
done

cd "$REPO"
make up >> "$SCHED_LOG" 2>&1
sleep 10  # let Postgres accept connections

python3 -m channelos.pipeline.collect >> "$LOG" 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wts-collect: done" >> "$SCHED_LOG"
