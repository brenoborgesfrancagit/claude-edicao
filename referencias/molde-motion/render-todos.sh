#!/usr/bin/env bash
cd "$(dirname "$0")"; mkdir -p out
for d in proj/*/; do id=$(basename $d); HF_WORKERS=4 bash ~/.claude/skills/claude-video/scripts/render.sh proj/$id out/$id.mp4 high 2>&1 | tail -1; done
echo FIM
