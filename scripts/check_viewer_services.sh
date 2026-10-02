#!/usr/bin/env bash
set -euo pipefail

FUSE_DIR="$HOME/fuse"
HUB_ROOT="/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/viewer_hub"
HUB_SESSION="viewer-hub"
TUNNEL_SESSION="s10-viewer-share"
CLOUDFLARED="$HOME/.local/bin/cloudflared"
HUB_PORT="8765"
LOG_DIR="$FUSE_DIR/logs"

mkdir -p "$LOG_DIR"

echo "[$(date '+%F %T')] checking viewer services..."

# 1. Viewer Hub
if tmux has-session -t "$HUB_SESSION" 2>/dev/null \
  && ss -H -ltnp "sport = :$HUB_PORT" | grep -q LISTEN; then
  echo "Viewer Hub: OK"
else
  echo "Viewer Hub: DOWN -> restarting"

  tmux kill-session -t "$HUB_SESSION" 2>/dev/null || true

  tmux new-session -d -s "$HUB_SESSION" \
    "cd '$FUSE_DIR' && exec python -u -m http.server $HUB_PORT \
      --bind 127.0.0.1 \
      --directory '$HUB_ROOT' \
      >> '$LOG_DIR/viewer_hub.log' 2>&1"

  sleep 2

  if curl -fsS "http://127.0.0.1:$HUB_PORT/" >/dev/null; then
    echo "Viewer Hub: RESTARTED"
  else
    echo "Viewer Hub: FAILED"
    exit 1
  fi
fi

# 2. Cloudflare Quick Tunnel
if tmux has-session -t "$TUNNEL_SESSION" 2>/dev/null \
  && tmux list-panes -t "$TUNNEL_SESSION" -F '#{pane_current_command}' \
       | grep -qx cloudflared; then
  echo "Cloudflare tunnel: OK"
else
  echo "Cloudflare tunnel: DOWN -> restarting"

  tmux kill-session -t "$TUNNEL_SESSION" 2>/dev/null || true

  tmux new-session -d -s "$TUNNEL_SESSION" \
    "cd '$FUSE_DIR' && exec '$CLOUDFLARED' tunnel \
      --no-autoupdate \
      --url http://127.0.0.1:$HUB_PORT \
      >> '$LOG_DIR/viewer_cloudflare_current.log' 2>&1"

  sleep 5

  if tmux has-session -t "$TUNNEL_SESSION" 2>/dev/null; then
    echo "Cloudflare tunnel: RESTARTED"
  else
    echo "Cloudflare tunnel: FAILED"
    exit 1
  fi
fi

echo
echo "Current status:"
tmux list-panes -t "$HUB_SESSION" -F 'viewer-hub: #{pane_pid} #{pane_current_command}' 2>/dev/null || true
tmux list-panes -t "$TUNNEL_SESSION" -F 'cloudflare: #{pane_pid} #{pane_current_command}' 2>/dev/null || true
ss -H -ltnp "sport = :$HUB_PORT" || true

echo
echo "Latest Cloudflare URL:"
grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' \
  "$LOG_DIR/viewer_cloudflare_current.log" \
  | tail -n 1 || true
