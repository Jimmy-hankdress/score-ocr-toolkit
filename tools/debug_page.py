"""辨識診斷工具：把分析器「看到的東西」畫成標註圖。

辨識結果不對時，光看文字看不出是哪一關出錯。這支工具會在原圖上疊出
列的範圍、每個字形的分類、量到的字高，讓問題一眼可見。

用法（在專案根目錄執行）::

    python tools/debug_page.py 你的樂譜.pdf
    python tools/debug_page.py 你的樂譜.jpg --page 2

輸出會放在 `build/debug/`，包含每頁一張 `debug-p1.png` 標註圖與一份
`debug.txt` 文字報告。把標註圖寄出來就能定位問題。

顏色對照：
    藍框 = 數字（音符）      綠框 = 增時線 `-`      紫框 = 小節線 `|`
    紅框 = 高低音點          橙框 = 減時線          灰框 = 被當成雜點濾掉
    黃線 = 量到的基線        青框 = 判定為歌詞的列
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import numpy as np  # noqa: E402

from app.omr import engine, jianpu, rasterize  # noqa: E402

COLORS = {
    "digit": (32, 96, 220),
    "dash": (26, 150, 70),
    "bar": (150, 60, 200),
    "dot": (220, 40, 40),
    "under": (230, 130, 20),
    "noise": (150, 150, 150),
}
# 標註文字含中文，必須先找中文字型；找不到才退回英數字型並改用英文標籤，
# 否則中文會全部畫成空心方框（DejaVuSans 沒有漢字）。
CJK_FONTS = [
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msjhl.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]
ASCII_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font(size: int) -> tuple[object, bool]:
    """回傳 (字型, 是否支援中文)。"""
    for f in CJK_FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size), True
            except OSError:
                pass
    for f in ASCII_FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size), False
            except OSError:
                pass
    return ImageFont.load_default(), False


def annotate(image_path: Path, out_png: Path, report: list[str]) -> None:
    status = engine.detect_engine()
    ink, gray = jianpu.load_ink(image_path)
    img_arr = np.asarray(gray)
    # 套用與 analyze_page 相同的遮罩，才能看到真實切列結果
    ink = jianpu.detect_and_mask_staff_systems(ink, img_arr)
    bands = jianpu.find_bands(ink)
    canvas = gray.convert("RGB")
    d = ImageDraw.Draw(canvas)
    fnt, cjk_ok = _font(max(12, canvas.height // 90))
    page_w = ink.shape[1]

    report.append("圖檔 %s  尺寸 %dx%d  切出 %d 列" % (image_path.name, canvas.width, canvas.height, len(bands)))
    lyric_lang = jianpu.pick_lyric_lang(status)
    digit_lang = jianpu.pick_digit_lang(status)
    report.append("數字模型 %s  歌詞模型 %s" % (digit_lang, lyric_lang))
    report.append("（下方逐列是「純幾何分析」結果，還沒判斷歌詞列，"
                  "token 裡的 ? 代表這一段不跑文字辨識；最終輸出在報告末端）")

    for bi, band in enumerate(bands):
        row = jianpu.build_glyphs(ink, band)
        met = row.met
        d.rectangle([0, band.top, page_w - 1, band.bottom], outline=(60, 130, 255), width=2)
        d.rectangle([0, band.win_top, page_w - 1, band.win_bottom], outline=(180, 200, 255), width=1)
        d.line([0, met.base, page_w - 1, met.base], fill=(230, 200, 0), width=1)

        kinds: dict[str, int] = {}
        for g in row.glyphs:
            c = COLORS.get(g.kind, COLORS["noise"])
            kinds[g.kind] = kinds.get(g.kind, 0) + 1
            d.rectangle([g.comp.x0, g.comp.y0, g.comp.x1, g.comp.y1], outline=c, width=2)
            for m in g.marks:
                # marks 只是連通元件，沒有種類欄位；減時線扁而寬，圓點接近正方
                flat = m.w / float(max(1, m.h)) >= 2.0
                mc = COLORS["under"] if flat else COLORS["dot"]
                d.rectangle([m.x0 - 1, m.y0 - 1, m.x1 + 1, m.y1 + 1], outline=mc, width=2)

        label = "列%d 核心高%d dh=%.0f base=%.0f %s 字團寬比%.2f 每團元件%.2f" % (
            bi, band.height, met.dh, met.base, kinds, row.text_score, row.comps_per_cluster
        )
        drawn = label if cjk_ok else (
            "row%d h=%d dh=%.0f base=%.0f %s width=%.2f comps=%.2f"
            % (bi, band.height, met.dh, met.base, kinds, row.text_score, row.comps_per_cluster)
        )
        d.text((4, max(0, band.win_top - fnt.size - 3)), drawn, font=fnt, fill=(200, 20, 20))
        report.append("  " + label)
        report.append("      token: " + " ".join(g.token() for g in row.glyphs))

    lines = jianpu.analyze_page(image_path, status, out_png.parent / "work")
    report.append("  --- 最終輸出 ---")
    for ln in lines:
        report.append("      [conf %.2f h=%d] %s" % (ln.confidence, ln.height, ln.text))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)
    report.append("標註圖 -> %s" % out_png)


def main() -> int:
    ap = argparse.ArgumentParser(description="樂譜辨識診斷")
    ap.add_argument("source", help="PDF 或圖片檔")
    ap.add_argument("--page", type=int, default=0, help="只診斷指定頁（PDF，1 起算）")
    ap.add_argument("--out", default=str(ROOT / "build" / "debug"), help="輸出目錄")
    a = ap.parse_args()

    src = Path(a.source)
    if not src.exists():
        print("找不到檔案：%s" % src)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    pages: list[Path] = []
    if src.suffix.lower() == ".pdf":
        pages = list(rasterize.pdf_to_images(src, out / "pages"))
    else:
        pages = [src]
    if a.page:
        pages = pages[a.page - 1 : a.page]
    if not pages:
        print("沒有可診斷的頁面")
        return 2

    report: list[str] = []
    st = engine.detect_engine()
    report.append("引擎 %s  版本 %s" % (st.path or "(未偵測到)", st.version or "?"))
    report.append("可用語言 %s" % (st.languages,))
    report.append("")
    for i, p in enumerate(pages, start=(a.page or 1)):
        annotate(p, out / ("debug-p%d.png" % i), report)
        report.append("")

    txt = out / "debug.txt"
    txt.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print("\n報告 -> %s" % txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
