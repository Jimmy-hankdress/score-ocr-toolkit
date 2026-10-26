/* ============================================================
 * Phase 4B — Command Stack（純資料層：undo/redo/history/merge）
 *
 * 定位：第四層 Editor 的可逆記錄層。
 *   輸入：4A command API 產出的 { newDoc, commandRecord }
 *   輸出：含 before/after doc 快照的 append-only 歷史
 *
 * 設計原則：
 *   1. 快照式 undo/redo：每個 history entry 保存
 *      { commandRecord, firstCommand, before, after, chain }；
 *      undo 回 before、redo 回 after（deep-copy 回傳，不污染歷史）。
 *      revertPayload 仍留在 record 內供審計 / 4C 使用，
 *      但 stack 不靠它重建（避免靜默近似）。
 *   2. applyCommand 不自行「重新計算」newDoc：newDoc 來自
 *      (a) 第 4 參數，或 (b) commandRecord.newDoc（由呼叫端附上）；
 *      兩者皆無 → throw（no-fabricate 同源：不靜默重建）。
 *   3. 截斷語義：在 redo 分支上再 apply → 截斷 currentIndex 之後的歷史
 *      （標準 undo-stack：全 undo 後新命令取代整個 redo 分支）。
 *   4. 合併語義：同一 measureId + track 且時間差 ≤ mergeWindowMs
 *      → 併入上一 entry（history 長度不增）；每步仍存於 entry.chain（可審計）。
 *      合併後 undo/redo 以「entry」為單位復原（整個合併群一進一出）。
 *   5. 純資料：無 DOM/UI/儲存；doc 快照一律 deep-copy 隔離。
 *
 * 用法（Node）：
 *   const CS = require('./command_stack.js');
 *   const stack = CS.createCommandStack();           // 預設 800ms 窗
 *   const { newDoc, commandRecord } = Editor.addNote(doc, 0, 0, { pitch: 1 });
 *   const next = CS.applyCommand(stack, doc, commandRecord, newDoc);
 *   const prev = CS.undo(stack, next);
 * ============================================================ */
