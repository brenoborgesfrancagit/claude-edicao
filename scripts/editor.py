#!/usr/bin/env python3
"""editor.py: motor da skill claude-edicao.

Transforma um vídeo bruto (pessoa falando para a câmera) num vídeo vertical pronto para Reels e TikTok:
corta pausas, vícios e trechos errados, reenquadra para 9:16, mantém a imagem sempre em movimento
(zoom lento + "punch-in" a cada corte), queima legendas animadas palavra por palavra, títulos de gancho,
inserções de motion graphics e barra de progresso, e normaliza o áudio para as redes.

Subcomandos (rode com o wrapper `scripts/ed`, que usa o Python com o faster-whisper):
  info        <video>                          dados do arquivo
  transcrever <video> [--pasta P] [--modelo M] transcrição palavra por palavra (palavras.json, transcricao.txt)
  plano       [--pasta P] [opções]             decide os cortes e escreve plano.json + transcricao-editada.txt
  render      [--pasta P] [--rapido]           monta o vídeo final a partir do plano.json
  quadros     <video> [--saida PNG] [--n N]    folha de contato com N quadros para conferir
"""
import argparse, json, math, os, re, shutil, subprocess, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTES = os.path.join(SKILL, "fontes")
W, H = 1080, 1920

# Hesitações: sempre cortadas. "é", "e", "ah" sozinhos só são vício quando vêm com reticências ou isolados por
# pausas (senão é o verbo "é"). "né", "tipo", "assim"... só com --agressivo (às vezes têm sentido).
VICIOS = {"éé", "ééé", "eee", "ãh", "ãã", "ããã", "ahn", "aham", "hum", "humm", "hmm", "hm", "uh", "uhm", "um", "er", "hã", "hãã", "eh", "ehh"}
VICIOS_AMBIGUOS = {"é", "e", "ah", "ã", "a", "o"}
VICIOS_AGRESSIVO = {"né", "tipo", "assim", "então", "enfim", "basicamente", "sabe", "entendeu", "olha", "bom", "beleza"}


# ---------------------------------------------------------------- utilidades
def rodar(cmd, quieto=True):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.stderr.write("\n".join(r.stderr.strip().splitlines()[-25:]) + "\n")
        raise SystemExit(f"Falhou: {' '.join(cmd[:6])} ...")
    return r


