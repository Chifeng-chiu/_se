"""模組 2: 視覺深偽分析器 (visual_forensics.py)

- 換臉邊界/閃爍: 臉緣梯度 (Laplacian) + 連續幀 ROI 差分
- 眨眼/姿態: MediaPipe FaceMesh 的 EAR + 鼻尖對稱性 (無 FaceMesh 時降級為 Haar)
- rPPG (僅深度掃描): 額頭/臉頰綠通道 FFT 找 0.75–2.5Hz 心跳峰
- 輸出偽造區域熱力圖 (Sobel 梯度 + 臉緣遮罩) base64 + 時間軸

預留 DL 接口: VISUAL_MODEL_PATH / load_deep_model()
"""
from __future__ import annotations

import os

import cv2
import numpy as np

MODEL_PATH = os.environ.get("DEEPSHIELD_VISUAL_MODEL", "")
_deep_model = None

# MediaPipe 468 點關鍵索引
L_EYE = [33, 160, 158, 133, 153, 144]
R_EYE = [362, 385, 387, 263, 373, 380]
MOUTH_UP, MOUTH_LO, MOUTH_L, MOUTH_R = 13, 14, 61, 291
FOREHEAD = [10, 67, 69, 104, 103, 54]


def load_deep_model(path: str = MODEL_PATH):
    global _deep_model
    if not path or not os.path.exists(path):
        return None
    try:
        import onnxruntime as ort  # type: ignore
        _deep_model = ort.InferenceSession(path)
        return _deep_model
    except Exception:
        return None


def _get_facemesh():
    try:
        import mediapipe as mp  # type: ignore
        return mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1,
            refine_landmarks=True, min_detection_confidence=0.4)
    except Exception:
        return None


def _ear(pts: np.ndarray, idx: list[int]) -> float:
    p = pts[idx].astype(float)
    v1 = np.linalg.norm(p[1] - p[5])
    v2 = np.linalg.norm(p[2] - p[4])
    h = np.linalg.norm(p[0] - p[3])
    return float((v1 + v2) / (2.0 * h + 1e-9))


def _topk_mean(vals: list[float], frac: float = 0.25) -> float:
    """Top-K 聚合：取最高風險的前 frac 個樣本平均，避免長片平均稀釋峰值。"""
    import math
    if not vals:
        return 0.0
    k = max(1, int(math.ceil(len(vals) * frac)))
    top = sorted(vals, reverse=True)[:k]
    return float(sum(top) / len(top))


def _edge_risk_of(lap_var: float) -> float:
    # 自然臉 lap var 通常 >60; <25 高度平滑可疑
    if lap_var < 12:
        return 85.0
    if lap_var < 25:
        return 65.0
    if lap_var < 45:
        return 35.0
    return 12.0


def _flick_risk_of(diff: float, has_lm: bool) -> float:
    if has_lm:
        return 75.0 if diff > 0.10 else (50.0 if diff > 0.07 else 12.0)
    return 75.0 if diff > 0.14 else (50.0 if diff > 0.10 else 12.0)


