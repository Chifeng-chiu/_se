/** 與後端 POST /api/v1/analyze/deep 回傳 JSON 對齊的型別. */

export type Verdict = "SAFE" | "WARNING" | "DANGER";

export interface TimelineEvent {
  start: number;
  end: number;
  type: "AUDIO_ANOMALY" | "FACE_FLICKER" | "LIP_SYNC_MISMATCH" | "SCAM_KEYWORD" | string;
  description: string;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface ScamSpan {
  start: number;
  end: number;
  text: string;
  keyword: string;
  category?: string;
}

export interface ScamHit {
  keyword: string;
  category: string;
  start: number;
  end: number;
}

export interface DimensionResult {
  risk: number;
  level?: Verdict;
  note?: string;
  error?: string;
  subscores?: Record<string, unknown>;
  anomalies?: TimelineEvent[];
  mismatches?: TimelineEvent[];
  spectrogram_b64?: string;
  heatmap_b64?: string;
  transcript?: TranscriptSegment[];
  full_text?: string;
  spans?: ScamSpan[];
  hits?: ScamHit[];
  hit_count?: number;
  stt_available?: boolean;
  duration?: number;
  frames_analyzed?: number;
  /** 後端額外證據欄位 (av_sync / audio) */
  deep_model?: string;
  lag_ms?: number;
  correlation?: number;
  sync_score?: number;
}

export interface FusionInfo {
  weights_used: Record<string, number>;
  boosts: string[];
}

export interface DeepReport {
  fake_probability: number;
  trust_score: number;
  status: Verdict;
  duration: number;
  filename?: string;
  /** 後端新增: 檔案 SHA-256 指紋 + 鑑識時間 (舊報告/示範可缺省, 前端自動 fallback) */
  sha256_hash?: string;
  analyzed_at?: string;
  fusion?: FusionInfo;
  dimensions: {
    audio: DimensionResult;
    visual: DimensionResult;
    av_sync: DimensionResult;
    semantic: DimensionResult;
  };
  timeline: TimelineEvent[];
  skipped_dimensions: string[];
}

export type MediaKind = "video" | "audio";

export interface LoadedCase {
  report: DeepReport;
  mediaUrl: string | null;
  mediaKind: MediaKind;
  /** upload | demo-celebrity | demo-voice | extension */
  source: string;
  label: string;
}