def info(video):
    r = rodar(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", video])
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise SystemExit("O arquivo não tem vídeo.")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = int(v.get("tags", {}).get("rotate", rot))
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    if not (10 <= fps <= 121):
        fps = 30.0
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    return {"largura": w, "altura": h, "fps": round(fps, 3), "duracao": round(dur, 3), "tem_audio": a is not None}


def norm(p):
    p = p.lower().strip()
    p = re.sub(r"[^\wà-ÿ]+", "", p)
    return p


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def ler_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def fmt_t(t):
    m, s = divmod(max(t, 0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def intervalos(texto):
    """'1.5-3.2, 10-12.4' -> [(1.5,3.2),(10,12.4)]. Aceita mm:ss.xx."""
    out = []
    if not texto:
        return out
    for parte in re.split(r"[,;]\s*", texto.strip()):
        if not parte:
            continue
        a, b = parte.split("-")
        out.append((seg(a), seg(b)))
    return out


def seg(x):
    x = x.strip()
    if ":" in x:
        m, s = x.split(":")
        return int(m) * 60 + float(s)
    return float(x)


# ---------------------------------------------------------------- transcrever
# Prompts com hesitações fazem o Whisper escrever os "é...", "ãh" e repetições em vez de escondê-los.
PROMPT_LONGO = "Então, é... ãh, tipo, eu acho que, hum, né? É isso aí. Bom, ééé, vamos lá."
PROMPT_LITERAL = "Transcrição literal, com repetições e hesitações: o, o segundo, é... é, eu eu acho, ãh, hum."


def suspeita(p, ultima=False):
    return (p["fim"] - p["ini"] > 0.8 and not ultima) or p["p"] < 0.45


def cmd_transcrever(a):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("faster-whisper não está instalado. Rode: bash " + os.path.join(SKILL, "instalar.sh"))
    os.makedirs(a.pasta, exist_ok=True)
    meta = info(a.video)
    wav = os.path.join(a.pasta, "audio16k.wav")
    rodar(["ffmpeg", "-y", "-v", "error", "-i", a.video, "-vn", "-ac", "1", "-ar", "16000", wav])
    print(f"Transcrevendo com o modelo '{a.modelo}' (a primeira vez baixa o modelo; pode demorar)...", flush=True)
    modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    # O prompt inicial com hesitações faz o Whisper escrever os "é...", "ãh" em vez de escondê-los.
    prompt = PROMPT_LONGO
    import wave, numpy as np  # lê o WAV direto: evita depender da versão do PyAV
    with wave.open(wav, "rb") as wf:
        amostras = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, inf = modelo.transcribe(amostras, language=a.idioma, word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False, initial_prompt=prompt, beam_size=5)
    brutas = []  # lista de frases; cada frase é lista de palavras (dicts sem índice)
    for sg in segs:
        ws = [{"w": w.word.strip(), "ini": round(w.start, 3), "fim": round(w.end, 3), "p": round(w.probability, 3)}
              for w in (sg.words or []) if w.word.strip()]
        if ws:
            brutas.append(ws)
        print(f"  {fmt_t(sg.end)} / {fmt_t(meta['duracao'])}", end="\r", flush=True)
    print()
    # revisão: frase com palavra suspeita (longa demais ou de baixa confiança) é re-transcrita sozinha.
    # Na transcrição longa o Whisper costuma "limpar" repetições e regravações; sozinha, ela aparece.
    revistas = 0
    for k, ws in enumerate(brutas):
        if not any(suspeita(w, j == len(ws) - 1) for j, w in enumerate(ws)):
            continue
        i0, i1 = max(0.0, ws[0]["ini"] - 0.3), ws[-1]["fim"] + 0.3
        pedaco = amostras[int(i0 * 16000):int(i1 * 16000)]
        sub, _ = modelo.transcribe(pedaco, language=a.idioma, word_timestamps=True, condition_on_previous_text=False,
                                   beam_size=5, initial_prompt=PROMPT_LITERAL)
        novas = [{"w": w.word.strip(), "ini": round(w.start + i0, 3), "fim": round(w.end + i0, 3),
                  "p": round(w.probability, 3)} for sg in sub for w in (sg.words or []) if w.word.strip()]
        if len(novas) > len(ws):
            brutas[k] = novas
            revistas += 1
    if revistas:
        print(f"Revisão: {revistas} frase(s) re-transcritas revelaram fala escondida (repetições/hesitações).")
    palavras, frases = [], []
    for ws in brutas:
        ids = []
        for w in ws:
            w["i"] = len(palavras)
            palavras.append(w)
            ids.append(w["i"])
        frases.append({"ini": palavras[ids[0]]["ini"], "fim": palavras[ids[-1]]["fim"], "ids": ids,
                       "texto": " ".join(palavras[i]["w"] for i in ids)})
    gravar_json(os.path.join(a.pasta, "palavras.json"), {"video": os.path.abspath(a.video), "info": meta,
                                                          "idioma": inf.language, "palavras": palavras, "frases": frases})
    escrever_transcricao(os.path.join(a.pasta, "transcricao.txt"), palavras, frases)
    os.remove(wav)
    print(f"Pronto: {len(palavras)} palavras. Veja {os.path.join(a.pasta, 'transcricao.txt')}")


def escrever_transcricao(caminho, palavras, frases):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Transcrição do BRUTO (tempo do vídeo original). Formato: [inicio-fim] texto com #índice a cada palavra\n")
        f.write("# Use os índices em  plano --cortar-palavras 12-30  ou os tempos em  --cortar 10.2-14.8\n")
        f.write("# ⚠ = palavra longa demais ou de baixa confiança: pode esconder repetição/erro. Confira com  ed trecho\n\n")
        for fr in frases:
            def marca(i):
                p = palavras[i]
                return f"{p['w']}#{i}" + ("⚠" if suspeita(p, i == fr["ids"][-1]) else "")
            corpo = " ".join(marca(i) for i in fr["ids"])
            f.write(f"[{fmt_t(fr['ini'])}-{fmt_t(fr['fim'])}] {corpo}\n")


# ---------------------------------------------------------------- plano (cortes)
def ilhas_de_som(video, limiar=None, sil_min=0.20):
    """Mede o áudio em janelas de 20 ms e devolve (ilhas, limiar_usado): trechos com som separados por
    silêncios de pelo menos sil_min. O limiar se adapta ao ruído de fundo de cada gravação."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    jan = 320
    n = len(x) // jan
    if n == 0:
        return [], limiar
    rms = np.sqrt(np.mean(x[: n * jan].reshape(n, jan) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    if limiar is None:
        chao, fala = np.percentile(db, 10), np.percentile(db, 95)
        limiar = float(min(max(chao + 0.3 * (fala - chao), chao + 6), fala - 12))
        limiar = max(limiar, -58.0)  # gravações com silêncio digital absoluto não puxam o limiar para baixo demais
    voz = db > limiar
    ilhas, k = [], 0
    while k < n:
        if voz[k]:
            j = k
            while j < n and voz[j]:
                j += 1
            ilhas.append([k * 0.02, j * 0.02])
            k = j
        else:
            k += 1
    # silêncios mais curtos que sil_min não separam ilhas; estalos menores que 60 ms somem
    juntas = []
    for il in ilhas:
        if juntas and il[0] - juntas[-1][1] < sil_min:
            juntas[-1][1] = il[1]
        else:
            juntas.append(il)
    return [(round(a, 3), round(b, 3)) for a, b in juntas if b - a >= 0.06], round(limiar, 1)


def subtrair(base, tira):
    res = []
    for a, b in base:
        pedacos = [(a, b)]
        for c, d in tira:
            novo = []
            for x, y in pedacos:
                if d <= x or c >= y:
                    novo.append((x, y))
                else:
                    if c > x:
                        novo.append((x, c))
                    if d < y:
                        novo.append((d, y))
            pedacos = novo
        res.extend(pedacos)
    return res


def juntar(iv, folga=0.0):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + folga:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cmd_plano(a):
    pw = ler_json(os.path.join(a.pasta, "palavras.json"))
    palavras, meta, video = pw["palavras"], pw["info"], pw["video"]
    fps, dur = meta["fps"], meta["duracao"]
    caminho_plano = os.path.join(a.pasta, "plano.json")
    antigo = ler_json(caminho_plano) if os.path.exists(caminho_plano) else {}

    vicios = set(VICIOS) | (VICIOS_AGRESSIVO if a.agressivo else set())
    vicios |= {norm(x) for x in (a.vicios or "").split(",") if x.strip()}
    removidas, motivos = set(), {}

    def remover(i, motivo):
        removidas.add(i)
        motivos.setdefault(motivo, []).append(palavras[i]["w"])

    for k, p in enumerate(palavras):
        n = norm(p["w"])
        antes = p["ini"] - palavras[k - 1]["fim"] if k > 0 else 9
        depois = palavras[k + 1]["ini"] - p["fim"] if k + 1 < len(palavras) else 9
        if n in vicios:
            remover(k, "vício")
        elif n in VICIOS_AMBIGUOS and ("..." in p["w"] or "…" in p["w"] or (antes > 0.3 and depois > 0.3)):
            remover(k, "vício")
    for x in (a.cortar_palavras or "").split(","):
        x = x.strip()
        if x:
            i, _, j = x.partition("-")
            for k in range(int(i), int(j or i) + 1):
                remover(k, "pedido")
    # regravações: uma sequência de 1 a 8 palavras repetida logo em seguida ("o segundo erro é, o segundo erro é
    # falar") fica só na última tentativa. Vícios já removidos no meio não contam.
    vivas = [p for p in palavras if p["i"] not in removidas]
    nv = [norm(p["w"]) for p in vivas]
    for n in range(8, 0, -1):
        k = 0
        while k + 2 * n <= len(vivas):
            bloco, seguinte = nv[k:k + n], nv[k + n:k + 2 * n]
            perto = vivas[k + n]["ini"] - vivas[k + n - 1]["fim"] < 1.5
            if all(bloco) and bloco == seguinte and perto and not any(p["i"] in removidas for p in vivas[k:k + 2 * n]) \
                    and (n > 1 or len(bloco[0]) > 1):
                for p in vivas[k:k + n]:
                    remover(p["i"], "regravação/repetição")
                k += n
            else:
                k += 1

    # 1) ilhas de som medidas no áudio; cada palavra é atribuída à ilha com que mais se sobrepõe (ou à mais próxima)
    if meta["tem_audio"]:
        ilhas, limiar = ilhas_de_som(video, a.limiar)
    else:
        ilhas, limiar = [(0.0, dur)], None
    donos = [[] for _ in ilhas]
    ilha_de = {}
    for p in palavras:
        melhor, nota = None, None
        for k, (x, y) in enumerate(ilhas):
            sob = min(y, p["fim"]) - max(x, p["ini"])
            dist = -sob if sob > 0 else max(x - p["fim"], p["ini"] - y)
            if nota is None or dist < nota:
                melhor, nota = k, dist
        if melhor is not None and nota < 0.6:
            donos[melhor].append(p)
            ilha_de[p["i"]] = melhor
    # 2) decide cada ilha: some se não tem palavra (hesitação não transcrita), se só tem vícios,
    #    ou se é um som curto com uma palavra só e de baixa confiança
    sons_cortados, decisao = [], []
    for (x, y), ws in zip(ilhas, donos):
        uteis = [w for w in ws if w["i"] not in removidas]
        corta = (not ws and y - x < a.som_max) or (ws and not uteis) or \
                (len(uteis) == 1 and uteis[0]["p"] < 0.5 and y - x < 0.6)
        decisao.append(not corta)
        if corta:
            sons_cortados.append((x, y))
    # 3) junta ilhas vizinhas mantidas quando a pausa entre elas é curta (respiro natural)
    manter = []
    for k, (x, y) in enumerate(ilhas):
        if not decisao[k]:
            continue
        x, y = max(0.0, x - a.folga), min(dur, y + a.folga * 1.5)
        vizinha_mantida = k > 0 and decisao[k - 1]
        if manter and vizinha_mantida and x - manter[-1][1] < a.pausa_max:
            manter[-1] = (manter[-1][0], y)
        else:
            manter.append((x, y))
    # 4) tira as palavras removidas e os trechos pedidos
    # cada palavra removida só pode cortar até as palavras mantidas vizinhas (os tempos do Whisper se sobrepõem)
    tira = []
    for i in sorted(removidas):
        ant = next((palavras[j]["fim"] for j in range(i - 1, -1, -1) if j not in removidas), 0.0)
        prox = next((palavras[j]["ini"] for j in range(i + 1, len(palavras)) if j not in removidas), dur)
        c, d = max(palavras[i]["ini"], ant), min(palavras[i]["fim"], prox)
        # se a palavra removida está em outra ilha de som, não invade a ilha da fala mantida vizinha
        ja = next((j for j in range(i - 1, -1, -1) if j not in removidas), None)
        jp = next((j for j in range(i + 1, len(palavras)) if j not in removidas), None)
        if jp is not None and ilha_de.get(jp) is not None and ilha_de.get(jp) != ilha_de.get(i):
            d = min(d, ilhas[ilha_de[jp]][0] - a.folga)
        if ja is not None and ilha_de.get(ja) is not None and ilha_de.get(ja) != ilha_de.get(i):
            c = max(c, ilhas[ilha_de[ja]][1] + a.folga * 1.5)
        k = ilha_de.get(i)
        if k is not None:
            x, y = ilhas[k]
            pi, pf = palavras[i]["ini"], palavras[i]["fim"]
            if (min(pf, y) - max(pi, x)) < 0.4 * (pf - pi):
                continue  # palavra "solta" no silêncio (tempo errado ou alucinação): não corta a fala de verdade
        if d - c > 0.03:
            tira.append((c, d))
    tira += intervalos(a.cortar)
    manter = subtrair(manter, tira)
    manter = [(x, y) for x, y in juntar(manter, folga=0.04) if y - x >= a.trecho_min]
    # 5) alinha à grade de quadros (assim áudio e vídeo nunca escorregam)
    q = 1.0 / fps
    alinhado = []
    for x, y in manter:
        x2, y2 = round(x / q) * q, round(y / q) * q
        if y2 - x2 >= 2 * q:
            alinhado.append((round(x2, 4), round(y2, 4)))
    if not alinhado:
        raise SystemExit("Nada sobrou depois dos cortes. Confira --limiar (talvez o áudio seja baixo) e --cortar.")

    segmentos = []
    gancho = intervalos(a.gancho)
    for x, y in gancho:
        segmentos.append({"ini": x, "fim": y, "gancho": True})
    for x, y in alinhado:
        segmentos.append({"ini": x, "fim": y})
    # zoom: alterna enquadramento a cada corte seco (esconde o pulo e cria ritmo)
    niveis = [1.0, a.zoom]
    k = 0
    for n, s in enumerate(segmentos):
        corte_seco = n > 0 and abs(s["ini"] - segmentos[n - 1]["fim"]) > 0.001
        if n > 0 and (corte_seco or s.get("gancho") or segmentos[n - 1].get("gancho")):
            k += 1
        s["zoom"] = niveis[k % 2]
        s["deriva"] = a.deriva

    marca = ler_marca(a.pasta)
    legendas_padrao = {"ligadas": True, "estilo": "pop", "max_palavras": 3, "destaques": [], "correcoes": {},
                       "cor": marca.get("cor_legenda", "#FFE14D"), "cor_destaque": marca.get("cor_destaque", "#3CFF8B"),
                       "tamanho": 96, "altura": 0.66, "maiusculas": True}
    plano = {
        "video": video,
        "info": meta,
        "formato": antigo.get("formato", a.formato),
        "enquadramento": antigo.get("enquadramento", a.enquadramento),
        "foco": antigo.get("foco", {"x": 0.5, "y": 0.4}),
        "legendas": antigo.get("legendas", legendas_padrao),
        "textos": antigo.get("textos", []),
        "insercoes": antigo.get("insercoes", []),
        "barra_progresso": antigo.get("barra_progresso", {"ligada": True, "cor": marca.get("cor_barra",
                                                                                        marca.get("cor_legenda", "#FFE14D"))}),
        "audio": antigo.get("audio", {"lufs": -14, "reduzir_ruido": True}),
        "parametros": {"pausa_max": a.pausa_max, "folga": a.folga, "limiar": a.limiar, "agressivo": a.agressivo,
                       "cortar": a.cortar, "cortar_palavras": a.cortar_palavras, "gancho": a.gancho},
        "palavras_removidas": sorted(removidas),
        "segmentos": segmentos,
    }
    # preserva zoom/foco ajustados à mão quando o segmento continua igual
    velhos = {(round(s["ini"], 2), round(s["fim"], 2)): s for s in antigo.get("segmentos", [])}
    for s in segmentos:
        v = velhos.get((round(s["ini"], 2), round(s["fim"], 2)))
        if v:
            for chave in ("zoom", "deriva", "foco"):
                if chave in v:
                    s[chave] = v[chave]
    gravar_json(caminho_plano, plano)
    final = escrever_editada(a.pasta, plano, palavras)
    if sons_cortados:
        motivos.setdefault("som sem palavra (hesitação)", []).extend(f"{fmt_t(x)}" for x, _ in sons_cortados)
    print(f"Limiar de silêncio: {limiar} dB")
    print(f"Bruto: {fmt_t(dur)}  ->  editado: {fmt_t(final)}  ({len(segmentos)} trechos, "
          f"{len(segmentos) - 1} cortes)")
    for m, lst in motivos.items():
        print(f"  cortado por {m}: " + ", ".join(lst[:30]) + (" ..." if len(lst) > 30 else ""))
    print(f"Plano: {caminho_plano}\nTexto final com tempos do vídeo editado: {os.path.join(a.pasta, 'transcricao-editada.txt')}")


def ler_marca(pasta):
    """marca.json da pessoa: na pasta de trabalho, na pasta de cima (onde ela guarda os vídeos) ou na atual."""
    for d in (pasta, os.path.dirname(os.path.abspath(pasta)), os.getcwd()):
        c = os.path.join(d, "marca.json")
        if os.path.exists(c):
            return ler_json(c)
    return {}


def mapa_tempo(segmentos):
    """lista de (ini_bruto, fim_bruto, ini_final)"""
    out, t = [], 0.0
    for s in segmentos:
        out.append((s["ini"], s["fim"], t))
        t += s["fim"] - s["ini"]
    return out, t


def palavras_finais(plano, palavras):
    """Palavras mantidas com tempos no vídeo editado (uma palavra pode aparecer 2x se estiver no gancho).
    Palavras com tempo impreciso (comum no Whisper perto de pausas) são encaixadas no trecho mais próximo."""
    mapa, _ = mapa_tempo(plano["segmentos"])
    removidas = set(plano.get("palavras_removidas", []))
    out, usadas = [], set()

    def por(p, a0, b0, t0, n):
        ini = t0 + min(max(p["ini"], a0), b0 - 0.05) - a0
        fim = t0 + max(min(p["fim"], b0), a0 + 0.05) - a0
        out.append({"i": p["i"], "w": p["w"], "ini": round(ini, 3), "fim": round(max(fim, ini + 0.05), 3)})
        usadas.add((p["i"], n))

    for n, (a0, b0, t0) in enumerate(mapa):
        for p in palavras:
            if p["i"] not in removidas and min(p["fim"], b0) - max(p["ini"], a0) > 0.02:
                if not any((p["i"], m) in usadas for m in range(n) if not plano["segmentos"][m].get("gancho")) \
                        or plano["segmentos"][n].get("gancho"):
                    por(p, a0, b0, t0, n)
    vistas = {i for i, n in usadas if not plano["segmentos"][n].get("gancho")}
    for p in palavras:
        if p["i"] in removidas or p["i"] in vistas:
            continue
        melhor = None
        for n, (a0, b0, t0) in enumerate(mapa):
            if plano["segmentos"][n].get("gancho"):
                continue
            d = max(a0 - p["fim"], p["ini"] - b0, 0)
            if d < 0.7 and (melhor is None or d < melhor[0]):
                melhor = (d, n)
        if melhor:
            a0, b0, t0 = mapa[melhor[1]]
            por(p, a0, b0, t0, melhor[1])
    out.sort(key=lambda p: (p["ini"], p["i"]))
    # mantém a ordem das palavras e evita sobreposição
    for k in range(1, len(out)):
        if out[k]["ini"] < out[k - 1]["ini"] + 0.04 and out[k]["i"] > out[k - 1]["i"]:
            out[k]["ini"] = round(out[k - 1]["ini"] + 0.04, 3)
            out[k]["fim"] = max(out[k]["fim"], out[k]["ini"] + 0.05)
    return out


def escrever_editada(pasta, plano, palavras):
    pf = palavras_finais(plano, palavras)
    _, total = mapa_tempo(plano["segmentos"])
    with open(os.path.join(pasta, "transcricao-editada.txt"), "w", encoding="utf-8") as f:
        f.write(f"# Texto do vídeo EDITADO (tempos já no vídeo final, duração {fmt_t(total)}).\n"
                "# Use estes tempos para 'textos' e 'insercoes' no plano.json.\n\n")
        linha, ini = [], None
        for k, p in enumerate(pf):
            if ini is None:
                ini = p["ini"]
            linha.append(p["w"])
            fim_frase = re.search(r"[.!?]$", p["w"]) or len(linha) >= 14 or k == len(pf) - 1
            if fim_frase:
                f.write(f"[{fmt_t(ini)}-{fmt_t(p['fim'])}] {' '.join(linha)}\n")
                linha, ini = [], None
    return total


# ---------------------------------------------------------------- legendas e títulos (ASS)
def cor_ass(hexcor, alpha=0):
    h = hexcor.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def t_ass(t):
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    cs = int(round((s - int(s)) * 100))
    if cs == 100:
        cs = 99
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def esc_ass(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def gerar_ass(plano, palavras, caminho, total):
    lg = plano["legendas"]
    tamanho = int(lg.get("tamanho", 96))
    y_leg = int(H * float(lg.get("altura", 0.66)))
    branco, preto = cor_ass("#FFFFFF"), cor_ass("#000000")
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Leg,Montserrat Black,{tamanho},{branco},{branco},{preto},{cor_ass('#000000', 0x60)},0,0,0,0,100,100,0,0,1,7,4,5,60,60,0,1",
        f"Style: Tit,Anton,118,{branco},{branco},{cor_ass('#111111')},{cor_ass('#000000', 0x80)},0,0,0,0,100,100,1,0,3,22,0,5,70,70,0,1",
        f"Style: Sub,Montserrat ExtraBold,60,{branco},{branco},{preto},{cor_ass('#000000', 0x60)},0,0,0,0,100,100,0,0,1,6,3,5,70,70,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []
    if lg.get("ligadas", True):
        pf = palavras_finais(plano, palavras)
        destaques = {sem_acento(norm(x)) for x in lg.get("destaques", [])}
        correcoes = {norm(k): v for k, v in lg.get("correcoes", {}).items()}
        maxp = int(lg.get("max_palavras", 3))
        blocos, atual = [], []
        for k, p in enumerate(pf):
            if atual and (len(atual) >= maxp or p["ini"] - atual[-1]["fim"] > 0.45
                          or sum(len(x["w"]) for x in atual) + len(p["w"]) > 18):
                blocos.append(atual)
                atual = []
            atual.append(p)
            if re.search(r"[.!?,:;]$", p["w"]):
                blocos.append(atual)
                atual = []
        if atual:
            blocos.append(atual)
        escondida = [(float(i["em"]), float(i["em"]) + float(i.get("dur") or 0)) for i in plano.get("insercoes", [])
                     if i.get("legenda") is False]
        cor_ativa, cor_dest = cor_ass(lg.get("cor", "#FFE14D")), cor_ass(lg.get("cor_destaque", "#3CFF8B"))
        for b, bloco in enumerate(blocos):
            fim_bloco = bloco[-1]["fim"] + 0.25
            if b + 1 < len(blocos):
                fim_bloco = min(fim_bloco, blocos[b + 1][0]["ini"])
            for j, p in enumerate(bloco):
                ini = bloco[0]["ini"] if j == 0 else p["ini"]
                fim = bloco[j + 1]["ini"] if j + 1 < len(bloco) else fim_bloco
                if fim - ini < 0.02 or any(x <= ini < y for x, y in escondida):
                    continue
                partes = []
                for m, q in enumerate(bloco):
                    txt = re.sub(r"[.,;:]+$", "", q["w"])
                    txt = correcoes.get(norm(txt), txt)
                    txt = txt.upper() if lg.get("maiusculas", True) else txt
                    txt = esc_ass(txt)
                    dest = sem_acento(norm(q["w"])) in destaques
                    if m == j:
                        cor = cor_dest if dest else cor_ativa
                        partes.append(f"{{\\c{cor}\\fscx118\\fscy118\\t(0,90,\\fscx100\\fscy100)}}{txt}{{\\r}}")
                    elif dest:
                        partes.append(f"{{\\c{cor_dest}}}{txt}{{\\r}}")
                    else:
                        partes.append(txt)
                entrada = "{\\fscx70\\fscy70\\t(0,110,\\fscx100\\fscy100)}" if j == 0 else ""
                ev.append(f"Dialogue: 1,{t_ass(ini)},{t_ass(fim)},Leg,,0,0,0,,{{\\an5\\pos({W // 2},{y_leg})}}{entrada}"
                          + " ".join(partes))
    for tx in plano.get("textos", []):
        estilo = "Sub" if tx.get("estilo") == "sub" else "Tit"
        y = int(H * float(tx.get("altura", 0.2)))
        cor = cor_ass(tx.get("cor", "#FFFFFF"))
        fundo = cor_ass(tx.get("fundo", "#111111"))
        txt = esc_ass(tx["texto"]).replace("\n", "\\N")
        anim = ("{\\an5\\pos(%d,%d)\\c%s\\3c%s\\fscx40\\fscy40\\t(0,140,\\fscx110\\fscy110)"
                "\\t(140,240,\\fscx100\\fscy100)\\fad(90,160)}" % (W // 2, y, cor, fundo))
        ev.append(f"Dialogue: 2,{t_ass(tx['ini'])},{t_ass(min(tx['fim'], total))},{estilo},,0,0,0,,{anim}{txt}")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas + ev) + "\n")


# ---------------------------------------------------------------- render
def cadeia_video(plano, s, dur):
    """Filtro de um trecho: reenquadra para 9:16 com zoom e deriva lenta (imagem nunca fica parada)."""
    meta = plano["info"]
    sw, sh = meta["largura"], meta["altura"]
    z0 = float(s.get("zoom", 1.0))
    dz = float(s.get("deriva", 0.03))
    foco = s.get("foco", plano.get("foco", {"x": 0.5, "y": 0.4}))
    fx, fy = float(foco.get("x", 0.5)), float(foco.get("y", 0.4))
    zexpr = f"({z0}+{dz}*t/{max(dur, 0.01):.4f})"
    modo = plano.get("enquadramento", "auto")
    if modo == "auto":  # pessoa falando: cortar no rosto ocupa a tela toda (o melhor para retenção)
        modo = "cortar"
    if modo == "cortar":
        esc = max(W / sw, H / sh)
        cw, ch = sw * esc, sh * esc
        return (f"scale=w='trunc({cw:.1f}*{zexpr}/2)*2':h='trunc({ch:.1f}*{zexpr}/2)*2':eval=frame:flags=bicubic,"
                f"crop={W}:{H}:x='(iw-{W})*{fx}':y='(ih-{H})*{fy}',setsar=1")
    # desfoque: vídeo horizontal inteiro no meio, fundo desfocado preenchendo 9:16
    esc = W / sw * 1.0
    fw, fh = sw * esc, sh * esc
    bg_esc = max(W / sw, H / sh)
    return (f"split=2[bg][fg];[bg]scale={int(sw * bg_esc / 2 + 1) * 2}:{int(sh * bg_esc / 2 + 1) * 2},crop={W}:{H},"
            f"boxblur=28:2,eq=brightness=-0.12:saturation=1.15[bgo];"
            f"[fg]scale=w='trunc({fw:.1f}*{zexpr}*1.12/2)*2':h='trunc({fh:.1f}*{zexpr}*1.12/2)*2':eval=frame,"
            f"crop=w='min(iw,{W})':h='min(ih,{int(H * 0.62)})':x='(iw-ow)*{fx}':y='(ih-oh)*{fy}'[fgo];"
            f"[bgo][fgo]overlay=x='(W-w)/2':y='(H-h)/2-{int(H * 0.04)}',setsar=1")


def render_trecho(args):
    plano, s, n, pasta, fps, crf, preset = args
    dur = s["fim"] - s["ini"]
    saida = os.path.join(pasta, "trechos", f"t{n:04d}.mkv")
    vf = cadeia_video(plano, s, dur)
    af = f"afade=t=in:d=0.012,afade=t=out:st={max(dur - 0.015, 0):.4f}:d=0.015"
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{s['ini']:.4f}", "-i", plano["video"], "-t", f"{dur:.4f}",
           "-filter_complex", f"[0:v]{vf},fps={fps}[v]", "-map", "[v]"]
    if plano["info"]["tem_audio"]:
        cmd += ["-map", "0:a:0", "-af", af, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", saida]
    rodar(cmd)
    return saida


def cmd_render(a):
    plano = ler_json(os.path.join(a.pasta, "plano.json"))
    pw = ler_json(os.path.join(a.pasta, "palavras.json"))
    fps = min(round(plano["info"]["fps"]), 60) or 30
    _, total = mapa_tempo(plano["segmentos"])
    tdir = os.path.join(a.pasta, "trechos")
    shutil.rmtree(tdir, ignore_errors=True)
    os.makedirs(tdir)
    crf, preset = (24, "ultrafast") if a.rapido else (14, "veryfast")
    print(f"Montando {len(plano['segmentos'])} trechos ({fmt_t(total)})...", flush=True)
    tarefas = [(plano, s, n, a.pasta, fps, crf, preset) for n, s in enumerate(plano["segmentos"])]
    with ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) // 2)) as ex:
        arquivos = list(ex.map(render_trecho, tarefas))
    lista = os.path.join(tdir, "lista.txt")
    with open(lista, "w") as f:
        for arq in arquivos:
            f.write(f"file '{os.path.abspath(arq)}'\n")
    for ins in plano.get("insercoes", []):  # completa a duração das inserções (usada também pelas legendas)
        arq = ins["arquivo"] if os.path.isabs(ins["arquivo"]) else os.path.join(a.pasta, ins["arquivo"])
        if not os.path.exists(arq):
            raise SystemExit(f"Inserção não encontrada: {arq}")
        if not ins.get("dur"):
            ins["dur"] = info(arq)["duracao"]
    ass = os.path.join(a.pasta, "legendas.ass")
    gerar_ass(plano, pw["palavras"], ass, total)

    entradas = ["-f", "concat", "-safe", "0", "-i", lista]
    fc, base = [], "[0:v]"
    for k, ins in enumerate(plano.get("insercoes", [])):
        arq = ins["arquivo"]
        if not os.path.isabs(arq):
            arq = os.path.join(a.pasta, arq)
        if not os.path.exists(arq):
            raise SystemExit(f"Inserção não encontrada: {arq}")
        entradas += ["-i", arq]
        em = float(ins["em"])
        d = float(ins.get("dur") or info(arq)["duracao"])
        idx = k + 1
        if ins.get("modo", "tela-cheia") == "janela":
            larg = int(W * float(ins.get("largura", 0.86)) / 2) * 2
            y = int(H * float(ins.get("altura", 0.1)))
            fc.append(f"[{idx}:v]trim=0:{d},setpts=PTS-STARTPTS+{em}/TB,scale={larg}:-2,fps={fps}[i{k}]")
            pos = f"x=(W-w)/2:y={y}"
        else:
            fc.append(f"[{idx}:v]trim=0:{d},setpts=PTS-STARTPTS+{em}/TB,scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},setsar=1,fps={fps}[i{k}]")
            pos = "x=0:y=0"
        fc.append(f"{base}[i{k}]overlay={pos}:enable='between(t,{em},{em + d})':eof_action=pass[b{k}]")
        base = f"[b{k}]"
    ass_esc = ass.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fontes_esc = FONTES.replace(":", "\\:").replace("'", "\\'")
    cadeia = f"{base}ass='{ass_esc}':fontsdir='{fontes_esc}'"
    bp = plano.get("barra_progresso", {})
    if bp.get("ligada", True):
        cadeia += (f",drawbox=x=0:y=0:w='{W}*t/{total:.3f}':h=12:color={bp.get('cor', '#FFE14D').replace('#', '0x')}@0.95:t=fill")
    fc.append(cadeia + ",format=yuv420p[v]")
    au = plano.get("audio", {})
    afiltros = ["highpass=f=70"]
    if au.get("reduzir_ruido", True):
        afiltros.append("afftdn=nf=-28")
    afiltros.append(f"loudnorm=I={au.get('lufs', -14)}:TP=-1.5:LRA=11")
    afiltros.append("aresample=48000")
    saida = a.saida or os.path.join(a.pasta, "previa.mp4" if a.rapido else "final.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats"] + entradas + ["-filter_complex", ";".join(fc), "-map", "[v]"]
    if plano["info"]["tem_audio"]:
        cmd += ["-map", "0:a", "-af", ",".join(afiltros), "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast" if a.rapido else "medium", "-crf", "26" if a.rapido else "18",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", "-t", f"{total:.3f}", saida]
    print("Juntando, legendando e mixando o áudio...", flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("Falhou a montagem final.")
    if not a.manter_trechos:
        shutil.rmtree(tdir, ignore_errors=True)
    m = info(saida)
    print(f"Pronto: {saida}  ({m['largura']}x{m['altura']}, {m['fps']} fps, {fmt_t(m['duracao'])})")


# ---------------------------------------------------------------- trecho (conferir um pedaço)
def cmd_trecho(a):
    """Re-transcreve só uma janela do bruto, pedindo transcrição literal. Revela repetições que o Whisper
    escondeu na transcrição longa. Imprime palavras com tempo absoluto do bruto."""
    from faster_whisper import WhisperModel
    import wave, numpy as np
    ini, fim = seg(a.ini), seg(a.fim)
    pw = ler_json(os.path.join(a.pasta, "palavras.json"))
    tmp = os.path.join(a.pasta, "_trecho.wav")
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini}", "-to", f"{fim}", "-i", pw["video"], "-vn", "-ac", "1",
           "-ar", "16000", tmp])
    with wave.open(tmp, "rb") as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    os.remove(tmp)
    m = WhisperModel(a.modelo, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    segs, _ = m.transcribe(x, language=a.idioma, word_timestamps=True, condition_on_previous_text=False, beam_size=5,
                           initial_prompt=PROMPT_LITERAL)
    for s in segs:
        for w in s.words or []:
            print(f"{w.start + ini:8.2f}-{w.end + ini:6.2f}  {w.word.strip()}  ({w.probability:.2f})")


# ---------------------------------------------------------------- quadros
def cmd_quadros(a):
    m = info(a.video)
    n = a.n
    cols = 6 if m["altura"] > m["largura"] else 4
    linhas = math.ceil(n / cols)
    passo = m["duracao"] / n
    saida = a.saida or os.path.splitext(a.video)[0] + "-quadros.png"
    larg = 220 if m["altura"] > m["largura"] else 400
    vf = (f"fps=1/{passo:.4f},scale={larg}:-2,drawtext=fontfile='{os.path.join(FONTES, 'Montserrat-ExtraBold.ttf')}':"
          f"text='%{{pts\\:hms}}':x=6:y=6:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6,tile={cols}x{linhas}:padding=4")
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{passo / 2:.3f}", "-i", a.video, "-vf", vf, "-frames:v", "1", saida])
    print(saida)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("video")
    p = sub.add_parser("transcrever"); p.add_argument("video"); p.add_argument("--pasta", default=".")
    p.add_argument("--modelo", default="medium", help="tiny, base, small, medium, large-v3 (maior = melhor e mais lento)")
    p.add_argument("--idioma", default="pt")
    p = sub.add_parser("plano"); p.add_argument("--pasta", default=".")
    p.add_argument("--pausa-max", type=float, default=0.30, help="pausas maiores que isto (s) são cortadas")
    p.add_argument("--folga", type=float, default=0.06, help="respiro antes/depois de cada fala (s)")
    p.add_argument("--limiar", type=float, default=None, help="dB abaixo do qual é silêncio (padrão: automático)")
    p.add_argument("--som-max", type=float, default=0.9, help="som sem palavra menor que isto (s) é tratado como hesitação")
    p.add_argument("--agressivo", action="store_true", help="corta também né, tipo, assim, então...")
    p.add_argument("--vicios", help="palavras extras para cortar, separadas por vírgula")
    p.add_argument("--cortar", help="trechos do bruto para remover: '12.3-15.8, 1:02-1:07.5'")
    p.add_argument("--cortar-palavras", help="índices de palavras para remover: '40-63, 88'")
    p.add_argument("--gancho", help="trecho do bruto repetido no início como gancho: '45.2-48.9'")
    p.add_argument("--zoom", type=float, default=1.14, help="zoom do punch-in nos cortes")
    p.add_argument("--deriva", type=float, default=0.035, help="zoom lento contínuo dentro de cada trecho")
    p.add_argument("--trecho-min", type=float, default=0.22)
    p.add_argument("--formato", default="9:16")
    p.add_argument("--enquadramento", default="auto", choices=["auto", "cortar", "desfoque"])
    p = sub.add_parser("render"); p.add_argument("--pasta", default=".")
    p.add_argument("--rapido", action="store_true", help="prévia rápida em baixa qualidade")
    p.add_argument("--saida"); p.add_argument("--manter-trechos", action="store_true")
    p = sub.add_parser("trecho"); p.add_argument("ini"); p.add_argument("fim"); p.add_argument("--pasta", default=".")
    p.add_argument("--modelo", default="medium"); p.add_argument("--idioma", default="pt")
    p = sub.add_parser("quadros"); p.add_argument("video"); p.add_argument("--saida"); p.add_argument("--n", type=int, default=24)
    a = ap.parse_args()
    if a.cmd == "info":
        print(json.dumps(info(a.video), indent=2))
    else:
        {"transcrever": cmd_transcrever, "plano": cmd_plano, "trecho": cmd_trecho, "render": cmd_render, "quadros": cmd_quadros}[a.cmd](a)


if __name__ == "__main__":
    main()
