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

/** 學生登入 */
export const login = (studentId, password) => {
  return api.post('/api/login', { student_id: studentId, password });
};

/** 修改密碼 */
export const changePassword = (studentId, oldPassword, newPassword) => {
  return api.post('/api/change-password', {
    student_id: studentId,
    old_password: oldPassword,
    new_password: newPassword
  });
};

/** 查詢課程總表（含已選標記與剩餘名額） */
export const fetchCourses = (studentId, semester) => {
  return api.get('/api/courses', {
    params: { student_id: studentId, semester }
  });
};

/** 查詢個人課表 */
export const fetchSchedule = (studentId, semester) => {
  return api.get('/api/schedule', {
    params: { student_id: studentId, semester }
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

/** 查詢學生成績 */
export const fetchGrades = (studentId, semester) => {
  return api.get('/api/grades', {
    params: { student_id: studentId, semester }
  });
};

/** 提出請假申請 */
export const createLeave = (payload) => {
  return api.post('/api/leave', payload);
};

/** 查詢個人請假紀錄 */
export const fetchLeaves = (studentId) => {
  return api.get('/api/leave', {
    params: { student_id: studentId }
  });
};

/** 撤銷請假申請（僅限待審核） */
export const cancelLeave = (studentId, leaveId) => {
  return api.post('/api/leave/cancel', { student_id: studentId, leave_id: leaveId });
};