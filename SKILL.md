---
name: claude-edicao
description: Edita vídeo bruto (pessoa falando para a câmera) e entrega pronto para Instagram Reels e TikTok, em português. Transcreve palavra por palavra, corta pausas, hesitações ("é...", "ãh", "hum"), repetições e regravações, reenquadra para 9:16, mantém a imagem sempre em movimento (zoom lento contínuo + punch-in a cada corte), queima legendas animadas palavra por palavra, título de gancho nos primeiros segundos, barra de progresso, e encaixa motion graphics feitos com a skill claude-video quando fazem sentido. Confere o resultado olhando os quadros. Use quando a pessoa mandar um vídeo e pedir "edita esse vídeo", "corta as pausas", "tira os vícios", "deixa pronto pro Reels/TikTok", "coloca legenda", "faz um corte pras redes", ou só mandar um arquivo de vídeo bruto. Também quando pedir "atualiza a skill claude-edicao".
license: MIT
metadata:
  author: Breno Borges
  version: "1.0"
---

# claude-edicao

Objetivo: transformar **qualquer vídeo bruto** num vídeo vertical que **prende a atenção do começo ao fim**
(retenção é o que faz o perfil crescer). Nenhum quadro fica parado: tem sempre algo se mexendo (zoom, legenda,
título, gráfico, barra). Leia `referencias/retencao.md` antes da primeira edição da conversa: são as regras de
ritmo que guiam todas as decisões abaixo.

`$SKILL` é a pasta desta skill (normalmente `~/.claude/skills/claude-edicao`). O motor é `$SKILL/scripts/ed`
(wrapper do `editor.py` que usa o Python isolado com o transcritor). Fale com a pessoa em português do Brasil,
simples, sem jargão. Diga o que verificou e o que não verificou. Você não ouve o áudio: suas fontes de verdade
são a transcrição, as medições do áudio e os quadros que você olha.

## Antes de começar

1. `bash $SKILL/scripts/checar.sh`. Se faltar algo, rode `bash $SKILL/instalar.sh` (sem sudo). Se faltar ffmpeg,
   dê o comando à pessoa e peça confirmação antes.
2. Leia `marca.json` na pasta onde a pessoa trabalha (a pasta atual). Se não existir, **não pergunte nada agora**:
   use os padrões e, na entrega do primeiro vídeo, ofereça em uma linha salvar cores/estilo/@ da pessoa.
   Formato em `referencias/marca.md`.
3. Crie uma pasta de trabalho por vídeo: `./edicao-<nome-curto>/`. O bruto fica onde está; nunca altere o original.

## Fluxo (faça tudo, sem pedir licença a cada passo)

**1. Olhar e transcrever.**
`$SKILL/scripts/ed info <bruto>` e `$SKILL/scripts/ed quadros <bruto> --saida <pasta>/bruto-quadros.png`, e leia
a imagem: onde está o rosto (para o `foco`), se é gravação de tela, se a luz/fundo muda.
`$SKILL/scripts/ed transcrever <bruto> --pasta <pasta>` (modelo `medium` por padrão; para vídeos com mais de 10
min, `--modelo small` e avise que a legenda pode ter mais erros). Rode em segundo plano se passar de ~2 min de
vídeo. A primeira vez baixa o modelo (~1,5 GB).

**2. Ler a transcrição como editor.** Abra `<pasta>/transcricao.txt`. Cada palavra tem `#índice`. Procure:
- **Regravações**: a pessoa errou e repetiu a frase (às vezes com palavras diferentes). Fica a ÚLTIMA versão
  boa. O plano já remove repetições literais; as com palavras diferentes são com você (`--cortar-palavras`).
- **Palavras com ⚠**: tempo longo ou baixa confiança, podem esconder repetição. A transcrição já re-transcreve
  essas frases sozinhas; se ainda parecer estranho, `ed trecho <ini> <fim> --pasta <pasta>` mostra o trecho literal.
- **Enrolação**: introdução lenta ("oi gente, tudo bem, hoje eu vou falar..."), frases que não acrescentam,
  despedidas longas. Corte sem dó: o vídeo deve chegar ao ponto em até 2 segundos.
- **O gancho**: a frase mais forte/curiosa do vídeo. Se ela não está no começo, use `--gancho <ini>-<fim>`
  (tempo do bruto) para repeti-la como abertura (2 a 4 s).
- Erros de transcrição em nomes/termos: anote para corrigir na legenda (passo 4).

**3. Plano de cortes.**
`$SKILL/scripts/ed plano --pasta <pasta> [--cortar-palavras 12-30,88] [--cortar 61.2-64.8] [--gancho 45.2-48.9] [--agressivo]`
O plano mede o som real (limiar automático) e corta: silêncios maiores que `--pausa-max` (0,30 s), hesitações
(inclusive as que o Whisper não escreveu), vícios, repetições, e o que você pediu. `--agressivo` também tira
"né", "tipo", "assim", "então": use se a pessoa fala muito isso, mas releia o resultado. Leia o resumo impresso
e `<pasta>/transcricao-editada.txt` (já com os tempos do vídeo final). Se uma frase ficou truncada ou sem
sentido, ajuste e rode de novo. Rodar o plano de novo preserva textos, inserções e legendas já configurados.

**3b. Revisão literal (obrigatória antes do final).** `$SKILL/scripts/ed revisar --pasta <pasta>` re-transcreve
cada trecho mantido sozinho (padrão `large-v3`; se o download travar, `--modelo medium`) e marca o que sobrou:
"é" de hesitação, "ãh", repetições. Leia `revisao.txt`: o "é" VERBO ("a segunda que mais cresce **é** engenheiro",
"também **é** uma vaga") e o "E" conjunção ("**E** designer de produtos") às vezes vêm marcados por engano; tire
esses itens de `revisao.json` antes de aplicar. Restos de frases cortadas também aparecem aqui (corte com
`--cortar`). Depois rode o mesmo `plano` de antes com `--revisao`. Para ritmo de Reels: `--pausa-max 0.12
--folga 0.05`. Confira as pausas no final com
`ffmpeg -i final.mp4 -af silencedetect=noise=-40dB:d=0.3 -f null -` (meta: quase nenhuma).