(function (root, factory) {
  'use strict';
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else if (root) root.CommandStack = factory();
})(typeof self !== 'undefined' ? self : (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  var DEFAULT_MERGE_WINDOW_MS = 800;

  function deepCopy(x) {
    if (x == null) return x;
    return JSON.parse(JSON.stringify(x));
  }

  /* ---- 建立 Command Stack（S 結構：{ history, currentIndex, config }）---- */
  function createCommandStack(options) {
    options = options || {};
    var w = (options.mergeWindowMs != null) ? options.mergeWindowMs : DEFAULT_MERGE_WINDOW_MS;
    if (typeof w !== 'number' || !isFinite(w) || w < 0) {
      throw new Error('command_stack: mergeWindowMs must be a finite number >= 0, got ' + w);
    }
    return {
      history: [],
      currentIndex: -1,
      config: { mergeWindowMs: w }
    };
  }

  /* ---- 取得歷史（回傳 live 陣列；供測試驗證長度）---- */
  function getHistory(stack) {
    return stack.history;
  }

  /* ---- 清空歷史 ---- */
  function clearHistory(stack) {
    stack.history = [];
    stack.currentIndex = -1;
  }

  function requireRecord(cr) {
    if (!cr || typeof cr !== 'object' || !cr.type) {
      throw new Error('command_stack: commandRecord must be an object with .type');
    }
    return cr;
  }

  /* ---- 應用命令：截斷 redo 分支 → （同 measure+track 且時間窗內）合併 → 推進 ---- */
  function applyCommand(stack, doc, commandRecord, newDoc) {
    requireRecord(commandRecord);
    var afterSrc = (newDoc != null) ? newDoc : commandRecord.newDoc;
    if (afterSrc == null) {
      throw new Error('command_stack: applyCommand needs newDoc（pass 4th arg or attach commandRecord.newDoc）— no silent reconstruction');
    }
    var before = deepCopy(doc);
    var after = deepCopy(afterSrc);

    // 1) 若 redo 分支存在（currentIndex 在尾端之前），截斷
    if (stack.currentIndex < stack.history.length - 1) {
      stack.history = stack.history.slice(0, stack.currentIndex + 1);
    }
    var last = stack.history[stack.history.length - 1];
    var sameTarget = last != null
      && last.commandRecord.measureId === commandRecord.measureId
      && last.commandRecord.track === commandRecord.track;
    var lastTs = (last != null) ? last.chain[last.chain.length - 1].commandRecord.timestamp : NaN;
    var inWindow = last != null
      && typeof commandRecord.timestamp === 'number'
      && isFinite(lastTs)
      && (commandRecord.timestamp - lastTs) <= stack.config.mergeWindowMs;

    if (sameTarget && inWindow) {
      // 2a) 合併：不增加 history 長度；步存 chain、after 推進到最新
      last.chain.push({ commandRecord: commandRecord, before: before, after: after });
      last.after = after;
      last.commandRecord = commandRecord; // 最新 record；firstCommand 保留供審計
    } else {
      // 2b) 新 entry
      stack.history.push({
        commandRecord: commandRecord,
        firstCommand: commandRecord,
        before: before,
        after: after,
        chain: [{ commandRecord: commandRecord, before: before, after: after }]
      });
    }
    // 3) 推進 currentIndex
    stack.currentIndex = stack.history.length - 1;
    return after;
  }

  /* ---- Undo：回退一個 entry（合併群＝一進）；空 stack 回傳原 doc，不崩潰 ---- */
  function undo(stack, doc) {
    if (stack.currentIndex < 0) return deepCopy(doc);
    var entry = stack.history[stack.currentIndex];
    stack.currentIndex -= 1;
    return deepCopy(entry.before);
  }

  /* ---- Redo：前進一個 entry；無前進空間回傳原 doc，不崩潰 ---- */
  function redo(stack, doc) {
    if (stack.currentIndex >= stack.history.length - 1) return deepCopy(doc);
    stack.currentIndex += 1;
    var entry = stack.history[stack.currentIndex];
    return deepCopy(entry.after);
  }

  /* ---- 顯式合併：遍歷 history，同一 measureId + track 且時間差 ≤ windowMs
     的相鄰 entry 併為一個（chain 拼接）；undo/redo 能力保留 ---- */
  function merge(stack, windowMs) {
    var w = (windowMs != null) ? windowMs : stack.config.mergeWindowMs;
    if (typeof w !== 'number' || !isFinite(w) || w < 0) {
      throw new Error('command_stack: merge windowMs must be a finite number >= 0, got ' + w);
    }
    var oldLen = stack.history.length;
    var wasAtTail = stack.currentIndex === oldLen - 1;
    var out = [];
    for (var i = 0; i < stack.history.length; i++) {
      var e = stack.history[i];
      var prev = out[out.length - 1];
      var collapsible = prev != null
        && prev.commandRecord.measureId === e.commandRecord.measureId
        && prev.commandRecord.track === e.commandRecord.track
        && isFinite(e.chain[0].commandRecord.timestamp)
        && isFinite(prev.chain[prev.chain.length - 1].commandRecord.timestamp)
        && (e.chain[0].commandRecord.timestamp - prev.chain[prev.chain.length - 1].commandRecord.timestamp) <= w;
      if (collapsible) {
        prev.chain = prev.chain.concat(e.chain);
        prev.after = e.after;
        prev.commandRecord = e.commandRecord; // 最新 record；firstCommand 保留
      } else {
        out.push(e);
      }
    }
    stack.history = out;
    if (wasAtTail) {
      stack.currentIndex = stack.history.length - 1;
    } else if (stack.currentIndex > stack.history.length - 1) {
      stack.currentIndex = stack.history.length - 1;
    }
  }

  return {
    createCommandStack: createCommandStack,
    getHistory: getHistory,
    clearHistory: clearHistory,
    applyCommand: applyCommand,
    undo: undo,
    redo: redo,
    merge: merge,
    version: 'phase4.0.0'
  };
});
