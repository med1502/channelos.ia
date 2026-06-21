#!/usr/bin/env bash
# Windows Task Scheduler wrapper — daily video production
# Called by: wsl.exe -u mfayech bash /home/mfayech/Github/channelos.ia/scripts/wts-produce.sh
REPO=/home/mfayech/Github/channelos.ia
LOG="$REPO/logs/produce.log"
SCHED_LOG="$REPO/logs/scheduler.log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wts-produce: start" >> "$SCHED_LOG"

# Wait up to 60 s for Docker Desktop to be ready after wake
for i in $(seq 1 10); do
  docker info > /dev/null 2>&1 && break
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] waiting for Docker ($i/10)..." >> "$SCHED_LOG"
  sleep 6
done

cd "$REPO"
make up >> "$SCHED_LOG" 2>&1
sleep 10

TOPIC=$(shuf -e \
  "AI tools for entrepreneurs" \
  "Claude Code workflows" \
  "no-code automation" \
  "AI for small business" \
  -n1)

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] topic: $TOPIC" >> "$SCHED_LOG"

/usr/bin/flock -n /tmp/channelos.lock \
  python3 -m channelos "$TOPIC" --publish --schedule \
  >> "$LOG" 2>&1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wts-produce: done" >> "$SCHED_LOG"