**4. Direção visual no `plano.json`** (edite o arquivo; regras de ritmo em `referencias/retencao.md`):
- `foco`: `{"x":0.5,"y":0.4}` posição do rosto (0 a 1) para o corte 9:16. Ajuste olhando os quadros do bruto.
  Para um trecho específico, coloque `"foco"` dentro do segmento.
- `enquadramento`: `cortar` (padrão, ocupa a tela) ou `desfoque` (vídeo inteiro com fundo desfocado: tela
  gravada, plano aberto, duas pessoas).
- `segmentos[].zoom` / `deriva`: o plano alterna 1.0 e 1.14 a cada corte e põe deriva lenta de 3,5 %. Para
  ênfase forte numa frase, zoom 1.25 naquele segmento.
- `legendas.destaques`: 1 palavra-chave a cada 1 ou 2 frases (números, promessas, a palavra que resume a frase).
  `legendas.correcoes`: `{"errado":"certo"}` para nomes e termos que a transcrição escreveu errado.
- `textos`: título do gancho em 0 a ~2,5 s (máx. 6 palavras, `\n` quebra linha), e títulos curtos em viradas
  ("ERRO #2"). Campos: `texto, ini, fim, altura (0-1), cor, fundo, estilo ("sub" = menor)`.
- `insercoes`: motion graphics (passo 5) ou b-roll. Campos: `arquivo, em (s do vídeo final), dur, modo
  ("tela-cheia" | "janela"), altura, largura, legenda (false = esconde a legenda durante)`.

**5. Motion graphics, quando convém.** Bons lugares: abertura com o título (1,5 a 3 s), listas e números
("3 erros", "R$ 10 mil"), comparação, passo a passo, dado que precisa de visual, CTA final. Não mais que
1 inserção a cada ~15 s, e nunca sobre o momento em que o rosto/emoção é o que importa.
Molde pronto de cards 9:16 (variação com número que conta, tendência, lista) usado no primeiro vídeo:
`referencias/molde-motion/` (gerar com `gerar.py`, renderizar com `render.sh` da claude-video).
Para peças novas: siga a **skill claude-video** (`~/.claude/skills/claude-video/SKILL.md`) direto na etapa C
(construir), **sem a galeria e sem as 5 perguntas**: o estilo vem do `marca.json` (`estilo_motion`) ou, se
não houver, escolha um da galeria que combine e diga qual escolheu. Brief: 1080x1920 (9x16), a duração exata
do trecho, 30 fps, sem loop, as palavras exatas da fala daquele momento. Salve o MP4 na pasta de trabalho e
referencie em `insercoes`. Se a claude-video não estiver instalada, use só `textos` e avise.
Se a pessoa quer entrega rápida, pule motion graphics e diga que dá para adicionar depois.

**6. Prévia e conferência.** `$SKILL/scripts/ed render --pasta <pasta> --rapido` e depois
`$SKILL/scripts/ed quadros <pasta>/previa.mp4 --n 24`. Leia a imagem e confira: rosto dentro do quadro em todos
os trechos (zoom não corta a cabeça), legenda legível e fora do rodapé, título não cobre o rosto, inserções nos
lugares certos. Corrija o plano e repita. Não diga que está bom sem ter olhado.

**7. Final.** `$SKILL/scripts/ed render --pasta <pasta>` gera `<pasta>/final.mp4` (1080x1920, H.264,
AAC, -14 LUFS, faststart): serve para Reels e TikTok. Escreva `<pasta>/post.txt` com: 3 opções de legenda
do post (primeira linha é gancho), 5 a 8 hashtags do nicho, e a sugestão de capa (o tempo do quadro mais forte).

**8. Entrega.** Diga em poucas linhas: caminho do `final.mp4`, duração antes → depois, o que foi cortado
(números), o que foi adicionado, o que você conferiu nos quadros, e o que não conferiu (você não ouve o áudio:
peça para a pessoa assistir uma vez antes de postar). Ofereça 1 ajuste concreto ("quer que eu corte mais
agressivo?", "quer um motion graphic na abertura?").

## Ajustes comuns que a pessoa pode pedir

- "Ficou corrido demais" → `--pausa-max 0.45 --folga 0.1`. "Ainda tem pausa" → `--pausa-max 0.2`.
- "Cortou palavra" → aumente `--folga` (0.1) ou confira o trecho com `ed trecho`. Se o áudio tem ruído de fundo
  forte, passe `--limiar` (o resumo do plano mostra o limiar automático; suba 3-6 dB para cortar mais).
- "Legenda maior/menor/outra cor" → `legendas.tamanho` (96), `cor`, `cor_destaque`, `altura` (0.66),
  `max_palavras` (3), `maiusculas`. "Sem legenda" → `legendas.ligadas: false`.
- "Vou usar a legenda do Instagram" → `legendas.ligadas: false` (títulos e motion graphics continuam).
- "Sem barra" → `barra_progresso.ligada: false`. "Sem zoom" → zoom 1.0 e deriva 0 nos segmentos.
- Vídeo para YouTube horizontal: fora do escopo atual desta skill (ela entrega 9:16). Diga isso.

## Atualizar a skill

`git -C $SKILL pull --ff-only` (ou `bash $SKILL/instalar.sh`). Depois, conversa nova.
