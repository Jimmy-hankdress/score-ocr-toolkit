# -*- coding: utf-8 -*-
"""
網頁歌譜網址抓取與解析模組（支援 jianpu.space / je.js 簡譜格式、通用簡譜網頁與直連檔案）。
"""
from __future__ import annotations

import html as html_mod
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Any

from ..models import ScoreDocument
from ..omr.scoreforge_engine import scoreforge_to_document


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def tokenize_je_lyric(line: str) -> list[str]:
    """依 jianpu.space (je.js) 規則將 `L:` 歌詞行切分為對位 token 列表。

    規則：
    - `_` 或 `*` 單獨出現時代表佔位符（消耗一個有音高音符但不顯示文字）
    - `"..."` 雙引號內視為單一音符的多字詞
    - 中日韓漢字每字一 token（標點符號附著在該字後）
    - 英文／拉丁字母以空白分詞，連字號 `-` 切分音節並保留在前半音節末（如 `hap-py` -> `hap-`, `py`）
    """
    s = line.strip()
    if s.startswith("L:") or s.startswith("l:"):
        s = s[2:].strip()

    tokens: list[str] = []
    i = 0
    n = len(s)

    def _is_cjk(ch: str) -> bool:
        cp = ord(ch)
        return (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0xF900 <= cp <= 0xFAFF
            or 0x3040 <= cp <= 0x30FF
        )

    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '"':
            end_q = s.find('"', i + 1)
            if end_q != -1:
                tokens.append(s[i + 1 : end_q].strip())
                i = end_q + 1
                continue
        if ch in ("_", "*"):
            tokens.append("")
            i += 1
            continue
        if _is_cjk(ch):
            tok = ch
            i += 1
            while i < n and s[i] in "，。、！？；：,.!?;:’”」』":
                tok += s[i]
                i += 1
            tokens.append(tok)
            continue

        # 拉丁／數字／符號構成的音節或單字
        buf = []
        while i < n and not s[i].isspace() and not _is_cjk(s[i]) and s[i] not in ('"', "_"):
            c = s[i]
            buf.append(c)
            i += 1
            if c == "-":
                break
        word = "".join(buf)
        if word:
            tokens.append(word)

    return tokens


_NOTE_TOKEN_RE = re.compile(
    r"(?P<bar>\|\||\|\]|\|\:|\:\||\|)"
    r"|(?P<chord>\[[^\]]+\])"
    r"|(?P<lparen>\()"
    r"|(?P<rparen>\))"
    r"|(?P<note>"
    r"(?P<acc>##|bb|#|b|n)?"
    r"(?P<step>[0-7\-])"
    r"(?P<oct>['’,，]*)"
    r"(?:(?P<dashes>-+)|(?:(?P<unders>[=_]+)?(?P<dots>\.{1,2})?))"
    r")"
)


