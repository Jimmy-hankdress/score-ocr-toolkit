/**
 * Sync Version Tracker Module (web/assets/sync-version.js)
 * 追蹤 ChordPro 與 Score Studio 雙端編輯版本與內容雜湊，防止過期覆蓋與迴圈觸發。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    var conflictMod = null;
    try { conflictMod = require('./sync-conflict.js'); } catch (e) {}
    module.exports = factory(conflictMod);
  } else {
    var api = factory(root.SyncConflict);
    root.SyncVersion = api;
    root.versionTracker = api.versionTracker;
    root.trackVersion = api.trackVersion;
    root.isStale = api.isStale;
  }
})(typeof self !== 'undefined' ? self : this, function (ConflictMod) {
  'use strict';

  var hashFn = (ConflictMod && ConflictMod.computeContentHash)
    ? ConflictMod.computeContentHash
    : function (text) {
        var str = String(text || '');
        var hash = 0;
        for (var i = 0; i < str.length; i++) {
          hash = ((hash << 5) - hash) + str.charCodeAt(i);
          hash |= 0;
        }
        return hash.toString(16);
      };

  var versionTracker = {
    chordpro: { version: 0, hash: null, timestamp: null },
    scoreStudio: { version: 0, hash: null, timestamp: null },
    score: { version: 0, hash: null, timestamp: null },
    lastModifiedFormat: null,
    lastModifiedTime: null,
    chordproHash: null,
    scoreHash: null,
    revision: 0
  };

  function normalizeFormatKey(format) {
    if (format === 'score' || format === 'scoreStudio') return 'scoreStudio';
    return 'chordpro';
  }

  /**
   * 記錄指定格式的最新內容版本
   * @param {'chordpro'|'score'|'scoreStudio'} format
   * @param {string|object} content
   * @returns {{ version: number, hash: string, timestamp: number, revision: number }}
   */
  function trackVersion(format, content) {
    var serialized = typeof content === 'string' ? content : JSON.stringify(content || {});
    var hash = hashFn(serialized);
    var now = Date.now();
    var key = normalizeFormatKey(format);

    var nextVer = ((versionTracker[key] && versionTracker[key].version) || 0) + 1;
    var entry = {
      version: nextVer,
      hash: hash,
      timestamp: now
    };
    versionTracker[key] = entry;
    if (key === 'scoreStudio') {
      versionTracker.score = entry;
      versionTracker.scoreHash = hash;
    } else {
      versionTracker.chordproHash = hash;
    }

    versionTracker.lastModifiedFormat = format;
    versionTracker.lastModifiedTime = now;
    versionTracker.revision += 1;

    return {
      version: entry.version,
      hash: entry.hash,
      timestamp: entry.timestamp,
      revision: versionTracker.revision
    };
  }

  /**
   * 檢查目標格式的預期雜湊是否已過期
   * @param {'chordpro'|'score'|'scoreStudio'} format
   * @param {string} expectedHash
   * @returns {boolean}
   */
  function isStale(format, expectedHash) {
    var key = normalizeFormatKey(format);
    var currentHash = versionTracker[key] ? versionTracker[key].hash : null;
    return currentHash !== null && currentHash !== expectedHash;
  }

  function resetVersionTracker() {
    versionTracker.chordpro = { version: 0, hash: null, timestamp: null };
    versionTracker.scoreStudio = { version: 0, hash: null, timestamp: null };
    versionTracker.score = { version: 0, hash: null, timestamp: null };
    versionTracker.lastModifiedFormat = null;
    versionTracker.lastModifiedTime = null;
    versionTracker.chordproHash = null;
    versionTracker.scoreHash = null;
    versionTracker.revision = 0;
  }

  return {
    versionTracker: versionTracker,
    trackVersion: trackVersion,
    isStale: isStale,
    resetVersionTracker: resetVersionTracker
  };
});
