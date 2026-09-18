/**
 * api.js - 統一的 API 呼叫服務
 * 集中管理 baseURL，方便後續調整後端位址
 */
import axios from 'axios';

// 後端 Flask 開發伺服器位置（CORS 已開啟，可直接連線）
const API_BASE = 'http://localhost:5000';

// 與後端回傳格式 { success, data, message } 對應
const api = axios.create({
  baseURL: API_BASE,
  timeout: 5000,
  headers: { 'Content-Type': 'application/json' }
});

/** 查詢個人課表 */
export const fetchSchedule = (studentId, semester) => {
  return api.get('/api/schedule', {
    params: { student_id: studentId, semester }   // axios 自動組合成 query string
  });
};

/** 加選課程 */
export const enrollCourse = (studentId, courseId, semester) => {
  return api.post('/api/enroll', {
    student_id: studentId,
    course_id: courseId,
    semester
  });
};

/** 退選課程 */
export const dropCourse = (studentId, courseId, semester) => {
  return api.delete('/api/enroll', {
    data: {                                   // axios DELETE 帶 body 需用 data 欄位
      student_id: studentId,
      course_id: courseId,
      semester
    }
  });
};