def parse_je_score_text(
    raw_text: str,
    title: str = "網頁匯入樂譜",
    composer: str = "",
) -> dict[str, Any]:
    """將 jianpu.space (je.js) 簡譜純文字解析為 ScoreForge 結構 JSON。"""
    key_sig = "C"
    time_sig = "4/4"
    tempo_bpm = 90

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    # 先收集所有音符小節與所有歌詞 token，依 je.js 全域順序配對
    raw_measures: list[dict[str, Any]] = []
    current_notes: list[dict[str, Any]] = []
    current_chords: list[dict[str, Any]] = []
    acc_beat = 0.0
    lyric_pool: list[str] = []
    in_slur = False

    def _flush_measure() -> None:
        nonlocal current_notes, current_chords, acc_beat
        if current_notes or current_chords:
            raw_measures.append({
                "chords": current_chords,
                "notes": current_notes,
            })
            current_notes = []
            current_chords = []
            acc_beat = 0.0

    for line in lines:
        norm_line = unicodedata.normalize("NFKC", line).strip()
        if not norm_line:
            continue

        # 歌詞行
        if norm_line.startswith("L:") or norm_line.startswith("l:"):
            lyric_pool.extend(tokenize_je_lyric(line))
            continue

        # 解析調號 /key(E3) 或 1=E
        m_key = re.search(r"/key\(\s*([A-Ga-g][#b]?)\d*\s*\)", norm_line)
        if not m_key:
            m_key = re.search(r"1\s*=\s*([A-Ga-g][#b]?)", norm_line)
        if m_key:
            raw_k = m_key.group(1)
            key_sig = raw_k[0].upper() + raw_k[1:]

        # 解析拍號 /metre(3/4) 或 4/4
        m_time = re.search(r"/metre\(\s*(\d+\s*/\s*\d+)\s*\)", norm_line)
        if not m_time:
            m_time = re.search(r"(?:^|\s)([23468]\s*/\s*[248])(?:\s|$)", norm_line)
        if m_time:
            time_sig = m_time.group(1).replace(" ", "")

        # 解析速度 bpm82.9
        m_bpm = re.search(r"bpm\s*(\d+(?:\.\d+)?)", norm_line, re.IGNORECASE)
        if m_bpm:
            try:
                tempo_bpm = max(30, min(260, int(round(float(m_bpm.group(1))))))
            except ValueError:
                pass

        # 移除指令標記後檢查是否含有簡譜音符或小節線
        clean_note_line = re.sub(r"/[a-zA-Z]+\([^)]*\)", " ", norm_line)
        clean_note_line = re.sub(r"bpm\s*\d+(?:\.\d+)?", " ", clean_note_line, flags=re.IGNORECASE)
        clean_note_line = re.sub(r"1\s*=\s*[A-Ga-g][#b]?", " ", clean_note_line)
        if "|" not in clean_note_line and not re.search(r"[0-7]", clean_note_line):
            continue

        for match in _NOTE_TOKEN_RE.finditer(clean_note_line):
            if match.group("bar"):
                _flush_measure()
                continue
            if match.group("chord"):
                cname = match.group("chord")[1:-1].strip()
                if cname:
                    current_chords.append({
                        "symbol": cname,
                        "beat": round(acc_beat, 3),
                    })
                continue
            if match.group("lparen"):
                in_slur = True
                continue
            if match.group("rparen"):
                in_slur = False
                continue
            if match.group("note"):
                acc_raw = match.group("acc") or ""
                step_ch = match.group("step")
                oct_raw = match.group("oct") or ""
                dashes = match.group("dashes") or ""
                unders = match.group("unders") or ""
                dots = match.group("dots") or ""

                # 計算八度位移
                oct_shift = 0
                for c in oct_raw:
                    if c in ("'", "’"):
                        oct_shift += 1
                    elif c in (",", "，"):
                        oct_shift -= 1

                # 計算拍長：beat = (0.5 ** type) * mul * (2 - 0.5 ** dots)
                mul = 1 + len(dashes)
                u_type = 0
                if mul == 1 and unders:
                    for c in unders:
                        if c == "=":
                            u_type += 2
                        elif c == "_":
                            u_type += 1
                dot_cnt = len(dots) if mul == 1 else 0
                dur_beats = (0.5 ** u_type) * mul * (2.0 - (0.5 ** dot_cnt))

                acc_val = None
                if acc_raw in ("#", "##"):
                    acc_val = "#"
                elif acc_raw in ("b", "bb"):
                    acc_val = "b"

                if step_ch == "-":
                    current_notes.append({
                        "degree": None,
                        "octave": 0,
                        "accidental": None,
                        "durationBeats": dur_beats,
                        "dotted": dot_cnt > 0,
                        "rest": False,
                        "dash": True,
                        "tie": False,
                        "slur": False,
                        "lyric": "",
                    })
                elif step_ch == "0":
                    current_notes.append({
                        "degree": 0,
                        "octave": 0,
                        "accidental": None,
                        "durationBeats": dur_beats,
                        "dotted": dot_cnt > 0,
                        "rest": True,
                        "dash": False,
                        "tie": False,
                        "slur": False,
                        "lyric": "",
                    })
                else:
                    deg = int(step_ch)
                    current_notes.append({
                        "degree": deg,
                        "octave": oct_shift,
                        "accidental": acc_val,
                        "durationBeats": dur_beats,
                        "dotted": dot_cnt > 0,
                        "rest": False,
                        "dash": False,
                        "tie": False,
                        "slur": in_slur,
                        "lyric": "",
                        "_consume_lyric": True,
                    })
                acc_beat += dur_beats

        # 行尾若尚有未關閉的小節則收尾
        _flush_measure()

    # 依序將 lyric_pool 配對給所有 step 1..7 的音符
    lyr_idx = 0
    prev_pitched: dict[str, Any] | None = None
    for m in raw_measures:
        for n in m["notes"]:
            if n.pop("_consume_lyric", False):
                lyr = lyric_pool[lyr_idx] if lyr_idx < len(lyric_pool) else ""
                lyr_idx += 1
                n["lyric"] = lyr
                # 若在圓滑線/連結線內且與前一音同音高且當前為空歌詞 `_`，標記前音 tie=True
                if (
                    lyr == ""
                    and prev_pitched is not None
                    and prev_pitched.get("degree") == n.get("degree")
                    and prev_pitched.get("octave") == n.get("octave")
                    and prev_pitched.get("accidental") == n.get("accidental")
                ):
                    prev_pitched["tie"] = True
                    prev_pitched["slur"] = False
                    n["slur"] = False
                prev_pitched = n

    return {
        "summary": {
            "title": title or "網頁匯入樂譜",
            "composer": composer,
            "key": key_sig,
            "keySignature": f"1={key_sig}",
            "timeSignature": time_sig,
            "tempoBpm": tempo_bpm,
            "measuresNotFull": [],
        },
        "sections": [
            {
                "label": "",
                "measures": raw_measures,
            }
        ],
    }


