// DeepShield popup: 後端狀態 + 快捷入口
(function () {
  var API = "http://localhost:8000";
  var st = document.getElementById("status");
  fetch(API + "/api/v1/health")
    .then(function (r) {
      if (!r.ok) throw new Error("bad status");
      return r.json();
    })
    .then(function (j) {
      var f = j.features || {};
      st.textContent =
        "後端運行中 v" + (j.version || "?") +
        "（opencv:" + (f.opencv ? "✓" : "✗") +
        " librosa:" + (f.librosa ? "✓" : "✗") +
        " mediapipe:" + (f.mediapipe ? "✓" : "✗") + "）";
      st.style.color = "#6ee7b7";
    })
    .catch(function () {
      st.textContent = "後端未連線：請先雙擊桌面「DeepShield 啟動」";
      st.style.color = "#fca5a5";
    });
  document.getElementById("openDash").addEventListener("click", function () {
    chrome.tabs.create({ url: "http://localhost:5173" });
  });
  document.getElementById("openDocs").addEventListener("click", function () {
    chrome.tabs.create({ url: API + "/docs" });
  });
})();
