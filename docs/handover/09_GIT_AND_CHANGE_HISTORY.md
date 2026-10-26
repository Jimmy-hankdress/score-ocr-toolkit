# Git 狀態與變更歷史

## 一、Git 狀態

**重要**: 此專案 **不是 Git 倉庫**。

```
D:\SheetMusicOMR_v3.00> git status
fatal: not a git repository (or any of the parent directories): .git
```

**結論**: 無 version control，所有版本管理依賴備份目錄。

## 二、備份目錄清單

| 目錄 | 建立時間 | 內容 | 用途 |
|------|----------|------|------|
| `web_backup_before_v305_20261001_164845/` | 2026-10-01 | app.js, index.html, styles.css | v3.05 前備份 |
| `_backup_before_chordslider/` | - | app.js, styles.css, score-chord-diagram.js | 和弦滑塊前備份 |
| `_backup_before_legacy_ui/` | - | app.js, index.html, styles.css | Legacy UI 前備份 |
| `_backup_before_phase5/` | - | phase4/, phase15/, web/ | Phase 5 前備份 |
| `_backup_before_phase6b4/` | - | phase6/, phase4/, phase15/, web/ | Phase 6b4 前備份 |
| `_backup_before_phase6b4_cleanup/` | - | phase6/, cache/, web/ | 清理前備份 |
| `_backup_before_phase6b5/` | - | HANDOFF.md, app/, phase6/, web/ | Phase 6b5 前備份 |

## 三、重要變更歷程

### v3.05.07 (當前)
- **日期**: 2026-10-13
- **變更**:
  - 回退 v3.05.08 的按鈕恢復
  - 維持乾淨 Legacy 顯示
  - 建立 Phase A Event Session 架構
- **檔案**:
  - `web/assets/app.js` SHA: `a828db1b01c0094f`
  - `web/assets/styles.css` SHA: `a1992be8926f2866`
  - `web/index.html` SHA: `dc46506250bcdc89`

### v3.05.08 (已回退)
- **日期**: 2026-10-13
- **變更**:
  - 恢復 note-add, lyric-add, chord-slot-add/del 按鈕
  - 新增 hover 顯示規則
- **狀態**: 已回退到 v3.05.07

### Phase A 建立
- **日期**: 2026-10-13
- **新增檔案**:
  - `web/assets/event_session.js`
  - `web/assets/event_session.css`
  - `web/assets/phase_a_integration.js`

## 四、未提交修改

由於無 Git，所有修改直接寫入檔案。

**建議**: 啟動前請先建立備份。

## 五、保護檔案

以下檔案請勿刪除或修改：

| 檔案/目錄 | 原因 |
|-----------|------|
| `data/projects/` | 使用者專案資料 |
| `data/sheetmusic.sqlite3` | 資料庫 |
| `data/tasks.db` | 任務佇列 |
| 所有 `_backup_*` 目錄 | 歷史備份 |

## 六、建議的 Version Control 策略

若未來需要 Git：

```powershell
# 初始化
cd D:\SheetMusicOMR_v3.00
git init

# 建立 .gitignore
echo ".venv/" > .gitignore
echo "data/projects/" >> .gitignore
echo "data/exports/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore

# 首次提交
git add .
git commit -m "Initial commit"
```
