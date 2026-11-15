#!/usr/bin/env bash
# instalar.sh: instala (ou atualiza) a skill claude-edicao em ~/.claude/skills/claude-edicao
# e o transcritor faster-whisper num ambiente Python isolado (sem sudo).
#   curl -fsSL https://raw.githubusercontent.com/brenoborgesfrancagit/claude-edicao/main/instalar.sh | bash
set -eu
REPO=${CLAUDE_EDICAO_REPO:-https://github.com/brenoborgesfrancagit/claude-edicao}
DEST=${CLAUDE_EDICAO_DEST:-$HOME/.claude/skills/claude-edicao}
VENV=${CLAUDE_EDICAO_VENV:-$HOME/.local/share/claude-edicao/venv}
diga() { printf '\n==> %s\n' "$*"; }

if [ -f "$DEST/SKILL.md" ] && [ -d "$DEST/.git" ]; then
  diga "Atualizando a skill em $DEST"; git -C "$DEST" pull --ff-only || diga "Não deu para atualizar; segue a versão atual."
elif [ ! -f "$DEST/SKILL.md" ]; then
  if [ -e "$DEST" ]; then mv "$DEST" "$DEST.antigo-$(date +%Y%m%d-%H%M%S)"; fi
  mkdir -p "$(dirname "$DEST")"; git clone --quiet --depth 1 "$REPO" "$DEST"; diga "Skill baixada em $DEST"
fi
chmod +x "$DEST"/scripts/*.sh "$DEST"/scripts/ed "$DEST"/instalar.sh 2>/dev/null || true

if ! [ -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import faster_whisper' 2>/dev/null; then
  diga "Instalando o transcritor (faster-whisper) em $VENV"
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q "faster-whisper==1.2.1"
fi
diga "Conferindo"
bash "$DEST/scripts/checar.sh" || true
echo; echo "Pronto. Abra uma conversa NOVA no Claude Code e mande: edita esse vídeo pro Reels: <arquivo>"
