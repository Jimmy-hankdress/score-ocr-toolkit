"""逐 token 比對辨識結果與標準答案，輸出準確率。

用法（在專案根目錄執行）：
    python tools/score_jianpu.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "jianpu-test"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
import json
import re
import sys
from pathlib import Path


from app.omr import engine, jianpu  # noqa: E402

truth = json.loads((OUT / "test-jianpu-truth.json").read_text(encoding="utf-8"))
status = engine.detect_engine()
print("引擎:", status.mode, status.version, "| 可用語言:", status.languages)
print("數字模型:", jianpu.pick_digit_lang(status), "| 歌詞模型:", jianpu.pick_lyric_lang(status))
print()

work = (OUT / "work")
work.mkdir(parents=True, exist_ok=True)
lines = jianpu.analyze_page(OUT / "test-jianpu.png", status, work, 1)

print("=== 辨識出的列 ===")
for ln in lines:
    print("  [conf %.2f] %s" % (ln.confidence, ln.text))
print()

TOK = re.compile(r"^[0-7]+['\u2019,_.]*$|^[-|]$")
note_lines = [ln.text for ln in lines
              if ln.text.split() and sum(1 for t in ln.text.split() if TOK.match(t)) >= len(ln.text.split())*0.7]
expected_rows = [[t for t in row if t != "|"] for row in truth["rows"]]

total = hit = 0
pitch_hit = 0
mark_total = mark_hit = 0
for ri, exp in enumerate(expected_rows):
    got_raw = note_lines[ri].split() if ri < len(note_lines) else []
    got = [t for t in got_raw if t != "|"]
    got = [t for t in got if t not in ("-",)] if False else got
    print("第 %d 行" % (ri + 1))
    print("  標準答案:", " ".join(exp))
    print("  辨識結果:", " ".join(got))
    for i, e in enumerate(exp):
        total += 1
        g = got[i] if i < len(got) else ""
        if g == e:
            hit += 1
        if g[:1] == e[:1]:
            pitch_hit += 1
        # 只比對附加符號部分
        em, gm = e[1:], g[1:]
        if em or gm:
            mark_total += 1
            if em == gm:
                mark_hit += 1
    print()

print("=== 成績 ===")
print("  完全正確 token : %d/%d  (%.0f%%)" % (hit, total, 100.0 * hit / max(1, total)))
print("  音高正確       : %d/%d  (%.0f%%)" % (pitch_hit, total, 100.0 * pitch_hit / max(1, total)))
print("  附加符號正確   : %d/%d  (%.0f%%)" % (mark_hit, mark_total, 100.0 * mark_hit / max(1, mark_total)))
print()
lyric_lines = [ln.text for ln in lines if ln.text not in note_lines and "=" not in ln.text]
print("=== 歌詞 ===")
for exp, got in zip(truth["lyrics"], lyric_lines + [""] * 3):
    ok = sum(1 for a, b in zip(exp, got) if a == b)
    print("  標準:%s  辨識:%s  逐字命中 %d/%d" % (exp, got, ok, len(exp)))
