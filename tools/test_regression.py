"""回歸測試：守住幾個曾經真的出過的錯。

這裡的每一項都對應一個實際發生過、而且**在原本的測試裡看不出來**的問題。
不需要語言包或字型，幾秒跑完。開發時改動 `app/omr/jianpu.py` 後請先跑這支::

    python tools/test_regression.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.omr.jianpu import (  # noqa: E402
    MAX_STRIP_WIDTH,
    Band,
    _crop_band,
    _is_watermark,
    find_bands,
)

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("✓" if ok else "✗", name, ("  " + detail) if detail else ""))
    if not ok:
        fails.append(name)


print("一、列裁切放大倍率（真實掃描件寬度）")
# 曾經的錯：上限寫成 `4000 // strip.width`，頁寬超過 2000px 就算出 1，
# 等於把放大整個關掉，歌詞辨識率大跌。當時的測試圖只有 1240px 寬，測不出來。
for w in (1240, 2000, 2480, 3000, 4000):
    strip = _crop_band(Image.new("L", (w, 400), 255), Band(top=100, bottom=120), w)
    check("頁寬 %d 的 20px 列有放大" % w, strip.height >= 40, "高度 %d" % strip.height)

print("二、放大後的寬度上限（避免超寬圖讓 Tesseract 卡住）")
for w in (2480, 6000):
    strip = _crop_band(Image.new("L", (w, 400), 255), Band(top=100, bottom=105), w)
    check(
        "頁寬 %d 的 5px 列不超過上限" % w,
        strip.width <= MAX_STRIP_WIDTH,
        "寬度 %d" % strip.width,
    )

print("三、高低音點列不能升格成內容列")
# 曾經的錯：核心列門檻用「所有投影列的中位數高度」，但點列數量多於內容列，
# 中位數被拉到圓點高度，點列自己變成內容列 → 八度記號永遠接不回數字上。
ink = np.zeros((300, 1240), dtype=np.uint8)
ink[100:120, 100:900] = 1  # 數字列
ink[88:93, 100:120] = 1  # 上方點列
ink[88:93, 200:220] = 1
ink[88:93, 300:320] = 1
ink[88:93, 400:420] = 1
ink[128:133, 150:170] = 1  # 下方點列
ink[128:133, 250:270] = 1
ink[128:133, 350:370] = 1
bands = find_bands(ink)
check("三條投影列只切出 1 條內容列", len(bands) == 1, "實際 %d 條" % len(bands))
if bands:
    b = bands[0]
    check("內容列高度是數字的高度", 18 <= b.height <= 22, "高度 %d" % b.height)
    check("分析視窗包含上下的點", b.win_top <= 90 and b.win_bottom >= 131,
          "視窗 %d~%d" % (b.win_top, b.win_bottom))

print("四、浮水印判定（寧可漏刪也不能誤刪歌詞）")
for text, want in [
    ("僅供個人學習使用,歡迎轉載、分享、收藏,篡改必究!", True),
    ("www.qupu123.com 曲譜網", True),
    ("Copyright All Rights Reserved", True),
    ("本譜版權所有,侵權必究", True),
    ("如果那兩個字沒有顫抖", False),
    ("我想和你分享這份心情", False),
    ("所有的星光都收藏起來", False),
    ("成千上萬個門口總有一個人要先走", False),
]:
    got = _is_watermark(text)
    check("%s → %s" % (text[:18], "浮水印" if want else "歌詞"), got == want)

print()
if fails:
    print("有 %d 項未通過：%s" % (len(fails), "、".join(fails)))
    raise SystemExit(1)
print("全部通過")
