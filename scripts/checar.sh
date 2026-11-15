#!/usr/bin/env bash
# checar.sh: confere o que a skill claude-edicao precisa. Imprime como corrigir cada item que falta.
VENV=${CLAUDE_EDICAO_VENV:-$HOME/.local/share/claude-edicao/venv}
ok=1
say() { printf '%-15s %s\n' "$1" "$2"; }
for t in ffmpeg ffprobe; do
  if command -v $t >/dev/null; then say $t ok; else say $t "Falta. Linux: sudo apt install ffmpeg | Mac: brew install ffmpeg"; ok=0; fi
done
if command -v ffmpeg >/dev/null; then
  if ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' ass '; then say "ffmpeg+libass" ok
  else say "ffmpeg+libass" "Seu ffmpeg não queima legendas (sem libass). Instale um ffmpeg completo."; ok=0; fi
fi
if command -v python3 >/dev/null; then say python3 ok; else say python3 "Falta python3"; ok=0; fi
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import faster_whisper' 2>/dev/null; then say faster-whisper ok
else say faster-whisper "Falta. Rode: bash $(cd "$(dirname "$0")/.." && pwd)/instalar.sh"; ok=0; fi
[ $ok = 1 ] && echo "pronto" || { echo "corrija as linhas acima e rode de novo"; exit 1; }
