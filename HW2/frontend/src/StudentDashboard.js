/**
 * StudentDashboard.js - 學生校務系統儀表板（2005 傳統 HTML Frame 風格）
 *
 * 功能：
 *   - 線上加退選作業：查看課程總表、加選/退選（含名額與衝堂檢查）
 *   - 選課清單查詢：已選課程表格
 *   - 學期成績查詢：歷年成績
 *   - 星期課表：依已選課程的「上課時間」自動排版
 *   - 修改密碼 / 登出
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchCourses,
  fetchSchedule,
  fetchGrades,
  enrollCourse,
  dropCourse,
  changePassword,
  fetchLeaves,
  createLeave,
  cancelLeave,
} from './services/api';

// ============================================================
// 固定常數
// ============================================================

// 星期欄位：一(Monday) ～ 日(Sunday)
const DAYS = [
  '一(Monday)', '二(Tuesday)', '三(Wednesday)',
  '四(Thursday)', '五(Friday)', '六(Saturday)', '日(Sunday)'
];

// 第 1～10 節的節次與時間
const PERIODS = [
  { no: 1,  label: '0810-0900' },
  { no: 2,  label: '0910-1000' },
  { no: 3,  label: '1010-1100' },
  { no: 4,  label: '1110-1200' },
  { no: 5,  label: '1330-1420' },
  { no: 6,  label: '1430-1520' },
  { no: 7,  label: '1530-1620' },
  { no: 8,  label: '1630-1720' },
  { no: 9,  label: '1730-1820' },
  { no: 10, label: '1830-1920' },
];

// 星期字元 → 索引 (1 = 一 ... 7 = 日)
const DAY_INDEX = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7 };

/** 解析上課時間字串「(四)5-6」→ { day, start, end }；無法解析時回傳 null */
function parseTime(time) {
  const m = String(time).match(/^\(([一二三四五六日])\)(\d+)-(\d+)$/);
  if (!m) return null;
  return { day: DAY_INDEX[m[1]], start: Number(m[2]), end: Number(m[3]) };
}

/** 找出涵蓋指定「星期 + 節次」的所有課程 */
function coursesAt(courses, day, period) {
  return courses.filter((course) => {
    const t = parseTime(course.time);
    return t && t.day === day && period >= t.start && period <= t.end;
  });
}

// 側邊欄樹狀目錄資料（view: 對應主內容區畫面）
const MENU = [
  {
    label: '學生網路選課', open: true,
    children: [
      { label: '線上加退選作業', view: 'adddrop' },
      { label: '停修申請', demo: true },
    ],
  },
  {
    label: '選課作業', open: false,
    children: [
      { label: '選課清單查詢', view: 'enrolled' },
      { label: '加退選作業', view: 'adddrop' },
    ],
  },
  {
    label: '請假', open: false,
    children: [
      { label: '線上請假申請', view: 'leave_form' },
      { label: '請假紀錄查詢', view: 'leaves' },
    ],
  },
  {
    label: '查詢', open: false,
    children: [
      { label: '學期成績查詢', view: 'grades' },
      { label: '歷年成績查詢', view: 'grades' },
      { label: '缺曠假表查詢', view: 'leaves' },
    ],
  },
  { label: '教學評量', open: false, children: [] },
];

