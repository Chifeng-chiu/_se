// DeepShield bridge (解法 B 雙保險)：跑在 http://localhost:5173/*。
// 外掛打開 dashboard 分頁時，把 chrome.storage 的送檢報告塞進該 origin 的
// localStorage，讓 App 的解法 A 讀不到時也有本地副本可讀。寫完才重整，且只重整一次。
(function () {
  try {
    const q = new URLSearchParams(location.search);
    if (q.get("from") !== "extension") return;
    const sid = q.get("session_id") || "";
    if (!sid) return;
    const key = "deepshield:session:" + sid;
    let existing = null;
    try {
      existing = localStorage.getItem(key);
    } catch (e) {
      existing = null;
    }
    if (existing) return; // 已有副本，不做任何事（避免重整迴圈）
    chrome.storage.local.get([key], (res) => {
      try {
        const val = res && res[key];
        if (!val) return; // 沒有備份就讓 App 走後端 session API
        localStorage.setItem(key, typeof val === "string" ? val : JSON.stringify(val));
        location.reload();
      } catch (e) {
        /* 寫入失敗就讓 App 走後端 */
      }
    });
  } catch (e) {
    /* 絕不影響 dashboard 本體 */
  }
})();
