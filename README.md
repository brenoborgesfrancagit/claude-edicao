# claude-edicao

Skill do [Claude Code](https://claude.com/claude-code) que edita **vídeo bruto** (você falando para a câmera)
e entrega pronto para **Instagram Reels e TikTok**, pensado para prender a atenção do começo ao fim.

Você manda o arquivo e diz "edita esse vídeo pro Reels". O Claude:

- **transcreve** palavra por palavra (faster-whisper, local, grátis, nada sai do seu computador);
- **corta** pausas, hesitações ("é...", "ãh", "hum", inclusive as que a transcrição não escreve), repetições,
  regravações ("o segundo erro é... o segundo erro é") e enrolação;
- **reenquadra** para 9:16 (corte no rosto ou fundo desfocado);
- mantém **cada quadro em movimento**: zoom lento contínuo + punch-in a cada corte;
- queima **legendas animadas** palavra por palavra, com palavras-chave destacadas;
- coloca **título de gancho** nos primeiros segundos, títulos nas viradas e **barra de progresso**;
- encaixa **motion graphics** feitos com a skill [claude-video](https://github.com/Felpborges/claude-video) quando convém;
- normaliza o áudio (-14 LUFS), exporta 1080x1920 H.264, e **confere olhando os quadros**;
- escreve sugestões de legenda do post, hashtags e capa.

## Instalar

No Claude Code, cole o link deste repositório e diga "instala essa skill". Ou no Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/brenoborgesfrancagit/claude-edicao/main/instalar.sh | bash
```

Precisa de: ffmpeg (com libass), Python 3 e ~2 GB livres (modelo de transcrição). O instalador cria um
ambiente Python isolado em `~/.local/share/claude-edicao/venv` (sem sudo). Para motion graphics, instale também
a skill claude-video.

## Usar

Abra uma conversa nova no Claude Code na pasta dos seus vídeos e diga:

> edita esse vídeo pro Reels e TikTok: bruto.mp4

## Usar o motor direto (sem o Claude)

```bash
ED=~/.claude/skills/claude-edicao/scripts/ed
$ED transcrever bruto.mp4 --pasta edicao-teste      # transcricao.txt com índices das palavras
$ED plano --pasta edicao-teste                       # cortes automáticos -> plano.json
$ED render --pasta edicao-teste --rapido             # prévia
$ED render --pasta edicao-teste                      # final.mp4
$ED quadros edicao-teste/final.mp4                   # folha de quadros para conferir
```

Veja `SKILL.md` para todas as opções do `plano.json` e `referencias/retencao.md` para as regras de ritmo.

## Licença

MIT. Fontes Montserrat e Anton sob SIL OFL 1.1.
