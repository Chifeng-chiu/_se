// DeepShield background service worker (MV3).
// 職責：替 content script 開新分頁（content 沒有 chrome.tabs 權限）。
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "OPEN_DASHBOARD" && typeof msg.url === "string") {
    chrome.tabs
      .create({ url: msg.url })
      .then(() => sendResponse({ ok: true }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true; // 非同步回覆
  }
  return false;
});

chrome.runtime.onInstalled.addListener(() => {
  console.log("[DeepShield] background ready");
});
