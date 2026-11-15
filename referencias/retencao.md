# Regras de retenção (Reels e TikTok)

A plataforma mede quanto do vídeo as pessoas assistem. Cada decisão de edição serve a uma pergunta:
**a pessoa tem um motivo para continuar assistindo AGORA?**

## Os 3 primeiros segundos (o gancho)
- A primeira palavra já é conteúdo. Nada de "oi gente", "e aí pessoal, tudo bem?", "hoje eu vou falar sobre".
  Corte isso; se a pessoa se apresenta, mova para depois ou corte.
- Título na tela em 0 s (máx. 6 palavras), escrito como promessa ou curiosidade: "3 ERROS QUE TRAVAM SEU PERFIL",
  "NINGUÉM TE CONTA ISSO", "PAREI DE FAZER X E...". Use as palavras da própria fala sempre que der.
- Se a frase mais forte está no meio, repita-a no início com `--gancho` (2 a 4 s), depois corte seco para o começo.
- Primeiro segmento com zoom 1.0 e o segundo com punch-in: o primeiro corte acontece em menos de 3 s.

## Ritmo: algo muda a cada 2 a 4 segundos
"Mudar" pode ser: corte com punch-in (automático), título curto, palavra destacada na legenda, inserção,
mudança de foco/zoom. Nenhum trecho com mais de ~5 s sem nenhuma mudança: se um segmento é longo, divida-o
no plano em dois com zooms diferentes (copie o segmento e ajuste `ini`/`fim`).
- Pausas: no máximo 0,30 s entre frases (padrão). Respiração no meio da frase pode ficar.
- Zoom contínuo (deriva) sempre ligado: a imagem nunca está 100 % parada.
- Ênfase: zoom 1.25 só na frase de impacto (a revelação, o número, a opinião forte). Se usar em tudo, perde efeito.

## Legendas
- Sempre ligadas (a maioria assiste sem som). 2-3 palavras por vez, palavra falada em destaque.
- Destaque (cor 2) em 1 palavra-chave a cada 1-2 frases: números, dinheiro, tempo, "erro", "segredo", o
  substantivo que resume a frase. Não mais que isso.
- Posição 0,66 da altura: acima da interface do TikTok/Reels (rodapé com descrição e botões laterais).

## Títulos e motion graphics
- Títulos em viradas: "ERRO #1", "PASSO 2", "RESULTADO". Duração 1,2 a 2,5 s. Altura 0,15-0,25 (topo), fora do rosto.
- Motion graphic quando a fala tem estrutura visual: lista, número grande, comparação antes/depois, processo.
  1,5 a 4 s, no máximo 1 a cada ~15 s. Use "janela" quando o rosto/reação ainda importa; "tela-cheia" para
  aberturas e explicações.
- O motion graphic diz as MESMAS palavras da fala daquele momento (reforço, não distração).

## Final
- Termine na última frase útil: corte despedidas longas. CTA curto em texto nos últimos 1,5 s
  ("SEGUE PRA PARTE 2", "SALVA PRA NÃO ESQUECER"): usa o `cta` do marca.json se houver.
- Se o final conecta com o começo (loop), melhor ainda: o replay conta como retenção.

## Duração
- Ideal 20 a 60 s. Se o bruto editado passa de 90 s, sugira dividir em partes (Parte 1, Parte 2) e diga onde
  cortaria. Não divida sem a pessoa pedir.

## Zonas seguras (1080x1920)
- Topo: 0 a 220 px pode ser coberto pela interface (nome, "Seguindo"). Títulos a partir de ~290 px (altura 0,15).
- Rodapé: abaixo de 1500 px (0,78) fica a descrição. Lateral direita (> 920 px) tem os botões.
- Rosto: idealmente entre 0,25 e 0,55 da altura.
