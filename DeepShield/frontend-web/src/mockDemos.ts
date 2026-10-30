import type { DeepReport, LoadedCase } from "./types";

/**
 * 內建高擬真範例 (免上傳、一鍵載入展示用).
 * 影音檔對應 public/demo/ 下的真實可播檔案 (8 秒), 時間軸與逐字稿時間一致.
 */

const celebrityReport: DeepReport = {
  fake_probability: 82.4,
  trust_score: 17.6,
  status: "DANGER",
  duration: 8.0,
  filename: "celebrity-investment-scam.mp4 (示範)",
  dimensions: {
    audio: {
      risk: 78.0,
      level: "DANGER",
      duration: 8.0,
      subscores: {
        high_freq_truncation: { risk: 92.0, hi_energy_ratio: 0.0091, cutoff_hz: 6000.0, rolloff_mean_hz: 5210.4 },
        noise_floor: { risk: 65.0, quiet_ratio: 0.31, digital_zero_ratio: 0.3821 },
        prosody_breath: { risk: 62.0, jitter: 0.0021, f0_std: 6.4, jitter_risk: 80.0, breath_gaps: 0, breath_per_min: 0.0, breath_risk: 50.0 },
      },
      anomalies: [
        { start: 1.0, end: 2.2, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0091)" },
        { start: 4.4, end: 6.0, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0082)" },
      ],
      spectrogram_b64: "/demo/celebrity-spectrogram.png",
      deep_model: "inactive (no weights)",
    },
    visual: {
      risk: 86.0,
      level: "DANGER",
      duration: 8.0,
      frames_analyzed: 60,
      subscores: {
        blending_boundary: { risk: 88.0, median_laplacian_var: 9.4 },
        temporal_flicker: { risk: 82.0, median_frame_diff: 0.1132 },
        blink_pose: { risk: 70.0, detail: "8 秒以上無眨眼" },
        rppg: { risk: 75.0, note: "無明顯心跳頻率峰值", peak_bpm: 0.0, snr: 1.02 },
      },
      anomalies: [
        { start: 2.1, end: 2.4, type: "FACE_FLICKER", description: "臉部區域幀間閃爍 (diff=0.131)" },
        { start: 5.5, end: 5.9, type: "FACE_FLICKER", description: "臉部區域幀間閃爍 (diff=0.148)" },
      ],
      heatmap_b64: "/demo/celebrity-heatmap.png",
    },
    av_sync: {
      risk: 71.0,
      level: "DANGER",
      lag_ms: 182.0,
      correlation: 0.18,
      sync_score: 29.0,
      mismatches: [
        { start: 2.0, end: 4.2, type: "LIP_SYNC_MISMATCH", description: "影音延遲約 182ms (超過 100ms 容忍)" },
        { start: 4.2, end: 6.2, type: "LIP_SYNC_MISMATCH", description: "雙唇音期間嘴型幾無變化 (疑似配音/Lip-Sync)" },
      ],
    },
    semantic: {
      risk: 88.0,
      level: "DANGER",
      hit_count: 6,
      stt_available: true,
      full_text: "各位粉絲大家好，我是你們最信任的財經老師現在加入我的群組，保證獲利，飆股內線免費送名額只剩最後三十位，趕快匯款到監管帳戶卡位記住不要告訴別人，這是老師給你的專屬機會",
      transcript: [
        { start: 0.0, end: 2.0, text: "各位粉絲大家好，我是你們最信任的財經老師" },
        { start: 2.0, end: 4.2, text: "現在加入我的群組，保證獲利，飆股內線免費送" },
        { start: 4.2, end: 6.2, text: "名額只剩最後三十位，趕快匯款到監管帳戶卡位" },
        { start: 6.2, end: 8.0, text: "記住不要告訴別人，這是老師給你的專屬機會" },
      ],
      hits: [
        { keyword: "保證獲利", category: "投資詐騙", start: 2.6, end: 3.2 },
        { keyword: "飆股", category: "投資詐騙", start: 3.4, end: 3.8 },
        { keyword: "匯款", category: "資金轉移", start: 4.9, end: 5.3 },
        { keyword: "監管帳戶", category: "假冒公檢法", start: 5.4, end: 6.0 },
        { keyword: "不要告訴別人", category: "社交工程", start: 6.4, end: 7.1 },
        { keyword: "老師", category: "假冒權威", start: 7.5, end: 7.8 },
      ],
      spans: [
        { start: 2.6, end: 3.2, text: "保證獲利", keyword: "保證獲利", category: "投資詐騙" },
        { start: 3.4, end: 3.8, text: "飆股", keyword: "飆股", category: "投資詐騙" },
        { start: 4.9, end: 5.3, text: "匯款", keyword: "匯款", category: "資金轉移" },
        { start: 5.4, end: 6.0, text: "監管帳戶", keyword: "監管帳戶", category: "假冒公檢法" },
        { start: 6.4, end: 7.1, text: "不要告訴別人", keyword: "不要告訴別人", category: "社交工程" },
        { start: 7.5, end: 7.8, text: "老師", keyword: "老師", category: "假冒權威" },
      ],
    },
  },
  timeline: [
    { start: 1.0, end: 2.2, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0091)" },
    { start: 2.0, end: 4.2, type: "LIP_SYNC_MISMATCH", description: "影音延遲約 182ms (超過 100ms 容忍)" },
    { start: 2.1, end: 2.4, type: "FACE_FLICKER", description: "臉部區域幀間閃爍 (diff=0.131)" },
    { start: 2.6, end: 3.2, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 保證獲利" },
    { start: 3.4, end: 3.8, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 飆股" },
    { start: 4.2, end: 6.2, type: "LIP_SYNC_MISMATCH", description: "雙唇音期間嘴型幾無變化 (疑似配音/Lip-Sync)" },
    { start: 4.4, end: 6.0, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0082)" },
    { start: 4.9, end: 5.3, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 匯款" },
    { start: 5.4, end: 6.0, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 監管帳戶" },
    { start: 5.5, end: 5.9, type: "FACE_FLICKER", description: "臉部區域幀間閃爍 (diff=0.148)" },
    { start: 6.4, end: 7.1, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 不要告訴別人" },
    { start: 7.5, end: 7.8, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 老師" },
  ],
  skipped_dimensions: [],
};

const voiceReport: DeepReport = {
  fake_probability: 76.9,
  trust_score: 23.1,
  status: "DANGER",
  duration: 8.0,
  filename: "voice-loan-scam.wav (示範)",
  dimensions: {
    audio: {
      risk: 81.0,
      level: "DANGER",
      duration: 8.0,
      subscores: {
        high_freq_truncation: { risk: 75.0, hi_energy_ratio: 0.0112, cutoff_hz: 6000.0, rolloff_mean_hz: 5872.9 },
        noise_floor: { risk: 85.0, quiet_ratio: 0.42, digital_zero_ratio: 0.4103 },
        prosody_breath: { risk: 78.0, jitter: 0.0016, f0_std: 4.1, jitter_risk: 90.0, breath_gaps: 0, breath_per_min: 0.0, breath_risk: 60.0 },
      },
      anomalies: [
        { start: 2.4, end: 3.6, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0112)" },
        { start: 5.2, end: 6.9, type: "AUDIO_ANOMALY", description: "數位絕對靜音疑似剪接點" },
      ],
      spectrogram_b64: "/demo/voice-spectrogram.png",
      deep_model: "inactive (no weights)",
    },
    visual: {
      risk: 0.0,
      level: "SAFE",
      note: "純音檔, 視覺維度略過",
      anomalies: [],
      heatmap_b64: "",
      subscores: {},
    },
    av_sync: {
      risk: 0.0,
      level: "SAFE",
      note: "純音檔, 同步維度略過",
      mismatches: [],
    },
    semantic: {
      risk: 91.0,
      level: "DANGER",
      hit_count: 4,
      stt_available: true,
      full_text: "喂，是我啦，堂弟，我出車禍了，現在急用錢你先幫我匯款三萬到這個帳號，救急一下這件事不能告訴別人，也不要跟爸媽說等一下我會傳驗證碼給你，你幫我收一下就好",
      transcript: [
        { start: 0.0, end: 2.2, text: "喂，是我啦，堂弟，我出車禍了，現在急用錢" },
        { start: 2.2, end: 4.4, text: "你先幫我匯款三萬到這個帳號，救急一下" },
        { start: 4.4, end: 6.4, text: "這件事不能告訴別人，也不要跟爸媽說" },
        { start: 6.4, end: 8.0, text: "等一下我會傳驗證碼給你，你幫我收一下就好" },
      ],
      hits: [
        { keyword: "急用錢", category: "親友詐騙", start: 1.5, end: 2.0 },
        { keyword: "匯款", category: "資金轉移", start: 2.6, end: 3.0 },
        { keyword: "不能告訴別人", category: "社交工程", start: 4.7, end: 5.4 },
        { keyword: "驗證碼", category: "個資竊取", start: 6.9, end: 7.4 },
      ],
      spans: [
        { start: 1.5, end: 2.0, text: "急用錢", keyword: "急用錢", category: "親友詐騙" },
        { start: 2.6, end: 3.0, text: "匯款", keyword: "匯款", category: "資金轉移" },
        { start: 4.7, end: 5.4, text: "不能告訴別人", keyword: "不能告訴別人", category: "社交工程" },
        { start: 6.9, end: 7.4, text: "驗證碼", keyword: "驗證碼", category: "個資竊取" },
      ],
    },
  },
  timeline: [
    { start: 1.5, end: 2.0, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 急用錢" },
    { start: 2.4, end: 3.6, type: "AUDIO_ANOMALY", description: "高頻能量異常低 (hi_ratio=0.0112)" },
    { start: 2.6, end: 3.0, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 匯款" },
    { start: 4.7, end: 5.4, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 不能告訴別人" },
    { start: 5.2, end: 6.9, type: "AUDIO_ANOMALY", description: "數位絕對靜音疑似剪接點" },
    { start: 6.9, end: 7.4, type: "SCAM_KEYWORD", description: "詐騙關鍵詞: 驗證碼" },
  ],
  skipped_dimensions: ["visual", "avsync"],
};

export const demoCelebrity: LoadedCase = {
  report: celebrityReport,
  mediaUrl: "/demo/celebrity-investment-scam.mp4",
  mediaKind: "video",
  source: "demo-celebrity",
  label: "範例：名人投資詐騙 Deepfake",
};

export const demoVoice: LoadedCase = {
  report: voiceReport,
  mediaUrl: "/demo/voice-loan-scam.wav",
  mediaKind: "audio",
  source: "demo-voice",
  label: "範例：AI 語音親友借錢詐騙",
};