def _strip_tags(html_fragment: str) -> str:
    txt = re.sub(r"<br\s*/?>", "\n", html_fragment, flags=re.IGNORECASE)
    txt = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", "", txt)
    return html_mod.unescape(txt)


def parse_html_score(html_text: str, source_url: str = "") -> dict[str, Any]:
    """從 HTML 原始碼擷取歌名、歌手與簡譜內容並轉為 ScoreDocument。"""
    title = ""
    composer = ""

    # 1. 擷取 <h1> 標題（例如 <h1>歌曲 Yesterday Once More</h1>）
    m_h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.IGNORECASE | re.DOTALL)
    if m_h1:
        h1_txt = _strip_tags(m_h1.group(1)).strip()
        h1_txt = re.sub(r"^歌曲\s*", "", h1_txt).strip()
        if h1_txt:
            title = h1_txt

    if not title:
        m_title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
        if m_title:
            t_txt = _strip_tags(m_title.group(1)).strip()
            t_txt = re.split(r"[-|_｜—]", t_txt)[0].strip()
            t_txt = re.sub(r"^歌曲\s*", "", t_txt).strip()
            if t_txt:
                title = t_txt

    # 2. 擷取歌手／作者（例如 <p>歌手：Carpenters</p>）
    m_artist = re.search(
        r"(?:歌手|演唱|原唱|作者|作曲)\s*[：:]\s*([^\n<]+)",
        html_text,
        re.IGNORECASE,
    )
    if m_artist:
        composer = html_mod.unescape(m_artist.group(1)).strip()

    # 3. 優先尋找 jianpu.space 的 #jianpuOut 或 .to-jianpu 區塊
    score_body = ""
    m_jp = re.search(
        r'<div[^>]+(?:id=["\']jianpuOut["\']|class=["\'][^"\']*to-jianpu[^"\']*["\'])[^>]*>(.*?)</div>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_jp:
        score_body = _strip_tags(m_jp.group(1)).strip()

    # 4. 備援：尋找頁面中含有簡譜小節線或 `<pre>` 的區塊
    if not score_body:
        for m_pre in re.finditer(r"<pre[^>]*>(.*?)</pre>", html_text, re.IGNORECASE | re.DOTALL):
            cand = _strip_tags(m_pre.group(1)).strip()
            if "|" in cand and re.search(r"[1-7]", cand):
                score_body = cand
                break

    if not score_body:
        body_txt = _strip_tags(html_text)
        cand_lines = [
            ln.strip()
            for ln in body_txt.splitlines()
            if ("|" in ln and re.search(r"[0-7]", ln))
            or ln.strip().startswith("L:")
            or "/key(" in ln
        ]
        if cand_lines:
            score_body = "\n".join(cand_lines)

    if not score_body:
        raise ValueError("無法在此網頁中找到可解析的簡譜內容（支援 jianpu.space 及含簡譜文字之網頁）。")

    sf_data = parse_je_score_text(
        score_body,
        title=title or "網頁匯入樂譜",
        composer=composer,
    )
    parsed = scoreforge_to_document(sf_data, source_name=source_url or title or "url-import")
    doc: ScoreDocument = parsed["document"]
    if composer and not doc.composer:
        doc.composer = composer
    doc.engineMode = "url-import"
    doc.engineNote = f"網址歌譜抓取｜{len(doc.measures)} 小節｜來源：{source_url}"
    doc.sourceName = source_url or title
    return {
        "document": doc,
        "warnings": parsed.get("warnings") or [],
        "rawText": score_body,
    }


def import_score_from_url(url: str, timeout: int = 25) -> dict[str, Any]:
    """從指定網址抓取網頁並解析成 ScoreDocument。"""
    clean_url = (url or "").strip()
    if not clean_url:
        raise ValueError("請輸入有效的歌譜網址。")
    if not re.match(r"^https?://", clean_url, re.IGNORECASE):
        clean_url = "https://" + clean_url

    parsed_u = urllib.parse.urlsplit(clean_url)
    safe_path = urllib.parse.quote(parsed_u.path, safe="/%:@!$&'()*+,;=-._~")
    safe_query = urllib.parse.quote_plus(parsed_u.query, safe="=&%:@!$'()*+,;-._~")
    req_url = urllib.parse.urlunsplit(
        (parsed_u.scheme, parsed_u.netloc, safe_path, safe_query, "")
    )

    req = urllib.request.Request(
        req_url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_bytes = resp.read()
        content_type = (resp.headers.get("Content-Type") or "").lower()

    charset = "utf-8"
    m_cs = re.search(r"charset=([\w\-]+)", content_type)
    if m_cs:
        charset = m_cs.group(1)
    try:
        html_text = raw_bytes.decode(charset, errors="replace")
    except LookupError:
        html_text = raw_bytes.decode("utf-8", errors="replace")

    return parse_html_score(html_text, source_url=clean_url)
