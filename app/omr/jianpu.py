"""簡譜專用辨識（第二代）。


第一代為什麼不行
----------------
第一代是「整頁丟給 Tesseract 一次」，實測有三個致命問題：

1. 數字與中文歌詞共用同一個模型。中文模型會把 `1 5 1 5` 讀成 `SS SS SS`，
   英文模型又讀不出歌詞。
2. **高低音點**（數字上下的小圓點）與**減時線**（數字下方的橫線）
   Tesseract 根本不會回報 —— 它只認字元，不認附加符號。
   所以八分／十六分音符、高低八度整批丟失。
3. 附點（數字右側的點）被當成標點或雜訊丟掉。

第二代的做法
------------
**不要求 OCR 做它做不到的事。** 版面與符號自己量，只把單個數字交給 OCR：

1. 橫向投影切出「核心列」。
2. 每列做欄投影，切成一個個「字團」（cluster）。
3. 字團內做連通元件分析：面積最大的是主字形，其餘是附加符號。
4. 主字形依幾何形狀分類 —— 細長橫的是延音線 `-`，瘦高的是小節線 `|`，
   其餘是數字。**只有數字才送進 Tesseract**（`--psm 10` 單字元 +
   字元白名單），因此速度與準確度都遠優於整頁辨識。
5. 附加符號依相對位置判定：
     上方圓點 → 高八度 `'`      下方圓點 → 低八度 `,`
     下方細長橫線 → 減時線 `_`   右側圓點 → 附點 `.`
   減時線可以橫跨數個音符（連音線），會分配給所有水平重疊的數字。
6. 歌詞列另外用 `chi_tra` 單一中文模型辨識（不與 `chi_sim` 混用，
   混用會互相拉低準確度）。

輸出沿用 `OcrLine`，所以 `layout.py` 的小節切分與 `musicxml.py` 不需改動。
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import cv2
from PIL import Image

from .engine import CHORD_TOKEN, EngineStatus, OcrLine

DIGITS = "01234567"
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# 標頭列必須「像標頭」才算，否則 OCR 雜訊裡的 `3/642` 會被誤認成拍號，
# 導致整條音符列被當成標頭丟掉（這是第一代實測踩到的 bug）。
META_KEY = re.compile(r"1\s*=\s*[A-G][b#]?", re.I)
META_TIME = re.compile(r"\b[2-9]\s*/\s*(2|4|8|16)\b")
META_TEMPO = re.compile(r"[\u266a\u2669J]\s*=\s*\d{2,3}")
META_CAPO = re.compile(r"\bcapo\s*[:=]?\s*\d{1,2}\b", re.I)

# OCR 讀錯時的形近字對照（白名單失效或回傳非數字時使用）
CONFUSION = {
    "S": "5", "s": "5", "$": "5",
    "l": "1", "I": "1", "i": "1", "!": "1", "|": "1", "/": "1",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "Z": "2", "z": "2",
    "G": "6", "b": "6",
    "T": "7", "?": "7",
    "A": "4", "h": "4",
    "E": "3",
}

# --- 幾何門檻（皆以字高為單位，與掃描 DPI 無關）-----------------------------
MIN_GLYPH_AREA_REL = 0.010  # 主字形最小面積（相對於 列高² ）
DOT_MAX_REL = 0.42  # 圓點寬高上限（相對主字形高度）
DOT_MIN_AREA = 3  # 圓點最小像素面積，濾掉掃描雜點
DASH_MIN_ASPECT = 2.2  # 延音線 寬/高 下限
DASH_MAX_H_REL = 0.34  # 延音線高度上限（相對列高）
BAR_MIN_ASPECT = 1.6  # 小節線 高/寬 下限（放寬以偵測更多小節線）
UNDERLINE_MIN_ASPECT = 2.0  # 減時線 寬/高 下限
DIGIT_MIN_H_REL = 0.55  # 數字高度下限（相對字高）
MAX_STRIP_WIDTH = 12000  # 放大後的列寬上限，避免超寬圖讓 Tesseract 卡住
NOTE_MAX_WIDTH_RATIO = 0.75  # 字團寬/字高 低於此值且元件單純 → 一定是音符列
NOTE_MAX_COMPS = 1.20  # 每字團主字形數低於此值 → 一定是音符列
LYRIC_MIN_CJK_RATIO = 0.60  # 判定為歌詞列所需的漢字占比
TEXT_WIDTH_RATIO = 0.80  # 字團寬/字高 超過此值視為漢字歌詞列（幾何備援）
TEXT_COMPS_PER_CLUSTER = 1.35  # 每字團主字形數超過此值視為漢字（幾何備援）


@dataclass
class Band:
    """一條核心列。

    `top`/`bottom` 是主字形（數字或漢字）本身的範圍，用來排序與量測門檻；
    `win_top`/`win_bottom` 額外包含上下的高低音點與減時線，是幾何分析視窗。
    兩者必須分開 —— 第一代把它們混為一談，圓點與減時線被切在視窗外，
    高低音與節拍因此完全讀不到。
    """

    top: int
    bottom: int
    win_top: int = -1
    win_bottom: int = -1

    def __post_init__(self) -> None:
        if self.win_top < 0:
            self.win_top = self.top
        if self.win_bottom < 0:
            self.win_bottom = self.bottom

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass
class Comp:
    """連通元件（座標為整頁絕對座標）。"""

    x0: int
    y0: int
    x1: int
    y1: int
    area: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def h(self) -> int:
        return self.y1 - self.y0 + 1

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


@dataclass
class Glyph:
    """一個主字形加上它的附加符號。"""

    comp: Comp
    kind: str  # "digit" | "dash" | "bar"
    char: str = ""
    conf: float = 0.0
    high: int = 0
    low: int = 0
    unders: int = 0
    dotted: bool = False
    marks: list[Comp] = field(default_factory=list)

    def token(self) -> str:
        if self.kind == "dash":
            return "-"
        if self.kind == "bar":
            return "|"
        return (
            (self.char or "?")
            + "'" * self.high
            + "," * self.low
            + "_" * self.unders
            + ("." if self.dotted else "")
        )


# ------------------------------------------------------------------ 影像前處理


def load_ink(image_path: Path) -> tuple[np.ndarray, Image.Image]:
    """回傳 (ink 布林陣列, 灰階影像)。ink=True 代表有墨。"""
    img = Image.open(image_path)
    if img.mode != "L":
        img = img.convert("L")
    gray = np.asarray(img, dtype=np.uint8)
    thr = _otsu(gray)
    ink = gray < max(1, int(thr * 0.95))
    return ink, img


def _otsu(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total <= 0:
        return 128
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom <= 0] = 1e-9
    sigma_b = (mu_t * omega - mu) ** 2 / denom
    return int(np.argmax(sigma_b))


def find_bands(ink: np.ndarray) -> list[Band]:
    """橫向投影切出核心列，並把附屬的圓點／減時線列掛回最近的核心列。

    高低音點與減時線各自會形成很矮的獨立投影列。它們不是獨立內容，而是鄰近
    數字列的一部分，因此用「掛附」而非「合併」處理：核心範圍維持數字本身
    （幾何門檻才會準），只把分析視窗擴大到含符號。
    """
    rows = ink.sum(axis=1)
    if rows.max() == 0:
        return []
    width = ink.shape[1]
    # 用「墨點數佔寬度比例」當 active 門檻；0.2% 太低（行間零星點也計入，
    # 導致整頁連成一段、分不出行）。提高到 1.2% 才濾得掉行間微量墨點。
    active = rows > max(1, width * 0.012)

    raw: list[list[int]] = []
    start = None
    for y, on in enumerate(active):
        if on and start is None:
            start = y
        elif not on and start is not None:
            raw.append([start, y])
            start = None
    if start is not None:
        raw.append([start, len(active)])
    if not raw:
        return []

    # 基準高度必須用「墨水量加權」的中位數 —— 一行音符會產生 1～2 條高低音點列，
    # 點列數量常多於真正的內容列，取單純中位數會把基準拉到圓點的高度（約 5px），
    # 於是點列自己升格成核心列，高低音點就永遠接不回數字上。
    # 一列圓點的墨水量只有數字列的幾十分之一，加權後基準一定落在真正的內容列。
    weighted: list[int] = []
    weighted: list[int] = []
    for b in raw:
        h = b[1] - b[0]
        mass = int(rows[b[0] : b[1]].sum())
        weighted.extend([h] * max(1, mass // 50))
    weighted.sort()
    median_h = weighted[len(weighted) // 2] or 1

    # 核心列門檻：簡譜數字列通常 ≥19px，歌詞列 ≤10px。
    # 用 median_h * 0.55（約 11-12px）而非 0.15，把歌詞列降為衛星列，
    # 由後續邏輯掛附到鄰近的簡譜列。
    core = [b for b in raw if (b[1] - b[0]) >= max(12, int(median_h * 0.55))]
    if not core:
        core = [max(raw, key=lambda b: b[1] - b[0])]
    sats = [b for b in raw if b not in core]
    bands = [Band(top=b[0], bottom=b[1]) for b in core]

    for s in sats:
        best: Band | None = None
        best_dist: int | None = None
        for bd in bands:
            if s[1] <= bd.top:
                dist = bd.top - s[1]
            elif s[0] >= bd.bottom:
                dist = s[0] - bd.bottom
            else:
                dist = 0
            if best_dist is None or dist < best_dist:
                best, best_dist = bd, dist
        if best is None or best_dist is None or best_dist > best.height * 0.85:
            continue
        best.win_top = min(best.win_top, s[0])
        best.win_bottom = max(best.win_bottom, s[1])

    # 視窗不得侵入相鄰核心列
    for i, bd in enumerate(bands):
        if i > 0:
            bd.win_top = max(bd.win_top, bands[i - 1].bottom + 1)
        if i + 1 < len(bands):
            bd.win_bottom = min(bd.win_bottom, bands[i + 1].top - 1)
        bd.win_top = min(bd.win_top, bd.top)
        bd.win_bottom = max(bd.win_bottom, bd.bottom)

    return bands


def _looks_like_tab(ink: np.ndarray, band: Band) -> bool:
    """判斷是不是吉他六线谱(TAB)。

    TAB 特徵：列內有約 6 條等距、**幾乎貫穿整行寬度**的細橫線（墨水占比高）。
    六线谱水平線會誤導 find_bands 成內容列，這裡識別出來供 analyze_page 跳過。

    判準刻意設嚴，避免誤殺整頁的純簡譜：簡譜的數字／歌詞列墨點是「散佈」的，
    不會讓某一整行接近滿墨；只有真正的水平線才會讓那一行的墨水占比趨近 1。
    """
    h = band.height
    if h <= 0:
        return False
    win = ink[band.win_top : band.win_bottom, :]
    if win.size == 0:
        return False
    w = win.shape[1]
    # 每行墨水占比 → 水平線會讓某幾行接近滿墨（占比高）
    row_ratio = win.sum(axis=1) / float(max(1, w))
    if row_ratio.max() <= 0.3:
        # 沒有任一行接近滿墨 → 不可能是六线谱水平線群
        return False
    # 找「接近滿墨」的行（占比 ≥ 0.55）連續段
    high = row_ratio >= 0.55
    segs = 0
    prev = False
    seg_heights = []
    cur_h = 0
    for v in high:
        if v:
            cur_h += 1
            if not prev:
                segs += 1
        else:
            if cur_h:
                seg_heights.append(cur_h)
            cur_h = 0
        prev = v
    if cur_h:
        seg_heights.append(cur_h)
    # 六线谱：高度夠大、有 ≥5 條接近滿墨的水平線段，且這些線很細（單條 ≤6px）
    if h < 70 or segs < 5:
        return False
    return all(sh <= 8 for sh in seg_heights[:segs])



def components(mask: np.ndarray, ox: int = 0, oy: int = 0, max_count: int = 600) -> list[Comp]:
    """回傳連通元件（8-鄰接）。只用在單一字團的小視窗，純 Python BFS 已足夠快。"""
    if mask.size == 0 or not mask.any():
        return []
    seen = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape
    out: list[Comp] = []
    for sy in range(h):
        row = mask[sy]
        if not row.any():
            continue
        for sx in range(w):
            if not row[sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            x0 = x1 = sx
            y0 = y1 = sy
            area = 0
            while stack:
                cy, cx = stack.pop()
                area += 1
                if cx < x0:
                    x0 = cx
                elif cx > x1:
                    x1 = cx
                if cy < y0:
                    y0 = cy
                elif cy > y1:
                    y1 = cy
                for ny in (cy - 1, cy, cy + 1):
                    if ny < 0 or ny >= h:
                        continue
                    mrow = mask[ny]
                    srow = seen[ny]
                    for nx in (cx - 1, cx, cx + 1):
                        if 0 <= nx < w and mrow[nx] and not srow[nx]:
                            srow[nx] = True
                            stack.append((ny, nx))
            out.append(Comp(x0 + ox, y0 + oy, x1 + ox, y1 + oy, area))
            if len(out) >= max_count:
                return out
    return out


def column_clusters(ink: np.ndarray, band: Band, min_gap: int) -> list[tuple[int, int]]:
    """在分析視窗內做欄投影，切出彼此分離的字團。"""
    win = ink[band.win_top : band.win_bottom, :]
    cols = win.any(axis=0)
    spans: list[list[int]] = []
    start = None
    gap = 0
    for x, on in enumerate(cols):
        if on:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                spans.append([start, x - gap + 1])
                start = None
                gap = 0
    if start is not None:
        spans.append([start, len(cols)])
    return [(a, b) for a, b in spans if b - a >= 2]


# ---------------------------------------------------------------------- OCR


def _tess_env(status: EngineStatus) -> dict:
    env = dict(os.environ)
    if status.tessdata:
        td = Path(status.tessdata)
        env["TESSDATA_PREFIX"] = str(td.parent if td.name == "tessdata" else td)
    return env


def _run_tess(
    status: EngineStatus,
    image: Image.Image,
    png: Path,
    lang: str,
    psm: int,
    whitelist: str | None = None,
) -> tuple[str, float]:
    png.parent.mkdir(parents=True, exist_ok=True)
    image.save(png)
    cmd = [status.path, str(png), "stdout", "-l", lang, "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", "tessedit_char_whitelist=" + whitelist]
    cmd += ["-c", "preserve_interword_spaces=1", "tsv"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, env=_tess_env(status)
        )
    except (OSError, subprocess.SubprocessError):
        return "", 0.0
    if proc.returncode != 0:
        return "", 0.0
    parts: list[str] = []
    confs: list[float] = []
    for row in (proc.stdout or "").splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12:
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        text = cols[11].strip()
        if not text or conf < 0:
            continue
        parts.append(text)
        confs.append(conf)
    return " ".join(parts), (sum(confs) / len(confs) if confs else 0.0)


LYRIC_NOISE = set("“”‘’\"'`´~^*_|\\/<>[]{}()＂＇｀＊＿｜")


# 只放**真正的版權用語**。「分享」「收藏」「所有」「轉載」這類詞在歌詞裡很常見
# （「所有的星光都收藏起來」就會被誤判），誤刪使用者的歌詞比漏刪浮水印嚴重得多。
WATERMARK_HINTS = (
    "僅供", "仅供", "個人學習", "个人学习", "歡迎轉載", "欢迎转载",
    "篡改", "必究", "版權", "版权", "侵權", "侵权",
    "曲譜網", "曲谱网", "製譜", "制谱", "打譜", "打谱",
    "copyright", "all rights", "reserved",
)
WATERMARK_URL = re.compile(r"(https?://|www\.|\.com|\.cn|\.net|\.tw)", re.I)


def _is_watermark(text: str) -> bool:
    """判斷是不是頁面浮水印／版權聲明，而不是歌詞。

    曲譜網站下載的譜常有「僅供個人學習使用,歡迎轉載、分享、收藏,篡改必究!」
    這類頁尾文字。它會被當成歌詞列，再被切成一個字一個小節塞進譜裡。

    判準刻意設嚴：**要命中兩個以上關鍵詞，或含網址**。只中一個不算 ——
    「分享」「所有」「收藏」單獨出現在真正的歌詞裡完全正常，不能誤刪使用者的內容。
    """
    low = (text or "").lower()
    if WATERMARK_URL.search(low):
        return True
    return sum(1 for k in WATERMARK_HINTS if k in low) >= 2


def _clean_lyric(text: str) -> str:
    """濾掉字距造成的標點雜訊。

    簡譜歌詞每個字要對準一個音符，字距被拉得很寬，Tesseract 會在空隙裡
    憑空補出 `“` `\'` `~` 這類標點。歌詞列的內容幾乎都是漢字，
    因此把「不含漢字、只有一個字元、且是標點」的 token 直接丟掉。
    """
    keep = []
    for tok in (text or "").split():
        if CJK.search(tok):
            keep.append(tok)
            continue
        if len(tok) <= 1 and tok in LYRIC_NOISE:
            continue
        keep.append(tok)
    return " ".join(keep)


def _lyric_ocr(
    status: EngineStatus,
    img: Image.Image,
    band: Band,
    page_w: int,
    png: Path,
    lang: str,
) -> tuple[str, float]:
    """歌詞列辨識：放大版與原尺寸各讀一次，取漢字較多者。

    放大到 48px 通常較準，但小字級掃描件放大後模糊，反而會漏字或吐雜訊；
    原尺寸有時又整列讀不到。實測沒有一種前處理穩定勝出（放大 92%／原尺寸
    58%，但原尺寸的輸出較乾淨），所以兩種都跑，用「漢字數優先、信心值次之」
    挑選。歌詞列數不多，多一次辨識的成本可以接受。

    注意：**不要對歌詞做二值化或更大倍率的放大**，實測會從 96% 掉到 62%。
    """
    pad = max(2, int(band.height * 0.12))
    core = img.crop(
        (0, max(0, band.top - pad), page_w, min(img.height, band.bottom + pad))
    )
    best: tuple[int, float, str] = (-1, -1.0, "")
    for idx, im in enumerate((_crop_band(img, band, page_w), core)):
        text, conf = _run_tess(status, im, png.with_name(png.stem + "-%d.png" % idx), lang, 7)
        text = _clean_lyric(text)
        cjk = len(CJK.findall(text))
        if (cjk, conf) > (best[0], best[1]):
            best = (cjk, conf, text)
    return best[2], max(0.0, best[1])


def looks_like_lyrics(
    status: EngineStatus,
    img: Image.Image,
    band: Band,
    page_w: int,
    row: "RowGeom",
    png: Path,
    lyric_lang: str,
) -> tuple[bool, str, float]:
    """判斷這一列是歌詞還是音符：中文模型的結果 + 幾何否決權。

    單靠幾何不可靠：漢字的筆畫可能是分離的，有些筆畫瘦高像小節線、有些細寬像
    減時線，實測會把「星光落在窗前」誤讀成一堆音符。

    但單靠中文模型也不可靠：對著一列數字，chi_tra 會硬湊出漢字。實測一列
    8 個數字被讀成「說 1 說 史 說 2 DD 6」，漢字占 44%，就通過了原本
    「≥40% 漢字」的門檻，整列音符因此被當成歌詞丟掉。

    所以兩者都要用：
    1. 幾何若**強烈**顯示是等寬的單字元（字團寬比 < 0.75 且每團元件 < 1.20），
       直接判定音符列，不理中文模型說什麼 —— 漢字不可能這麼窄又這麼單純。
    2. 否則才看中文模型，且漢字占比門檻提高到 60%。真正的歌詞列幾乎全是漢字
       （實測 100%），44% 這種比例只會出現在誤讀。

    未安裝中文語言包時回傳 `(False, "", 0.0)`，由呼叫方改用幾何備援規則。
    """
    if lyric_lang == "eng":
        return False, "", 0.0
    if row.text_score < NOTE_MAX_WIDTH_RATIO and row.comps_per_cluster < NOTE_MAX_COMPS:
        return False, "", 0.0
    text, conf = _lyric_ocr(status, img, band, page_w, png, lyric_lang)
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return False, text, conf
    if _is_watermark(text):
        return False, "", 0.0
    cjk = [c for c in letters if CJK.match(c)]
    return (len(cjk) >= 1 and len(cjk) >= len(letters) * LYRIC_MIN_CJK_RATIO), text, conf


def pick_lyric_lang(status: EngineStatus) -> str:
    """歌詞只用一種中文模型；chi_tra 與 chi_sim 併用會互相拉低準確度。"""
    for cand in ("chi_tra", "chi_sim"):
        if cand in status.languages:
            return cand
    return "eng"


def pick_digit_lang(status: EngineStatus) -> str:
    return "eng" if "eng" in status.languages else (status.languages[:1] or ["eng"])[0]


def recognize_digit(
    status: EngineStatus, img: Image.Image, comp: Comp, work: Path, tag: str, lang: str
) -> tuple[str, float]:
    """單一數字辨識：裁切 → 放大 → `--psm 10` 單字元模式。"""
    pad = max(4, int(comp.h * 0.22))
    crop = img.crop(
        (
            max(0, comp.x0 - pad),
            max(0, comp.y0 - pad),
            min(img.width, comp.x1 + 1 + pad),
            min(img.height, comp.y1 + 1 + pad),
        )
    )
    if crop.height < 64:
        scale = max(1, int(round(64.0 / max(1, crop.height))))
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)

    # 對數字裁切做局部二值化，提升 Tesseract 數字辨識率
    import PIL.ImageOps as _ImageOps
    try:
        crop_bin = _ImageOps.autocontrast(crop.convert("L"), cutoff=2)
        crop_bin = crop_bin.point(lambda px: 0 if px > 128 else 255, mode="1")
    except Exception:
        crop_bin = crop

    png = work / ("g-%s.png" % tag)
    text, conf = _run_tess(status, crop_bin, png, lang, 10, DIGITS)
    ch = _first_digit(text)
    if ch:
        return ch, conf
    # 白名單沒抓到就放寬，再用形近字對照救回
    text2, conf2 = _run_tess(status, crop_bin, png, lang, 10, None)
    ch = _first_digit(text2)
    if ch:
        return ch, conf2 * 0.8
    for raw in (text2 or "").strip():
        if raw in CONFUSION:
            return CONFUSION[raw], conf2 * 0.5
    return "", 0.0


def _first_digit(text: str) -> str:
    for ch in (text or "").strip():
        if ch in DIGITS:
            return ch
    return ""


# ------------------------------------------------------- 字團 → 音符 token


@dataclass
class Metrics:
    """以數字本身推算的列尺寸。

    **不能用投影列的下緣當數字基線**：小節線很高，會把整條列的下緣
    撐到減時線下面，於是減時線反而落在「列中段」被誤讀成延音線。
    改用數字字形的中位下緣作為基線後，兩者就能穩定區分。
    """

    base: float  # 數字基線（中位 y1）
    dh: float  # 數字高度（中位）


def _metrics(comps: list[Comp], band: Band) -> Metrics:
    cand = [
        c
        for c in comps
        if c.h >= band.height * 0.25 and 0.25 <= c.w / float(max(1, c.h)) <= 1.6
    ]
    if not cand:
        return Metrics(base=float(band.bottom), dh=float(max(1, band.height)))
    # 同理，cand 裡混著數字與圓點時中位數會被圓點拉低，導致圓點通過
    # 「主字形」門檻被當成數字送去 OCR。先用上四分位高度定出數字的尺度，
    # 再只用接近該尺度的元件算中位數。
    desc = sorted((c.h for c in cand), reverse=True)
    ref = desc[len(desc) // 4] or 1
    solid = [c for c in cand if c.h >= ref * 0.6] or cand
    hs = sorted(c.h for c in solid)
    ys = sorted(c.y1 for c in solid)
    return Metrics(base=float(ys[len(ys) // 2]), dh=float(hs[len(hs) // 2] or 1))


@dataclass
class RowGeom:
    """一條列的幾何分析結果。"""

    glyphs: list[Glyph]
    met: Metrics
    cluster_w: list[int]

    @property
    def text_score(self) -> float:
        """字團寬度 / 字高。漢字接近 1.0，阿拉伯數字約 0.6。

        不能拿單一連通元件的寬高比來判斷漢字 —— 很多漢字的筆畫本身
        就是分離的（例如「水」「小」），每個筆畫都細長，會被誤判成數字。
        改看「字團」的寬度就穩定了。
        """
        if not self.cluster_w or self.met.dh <= 0:
            return 0.0
        ws = sorted(self.cluster_w)
        return ws[len(ws) // 2] / self.met.dh

    @property
    def comps_per_cluster(self) -> float:
        """每個字團的主字形數。漢字筆畫多（≥ 1.8），簡譜數字接近 1.0。"""
        if not self.cluster_w:
            return 0.0
        return len(self.glyphs) / float(len(self.cluster_w))


def build_glyphs(ink: np.ndarray, band: Band) -> RowGeom:
    """把一條核心列切成主字形 + 附加符號。"""
    bh = max(1, band.height)
    min_gap = max(2, int(bh * 0.12))
    clusters = column_clusters(ink, band, min_gap)

    groups: list[list[Comp]] = []
    widths: list[int] = []
    for x0, x1 in clusters:
        comps = components(ink[band.win_top : band.win_bottom, x0:x1], ox=x0, oy=band.win_top)
        if comps:
            groups.append(comps)
            widths.append(x1 - x0)
    if not groups:
        return RowGeom([], Metrics(float(band.bottom), float(max(1, band.height))), [])

    met = _metrics([c for g in groups for c in g], band)
    min_area = max(4, int(met.dh * met.dh * MIN_GLYPH_AREA_REL))

    glyphs: list[Glyph] = []
    orphan_dots: list[Comp] = []
    for comps in groups:
        mains = [c for c in comps if _is_main(c, met, min_area)]
        marks = [c for c in comps if c not in mains and c.area >= DOT_MIN_AREA]
        if not mains:
            # 整個字團都是小東西 → 可能是被切開的附點或雜訊
            orphan_dots.extend(marks)
            continue
        made = [Glyph(comp=c, kind=_main_kind(c, met)) for c in mains]
        _assign_marks(made, marks, met)
        glyphs.extend(made)

    glyphs.sort(key=lambda g: g.comp.x0)
    _assign_orphans(glyphs, orphan_dots, met)
    return RowGeom(glyphs, met, widths)


def _is_line(c: Comp, dh: float) -> bool:
    return (
        c.w / float(max(1, c.h)) >= UNDERLINE_MIN_ASPECT
        and c.h <= max(2, int(dh * 0.26))
    )


def _is_main(c: Comp, met: Metrics, min_area: int) -> bool:
    """區分主字形與附加符號。

    延音線 `-` 與減時線寬高幾乎一樣，**只能用垂直位置區分**：
    延音線落在數字高度的中段，減時線落在數字基線之下。
    第一代只看寬高比，所以把每根減時線都誤讀成延音線。
    """
    if c.area < min_area:
        return False
    if _is_line(c, met.dh):
        return c.cy <= met.base - met.dh * 0.10
    return c.h >= met.dh * DIGIT_MIN_H_REL


def _main_kind(c: Comp, met: Metrics) -> str:
    aspect = c.w / float(max(1, c.h))
    if aspect >= DASH_MIN_ASPECT and c.h <= met.dh * DASH_MAX_H_REL:
        return "dash"
    if (c.h / float(max(1, c.w))) >= BAR_MIN_ASPECT and c.w <= max(4, int(met.dh * 0.40)):
        return "bar"
    return "digit"


def _assign_marks(glyphs: list[Glyph], marks: list[Comp], met: Metrics) -> None:
    """把附加符號依相對位置指派給數字。"""
    digits = [g for g in glyphs if g.kind == "digit"]
    if not digits:
        return
    for m in marks:
        aspect = m.w / float(max(1, m.h))
        is_line = _is_line(m, met.dh)

        if is_line:
            # 減時線可橫跨多個音符（連音線）→ 給所有水平重疊的數字
            hit = False
            for g in digits:
                if m.x1 >= g.comp.x0 - 2 and m.x0 <= g.comp.x1 + 2 and m.cy > g.comp.cy:
                    g.unders += 1
                    g.marks.append(m)
                    hit = True
            if hit:
                continue

        target = min(digits, key=lambda g: abs(g.comp.cx - m.cx))
        d = target.comp
        limit = max(2.5, d.h * DOT_MAX_REL)
        round_ish = m.w <= limit and m.h <= limit and 0.35 <= aspect <= 2.8

        if not round_ish:
            continue
        if m.cy < d.y0:
            target.high += 1
        elif m.cy > d.y1:
            target.low += 1
        elif m.cx > d.x1:
            target.dotted = True
        target.marks.append(m)


def _assign_orphans(glyphs: list[Glyph], dots: list[Comp], met: Metrics) -> None:
    """處理被欄投影切開的附點：指派給左側最近的數字。"""
    digits = [g for g in glyphs if g.kind == "digit"]
    if not digits:
        return
    for m in dots:
        aspect = m.w / float(max(1, m.h))
        if not (0.35 <= aspect <= 2.8):
            continue
        left = [g for g in digits if g.comp.x1 <= m.x0]
        if not left:
            continue
        target = left[-1]
        d = target.comp
        if m.x0 - d.x1 > d.w * 1.1:
            continue
        if m.w > d.h * DOT_MAX_REL or m.h > d.h * DOT_MAX_REL:
            continue
        if m.cy < d.y0:
            target.high += 1
        elif m.cy > d.y1:
            target.low += 1
        else:
            target.dotted = True


# ------------------------------------------------------------------ 主流程


def mask_tab_regions(ink: np.ndarray, gray_img: np.ndarray) -> np.ndarray:
    """全頁掃描吉他六線譜(TAB)區域並遮罩。

    TAB 特徵：約 6 條等距、近滿寬的細橫線，會在水平投影中形成多個
    高墨水密度的薄列。在 find_bands 前遮罩可防止它們被切成獨立列。
    """
    h, w = ink.shape
    # 用較寬鬆的參數檢測水平線群
    edges = cv2.Canny(gray_img, 30, 100)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=25,
                             minLineLength=max(80, int(w*0.25)), maxLineGap=20)
    if lines is None:
        return ink
    ys = []
    for ln in lines:
        x1, y1, x2, y2 = ln
        if abs(x2-x1) > abs(y2-y1)*3 and abs(x2-x1) > w*0.25:
            ys.append((y1+y2)/2)
    if len(ys) < 5:  # TAB 至少 5 條線
        return ink
    ys.sort()
    # 合併近距離線群
    groups = []
    cur = [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= max(8, (ys[-1]-ys[0])/max(1,len(ys))*2):
            cur.append(y)
        else:
            if len(cur) >= 5:
                groups.append(cur)
            cur = [y]
    if len(cur) >= 5:
        groups.append(cur)
    # 遮罩每個 TAB 群（上下各延伸 12px）
    for g in groups:
        y0 = max(0, int(g[0]-12))
        y1 = min(h, int(g[-1]+12))
        if y1 > y0:
            ink[y0:y1, :] = False
    return ink


def detect_and_mask_staff_systems(ink, gray_img):
    """檢測水平譜線群組（>=3條平行線），遮罩整個譜表區域。"""
    # 先遮罩 TAB 區域
    ink = mask_tab_regions(ink, gray_img)
    h, w = ink.shape
    edges = cv2.Canny(gray_img, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=40,
                             minLineLength=max(50, w*0.3), maxLineGap=15)
    if lines is None:
        return ink
    ys = []
    for ln in lines:
        x1, y1, x2, y2 = ln
        if abs(x2-x1) > abs(y2-y1)*3 and abs(x2-x1) > w*0.25:
            ys.append((y1+y2)/2)
    if len(ys) < 3:
        return ink
    ys.sort()
    groups = []
    cur = [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= max(10, (ys[-1]-ys[0])/max(1,len(ys))*2.5):
            cur.append(y)
        else:
            if len(cur) >= 3:
                groups.append(cur)
            cur = [y]
    if len(cur) >= 3:
        groups.append(cur)
    for g in groups:
        y0 = max(0, int(g[0]-10))
        y1 = min(h, int(g[-1]+12))
        if y1 > y0:
            ink[y0:y1, :] = False
    return ink


def analyze_page(
    image_path: Path,
    status: EngineStatus,
    work_dir: Path,
    page_no: int = 1,
) -> list[OcrLine]:
    """辨識單一頁面，回傳與第一代相同型別的 OcrLine 清單。"""
    if not status.available:
        raise RuntimeError(status.note or "OMR 引擎不可用。")

    ink, img = load_ink(image_path)
    img_arr = np.asarray(img)
    ink = detect_and_mask_staff_systems(ink, img_arr)
    bands = find_bands(ink)
    if not bands:
        return []

    digit_lang = pick_digit_lang(status)
    lyric_lang = pick_lyric_lang(status)
    page_w = ink.shape[1]
    work_dir.mkdir(parents=True, exist_ok=True)
    results: list[OcrLine] = []

    for bi, band in enumerate(bands):
        # 跳過吉他六線譜(TAB)或五线谱欄：這些不是簡譜/歌詞內容列
        # 但「和弦方格+上方和弦名」也在這層——先試提取和弦名再決定跳過
        if _looks_like_tab(ink, band) or (band.height >= 35 and band.height < 70):
            # 裁上 1/3 看有沒有和弦名文字
            chord_text, chord_conf = _chord_line_ocr(
                status, img, band, page_w, work_dir, "p%d-b%d" % (page_no, bi)
            )
            if chord_text:
                results.append(_line(chord_text, chord_conf, band))
                continue
            continue  # 沒有和弦名 → 純 TAB，跳過
        row = build_glyphs(ink, band)
        glyphs = row.glyphs
        digit_glyphs = [g for g in glyphs if g.kind == "digit"]

        # 過濾純雜訊：若字團數太少（<3）且沒有小節線，就跳過
        if len(glyphs) < 3 and len([g for g in glyphs if g.kind == "bar"]) < 2:
            continue

        strip = _crop_band(img, band, page_w)
        tag = "p%d-b%d" % (page_no, bi)

        # 前幾列先確認是不是調號／拍號／速度標頭，不然會被從數字列讀成一堆音符
        if bi <= 2:
            head, hconf = _run_tess(
                status, strip, work_dir / ("h-%s.png" % tag), digit_lang, 7
            )
            if _is_meta(head):
                results.append(_line(head, hconf, band))
                continue

        # --- 高列（元信息／和弦方格／表頭）分流 ---
        # band 高度 ≥ 55 時，通常是標頭、和弦方格或圖表區，不是簡譜數字列。
        if band.height >= 55:
            head, hconf = _run_tess(
                status, strip, work_dir / ("hl-%s.png" % tag), digit_lang, 7
            )
            head_clean = " ".join(head.split())
            # 元信息（含調號/拍號/Capo）
            if _is_meta(head_clean):
                results.append(_line(head_clean, hconf, band))
                continue
            # 幾乎全是 A-G 升降記號 → 和弦名行
            letters = re.findall(r"[A-Ga-g]", head_clean)
            if len(letters) >= 2 and len(letters) >= len([c for c in head_clean if c.isalnum()]) * 0.4:
                results.append(_line(head_clean, hconf, band))
                continue
            # 用精準裁切提取和弦名稱文字（位於方格正上方的純文字行）
            chord_text, chord_conf = _chord_line_ocr(
                status, img, band, page_w, work_dir, tag
            )
            if chord_text:
                results.append(_line(chord_text, chord_conf, band))
                continue
            # 讀不出足夠數字的圖形區（和弦方格）：整行只取極少數字 → 跳過逐字OCR
            if len(re.findall(r"[0-7]", head_clean)) < 2:
                results.append(_line(head_clean, hconf, band))
                continue

        # 優先用中文模型確認是不是歌詞列（最可靠）；
        # 未安裝中文語言包時退回幾何備援規則。
        strip_png = work_dir / ("s-%s.png" % tag)
        is_lyric, ltext, lconf = looks_like_lyrics(status, img, band, page_w, row, strip_png, lyric_lang)
        if not is_lyric and lyric_lang == "eng":
            is_lyric = (
                row.text_score >= TEXT_WIDTH_RATIO
                or row.comps_per_cluster >= TEXT_COMPS_PER_CLUSTER
            )
            if is_lyric:
                ltext, lconf = _lyric_ocr(status, img, band, page_w, strip_png, lyric_lang)

        if is_lyric or not digit_glyphs:
            if not ltext and digit_glyphs:
                ltext, lconf = _lyric_ocr(status, img, band, page_w, strip_png, lyric_lang)
            if not ltext:
                # 沒有歌詞文字且沒有數字 → 純雜訊（只有小節線等），跳過
                continue
            # 信度過低者視為雜訊（如 37px 寬帶被 chi_tra 硬湊出漢字）
            if lconf < 50.0:
                continue
            results.append(_line(ltext, lconf, band))
            continue

        # --- 音符列：逐字辨識 ---
        confs: list[float] = []
        for gi, g in enumerate(digit_glyphs):
            ch, cf = recognize_digit(
                status, img, g.comp, work_dir, "%s-%d" % (tag, gi), digit_lang
            )
            g.char = ch
            g.conf = cf
            confs.append(cf if ch else 0.0)

        token_text = " ".join(g.token() for g in glyphs if g.token())
        if not token_text.strip():
            continue

        # 若整列幾乎讀不到數字，退回文字辨識，避免產生一整列 `?`
        good = sum(1 for g in digit_glyphs if g.char)
        if digit_glyphs and good < len(digit_glyphs) * 0.34:
            text, conf = ltext, lconf
            if not text:
                text, conf = _lyric_ocr(status, img, band, page_w, strip_png, lyric_lang)
            if text.strip():
                # 信度過低者視為雜訊（Tesseract 回傳 0-100 尺度）
                if conf < 50.0:
                    continue
                # 太短的文字也視為雜訊
                if len(text.strip()) >= 4 and len([c for c in text if c.strip()]) >= 2:
                    results.append(_line(text, conf, band))
                    continue
            # 沒有歌詞文字、數字也全讀不出 → 純雜訊，跳過
            continue

        avg = sum(confs) / len(confs) if confs else 0.0
        # 計算平均信心：包含數字和小節線的信心
        bar_confs = [g.conf for g in glyphs if g.kind == "bar" and g.conf]
        all_confs = confs + bar_confs
        avg = sum(all_confs) / len(all_confs) if all_confs else 0.0
        # 噪音帶過濾：37px 高寬的雜訊會被分類為數字，但信度極低且幾乎全 ?
        if band.height >= 35 and avg < 30.0:
            continue
        # 先檢查是否有小節線 - 有小節線的行保留（結構重要），不做 nonzero 過濾
        has_bars = any(g.kind == "bar" for g in glyphs)
        if has_bars:
            results.append(_line(token_text, avg, band))
            continue
        # 純雜訊：所有數字都識別為 0 且平均信度低 → 幾乎確定是噪點
        nonzero = [g.char for g in digit_glyphs if g.char and g.char != "0"]
        if not nonzero and avg < 50.0:
            continue
        # 若整列數字皆為 0（無 1-7），且無未識別的 ? 字元 → 純噪點列，跳過
        if not nonzero and not any(g.char == "" for g in digit_glyphs):
            continue
        # 真實簡譜列每行至少 3-4 個非零數字；1-2 個非零數字極大機率是噪點
        if len(nonzero) < 3:
            continue
        results.append(_line(token_text, avg, band))

    return results


def _crop_band(img: Image.Image, band: Band, page_w: int) -> Image.Image:
    pad = max(2, int(band.height * 0.12))
    strip = img.crop((0, max(0, band.top - pad), page_w, min(img.height, band.bottom + pad)))
    if strip.height < 48:
        scale = max(1, int(round(48.0 / max(1, strip.height))))
        # 放大倍率要設上限：高解析掃描件上一條很矮的列（例如 5px）會算出 10 倍，
        # 2500px 寬的頁面就變成 25000px 寬，Tesseract 會慢到像卡住。
        #
        # 上限必須看**放大後的寬度**。之前寫成 `4000 // strip.width`，
        # 頁寬只要超過 2000px 就直接算出 1，等於把放大整個關掉 —— 而不放大時
        # 有些歌詞列會整列讀不到。這個錯誤沒被測出來，是因為當時的測試圖只有
        # 1240px 寬剛好不受影響。真實掃描件都在 2400px 以上。
        scale = min(scale, 6)
        while scale > 1 and strip.width * scale > MAX_STRIP_WIDTH:
            scale -= 1
        if scale > 1:
            strip = strip.resize(
                (strip.width * scale, strip.height * scale), Image.LANCZOS
            )
    return strip


def _chord_line_ocr(
    status: EngineStatus,
    img: Image.Image,
    band: Band,
    page_w: int,
    work_dir: Path,
    tag: str,
) -> tuple[str, float]:
    """針對高列（和弦方格帶）上方的和弦名稱文字區域做精準裁切與 OCR。

    吉他彈唱譜中的和弦方格區塊：上方是純文字和弦名（C、G、Am、D/F#），
    下方是指法圖形。裁切上 25% 區域（和弦名稱文字通常在方格正上方），
    用 `eng` 語言模型 OCR 該區域，再用 CHORD_TOKEN 驗證每個 token。
    至少要有 1 個合法和弦 token 才返回，否則返回空字串（該帶不是和弦行）。
    """
    # 只裁切 band 的上 40%（和弦名稱文字在方格上方，不在方格內）
    pad = max(2, int(band.height * 0.08))
    top = max(0, band.top - pad)
    bottom = band.top + int(band.height * 0.40)
    crop = img.crop((0, top, page_w, bottom))
    if crop.height < 24:
        scale = max(1, int(round(24.0 / max(1, crop.height))))
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    png = work_dir / ("chord-%s.png" % tag)
    crop.save(png)
    text, conf = _run_tess(status, crop, png, "eng", 7)
    text = " ".join(text.split())
    # 驗證每個 token 是否為合法和弦名
    valid_chords = [t for t in text.split() if t and CHORD_TOKEN.match(t)]
    if not valid_chords:
        return "", 0.0
    return " ".join(valid_chords), conf


def _line(text: str, conf: float, band: Band) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=round(max(0.0, min(conf, 100.0)) / 100.0, 3),
        top=band.top,
        left=0,
        height=band.height,
    )


def _is_meta(text: str) -> bool:
    """標頭列必須真的像標頭，否則音符列的雜訊會被誤判成拍號。"""
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    if len(compact) > 28:
        return False
    hits = sum(
        1
        for pat in (META_KEY, META_TIME, META_TEMPO, META_CAPO)
        if pat.search(text)
    )
    return hits >= 1