def _heat_overlay(frame_bgr: np.ndarray, face_box: tuple | None) -> np.ndarray:
    """Sobel 梯度 + 臉緣環遮罩 → JET 熱力圖疊加 (Grad-CAM 模擬).

    全程顯式型別 (numpy 為主)，避開 OpenCV 5 對混合型別/輸出行參數的嚴格限制。
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    mx = float(grad.max()) if grad.size else 0.0
    grad_n = (grad / mx * 255.0) if mx > 1e-9 else np.zeros_like(grad)
    if face_box is not None:
        x, y, w, h = face_box
        mask = np.zeros(grad.shape, dtype=np.float64)
        cv2.ellipse(mask, (x + w // 2, y + h // 2), (w // 2, h // 2), 0, 0, 360, 1.0, -1)
        eroded = cv2.erode((mask * 255.0).astype(np.uint8),
                           np.ones((15, 15), np.uint8)).astype(np.float64) / 255.0
        ring = np.clip(mask - eroded, 0.0, 1.0)  # 臉緣環
        heat_src = np.clip(grad_n * 0.6 + ring * 180.0, 0, 255).astype(np.uint8)
    else:
        heat_src = np.clip(grad_n, 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(heat_src, cv2.COLORMAP_JET)
    return cv2.addWeighted(frame_bgr, 0.55, heat, 0.45, 0)


def analyze_video_file(path: str, max_frames: int = 90, sample_every: int = 8,
                       with_rppg: bool = True) -> dict:
    """主入口: 影片路徑 → 風險 + 熱力圖 + 時間軸. 永不拋錯."""
    from .utils import b64_of_bgr
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"risk": 0.0, "error": "cannot open video",
                "subscores": {}, "anomalies": [], "heatmap_b64": "",
                "frames_analyzed": 0}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = round(total / fps, 2) if fps else 0.0

    mesh = _get_facemesh()
    haar, haar_ok = None, False
    # 候選順序: 專案自帶 models/ → cv2 內附 (opencv>=5 的 pip 包可能缺檔)
    candidates = [os.path.join(os.path.dirname(__file__), "..", "models",
                               "haarcascade_frontalface_default.xml")]
    try:
        candidates.append(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        pass
    for cand in candidates:
        try:
            h = cv2.CascadeClassifier(cand)
            if not h.empty():
                haar, haar_ok = h, True
                break
        except Exception:
            continue

    edge_scores, flickers, ears, syms = [], [], [], []
    scene_diffs, scene_laps = [], []  # 無臉時的場景級退路訊號
    prev_full = None
    green_series: list[float] = []
    times: list[float] = []
    anomalies: list[dict] = []
    heat_b64, worst_frame = "", None
    worst_score = float("-inf")
    prev_roi: np.ndarray | None = None
    idx = n = 0
    blink_count = 0
    prev_ear = None

    while n < max_frames:
        ok = cap.grab()
        if not ok:
            break
        if idx % sample_every != 0:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        idx += 1
        if not ok or frame is None:
            break
        t = round(idx / fps, 2)
        small = cv2.resize(frame, (480, int(frame.shape[0] * 480 / frame.shape[1])))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # 場景級退路訊號 (每一幀都採，與有無人臉無關)
        try:
            full = cv2.resize(gray, (160, 90)).astype(np.float64)
            if prev_full is not None:
                scene_diffs.append(float(np.mean(np.abs(full - prev_full)) / 255.0))
                scene_laps.append(float(cv2.Laplacian(full, cv2.CV_64F).var()))
            prev_full = full
        except Exception:
            pass

        pts = None
        box = None
        if mesh is not None:
            try:
                res = mesh.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    H, W = small.shape[:2]
                    pts = np.array([(p.x * W, p.y * H) for p in lm])
                    xs, ys = pts[:, 0], pts[:, 1]
                    box = (int(xs.min()), int(ys.min()),
                           int(xs.max() - xs.min()), int(ys.max() - ys.min()))
            except Exception:
                pts = None
        if pts is None and haar_ok:
            try:
                faces = haar.detectMultiScale(gray, 1.2, 4, minSize=(60, 60))
                if len(faces):
                    box = tuple(int(v) for v in faces[0])
            except Exception:
                pass

        if box is None:
            continue
        n += 1
        x, y, w, h = box
        x, y = max(x, 0), max(y, 0)
        roi = gray[y:y + h, x:x + w]
        if roi.size == 0:
            continue
        # 1) 臉緣梯度: 真臉邊緣銳利 (laplacian var 高); 換臉融合區過度平滑 (var 低)
        lap_var = float(cv2.Laplacian(roi, cv2.CV_64F).var())
        edge_scores.append(lap_var)
        # 2) 閃爍: 連續 ROI 差分
        rsz = cv2.resize(roi, (128, 128)).astype(np.float32) / 255.0
        if prev_roi is not None:
            flick = float(np.mean(np.abs(rsz - prev_roi)))
            flickers.append(flick)
            if flick > 0.12:
                anomalies.append({"start": t, "end": round(t + sample_every / fps, 2),
                                  "type": "FACE_FLICKER",
                                  "description": f"臉部區域幀間閃爍 (diff={flick:.3f})"})
        prev_roi = rsz
        # 3) EAR / 對稱
        if pts is not None:
            ear = (_ear(pts, L_EYE) + _ear(pts, R_EYE)) / 2
            ears.append(ear)
            if prev_ear is not None and prev_ear > 0.20 and ear <= 0.16:
                blink_count += 1
            prev_ear = ear
            nose = pts[1]
            syms.append(float(abs((nose[0] - (x + w / 2)) / (w + 1e-9))))
            # 綠通道 rPPG 採樣 (額頭)
            try:
                fpts = pts[FOREHEAD]
                fx, fy = float(fpts[:, 0].mean()), float(fpts[:, 1].mean())
                fh, fw = 18, 40
                patch = small[max(int(fy - fh), 0):int(fy),
                              max(int(fx - fw // 2), 0):int(fx + fw // 2)]
                if patch.size:
                    green_series.append(float(patch[:, :, 1].mean()))
                    times.append(t)
            except Exception:
                pass
        # 熱力圖候選: 梯度最低 (最平滑) 的臉 = 最可疑
        score = -lap_var
        if score > worst_score:
            worst_score = score
            worst_frame = _heat_overlay(small.copy(), box)
        times_all = t

    cap.release()
    try:
        mesh.close()
    except Exception:
        pass

    if n == 0:
        # 無人臉 → 場景級粗估 (AI 生成場景常有整體閃爍/過滑)，風險上限 65
        if scene_diffs:
            s_flick_rs = [_flick_risk_of(v, False) for v in scene_diffs]
            s_edge_rs = [_edge_risk_of(v) for v in (scene_laps or [])]
            flick_r = _topk_mean(s_flick_rs)
            edge_r = _topk_mean(s_edge_rs)
            med_d = float(np.median(scene_diffs))
            med_l = float(np.median(scene_laps)) if scene_laps else 100.0
            risk = min(65.0, _topk_mean(s_flick_rs + s_edge_rs))
            level = "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER")
            anomalies = []
            if med_d > 0.12:
                anomalies.append({"start": 0.0, "end": duration,
                                  "type": "SCENE_FLICKER",
                                  "description": f"場景級整體閃爍偏高 (diff={med_d:.3f})，疑似 AI 生成"})
            return {"risk": risk, "level": level, "frames_analyzed": 0,
                    "subscores": {
                        "scene_temporal": {"risk": flick_r, "median_frame_diff": round(med_d, 4)},
                        "scene_texture": {"risk": edge_r, "median_laplacian_var": round(med_l, 1)},
                    },
                    "anomalies": anomalies, "heatmap_b64": "", "duration": duration,
                    "note": "未偵測到人臉，改用場景級訊號粗估 (非人臉證據，僅供參考)"}
        det = ("無可用人臉偵測器 (mediapipe 未安裝且 haar 資料缺失)"
               if mesh is None and not haar_ok else "未偵測到人臉")
        return {"risk": 0.0, "level": "SAFE", "frames_analyzed": 0,
                "subscores": {}, "anomalies": [],
                "heatmap_b64": "", "duration": duration,
                "note": f"{det}, 視覺維度略過 (以 0 計)"}

    # —— 子分數 (Top-K 聚合：逐樣本風險取前 25% 平均，峰值不被稀釋) ——
    med_lap = float(np.median(edge_scores)) if edge_scores else 100.0
    med_flick = float(np.median(flickers)) if flickers else 0.0
    has_lm = len(ears) > 0  # 有無臉部關鍵點 (無則人臉框較抖動，門檻放寬)
    edge_rs = [_edge_risk_of(v) for v in edge_scores]
    # 共模抵銷：臉部閃爍若與整體場景同動 (比值 <1.5)，多半是鏡頭/人物移動
    # 而非換臉破綻 → 閃爍分量折半；靜態鏡頭下的臉部抖動則全額計分
    scene_med = float(np.median(scene_diffs)) if scene_diffs else 0.0
    common_mode = bool(scene_med > 1e-6 and (med_flick / max(scene_med, 1e-6)) < 1.5)
    disc = 0.5 if common_mode else 1.0
    flick_rs = [_flick_risk_of(v, has_lm) * disc for v in flickers]
    face_topk = _topk_mean(edge_rs + flick_rs)
    edge_risk = _topk_mean(edge_rs)
    flick_risk = _topk_mean(flick_rs)

    # 眨眼: 正常 12~25 次/分; deepfake 常 ~0 或 >40
    # (無關鍵點時測不到眨眼，給中性分避免誤罰)
    minutes = max(duration / 60.0, 1e-3)
    bpm_blink = blink_count / minutes if duration > 5 else -1
    if not has_lm:
        blink_risk, blink_note = 30.0, "無臉部關鍵點，眨眼僅供參考"
    elif bpm_blink < 0:
        blink_risk, blink_note = 30.0, "片段過短, 眨眼僅供參考"
    elif blink_count == 0 and duration > 8:
        blink_risk, blink_note = 70.0, "8 秒以上無眨眼"
    elif bpm_blink > 40:
        blink_risk, blink_note = 60.0, f"眨眼過頻 ({bpm_blink:.0f}/min)"
    else:
        blink_risk, blink_note = 12.0, f"眨眼 {blink_count} 次 ({bpm_blink:.1f}/min)"

    # rPPG
    rppg: dict = {"risk": 30.0, "note": "insufficient data"}
    if with_rppg and len(green_series) >= 20 and (times[-1] - times[0]) >= 4:
        try:
            g = np.array(green_series, dtype=float)
            g = (g - g.mean()) / (g.std() + 1e-9)
            dt = np.median(np.diff(np.array(times, dtype=float)))
            fs = 1.0 / max(dt, 1e-3)
            freqs = np.fft.rfftfreq(len(g), 1 / fs)
            mag = np.abs(np.fft.rfft(g * np.hanning(len(g))))
            band = (freqs >= 0.75) & (freqs <= 2.5)
            if band.any() and mag.sum() > 0:
                peak = float(mag[band].max() / (mag.sum() + 1e-12) * len(mag))
                bpm = float(freqs[band][np.argmax(mag[band])] * 60)
                snr = peak
                rppg = {"risk": 15.0 if snr > 2.2 else (45.0 if snr > 1.4 else 75.0),
                        "peak_bpm": round(bpm, 1), "snr": round(float(snr), 2),
                        "note": f"心跳峰 {bpm:.0f} BPM" if snr > 1.4 else "無明顯心跳頻率峰值"}
            else:
                rppg = {"risk": 60.0, "note": "頻譜無心跳帶能量"}
        except Exception as e:
            rppg = {"risk": 30.0, "note": f"rppg failed: {e}"[:100]}

    risk = round(0.65 * face_topk + 0.15 * blink_risk
                 + 0.20 * rppg["risk"], 1)
    # 場景級併入: 有臉但臉幀太少 (<8) 時，臉部統計不穩，取 max(臉, 場景)
    # (短影音臉只出現一下、其餘為 AI 場景時特別有用)
    scene_note = ""
    scene_sub = {}
    if scene_diffs:
        s_flick_rs = [_flick_risk_of(v, False) for v in scene_diffs]
        s_edge_rs = [_edge_risk_of(v) for v in (scene_laps or [])]
        scene_topk = _topk_mean(s_flick_rs + s_edge_rs)
        med_d = float(np.median(scene_diffs))
        med_l = float(np.median(scene_laps)) if scene_laps else 100.0
        scene_risk = min(65.0, scene_topk)
        scene_sub = {
            "scene_temporal": {"risk": _topk_mean(s_flick_rs),
                               "median_frame_diff": round(med_d, 4)},
            "scene_texture": {"risk": _topk_mean(s_edge_rs),
                              "median_laplacian_var": round(med_l, 1)},
        }
        if 0 < n < 8:
            if scene_risk > risk:
                scene_note = f"臉幀僅 {n} 幀，併入場景級訊號 (scene={scene_risk})"
                risk = scene_risk
            if med_d > 0.12:
                anomalies.append({"start": 0.0, "end": duration,
                                  "type": "SCENE_FLICKER",
                                  "description": f"場景級整體閃爍偏高 (diff={med_d:.3f})，疑似 AI 生成"})
    if worst_frame is not None:
        heat_b64 = b64_of_bgr(worst_frame)

    level = "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER")
    subs = {
        "blending_boundary": {"risk": edge_risk, "median_laplacian_var": round(med_lap, 1)},
        "temporal_flicker": {"risk": flick_risk, "median_frame_diff": round(med_flick, 4)},
        "blink_pose": {"risk": blink_risk, "detail": blink_note},
        "rppg": rppg,
    }
    subs.update(scene_sub)
    return {
        "risk": risk,
        "level": level,
        "duration": duration,
        "frames_analyzed": n,
        "subscores": subs,
        "anomalies": anomalies,
        "heatmap_b64": heat_b64,
        "note": scene_note,
    }


def quick_scan_frames(frames_bgr: list) -> dict:
    """輕量版 (WS 用): 不跑 MediaPipe, 只用 Laplacian + 亮度做快速掃描."""
    if not frames_bgr:
        return {"risk": 0.0, "alerts": []}
    vals = []
    for f in frames_bgr[:4]:
        try:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            vals.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        except Exception:
            continue
    if not vals:
        return {"risk": 0.0, "alerts": []}
    med = float(np.median(vals))
    if med < 12:
        return {"risk": 70.0, "alerts": ["臉部邊界快速掃描異常 (過度平滑疑似換臉)"],
                "laplacian_var": round(med, 1)}
    if med < 25:
        return {"risk": 45.0, "alerts": ["臉部紋理偏平滑, 建議送交深度鑑識"],
                "laplacian_var": round(med, 1)}
    return {"risk": 8.0, "alerts": [], "laplacian_var": round(med, 1)}
