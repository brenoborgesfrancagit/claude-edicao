# marca.json

Arquivo opcional na pasta onde a pessoa guarda os vídeos (ex.: `~/Vídeos/meusvideos-claude/marca.json`).
O `ed plano` lê dele as cores padrão; o Claude lê o resto para decidir textos, CTA e motion graphics.
Crie quando a pessoa aceitar salvar as preferências (ofereça na entrega do primeiro vídeo).

```json
{
  "arroba": "@seuperfil",
  "nicho": "marketing para pequenos negócios",
  "tom": "direto, animado, sem gíria pesada",
  "cor_legenda": "#FFE14D",
  "cor_destaque": "#3CFF8B",
  "cor_barra": "#FFE14D",
  "estilo_motion": "poster-suico",
  "cta": "Segue pra mais dicas",
  "hashtags_fixas": ["#marketingdigital"]
}
```

- `cor_*`: hex. Amarelo + verde é o padrão (alto contraste em qualquer fundo).
- `estilo_motion`: id de um estilo da galeria da claude-video (`~/.claude/skills/claude-video/estilos/`).
- `cta`: frase de chamada para ação usada no último título e no post.
- Tudo é opcional; o que faltar usa o padrão.
