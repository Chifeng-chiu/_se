"""模組 3: 影音同步分析器 (av_sync_analyzer.py, 僅模式 A)

唇音物理對應: 追蹤 MAR (嘴唇縱橫比) 與音訊包絡/Onset 的互相關,
抓出 >100ms 延遲, 以及「有聲無嘴動 / 有嘴動無聲」的可疑段.
"""
from __future__ import annotations

import numpy as np

MOUTH_UP, MOUTH_LO, MOUTH_L, MOUTH_R = 13, 14, 61, 291


def _mar_of(pts: np.ndarray) -> float:
    v = float(np.linalg.norm(pts[MOUTH_UP] - pts[MOUTH_LO]))
    h = float(np.linalg.norm(pts[MOUTH_L] - pts[MOUTH_R]) + 1e-9)
    return v / h


def analyze_av_sync(video_path: str, audio_path: str | None = None) -> dict:
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"risk": 0.0, "error": "cannot open video", "mismatches": []}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    mesh = None
    try:
        import mediapipe as mp  # type: ignore
        mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1, min_detection_confidence=0.4)
    except Exception:
        mesh = None

    # 無 MediaPipe 時的粗估退路: Haar 人臉框 + 下半部嘴帶動能 (無關鍵點)
    haar, haar_ok = None, False
    if mesh is None:
        import cv2 as _cv
        import os as _os
        cands = [_os.path.join(_os.path.dirname(__file__), "..", "models",
                               "haarcascade_frontalface_default.xml")]
        try:
            cands.append(_cv.data.haarcascades + "haarcascade_frontalface_default.xml")
        except Exception:
            pass
        for cand in cands:
            try:
                h = _cv.CascadeClassifier(cand)
                if not h.empty():
                    haar, haar_ok = h, True
                    break
            except Exception:
                continue

    mar_series: list[float] = []
    t_series: list[float] = []
    global_series: list[float] = []  # 上半臉全域動能 (鏡頭/頭部晃動量)
    mode = "landmark"  # or "coarse"
    prev_mouth = None
    prev_upper = None
    last_box = None  # 粗估臉框閂鎖：偵測到就更新位置，沒偵測到沿用上次
    idx = n = 0
    step = 3  # 密集一點：短影音臉出現時間短，稀疏取樣會完全錯過
    while n < 120:
        ok = cap.grab()
        if not ok:
            break
        if idx % step != 0:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        idx += 1
        if not ok:
            break
        t = idx / fps
        if mesh is not None:
            try:
                small = cv2.resize(frame, (320, int(frame.shape[0] * 320 / frame.shape[1])))
                res = mesh.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                if not res.multi_face_landmarks:
                    continue
                lm = res.multi_face_landmarks[0].landmark
                H, W = small.shape[:2]
                pts = np.array([(p.x * W, p.y * H) for p in lm])
                mar_series.append(_mar_of(pts))
                t_series.append(t)
            except Exception:
                continue
        elif haar_ok:
            # 粗估: 嘴部專屬 ROI + 上半臉晃動抵銷
            # 嘴定位於臉框下半中央 (y+0.65h~y+0.92h, x+0.25w~x+0.75w)；
            # 上半臉 (額/眼區) 只做整體平移，兩者相減抵銷鏡頭晃動。
            # 真人自拍晃動 → 兩區同動 → 抵銷後趨零 (不誤報)；
            # HeyGen 類 (頭不動、嘴合成亂動) → 殘留動能參與比對。
            try:
                small = cv2.resize(frame, (480, int(frame.shape[0] * 480 / frame.shape[1])))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                try:
                    faces = haar.detectMultiScale(gray, 1.2, 4, minSize=(60, 60))
                    if len(faces):
                        last_box = tuple(int(v) for v in faces[0])
                except Exception:
                    pass
                if last_box is None:
                    continue
                x, y, w, h = last_box
                H, W = gray.shape
                mx0, mx1 = max(x + int(w * 0.25), 0), min(x + int(w * 0.75), W)
                my0, my1 = max(y + int(h * 0.65), 0), min(y + int(h * 0.92), H)
                ux0, ux1 = max(x + int(w * 0.20), 0), min(x + int(w * 0.80), W)
                uy0, uy1 = max(y + int(h * 0.10), 0), min(y + int(h * 0.40), H)
                if mx1 <= mx0 or my1 <= my0 or ux1 <= ux0 or uy1 <= uy0:
                    continue
                mouth = cv2.resize(gray[my0:my1, mx0:mx1], (64, 32)).astype(np.float32) / 255.0
                upper = cv2.resize(gray[uy0:uy1, ux0:ux1], (64, 32)).astype(np.float32) / 255.0
                if prev_mouth is not None and prev_upper is not None \
                        and prev_mouth.shape == mouth.shape:
                    md = float(np.mean(np.abs(mouth - prev_mouth)))
                    ud = float(np.mean(np.abs(upper - prev_upper)))
                    comp = max(0.0, md - ud * 0.9)
                    mar_series.append(comp)
                    t_series.append(t)
                    global_series.append(ud)
                    mode = "coarse"
                prev_mouth, prev_upper = mouth, upper
            except Exception:
                continue
        else:
            break  # 兩種偵測器都沒有，直接結束
    cap.release()
    try:
        if mesh is not None:
            mesh.close()
    except Exception:
        pass

    # 短影音臉出現時間短：粗估模式樣本門檻放寬到 8 (landmark 維持 15)
    min_samples = 8 if mode == "coarse" else 15
    if len(mar_series) < min_samples or not audio_path:
        return {"risk": 0.0, "level": "SAFE", "lag_ms": 0.0, "sync_score": 100.0,
                "mismatches": [],
                "note": "嘴型軌跡不足或無音軌, 同步維度略過" if not audio_path
                else f"偵測幀過少 ({len(mar_series)}<{min_samples}), 同步維度略過"}

    # 晃動閘門 (僅粗估)：上半臉全域動能大 + 抵銷後嘴部幾無殘留 →
    # 代表鏡頭/頭部在晃、嘴部穩定，此時「靜音嘴」是晃動假象，不判分
    global_high = bool(mode == "coarse" and global_series
                       and float(np.mean(global_series)) > 0.025)
    comp_energy = float(np.mean(mar_series)) if mar_series else 0.0
    if mode == "coarse" and global_high and comp_energy < 0.005:
        return {"risk": 15.0, "level": "SAFE", "lag_ms": 0.0, "sync_score": 0.0,
                "mismatches": [],
                "note": "粗估：鏡頭/頭部晃動大且嘴部殘留動能極小，同步維度保守評分 (15)"}

    # 音訊包絡 (onset strength), 重採樣到 MAR 時間軸做互相關
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
        o_times = librosa.times_like(oenv, sr=sr, hop_length=512)
        mar = np.array(mar_series)
        mar_n = (mar - mar.mean()) / (mar.std() + 1e-9)
        # 嘴開速度 (dMAR/dt 正值 = 張嘴)
        dmar = np.maximum(0, np.diff(mar_n, prepend=mar_n[0]))
        audio_e = np.interp(np.array(t_series), o_times,
                            (oenv - oenv.mean()) / (oenv.std() + 1e-9))
        # lag 搜尋 ±0.5s
        dt_med = float(np.median(np.diff(np.array(t_series)))) or 0.2
        max_lag = max(1, int(0.5 / dt_med))
        best_lag, best_corr = 0, -1e9
        for lag in range(-max_lag, max_lag + 1):
            a = np.roll(audio_e, lag)
            c = float(np.corrcoef(dmar, a)[0, 1]) if np.std(a) > 1e-9 else 0.0
            if c > best_corr:
                best_corr, best_lag = c, lag
        lag_ms = round(abs(best_lag * dt_med) * 1000, 1)
        sync_score = round(float(max(0.0, min(1.0, (best_corr + 0.2) / 0.9)) * 100), 1)
        risk = round(100 - sync_score, 1)
        if abs(best_lag * dt_med) > 0.1:
            risk = max(risk, 65.0)
        mismatches = []
        if abs(best_lag * dt_med) > 0.1:
            mismatches.append({"start": 0.0, "end": round(t_series[-1], 2),
                               "type": "LIP_SYNC_MISMATCH",
                               "description": f"影音延遲約 {lag_ms:.0f}ms (超過 100ms 容忍)"})
        # 有聲無嘴動: 音訊高能量但嘴部訊號變異極小
        # (landmark 看 MAR 絕對變異; coarse 看正規化後動能變異；
        #  晃動大時不判，避免把晃動假象當配音)
        if mode == "coarse":
            flat = (not global_high
                    and float(np.std(mar_n)) < 0.35
                    and float(np.mean(np.abs(audio_e))) > 0.4)
        else:
            flat = float(np.std(mar)) < 0.015 and float(np.mean(np.abs(audio_e))) > 0.4
        if flat:
            risk = max(risk, 70.0)
            mismatches.append({"start": 0.0, "end": round(t_series[-1], 2),
                               "type": "LIP_SYNC_MISMATCH",
                               "description": "雙唇音期間嘴型幾無變化 (疑似配音/Lip-Sync)"})
        out = {"risk": risk,
               "level": "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER"),
               "lag_ms": lag_ms, "correlation": round(float(best_corr), 3),
               "sync_score": sync_score, "mismatches": mismatches}
        if mode == "coarse":
            out["note"] = "粗估 (嘴部ROI＋上半臉晃動抵銷，無臉部關鍵點)"
        return out
    except Exception as e:
        return {"risk": 0.0, "level": "SAFE", "mismatches": [],
                "note": f"sync compute failed: {e}"[:150]}
