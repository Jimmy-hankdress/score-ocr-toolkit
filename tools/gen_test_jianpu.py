"""產生含標準答案的簡譜測試圖，用來量化辨識準確度。

用法（在專案根目錄執行）：
    python tools/gen_test_jianpu.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "jianpu-test"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DIGIT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"

W, H = 2480, 1400  # A4 300dpi 寬
FS = 46            # 數字字級
LYRIC_FS = 40


def draw_note(dr, x, y, token, font):
    """畫一個音符 token，回傳寬度。token 例：5'  1,  5_  7__  2.  3',_"""
    digit = token[0]
    high = token.count("'")
    low = token.count(",")
    unders = token.count("_")
    dotted = "." in token

    bbox = dr.textbbox((x, y), digit, font=font)
    dr.text((x, y), digit, fill=0, font=font)
    dw = bbox[2] - bbox[0]
    dh = bbox[3] - bbox[1]
    cx = bbox[0] + dw / 2
    r = max(2, int(dh * 0.075))  # 圓點半徑

    # 高音點：往上疊
    for i in range(high):
        cy = bbox[1] - int(dh * 0.22) - i * int(dh * 0.30)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)

    # 減時線：緊貼數字下方
    line_y = bbox[3] + int(dh * 0.16)
    th = max(2, int(dh * 0.055))
    for i in range(unders):
        yy = line_y + i * (th + int(dh * 0.13))
        dr.rectangle([bbox[0], yy, bbox[0] + dw, yy + th], fill=0)

    # 低音點：畫在減時線更下方，避免重疊
    base = line_y + unders * (th + int(dh * 0.13)) + int(dh * 0.18)
    for i in range(low):
        cy = base + r + i * int(dh * 0.30)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)

    # 附點：右側中段
    if dotted:
        px = bbox[2] + int(dw * 0.32)
        py = bbox[1] + dh * 0.55
        dr.ellipse([px - r, py - r, px + r, py + r], fill=0)

    return dw + int(dw * (1.15 if dotted else 0.75))


def main():
    out = (OUT / "test-jianpu.png")
    img = Image.new("L", (W, H), 255)
    dr = ImageDraw.Draw(img)
    dfont = ImageFont.truetype(DIGIT_FONT, FS)
    hfont = ImageFont.truetype(DIGIT_FONT, 40)
    lfont = ImageFont.truetype(CJK_FONT, LYRIC_FS)

    dr.text((150, 90), "1=A   4/4   J=90", fill=0, font=hfont)

    # 標準答案：每行的 token 序列（含小節線）
    rows = [
        ["1", "5'", "1,", "-", "|", "5_", "7__", "2.", "3", "|", "6", "4", "2'", "1"],
        ["3_", "3_", "2.", "1", "|", "5,", "6,", "7,", "1", "|", "2''", "1'", "5", "-"],
        ["1_", "2_", "3_", "4_", "|", "5.", "6", "7__", "1'", "|", "6,", "5,", "3", "-"],
    ]
    lyrics = ["春風輕唱著歌謠", "星光落在窗前", "夜色溫柔如水"]

    truth = []
    y = 230
    for ri, row in enumerate(rows):
        x = 180
        for token in row:
            if token == "|":
                bb = dr.textbbox((x, y), "|", font=dfont)
                dr.text((x, y), "|", fill=0, font=dfont)
                x += (bb[2] - bb[0]) + 26
                continue
            x += draw_note(dr, x, y, token, dfont) + 22
        truth.append([t for t in row])
        dr.text((180, y + 150), lyrics[ri], fill=0, font=lfont)
        y += 330

    img.save(out)
    (OUT / "test-jianpu-truth.json").write_text(
        json.dumps({"rows": truth, "lyrics": lyrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("已產生", out, img.size)
    print("標準答案列數:", len(truth))


if __name__ == "__main__":
    main()
