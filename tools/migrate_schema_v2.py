#!/usr/bin/env python3
"""Schema v1 → v2 遷移：為所有專案補齊 noteTicks/lyricTicks/chordTicks

用法：
  python tools/migrate_schema_v2.py --dry-run   # 預覽
  python tools/migrate_schema_v2.py --execute   # 實際執行
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import ScoreDocument, ScoreMeasure, split_notes, split_lyrics, split_chords

DATA_ROOT = Path(r"D:\SheetMusicOMR_v3.00\data\projects")
BACKUP_ROOT = Path(r"D:\SheetMusicOMR_v3.00\_backup_schema_v2")

def tick_to_beat(tick: int) -> int:
    return max(1, (tick // 480) + 1)

def default_ticks(count: int, step: int = 480) -> list[int]:
    return [i * step for i in range(count)]

def rebuild_measure_ticks(m: ScoreMeasure) -> bool:
    """重建單個小節的 tick 陣列。回傳是否有變更。"""
    changed = False
    
    notes = split_notes(m.noteText)
    lyrics = split_lyrics(m.lyricText)
    chords = split_chords(m.chordText)
    
    # noteTicks
    if notes and (not m.noteTicks or len(m.noteTicks) != len(notes)):
        m.noteTicks = default_ticks(len(notes))
        changed = True
    
    # lyricTicks (for all 4 lyric fields; field 1 的 tick 欄位名為 lyricTicks)
    for field, tick_field in [('lyricText', 'lyricTicks'),
                              ('lyricText2', 'lyricText2Ticks'),
                              ('lyricText3', 'lyricText3Ticks'),
                              ('lyricText4', 'lyricText4Ticks')]:
        lyric_val = getattr(m, field)
        lyric_syls = split_lyrics(lyric_val)
        existing = getattr(m, tick_field, [])
        if lyric_syls and (not existing or len(existing) != len(lyric_syls)):
            # 對齊到音符拍位
            if m.noteTicks:
                # 使用音符的 tick 位置
                target_ticks = m.noteTicks[:len(lyric_syls)]
                if len(target_ticks) < len(lyric_syls):
                    # 補齊
                    last = target_ticks[-1] if target_ticks else 0
                    target_ticks = target_ticks + [last + 480 * (i + 1) for i in range(len(lyric_syls) - len(target_ticks))]
                setattr(m, tick_field, target_ticks)
            else:
                setattr(m, tick_field, default_ticks(len(lyric_syls)))
            changed = True
    
    # chordTicks
    if chords:
        if not m.chordTicks or len(m.chordTicks) != len(chords):
            if m.chordOffsets and len(m.chordOffsets) >= len(chords):
                m.chordTicks = [x * 480 for x in m.chordOffsets[:len(chords)]]
            else:
                # 對齊到拍群
                if m.noteTicks:
                    target_ticks = m.noteTicks[:len(chords)]
                    if len(target_ticks) < len(chords):
                        last = target_ticks[-1] if target_ticks else 0
                        target_ticks = target_ticks + [last + 480 * (i + 1) for i in range(len(chords) - len(target_ticks))]
                    m.chordTicks = target_ticks
                else:
                    m.chordTicks = default_ticks(len(chords))
            changed = True
    
    return changed

def migrate_project(project_dir: Path, dry_run: bool = True) -> dict:
    """遷移單個專案。"""
    project_file = project_dir / "project.json"
    if not project_file.exists():
        return {"id": project_dir.name, "status": "no_project_json"}
    
    try:
        data = json.loads(project_file.read_text(encoding="utf-8"))
        doc = ScoreDocument.from_dict(data)
        
        total_changed = 0
        for m in doc.measures:
            if rebuild_measure_ticks(m):
                total_changed += 1
        
        if total_changed > 0:
            if not dry_run:
                # 備份
                BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = BACKUP_ROOT / f"{project_dir.name}_{ts}.json"
                backup_file.write_text(project_file.read_text(encoding="utf-8"), encoding="utf-8")
                
                # 寫回
                payload = json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)
                project_file.write_text(payload, encoding="utf-8")
            
            return {"id": data.get("id"), "title": data.get("title"), "measures_changed": total_changed, "status": "migrated"}
        else:
            return {"id": data.get("id"), "title": data.get("title"), "status": "no_change"}
            
    except Exception as e:
        return {"id": project_dir.name, "status": "error", "error": str(e)}

def main():
    dry_run = "--dry-run" in sys.argv
    execute = "--execute" in sys.argv
    
    if not dry_run and not execute:
        print("用法: python migrate_schema_v2.py --dry-run | --execute")
        sys.exit(1)
    
    print(f"模式: {'預覽' if dry_run else '執行'}")
    print(f"掃描目錄: {DATA_ROOT}")
    
    if not DATA_ROOT.exists():
        print(f"目錄不存在: {DATA_ROOT}")
        sys.exit(1)
    
    results = []
    for project_dir in sorted(DATA_ROOT.iterdir()):
        if project_dir.is_dir():
            result = migrate_project(project_dir, dry_run=dry_run)
            results.append(result)
            status = result.get("status", "unknown")
            if status == "migrated":
                print(f"  ✓ {result['title']} ({result['id']}) - {result['measures_changed']} 小節已更新")
            elif status == "no_change":
                print(f"  - {result['title']} ({result['id']}) - 無需變更")
            elif status == "error":
                print(f"  ✗ {result['id']} - 錯誤: {result.get('error')}")
            else:
                print(f"  ? {result['id']} - {status}")
    
    migrated = sum(1 for r in results if r.get("status") == "migrated")
    errors = sum(1 for r in results if r.get("status") == "error")
    print(f"\n總計: {len(results)} 專案, {migrated} 已遷移, {errors} 錯誤")
    
    if dry_run:
        print("\n若確認無誤，請執行: python tools/migrate_schema_v2.py --execute")

if __name__ == "__main__":
    main()