// ============================================================
// 主元件
// ============================================================
export default function StudentDashboard({ student, onLogout }) {
  const [courses, setCourses] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [grades, setGrades] = useState([]);
  const [leaves, setLeaves] = useState([]);
  const [leaveForm, setLeaveForm] = useState({
    leave_type: '事假',
    start_date: '',
    end_date: '',
    periods: '全天',
    reason: '',
  });
  const [view, setView] = useState('adddrop');
  const [viewHistory, setViewHistory] = useState([]);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [openFolders, setOpenFolders] = useState(['學生網路選課']);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [pwdForm, setPwdForm] = useState({ old: '', new: '', confirm: '' });
  const [pwdError, setPwdError] = useState('');

  const semester = student.semester;
  const [sy, sn] = String(semester).split('-');
  const semesterLabel = `${sy}學年度第${sn}學期`;

  // ---- 資料載入 ----
  const refresh = useCallback(async () => {
    try {
      const [c, s, g, l] = await Promise.all([
        fetchCourses(student.student_id, semester),
        fetchSchedule(student.student_id, semester),
        fetchGrades(student.student_id, semester),
        fetchLeaves(student.student_id),
      ]);
      setCourses(c.data.data);
      setSchedule(s.data.data);
      setGrades(g.data.data);
      setLeaves(l.data.data);
    } catch (err) {
      setMsg({ type: 'error', text: '無法載入資料：' + (err.response?.data?.message || err.message) });
    }
  }, [student.student_id, semester]);

  useEffect(() => { refresh(); }, [refresh]);

  /** 切換主內容畫面並記錄上一頁 */
  const go = (nextView) => {
    if (nextView !== view) {
      setViewHistory((prev) => [...prev, view]);
      setView(nextView);
    }
  };

  /** 回上一頁 */
  const goBack = () => {
    setViewHistory((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      setView(last);
      return prev.slice(0, -1);
    });
  };

  /** 樹狀目錄展開/收合 */
  const toggleFolder = (label) => {
    setOpenFolders((prev) =>
      prev.includes(label) ? prev.filter((f) => f !== label) : [...prev, label]
    );
  };

  // ---- 加退選動作 ----
  const handleEnroll = async (course) => {
    setBusy(true);
    try {
      await enrollCourse(student.student_id, course.course_id, semester);
      setMsg({ type: 'ok', text: `加選成功：「${course.course_name}」` });
      await refresh();
    } catch (err) {
      setMsg({ type: 'error', text: err.response?.data?.message || '加選失敗' });
    } finally {
      setBusy(false);
    }
  };

  const handleDrop = async (course) => {
    if (!window.confirm(`確定要退選「${course.course_name}」嗎？`)) return;
    setBusy(true);
    try {
      await dropCourse(student.student_id, course.course_id, semester);
      setMsg({ type: 'ok', text: `退選成功：「${course.course_name}」` });
      await refresh();
    } catch (err) {
      setMsg({ type: 'error', text: err.response?.data?.message || '退選失敗' });
    } finally {
      setBusy(false);
    }
  };

  // ---- 修改密碼 ----
  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwdError('');
    if (!pwdForm.old || !pwdForm.new || !pwdForm.confirm) {
      setPwdError('請完整填寫欄位');
      return;
    }
    if (pwdForm.new !== pwdForm.confirm) {
      setPwdError('兩次輸入的新密碼不一致');
      return;
    }
    try {
      await changePassword(student.student_id, pwdForm.old, pwdForm.new);
      setMsg({ type: 'ok', text: '密碼修改成功' });
      setShowPwd(false);
      setPwdForm({ old: '', new: '', confirm: '' });
    } catch (err) {
      setPwdError(err.response?.data?.message || '修改失敗');
    }
  };

  // ---- 請假 ----
  const handleSubmitLeave = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createLeave({
        student_id: student.student_id,
        leave_type: leaveForm.leave_type,
        start_date: leaveForm.start_date,
        end_date: leaveForm.end_date,
        periods: leaveForm.periods,
        reason: leaveForm.reason,
      });
      setMsg({ type: 'ok', text: '請假申請已送出，等待審核' });
      setLeaveForm({
        leave_type: '事假',
        start_date: '',
        end_date: '',
        periods: '全天',
        reason: '',
      });
      await refresh();
      go('leaves');
    } catch (err) {
      setMsg({ type: 'error', text: err.response?.data?.message || '請假申請送出失敗' });
    } finally {
      setBusy(false);
    }
  };

  const handleCancelLeave = async (leave) => {
    if (!window.confirm('確定要撤銷這筆請假申請嗎？（僅限待審核）')) return;
    setBusy(true);
    try {
      await cancelLeave(student.student_id, leave.leave_id);
      setMsg({ type: 'ok', text: '請假申請已撤銷' });
      await refresh();
    } catch (err) {
      setMsg({ type: 'error', text: err.response?.data?.message || '撤銷失敗' });
    } finally {
      setBusy(false);
    }
  };

  const totalCredits = schedule.reduce((sum, c) => sum + (c.credits || 0), 0);
  const avgScore = grades.length
    ? (grades.reduce((sum, g) => sum + (g.final_score || 0), 0) / grades.length).toFixed(2)
    : '-';

  return (
    <div className="app">
      {/* ============ Header：三欄 Table ============ */}
      <div className="header-wrap">
        <table className="header-table">
          <tbody>
            <tr>
              <td className="header-left">
                <button className="retro-btn left-btn" onClick={() => setShowPwd(true)}>修改密碼</button>
                <button className="retro-btn left-btn" onClick={() => setSidebarHidden((v) => !v)}>隱藏選單</button>
              </td>
              <td className="header-center">
                <span className="logo">國立金門大學</span>
                <br />
                <span className="logo-en">National Quemoy University</span>
              </td>
              <td className="header-right">
                <div className="user-info">
                  <div className="user-line">{semesterLabel}</div>
                  <div className="user-line">{student.class_name}</div>
                  <div className="user-line">
                    {student.name}
                    <button className="retro-btn black logout-btn" onClick={onLogout}>登 出</button>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ============ Body：Table 左右分割 ============ */}
      <div className="app-body">
        <table className="body-table">
          <tbody>
            <tr>
              {/* ---- Sidebar：Windows TreeView 樹狀目錄 ---- */}
              {!sidebarHidden && (
                <td className="sidebar-col">
                  <div className="sidebar-scroll">
                    <ul className="tree">
                      {MENU.map((folder) => (
                        <li key={folder.label}>
                          <span
                            className="tree-toggle"
                            onClick={() => toggleFolder(folder.label)}
                            onKeyDown={(e) => { if (e.key === 'Enter') toggleFolder(folder.label); }}
                            tabIndex="0"
                          >
                            {openFolders.includes(folder.label) ? '-' : '+'}
                          </span>
                          <span className="tree-folder">📁</span>
                          <span style={{ cursor: 'pointer' }} onClick={() => toggleFolder(folder.label)}>
                            {folder.label}
                          </span>
                          {openFolders.includes(folder.label) && folder.children.length > 0 && (
                            <ul>
                              {folder.children.map((item) => (
                                <li key={item.label}>
                                  <span className="tree-red-dot" />
                                  <span
                                    className={`tree-leaf${view === item.view ? ' active' : ''}`}
                                    onClick={() => item.demo
                                      ? alert(`「${item.label}」為展示功能，尚未實作`)
                                      : go(item.view)}
                                  >
                                    {item.label}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                </td>
              )}

              {/* ---- Main：右側內容區 ---- */}
              <td className="main-col">
                <div className="main-scroll">
                  <div className="topbar">
                    <button className="retro-btn black" onClick={goBack}>回上一頁</button>
                    <span>
                      學生：『
                      <a href="#" className="student-link" onClick={(e) => e.preventDefault()}>{student.name}</a>
                      』{semesterLabel} 課表資料如下：
                    </span>
                  </div>

                  {msg && (
                    <div className={`status-bar ${msg.type}`}>
                      {msg.text}
                      <button
                        className="status-close"
                        onClick={() => setMsg(null)}
                        title="關閉"
                      >×</button>
                    </div>
                  )}

                  {view === 'adddrop' && renderAddDrop()}
                  {view === 'enrolled' && renderEnrolled()}
                  {view === 'grades' && renderGrades()}
                  {view === 'leave_form' && renderLeaveForm()}
                  {view === 'leaves' && renderLeaves()}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ============ 修改密碼 Modal ============ */}
      {showPwd && (
        <div className="modal-overlay" onClick={() => setShowPwd(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">修改密碼</div>
            <form onSubmit={handleChangePassword}>
              <table className="modal-table">
                <tbody>
                  <tr>
                    <td className="modal-label">舊密碼</td>
                    <td>
                      <input
                        type="password"
                        value={pwdForm.old}
                        onChange={(e) => setPwdForm({ ...pwdForm, old: e.target.value })}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="modal-label">新密碼</td>
                    <td>
                      <input
                        type="password"
                        value={pwdForm.new}
                        onChange={(e) => setPwdForm({ ...pwdForm, new: e.target.value })}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="modal-label">確認新密碼</td>
                    <td>
                      <input
                        type="password"
                        value={pwdForm.confirm}
                        onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })}
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
              {pwdError && <div className="login-error">{pwdError}</div>}
              <div className="modal-buttons">
                <input type="submit" value="確定" className="retro-btn black" />
                <button type="button" className="retro-btn black" onClick={() => setShowPwd(false)}>取消</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );

  // ============================================================
  // 畫面：線上加退選作業
  // ============================================================
  function renderAddDrop() {
    return (
      <>
        <div className="panel-title">【 線 上 加 退 選 作 業 】</div>

        <div className="panel-sub">已選課程（{schedule.length} 門，共 {totalCredits} 學分）</div>
        <table className="grid-table course-table">
          <thead>
            <tr>
              <th>選課代碼</th>
              <th>科目名稱</th>
              <th>學分</th>
              <th>必選修</th>
              <th>上課時間</th>
              <th>授課教師</th>
              <th>上課教室</th>
              <th>退選</th>
            </tr>
          </thead>
          <tbody>
            {schedule.length === 0 && (
              <tr><td colSpan="8">目前尚未選修任何課程</td></tr>
            )}
            {schedule.map((course) => (
              <tr key={course.course_id}>
                <td>{course.course_id}</td>
                <td className="left">{course.course_name}</td>
                <td>{course.credits}.0</td>
                <td>{course.course_type === '必修' ? '【必修】' : '【選修】'}</td>
                <td>{course.time}</td>
                <td>{course.teacher}</td>
                <td>{course.room}</td>
                <td>
                  <button
                    className="action-btn drop"
                    disabled={busy}
                    onClick={() => handleDrop(course)}
                  >退選</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="panel-sub">課程總表（尚未加選課程）</div>
        <table className="grid-table course-table">
          <thead>
            <tr>
              <th>選課代碼</th>
              <th>科目名稱</th>
              <th>班級</th>
              <th>學分</th>
              <th>必選修</th>
              <th>上課時間</th>
              <th>授課教師</th>
              <th>上課教室</th>
              <th>名額</th>
              <th>加選</th>
            </tr>
          </thead>
          <tbody>
            {courses.length === 0 && (
              <tr><td colSpan="10">課程資料載入中...</td></tr>
            )}
            {courses.map((course) => (
              <tr key={course.course_id}>
                <td>{course.course_id}</td>
                <td className="left">{course.course_name}</td>
                <td>{course.class_group}</td>
                <td>{course.credits}.0</td>
                <td>{course.course_type === '必修' ? '【必修】' : '【選修】'}</td>
                <td>{course.time}</td>
                <td>{course.teacher}</td>
                <td>{course.room}</td>
                <td>
                  <span style={{ color: course.remaining <= 0 ? 'red' : '#000' }}>
                    {course.current_enrolled}/{course.max_capacity}
                    {course.remaining > 0 && `（剩 ${course.remaining}）`}
                  </span>
                </td>
                <td>
                  {course.enrolled ? (
                    <span className="enrolled-tag">已選</span>
                  ) : (
                    <button
                      className="action-btn add"
                      disabled={busy || course.remaining <= 0}
                      onClick={() => handleEnroll(course)}
                    >加選</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  // ============================================================
  // 畫面：選課清單查詢
  // ============================================================
  function renderEnrolled() {
    return (
      <>
        <div className="panel-title">【 選 課 清 單 】</div>
        <table className="grid-table course-table">
          <thead>
            <tr>
              <th>選課代碼</th>
              <th>科目名稱</th>
              <th>科目英文名</th>
              <th>班級</th>
              <th>學分</th>
              <th>必選修</th>
              <th>上課時間</th>
              <th>授課教師</th>
              <th>上課教室</th>
            </tr>
          </thead>
          <tbody>
            {schedule.length === 0 && (
              <tr><td colSpan="9">目前尚未選修任何課程</td></tr>
            )}
            {schedule.map((course) => (
              <tr key={course.course_id}>
                <td>{course.course_id}</td>
                <td className="left">{course.course_name}</td>
                <td className="left">{course.name_en || '-'}</td>
                <td>{course.class_group}</td>
                <td>{course.credits}.0</td>
                <td>{course.course_type === '必修' ? '【必修】' : '【選修】'}</td>
                <td>{course.time}</td>
                <td>{course.teacher}</td>
                <td>{course.room}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* ============ 星期課表 ============ */}
        <div className="panel-title">【 星 期 課 表 】</div>
        <table className="grid-table timetable">
          <thead>
            <tr>
              <th>節次</th>
              {DAYS.map((d) => <th key={d}>{d}</th>)}
            </tr>
          </thead>
          <tbody>
            {PERIODS.map((p) => (
              <tr key={p.no}>
                <td className="time-col">
                  第 {p.no} 節<br />
                  {p.label}
                </td>
                {DAYS.map((dayLabel, idx) => {
                  const list = coursesAt(schedule, idx + 1, p.no);
                  return (
                    <td
                      key={dayLabel}
                      className="cell"
                      style={{ verticalAlign: 'top', background: '#fff', padding: '3px' }}
                    >
                      {list.map((course) => (
                        <div key={course.course_id} className="tcell" title={`${course.course_name} / ${course.name_en || ''}`}>
                          <div className="cn">{course.course_name}</div>
                          {course.name_en}
                          <br />
                          {course.teacher}
                          <br />
                          {course.room}
                        </div>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  // ============================================================
  // 畫面：學期成績查詢
  // ============================================================
  function renderGrades() {
    return (
      <>
        <div className="panel-title">【 學 期 成 績 查 詢 】</div>
        <table className="grid-table course-table">
          <thead>
            <tr>
              <th>學期</th>
              <th>課程代號</th>
              <th>科目名稱</th>
              <th>成績</th>
              <th>等第</th>
            </tr>
          </thead>
          <tbody>
            {grades.length === 0 && (
              <tr><td colSpan="5">目前尚無成績資料</td></tr>
            )}
            {grades.map((g, i) => (
              <tr key={i}>
                <td>{g.semester}</td>
                <td>{g.course_id}</td>
                <td className="left">{g.course_name}</td>
                <td>{g.final_score ?? '-'}</td>
                <td>{gradeLetter(g.final_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {grades.length > 0 && (
          <div className="grade-summary">平均成績：{avgScore}　（共 {grades.length} 科）</div>
        )}
      </>
    );
  }

  // ============================================================
  // 畫面：線上請假申請
  // ============================================================
  function renderLeaveForm() {
    return (
      <>
        <div className="panel-title">【 線 上 請 假 申 請 】</div>
        <form onSubmit={handleSubmitLeave}>
          <table className="grid-table leave-form-table">
            <tbody>
              <tr>
                <td className="form-label">學號</td>
                <td className="left">{student.student_id}（{student.name}）</td>
              </tr>
              <tr>
                <td className="form-label">請假類別</td>
                <td className="left">
                  <select
                    value={leaveForm.leave_type}
                    onChange={(e) => setLeaveForm({ ...leaveForm, leave_type: e.target.value })}
                  >
                    <option>事假</option>
                    <option>病假</option>
                    <option>公假</option>
                    <option>喪假</option>
                    <option>其他</option>
                  </select>
                </td>
              </tr>
              <tr>
                <td className="form-label">開始日期</td>
                <td className="left">
                  <input
                    type="date"
                    value={leaveForm.start_date}
                    onChange={(e) => setLeaveForm({ ...leaveForm, start_date: e.target.value })}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-label">結束日期</td>
                <td className="left">
                  <input
                    type="date"
                    value={leaveForm.end_date}
                    onChange={(e) => setLeaveForm({ ...leaveForm, end_date: e.target.value })}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-label">請假節次</td>
                <td className="left">
                  <input
                    type="text"
                    value={leaveForm.periods}
                    placeholder="例如：1-4 或 全天"
                    onChange={(e) => setLeaveForm({ ...leaveForm, periods: e.target.value })}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-label">請假事由</td>
                <td className="left">
                  <textarea
                    rows="3"
                    value={leaveForm.reason}
                    placeholder="請填寫請假事由"
                    onChange={(e) => setLeaveForm({ ...leaveForm, reason: e.target.value })}
                    required
                  />
                </td>
              </tr>
            </tbody>
          </table>
          <div className="form-actions">
            <input type="submit" value="送出申請" className="retro-btn black" disabled={busy} />
            <button
              type="button"
              className="retro-btn black"
              onClick={() => setLeaveForm({ leave_type: '事假', start_date: '', end_date: '', periods: '全天', reason: '' })}
            >清除</button>
          </div>
        </form>
      </>
    );
  }

  // ============================================================
  // 畫面：請假紀錄查詢（缺曠假表）
  // ============================================================
  function renderLeaves() {
    return (
      <>
        <div className="panel-title">【 請 假 紀 錄 查 詢 】</div>
        <table className="grid-table course-table">
          <thead>
            <tr>
              <th>編號</th>
              <th>類別</th>
              <th>開始日期</th>
              <th>結束日期</th>
              <th>天數</th>
              <th>節次</th>
              <th>事由</th>
              <th>狀態</th>
              <th>申請時間</th>
              <th>動作</th>
            </tr>
          </thead>
          <tbody>
            {leaves.length === 0 && (
              <tr><td colSpan="10">目前尚無請假紀錄</td></tr>
            )}
            {leaves.map((leave) => (
              <tr key={leave.leave_id}>
                <td>{leave.leave_id}</td>
                <td>{leave.leave_type}</td>
                <td>{leave.start_date}</td>
                <td>{leave.end_date}</td>
                <td>{leave.days}</td>
                <td>{leave.periods || '-'}</td>
                <td className="left">{leave.reason}</td>
                <td><span className={`leave-status ${leave.status}`}>{leave.status}</span></td>
                <td>{leave.created_at}</td>
                <td>
                  {leave.status === '待審核' && (
                    <button
                      className="action-btn drop"
                      disabled={busy}
                      onClick={() => handleCancelLeave(leave)}
                    >撤銷</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {leaves.length > 0 && (
          <div className="grade-summary">
            累計請假 {leaves.length} 次，共 {leaves.reduce((sum, l) => sum + (l.days || 0), 0)} 天
          </div>
        )}
      </>
    );
  }
}

/** 分數 → 等第 */
function gradeLetter(score) {
  if (score == null) return '-';
  if (score >= 90) return 'A+';
  if (score >= 85) return 'A';
  if (score >= 80) return 'A-';
  if (score >= 77) return 'B+';
  if (score >= 73) return 'B';
  if (score >= 70) return 'B-';
  if (score >= 67) return 'C+';
  if (score >= 63) return 'C';
  if (score >= 60) return 'C-';
  return 'F';
}