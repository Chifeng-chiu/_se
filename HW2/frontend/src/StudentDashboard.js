/**
 * StudentDashboard.js - 學生選課儀表板
 * 2005 年傳統 HTML Frame 校務系統（全 Table 排版，無 Flexbox/Grid）
 *
 * 版面結構：
 *   Header     3 欄 Table（修改密碼/隱藏選單 | Logo | 黃色使用者資訊 + 登出）
 *   Body Table 左欄 Sidebar（白底 220px 樹狀目錄）＋ 右欄 Main（#eaeaea）
 *     Main ─ 頂部提示列 ─ 【 選 課 清 單 】表格 ─ 【 星 期 課 表 】表格
 */
import React, { useState } from 'react';

// ============================================================
// 真實課表資料（由後端選課結果彙整）
// ============================================================
const myCourses = [
  { id: "0890", name: "資訊科技於金門社區長者之運用", nameEn: "The Application of Information Technology for the Elderly in Kinmen Communities", class: "日大學通識", group: "01", credits: "2.0", hours: "2.0", required: "【必修】", term: "【學期】", time: "(四)5-6", teacher: "黃玉苹,趙于翔", room: "D203護理系普通教室" },
  { id: "0156", name: "作業系統", nameEn: "Operating System", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "【必修】", term: "【學期】", time: "(一)2-4", teacher: "馮玄明", room: "I101圖資電腦教室" },
  { id: "0148", name: "計算機結構", nameEn: "Computer Architecture", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【必修】", term: "【學期】", time: "(四)2-4", teacher: "陳鍾誠", room: "E320多媒體實驗室" },
  { id: "0149", name: "資料庫系統管理", nameEn: "Database System and Management", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【必修】", term: "【學期】", time: "(一)5-7", teacher: "馮玄明", room: "I101圖資電腦教室" },
  { id: "0150", name: "TCP/IP協定", nameEn: "TCP/IP Protocol Suite", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【選修】", term: "【學期】", time: "(三)2-4", teacher: "柯志亨", room: "E321電腦網路實驗室" },
  { id: "0151", name: "電路學", nameEn: "Circuits Studies", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【必修】", term: "【學期】", time: "(二)2-4", teacher: "陳正德", room: "E202教室(理工大樓)" },
  { id: "0152", name: "現代程式語言", nameEn: "Modern Programming Language", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【選修】", term: "【學期】", time: "(二)5-7", teacher: "李錫捷", room: "E320多媒體實驗室" },
  { id: "0153", name: "現代軟體工程", nameEn: "Modern Software Engineering", class: "資工二", group: "01", credits: "3.0", hours: "3.0", required: "【選修】", term: "【學期】", time: "(五)2-4", teacher: "陳鍾誠", room: "E320多媒體實驗室" }
];

// ============================================================
// 固定常數
// ============================================================

// 星期欄位：一(Monday) ～ 日(Sunday)
const DAYS = [
  '一(Monday)', '二(Tuesday)', '三(Wednesday)',
  '四(Thursday)', '五(Friday)', '六(Saturday)', '日(Sunday)'
];

// 第 1～10 節的節次與時間（精確對齊傳統系統）
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

/**
 * 解析上課時間字串「(四)5-6」→ { day: 4, start: 5, end: 6 }
 * 無法解析時回傳 null（該課程僅出現在選課清單，不排入課表）
 */
function parseTime(time) {
  const m = String(time).match(/^\(([一二三四五六日])\)(\d+)-(\d+)$/);
  if (!m) return null;
  return {
    day: DAY_INDEX[m[1]],
    start: Number(m[2]),
    end: Number(m[3]),
  };
}

/**
 * 找出涵蓋指定「星期 + 節次」的所有課程（連堂課會在所有涵蓋節次重複顯示）
 * 不使用 rowSpan，每個 <td> 都是獨立格子
 */
function coursesAt(day, period) {
  return myCourses.filter((course) => {
    const t = parseTime(course.time);
    return t && t.day === day && period >= t.start && period <= t.end;
  });
}

// 側邊欄樹狀目錄資料
const MENU = [
  {
    label: '學生網路選課', open: true,
    children: [
      { label: '線上加退選作業', active: true },
      { label: '停修申請' },
    ],
  },
  {
    label: '選課作業', open: false,
    children: [
      { label: '選課清單查詢' },
      { label: '加退選作業' },
    ],
  },
  {
    label: '查詢', open: false,
    children: [
      { label: '學期成績查詢' },
      { label: '歷年成績查詢' },
      { label: '缺曠假表查詢' },
    ],
  },
  { label: '教學評量', open: false, children: [] },
];

// ============================================================
// 主元件
// ============================================================
export default function StudentDashboard() {
  const [openFolders, setOpenFolders] = useState(['學生網路選課']);

  /** 樹狀目錄展開/收合 */
  const toggleFolder = (label) => {
    setOpenFolders((prev) =>
      prev.includes(label) ? prev.filter((f) => f !== label) : [...prev, label]
    );
  };

  return (
    <div className="app">
      {/* ============ Header：三欄 Table ============ */}
      <div className="header-wrap">
        <table className="header-table">
          <tbody>
            <tr>
              {/* 左：兩個垂直按鈕 */}
              <td className="header-left">
                <button className="retro-btn left-btn" onClick={() => alert('修改密碼功能（尚未實作）')}>修改密碼</button>
                <button className="retro-btn left-btn" onClick={() => alert('隱藏選單功能（尚未實作）')}>隱藏選單</button>
              </td>
              {/* 中：Logo */}
              <td className="header-center">
                <span className="logo">國立金門大學</span>
                <br />
                <span className="logo-en">National Quemoy University</span>
              </td>
              {/* 右：使用者資訊三行黃字 + 登出 */}
              <td className="header-right">
                <div className="user-info">
                  <div className="user-line">116學年度第1學期</div>
                  <div className="user-line">資工二</div>
                  <div className="user-line">
                    邱祺峰
                    <button className="retro-btn black logout-btn" onClick={() => alert('登出功能（尚未實作）')}>登 出</button>
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
                                  className={`tree-leaf${item.active ? ' active' : ''}`}
                                  onClick={() => alert(`已切換至「${item.label}」（Demo）`)}
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

              {/* ---- Main：右側內容區 ---- */}
              <td className="main-col">
                <div className="main-scroll">
                  {/* 頂部提示列 */}
                  <div className="topbar">
                    <button className="retro-btn black" onClick={() => alert('回上一頁功能（尚未實作）')}>回上一頁</button>
                    <span>
                      學生：『
                      <a href="#" className="student-link" onClick={(e) => e.preventDefault()}>邱祺峰</a>
                      』課表資料如下：
                    </span>
                  </div>

                  {/* ============ 區塊 B：選課清單 ============ */}
                  <div className="panel-title">【 選 課 清 單 】</div>
                  <table className="grid-table course-table">
                    <thead>
                      <tr>
                        <th>選課代碼</th>
                        <th>科目名稱</th>
                        <th>科目英文名</th>
                        <th>班級</th>
                        <th>分組</th>
                        <th>學分</th>
                        <th>時數</th>
                        <th>必選修</th>
                        <th>開課別</th>
                        <th>上課時間</th>
                        <th>授課教師</th>
                        <th>上課教室</th>
                        <th>教學綱要</th>
                      </tr>
                    </thead>
                    <tbody>
                      {myCourses.map((course) => (
                        <tr key={course.id}>
                          <td>{course.id}</td>
                          <td className="left">{course.name}</td>
                          <td className="left">{course.nameEn}</td>
                          <td>{course.class}</td>
                          <td>{course.group}</td>
                          <td>{course.credits}</td>
                          <td>{course.hours}</td>
                          <td>{course.required}</td>
                          <td>{course.term}</td>
                          <td>{course.time}</td>
                          <td>{course.teacher}</td>
                          <td>{course.room}</td>
                          <td>
                            <a
                              href="#"
                              className="syllabus-link"
                              onClick={(e) => { e.preventDefault(); alert(`查詢「${course.name}」教學綱要（Demo）`); }}
                            >
                              課程綱要
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {/* ============ 區塊 C：星期課表 ============ */}
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
                            // 每個格子都是獨立 <td>，不做任何 rowSpan 合併
                            // 連堂課在每一節都重複渲染出完整課程資訊
                            const courses = coursesAt(idx + 1, p.no);
                            return (
                              <td
                                key={dayLabel}
                                className="cell"
                                style={{ verticalAlign: 'top', background: '#fff', padding: '3px' }}
                              >
                                {courses.map((course) => (
                                  <div key={course.id} className="tcell" title={`${course.name} / ${course.nameEn}`}>
                                    <div className="cn">{course.name}</div>
                                    {course.nameEn}
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
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}