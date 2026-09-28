# -*- coding: utf-8 -*-
"""
system.py - 校務系統 (單檔 Flask: 前端 + 後端)
================================================
前端：登入 -> 學生(課表/請假) 或 管理員(審核) (2005 傳統 HTML Table 排版)
後端：Flask + SQLite
  - GET  /                         首頁 (登入畫面)
  - GET  /index.html               同上
  - GET  /enroll.html              線上加退選作業頁
  - POST /api/login                登入 (回傳 role: student/admin)
  - POST /api/leave                學生送出請假單
  - GET  /api/admin/leaves         管理員撈出審核中假單
  - PUT  /api/admin/leaves/<id>    批准或退回

預設帳號：student / 123456 , admin / 123456
啟動：python system.py  ->  開啟 http://localhost:5000
"""
import os
import sqlite3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'system.db')

INDEX_PAGE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>國立金門大學 - 校務系統</title>
<style>
/* ============================================================
   styles.css - 2005 年傳統 HTML Frame 校務系統介面
   ---------- 嚴格規範 ----------
   * 字體：新細明體 PMingLiU
   * 基礎字體：12px
   * 全域移除 padding/margin，絕對無 border-radius、無陰影
   * Header 與左右分割皆使用 Table 排版（非 Flexbox）
   ============================================================ */

/* ---------- 全域重置 ---------- */
* {
  margin: 0;
  padding: 0;
  border-radius: 0 !important;
  box-shadow: none !important;
}

html, body {
  height: 100%;
}

body {
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  font-size: 12px;
  color: #000;
  background: #fff;
}

/* 版面骨架：上方 Header + 下方 Body Table，滿版不捲動 */
.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ============================================================
   Header 上方橫幅：深藍 #3b5598，約 70px，三欄 Table
   ============================================================ */
.header-wrap {
  background: #3b5598;
  flex-shrink: 0;
}

.header-table {
  width: 100%;
  height: 70px;
  border-collapse: collapse;
  table-layout: fixed;
  border: 0;
}

.header-left,
.header-center,
.header-right {
  vertical-align: middle;
}

.header-left {
  width: 160px;
  padding: 2px 6px;
  text-align: left;
}

/* 左側傳統立體按鈕（垂直排列） */
.retro-btn {
  background: #c0c0c0;
  border: 2px outset;
  border-color: #ffffff #808080 #808080 #ffffff;
  padding: 2px 10px;
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  font-size: 12px;
  color: #fff;                      /* 左側按鈕文字白色 */
  cursor: pointer;
  white-space: nowrap;
}
.retro-btn.black { color: #000; }   /* 登出 / 回上一頁 黑色字 */
.retro-btn:active { border-style: inset; }
.retro-btn:hover { background: #d0d0d0; }

.left-btn {
  display: block;                   /* 兩個按鈕垂直排列 */
  width: 70px;
  text-align: center;
  margin: 3px 0;
}

.header-center {
  text-align: center;
  color: #fff;
}
.header-center .logo {
  font-size: 22px;
  letter-spacing: 3px;
  font-weight: bold;
}
.header-center .logo-en {
  font-size: 12px;
  letter-spacing: 2px;
}

.header-right {
  width: 230px;
  padding: 2px 6px;
  text-align: left;
}

/* 右側三行黃色粗體文字 */
.user-info {
  color: #ffff00;
  font-weight: bold;
}
.user-line {
  line-height: 1.3;
  padding: 1px 0;
}
.logout-btn {
  vertical-align: middle;
  margin-left: 8px;
}

/* ============================================================
   下半部 Body：Table 左右分割（Sidebar 220px + Main 剩餘）
   ============================================================ */
.app-body {
  flex: 1;
  overflow: hidden;
}

.body-table {
  width: 100%;
  height: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  border: 0;
}
.body-table tbody,
.body-table tr {
  height: 100%;
}

/* ---------- Sidebar 左側：淺灰 #e8e8e8 220px ---------- */
.sidebar-col {
  width: 220px;
  background: #e8e8e8;
  border-right: 1px solid #999;
  vertical-align: top;
  height: 100%;
  font-family: "新細明體", PMingLiU, serif;
  font-size: 12px;
}
.sidebar-scroll {
  height: 100%;
  overflow-y: auto;
}

/* ----- 傳統 Windows TreeView 樹狀目錄 ----- */
ul.tree {
  list-style-type: none;
  padding-left: 0;
  margin: 0;
}
ul.tree ul {
  list-style-type: none;
  padding-left: 16px;
  margin: 0;
  position: relative;
}
ul.tree ul::before {
  content: "";
  position: absolute;
  top: 0;
  left: 6px;
  bottom: 0;
  border-left: 1px dotted #888;
}
ul.tree li {
  margin: 0;
  padding: 2px 0 2px 15px;
  position: relative;
  line-height: 1.5;
}
ul.tree li::before {
  content: "";
  position: absolute;
  top: 10px;
  left: -10px;
  width: 20px;
  border-top: 1px dotted #888;
}
/* 最後一個子節點的虛線要切斷 */
ul.tree li:last-child::before {
  background: #e8e8e8;
  height: auto;
  top: 10px;
  bottom: 0;
  border-left: 1px dotted #888;
}

/* 經典加減號方塊 */
.tree-toggle {
  display: inline-block;
  width: 9px;
  height: 9px;
  line-height: 7px;
  text-align: center;
  border: 1px solid #888;
  background: #fff;
  font-size: 9px;
  cursor: pointer;
  margin-right: 4px;
  position: relative;
  z-index: 1;
  user-select: none;
}

/* 立體紅點 */
.tree-red-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: radial-gradient(circle at 3px 3px, #ff9999, #cc0000);
  margin-right: 4px;
  vertical-align: middle;
}

/* 資料夾圖示微調 */
.tree-folder {
  margin-right: 4px;
  font-size: 14px;
  vertical-align: middle;
}

/* 葉節點 */
.tree-leaf {
  cursor: pointer;
}
.tree-leaf a {
  text-decoration: none;
  color: #000;
}
.tree-leaf:hover {
  background: #dde4f0;
}
.tree-leaf.active {
  background: #cfe0ff;
}

/* ---------- Main 右側：極淺灰 #eaeaea ---------- */
.main-col {
  background: #eaeaea;
  vertical-align: top;
  height: 100%;
}
.main-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 4px 6px;
}

/* 頂部提示列：淺灰底 + 底部 1px 灰線 */
.topbar {
  background: #e0e0e0;
  border-bottom: 1px solid #999;
  padding: 3px 4px;
  margin-bottom: 6px;
}
.topbar .student-link {
  color: blue;
  text-decoration: underline;
}

/* 章節標題：置中純文字 */
.panel-title {
  text-align: center;
  font-weight: bold;
  margin: 8px 0 4px 0;
}

/* ============================================================
   通用表格：collapse、1px 灰框、表頭 #e0e0e0
   ============================================================ */
.grid-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid #999;
  background: #fff;
  margin-bottom: 8px;
}
.grid-table th,
.grid-table td {
  border: 1px solid #999;
  padding: 3px;
  font-size: 12px;
  text-align: center;
  vertical-align: middle;
}
.grid-table th {
  background: #e0e0e0;
  font-weight: normal;
}

/* ---------- 選課清單 ---------- */
.course-table td.left { text-align: left; }
.syllabus-link {
  color: red;                       /* 教學綱要：紅字 */
  text-decoration: underline;
  cursor: pointer;
}

/* ---------- 星期課表 ---------- */
.timetable td { vertical-align: top; }

.timetable td.time-col {
  background: #fdf7e3;              /* 淺米黃色時間欄 */
  text-align: center;
  white-space: nowrap;
  vertical-align: middle;
}

.timetable td.cell {
  text-align: left;
  vertical-align: top;
}

/* 單堂課：四行資訊 */
.tcell {
  border: 1px solid #ccc;
  background: #fff;
  padding: 1px 3px;
  margin: 1px 0;
}
.tcell .cn { font-weight: bold; }

/* ============================================================
   登入 / 學生請假 / 管理員批准 頁面
   ============================================================ */

/* ---------- 登入頁 ---------- */
.login-wrap {
  text-align: center;
  padding-top: 60px;
  background: #eaeaea;
  height: 100%;
}

.login-box {
  display: inline-block;
  border: 1px solid #999;
  background: #fff;
  padding: 12px;
}

.login-title {
  font-size: 16px;
  font-weight: bold;
  letter-spacing: 2px;
  margin-bottom: 6px;
}

.login-box table {
  border-collapse: collapse;
  text-align: left;
  margin: 0 auto;
}

.login-box td {
  padding: 4px 6px;
  font-size: 12px;
}

/* 傳統輸入框 */
.retro-input {
  border: 1px solid #808080;
  background: #fff;
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  font-size: 12px;
  padding: 2px;
}

/* ---------- 訊息列 ---------- */
.msg-bar {
  text-align: center;
  margin: 6px 0;
  min-height: 14px;
}
.msg-ok   { color: #006600; }
.msg-err  { color: #cc0000; }

/* ---------- 表單表格 ---------- */
.form-table {
  margin: 0 auto 8px auto;
  border-collapse: collapse;
}
.form-table td {
  padding: 3px 6px;
  font-size: 12px;
  text-align: left;
  vertical-align: middle;
}

/* ---------- 管理表格內的小按鈕 ---------- */
.mini-btn {
  background: #c0c0c0;
  border: 2px outset;
  border-color: #ffffff #808080 #808080 #ffffff;
  padding: 1px 8px;
  font-size: 12px;
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  cursor: pointer;
  white-space: nowrap;
}
.mini-btn:active { border-style: inset; }
.mini-btn.approve { color: #006600; }
.mini-btn.reject  { color: #cc0000; }

/* ---------- 狀態顏色 ---------- */
.status-pending  { color: #cc6600; }
.status-approved { color: #006600; }
.status-rejected { color: #cc0000; }

</style>
</head>
<body>
<div class="app">
  <!-- ============ Header：LOGO + 登入後的使用者資訊 ============ -->
  <div class="header-wrap">
    <table class="header-table">
      <tbody>
        <tr>
          <td class="header-left">
            <button class="retro-btn left-btn" onclick="logout()">登 出</button>
          </td>
          <td class="header-center">
            <span class="logo">國立金門大學</span><br>
            <span class="logo-en">National Quemoy University</span>
          </td>
          <td class="header-right">
            <div class="user-info">
              <div class="user-line" id="userLine1">尚未登入</div>
              <div class="user-line" id="userLine2">&nbsp;</div>
              <div class="user-line" id="userLine3">&nbsp;</div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- ============ 主要內容（畫面切換） ============ -->
  <div class="main-scroll">

    <!-- ---------- 畫面 1：登入 ---------- -->
    <div id="viewLogin" class="login-wrap">
      <div class="login-box">
        <div class="login-title">校 務 系 統 登 入</div>
        <table>
          <tr>
            <td>帳號</td>
            <td><input class="retro-input" id="loginUser" type="text"></td>
          </tr>
          <tr>
            <td>密碼</td>
            <td><input class="retro-input" id="loginPass" type="password"></td>
          </tr>
        </table>
        <div class="btn-bar">
          <button class="retro-btn" onclick="doLogin()">登 入</button>
          <button class="retro-btn" onclick="clearLogin()">清 除</button>
        </div>
        <div class="msg-bar"><span id="loginMsg"></span></div>
      </div>
    </div>

    <!-- ---------- 畫面 2：學生（課表 + 請假） ---------- -->
    <div id="viewStudent" style="display:none">
      <!-- 功能切換列 -->
      <div class="btn-bar">
        <button class="retro-btn" onclick="showStudentTab('schedule')">課 表</button>
        <button class="retro-btn" onclick="showStudentTab('leave')">學生請假</button>
      </div>

      <!-- ===== 子畫面 2a：課表（原本的選課清單 + 星期課表） ===== -->
      <div id="studentSchedule">
        <table class="body-table" style="height:auto;border:0">
          <tbody>
            <tr>
              <!-- 左側 Sidebar：Windows TreeView 樹狀目錄 -->
              <td class="sidebar-col" style="height:auto;width:220px">
                <div class="sidebar-scroll">
                  <ul class="tree" id="tree"></ul>
                </div>
              </td>
              <!-- 右側 Main：選課清單 + 星期課表 -->
              <td class="main-col" style="height:auto">
                <div class="main-scroll" style="height:auto;background:#eaeaea">
                  <div class="topbar">
                    <span>學生：『<a href="#" class="student-link" onclick="event.preventDefault()">邱祺峰</a>』課表資料如下：</span>
                  </div>

                  <div class="panel-title">【 選 課 清 單 】</div>
                  <table class="grid-table course-table">
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
                    <tbody id="courseBody"></tbody>
                  </table>

                  <div class="panel-title">【 星 期 課 表 】</div>
                  <table class="grid-table timetable">
                    <thead>
                      <tr>
                        <th>節次</th>
                        <th>一(Monday)</th>
                        <th>二(Tuesday)</th>
                        <th>三(Wednesday)</th>
                        <th>四(Thursday)</th>
                        <th>五(Friday)</th>
                        <th>六(Saturday)</th>
                        <th>日(Sunday)</th>
                      </tr>
                    </thead>
                    <tbody id="timeBody"></tbody>
                  </table>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ===== 子畫面 2b：學生請假 ===== -->
      <div id="studentLeave" style="display:none">
        <div class="panel-title">【 學 生 請 假 申 請 】</div>
        <table class="form-table">
          <tr>
            <td>學號</td>
            <td><input class="retro-input" id="leaveSid" type="text" value="A123456789"></td>
          </tr>
          <tr>
            <td>假別</td>
            <td>
              <select class="retro-input" id="leaveType">
                <option>病假</option>
                <option>事假</option>
                <option>公假</option>
                <option>喪假</option>
                <option>其他</option>
              </select>
            </td>
          </tr>
          <tr>
            <td>日期</td>
            <td><input class="retro-input" id="leaveDate" type="text" placeholder="YYYY-MM-DD"></td>
          </tr>
          <tr>
            <td>事由</td>
            <td><textarea class="retro-input" id="leaveReason" rows="2" cols="40"></textarea></td>
          </tr>
        </table>
        <div class="btn-bar">
          <button class="retro-btn" onclick="submitLeave()">送出請假單</button>
          <button class="retro-btn" onclick="clearLeaveForm()">清 除</button>
        </div>
        <div class="msg-bar"><span id="leaveMsg"></span></div>

        <div class="panel-title">【 本 次 送 出 紀 錄 】</div>
        <table class="grid-table course-table">
          <thead>
            <tr>
              <th>假單號</th>
              <th>假別</th>
              <th>日期</th>
              <th>事由</th>
              <th>狀態</th>
            </tr>
          </thead>
          <tbody id="myLeaveBody"></tbody>
        </table>
      </div>
    </div>

    <!-- ---------- 畫面 3：管理員批准 ---------- -->
    <div id="viewAdmin" style="display:none">
      <div class="panel-title">【 管 理 員 批 准 】</div>
      <div class="btn-bar">
        <button class="retro-btn" onclick="loadAdminLeaves()">重新整理</button>
      </div>
      <table class="grid-table course-table">
        <thead>
          <tr>
            <th>假單號</th>
            <th>學號</th>
            <th>姓名</th>
            <th>假別</th>
            <th>日期</th>
            <th>事由</th>
            <th>狀態</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody id="adminLeaveBody"></tbody>
      </table>
      <div class="msg-bar"><span id="adminMsg"></span></div>
    </div>

  </div>
</div>

<script>
/* ============================================================
   1. 課表資料（與原本相同）
   ============================================================ */
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

const DAY_INDEX = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7 };

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

const MENU = [
  { label: '學生網路選課', open: true, children: [{ label: '線上加退選作業', active: true }, { label: '停修申請' }] },
  { label: '選課作業', open: false, children: [{ label: '選課清單查詢' }, { label: '加退選作業' }] },
  { label: '查詢', open: false, children: [{ label: '學期成績查詢' }, { label: '歷年成績查詢' }, { label: '缺曠假表查詢' }] },
  { label: '教學評量', open: false, children: [] },
];

function parseTime(time) {
  var m = String(time).match(/^\(([一二三四五六日])\)(\d+)-(\d+)$/);
  if (!m) return null;
  return { day: DAY_INDEX[m[1]], start: Number(m[2]), end: Number(m[3]) };
}

function coursesAt(day, period) {
  return myCourses.filter(function (course) {
    var t = parseTime(course.time);
    return t && t.day === day && period >= t.start && period <= t.end;
  });
}

function toggleFolder(label) {
  var uls = document.querySelectorAll('ul.tree ul[data-folder="' + CSS.escape(label) + '"]');
  uls.forEach(function (ul) {
    var hidden = ul.style.display === 'none';
    ul.style.display = hidden ? '' : 'none';
    var toggle = ul.closest('li').querySelector('.tree-toggle');
    if (toggle) toggle.textContent = hidden ? '-' : '+';
  });
}

(function renderTree() {
  var root = document.getElementById('tree');
  MENU.forEach(function (folder) {
    var li = document.createElement('li');

    var toggle = document.createElement('span');
    toggle.className = 'tree-toggle';
    toggle.textContent = folder.open ? '-' : '+';
    toggle.onclick = function () { toggleFolder(folder.label); };
    toggle.tabIndex = 0;
    toggle.onkeydown = function (e) { if (e.key === 'Enter') toggleFolder(folder.label); };
    li.appendChild(toggle);

    var folderIcon = document.createElement('span');
    folderIcon.className = 'tree-folder';
    folderIcon.textContent = '\uD83D\uDCC1';
    li.appendChild(folderIcon);

    var folderLabel = document.createElement('span');
    folderLabel.textContent = folder.label;
    folderLabel.style.cursor = 'pointer';
    folderLabel.onclick = function () { toggleFolder(folder.label); };
    li.appendChild(folderLabel);

    if (folder.children.length > 0) {
      var ul = document.createElement('ul');
      ul.setAttribute('data-folder', folder.label);
      if (!folder.open) ul.style.display = 'none';
      folder.children.forEach(function (item) {
        var childLi = document.createElement('li');
        var dot = document.createElement('span');
        dot.className = 'tree-red-dot';
        childLi.appendChild(dot);
        var leaf = document.createElement('span');
        leaf.className = 'tree-leaf' + (item.active ? ' active' : '');
        if (item.label === '\u7DDA\u4E0A\u52A0\u9000\u9078\u4F5C\u696D') {
          leaf.innerHTML = '<a href="enroll.html">\u7DDA\u4E0A\u52A0\u9000\u9078\u4F5C\u696D</a>';
        } else {
          leaf.textContent = item.label;
          leaf.onclick = function () { alert('\u5DF2\u5207\u63DB\u81F3\u300C' + item.label + '\u300D\uFF08Demo\uFF09'); };
        }
        childLi.appendChild(leaf);
        ul.appendChild(childLi);
      });
      li.appendChild(ul);
    }
    root.appendChild(li);
  });
})();

(function renderCourseList() {
  var body = document.getElementById('courseBody');
  var html = '';
  myCourses.forEach(function (course) {
    html += '<tr>' +
      '<td>' + course.id + '</td>' +
      '<td class="left">' + course.name + '</td>' +
      '<td class="left">' + course.nameEn + '</td>' +
      '<td>' + course.class + '</td>' +
      '<td>' + course.group + '</td>' +
      '<td>' + course.credits + '</td>' +
      '<td>' + course.hours + '</td>' +
      '<td>' + course.required + '</td>' +
      '<td>' + course.term + '</td>' +
      '<td>' + course.time + '</td>' +
      '<td>' + course.teacher + '</td>' +
      '<td>' + course.room + '</td>' +
      '<td><a href="#" class="syllabus-link" onclick="event.preventDefault(); alert(\'查詢「' + course.name + '」教學綱要（Demo）\')">課程綱要</a></td>' +
      '</tr>';
  });
  body.innerHTML = html;
})();

(function renderTimetable() {
  var body = document.getElementById('timeBody');
  var html = '';
  PERIODS.forEach(function (p) {
    html += '<tr>' +
      '<td class="time-col">第 ' + p.no + ' 節<br>' + p.label + '</td>';
    for (var day = 1; day <= 7; day++) {
      var courses = coursesAt(day, p.no);
      html += '<td class="cell" style="background:#fff">';
      courses.forEach(function (course) {
        html += '<div class="tcell" title="' + course.name + ' / ' + course.nameEn + '">' +
          '<div class="cn">' + course.name + '</div>' +
          course.nameEn + '<br>' +
          course.teacher + '<br>' +
          course.room +
          '</div>';
      });
      html += '</td>';
    }
    html += '</tr>';
  });
  body.innerHTML = html;
})();

/* ============================================================
   2. 登入 / 角色分流
   ============================================================ */
var currentUser = null;

function clearLogin() {
  document.getElementById('loginUser').value = '';
  document.getElementById('loginPass').value = '';
  document.getElementById('loginMsg').textContent = '';
}

function showView(name) {
  document.getElementById('viewLogin').style.display   = (name === 'login')   ? 'block' : 'none';
  document.getElementById('viewStudent').style.display = (name === 'student') ? 'block' : 'none';
  document.getElementById('viewAdmin').style.display   = (name === 'admin')   ? 'block' : 'none';
}

function showMessage(id, text, ok) {
  var el = document.getElementById(id);
  el.textContent = text;
  el.className = ok ? 'msg-ok' : 'msg-err';
}

function doLogin() {
  var user_id = document.getElementById('loginUser').value.trim();
  var password = document.getElementById('loginPass').value.trim();
  showMessage('loginMsg', '', true);

  fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: user_id, password: password })
  })
    .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
    .then(function (r) {
      if (!r.ok) {
        showMessage('loginMsg', r.data.message || '登入失敗', false);
        return;
      }
      currentUser = r.data.data;
      document.getElementById('userLine1').textContent = '116學年度第1學期';
      document.getElementById('userLine2').textContent = '登入帳號：' + currentUser.user_id;
      document.getElementById('userLine3').textContent =
        '身分：' + (currentUser.role === 'admin' ? '管理員' : '學生');
      if (currentUser.role === 'admin') {
        showView('admin');
        loadAdminLeaves();
      } else {
        showView('student');
        showStudentTab('schedule');
      }
    })
    .catch(function () { showMessage('loginMsg', '無法連線到伺服器', false); });
}

function logout() {
  currentUser = null;
  document.getElementById('userLine1').textContent = '尚未登入';
  document.getElementById('userLine2').textContent = '&nbsp;';
  document.getElementById('userLine3').textContent = '&nbsp;';
  clearLogin();
  showView('login');
}

document.getElementById('loginPass').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});

/* 學生的兩個子畫面切換：課表 / 請假 */
function showStudentTab(tab) {
  document.getElementById('studentSchedule').style.display = (tab === 'schedule') ? 'block' : 'none';
  document.getElementById('studentLeave').style.display    = (tab === 'leave')    ? 'block' : 'none';
  if (tab === 'leave') prefillLeaveDate();
}

/* ============================================================
   3. 學生請假
   ============================================================ */
function prefillLeaveDate() {
  var d = new Date();
  var pad = function (n) { return (n < 10 ? '0' : '') + n; };
  document.getElementById('leaveDate').value =
    d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function clearLeaveForm() {
  document.getElementById('leaveReason').value = '';
  prefillLeaveDate();
  document.getElementById('leaveMsg').textContent = '';
}

function submitLeave() {
  var sid = document.getElementById('leaveSid').value.trim();
  var leave_type = document.getElementById('leaveType').value;
  var leave_date = document.getElementById('leaveDate').value.trim();
  var reason = document.getElementById('leaveReason').value.trim();
  showMessage('leaveMsg', '', true);

  if (!sid || !leave_date || !reason) {
    showMessage('leaveMsg', '學號、日期、事由為必填欄位', false);
    return;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(leave_date)) {
    showMessage('leaveMsg', '日期格式錯誤，應為 YYYY-MM-DD', false);
    return;
  }

  fetch('/api/leave', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ student_id: sid, leave_type: leave_type, leave_date: leave_date, reason: reason })
  })
    .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
    .then(function (r) {
      if (!r.ok) {
        showMessage('leaveMsg', r.data.message || '送出失敗', false);
        return;
      }
      showMessage('leaveMsg', r.data.message, true);
      var d = r.data.data;
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + d.leave_id + '</td>' +
        '<td>' + d.leave_type + '</td>' +
        '<td>' + d.leave_date + '</td>' +
        '<td class="left">' + d.reason + '</td>' +
        '<td class="status-pending">審核中</td>';
      document.getElementById('myLeaveBody').appendChild(tr);
      document.getElementById('leaveReason').value = '';
    })
    .catch(function () { showMessage('leaveMsg', '無法連線到伺服器', false); });
}

/* ============================================================
   4. 管理員審核
   ============================================================ */
function loadAdminLeaves() {
  showMessage('adminMsg', '', true);
  fetch('/api/admin/leaves')
    .then(function (res) { return res.json(); })
    .then(function (data) {
      var body = document.getElementById('adminLeaveBody');
      body.innerHTML = '';
      if (!data.success) {
        showMessage('adminMsg', data.message || '讀取失敗', false);
        return;
      }
      if (data.total === 0) {
        body.innerHTML = '<tr><td colspan="8">目前沒有待審核的請假單</td></tr>';
        return;
      }
      data.data.forEach(function (row) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + row.leave_id + '</td>' +
          '<td>' + row.student_id + '</td>' +
          '<td>' + row.student_name + '</td>' +
          '<td>' + row.leave_type + '</td>' +
          '<td>' + row.leave_date + '</td>' +
          '<td class="left">' + row.reason + '</td>' +
          '<td class="status-pending">審核中</td>' +
          '<td>' +
            '<button class="mini-btn approve" onclick="reviewLeave(' + row.leave_id + ', \'已批准\')">批准</button>' +
            '&nbsp;' +
            '<button class="mini-btn reject" onclick="reviewLeave(' + row.leave_id + ', \'退回\')">退回</button>' +
          '</td>';
        body.appendChild(tr);
      });
    })
    .catch(function () { showMessage('adminMsg', '無法連線到伺服器', false); });
}

function reviewLeave(leave_id, status) {
  showMessage('adminMsg', '', true);
  fetch('/api/admin/leaves/' + leave_id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: status })
  })
    .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
    .then(function (r) {
      if (!r.ok) {
        showMessage('adminMsg', r.data.message || '審核失敗', false);
        return;
      }
      showMessage('adminMsg', r.data.message, true);
      loadAdminLeaves();
    })
    .catch(function () { showMessage('adminMsg', '無法連線到伺服器', false); });
}
</script>
</body>
</html>"""

ENROLL_PAGE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>國立金門大學 - 線上加退選作業</title>
<style>
/* ============================================================
   2005 年傳統 HTML Frame 校務系統介面
   * 字體：新細明體 PMingLiU，基礎 12px
   * 全域無 border-radius、無陰影、無 Flexbox/Grid 留白
   ============================================================ */
* {
  margin: 0;
  padding: 0;
  border-radius: 0 !important;
  box-shadow: none !important;
}

html, body {
  height: 100%;
}

body {
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  font-size: 12px;
  color: #000;
  background: #fff;
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ---------- Header 上方深藍橫幅 ---------- */
.header-wrap {
  background: #3b5598;
  flex-shrink: 0;
}

.header-table {
  width: 100%;
  height: 70px;
  border-collapse: collapse;
  table-layout: fixed;
  border: 0;
}

.header-left,
.header-center,
.header-right {
  vertical-align: middle;
}

.header-left {
  width: 160px;
  padding: 2px 6px;
  text-align: left;
}

.header-center {
  text-align: center;
  color: #fff;
}

.header-center .logo {
  font-size: 22px;
  letter-spacing: 3px;
  font-weight: bold;
}

.header-center .logo-en {
  font-size: 12px;
  letter-spacing: 2px;
}

.header-right {
  width: 230px;
  padding: 2px 6px;
  text-align: left;
}

.user-info {
  color: #ffff00;
  font-weight: bold;
}

.user-line {
  line-height: 1.3;
  padding: 1px 0;
}

/* ---------- 傳統立體按鈕（灰底黑字） ---------- */
.retro-btn {
  background: #c0c0c0;
  border: 2px outset;
  border-color: #ffffff #808080 #808080 #ffffff;
  padding: 2px 10px;
  font-family: "新細明體", PMingLiU, MingLiU, serif;
  font-size: 12px;
  color: #000;
  cursor: pointer;
  white-space: nowrap;
}
.retro-btn:active { border-style: inset; }
.retro-btn:hover { background: #d0d0d0; }

/* ---------- 內容區 ---------- */
.main-scroll {
  flex: 1;
  overflow-y: auto;
  background: #eaeaea;
  padding: 4px 6px;
}

/* 置中按鈕列 */
.btn-bar {
  text-align: center;
  margin: 6px 0;
}

.panel-title {
  text-align: center;
  font-weight: bold;
  margin: 8px 0 4px 0;
}

/* ---------- 選課表格：傳統 Table 排版 ---------- */
table.course-grid {
  width: 100%;
  border: 1px solid #999;
  border-collapse: collapse;
  text-align: center;
  background: #fff;
  font-size: 12px;
}

table.course-grid th,
table.course-grid td {
  border: 1px solid #999;
  padding: 3px;
  font-size: 12px;
  text-align: center;
  vertical-align: middle;
}

table.course-grid th {
  background: #e0e0e0;
  font-weight: normal;
}

/* 第一欄表頭「加選」：紅字 */
table.course-grid th.enroll-head {
  color: red;
}

/* 必修白底 / 選修淺黃綠底 由 JS 依資料上色 */
.required-bg { background: #ffffff; }
.elective-bg { background: #e6f2c8; }
</style>
</head>
<body>
<div class="app">
  <!-- ============ Header：三欄 Table ============ -->
  <div class="header-wrap">
    <table class="header-table">
      <tbody>
        <tr>
          <td class="header-left">
            <button class="retro-btn" onclick="location.href='index.html'">回上一頁</button>
          </td>
          <td class="header-center">
            <span class="logo">國立金門大學</span><br>
            <span class="logo-en">National Quemoy University</span>
          </td>
          <td class="header-right">
            <div class="user-info">
              <div class="user-line">116學年度第1學期</div>
              <div class="user-line">資工二</div>
              <div class="user-line">邱祺峰</div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- ============ 主要內容 ============ -->
  <div class="main-scroll">
    <!-- 上方置中按鈕列 -->
    <div class="btn-bar">
      <button class="retro-btn" onclick="location.href='index.html'">回上一頁</button>
      <button class="retro-btn" onclick="submitEnroll()">確定送出</button>
    </div>

    <div class="panel-title">【 線 上 加 退 選 作 業 】</div>

    <!-- 可加選課程表格 -->
    <table class="course-grid" id="courseGrid">
      <thead>
        <tr>
          <th class="enroll-head">加選</th>
          <th>選課代號</th>
          <th>科目</th>
          <th>科目英文名</th>
          <th>班級</th>
          <th>分組</th>
          <th>學分</th>
          <th>小時</th>
          <th>必選修</th>
          <th>開課別</th>
          <th>教師</th>
          <th>教室</th>
          <th>時間</th>
          <th>合班班級</th>
          <th>上限人數</th>
          <th>下限人數</th>
          <th>實收人數</th>
          <th>限修備註</th>
          <th>備註</th>
        </tr>
      </thead>
      <tbody id="courseBody"></tbody>
    </table>

    <!-- 下方置中按鈕列 -->
    <div class="btn-bar">
      <button class="retro-btn" onclick="location.href='index.html'">回上一頁</button>
      <button class="retro-btn" onclick="submitEnroll()">確定送出</button>
    </div>
  </div>
</div>

<script>
/* ============================================================
   可加選課程資料
   ============================================================ */
const availableCourses = [
  { id: "0156", name: "作業系統", nameEn: "Operating System", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "必修", term: "學期", teacher: "馮玄明", room: "I101圖資電腦教室", time: "(一)2-4", max: 65, min: 10, current: 62 },
  { id: "0154", name: "專題製作(一)", nameEn: "Senior Projects (I)", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "必修", term: "學期", teacher: "李錫捷,吳佳駿,柯志亨,潘進儒,王建鈞,趙于翔,陳正德,陳鍾誠,馮玄明", room: "E319數位系統應用實驗", time: "(五)5-7", max: 60, min: 10, current: 49 },
  { id: "0160", name: "人工智慧導論", nameEn: "Introduction to Artificial Intelligence", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "選修", term: "學期", teacher: "李錫捷", room: "E320多媒體實驗室", time: "(一)5-7", max: 60, min: 10, current: 23 },
  { id: "0159", name: "伺服器架設", nameEn: "Server Setup & Maintenance", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "選修", term: "學期", teacher: "柯志亨", room: "E321電腦網路實驗室", time: "(二)2-4", max: 60, min: 10, current: 31 },
  { id: "0158", name: "微電腦數位實習", nameEn: "Micro-Computer Digital Practice", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "選修", term: "學期", teacher: "趙于翔", room: "E322嵌入式實驗室", time: "(四)2-4", max: 60, min: 10, current: 30 },
  { id: "0155", name: "演算法", nameEn: "Introduction to Algorithms", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "選修", term: "學期", teacher: "陳鍾誠", room: "E320多媒體實驗室", time: "(三)2-4", max: 60, min: 10, current: 49 },
  { id: "0157", name: "遊戲程式設計", nameEn: "Game Programming", class: "資工三", group: "01", credits: "3.0", hours: "3.0", required: "選修", term: "學期", teacher: "趙于翔", room: "E322嵌入式實驗室", time: "(二)5-7", max: 60, min: 10, current: 25 }
];

/* ---------- 以 .map() 產生資料列 ---------- */
(function renderRows() {
  const body = document.getElementById('courseBody');

  body.innerHTML = availableCourses.map(function (c) {
    // 選修課 => 淺黃綠底；必修課 => 白底
    const bgClass = c.required === '選修' ? 'elective-bg' : 'required-bg';

    return '<tr class="' + bgClass + '">' +
      '<td><input type="checkbox" data-id="' + c.id + '" data-name="' + c.name + '" /></td>' +
      '<td>' + c.id + '</td>' +
      '<td>' + c.name + '</td>' +
      '<td>' + c.nameEn + '</td>' +
      '<td>' + c.class + '</td>' +
      '<td>' + c.group + '</td>' +
      '<td>' + c.credits + '</td>' +
      '<td>' + c.hours + '</td>' +
      '<td>' + c.required + '</td>' +
      '<td>' + c.term + '</td>' +
      '<td>' + c.teacher + '</td>' +
      '<td>' + c.room + '</td>' +
      '<td>' + c.time + '</td>' +
      '<td></td>' +
      '<td>' + c.max + '</td>' +
      '<td>' + c.min + '</td>' +
      '<td>' + c.current + '</td>' +
      '<td></td>' +
      '<td></td>' +
      '</tr>';
  }).join('');
})();

/* ---------- 確定送出：收集勾選的課程 ---------- */
function submitEnroll() {
  const checked = document.querySelectorAll('#courseGrid input[type="checkbox"]:checked');
  if (checked.length === 0) {
    alert('尚未勾選任何課程，請先選擇要加退選的課程。');
    return;
  }

  let msg = '您已勾選 ' + checked.length + ' 門課程，將進行加選處理：\n\n';
  checked.forEach(function (cb) {
    msg += ' - [' + cb.dataset.id + '] ' + cb.dataset.name + '\n';
  });
  alert(msg);
}
</script>
</body>
</html>"""

LEAVE_TYPES = ('病假', '事假', '公假', '喪假', '其他')
ALLOWED_STATUS = ('已批准', '退回')


# ============================================================
# 資料庫
# ============================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def query(sql, params=()):
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def execute(sql, params=()):
    conn = get_connection()
    cur = conn.execute(sql, params)
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected


def init_db():
    conn = get_connection()

    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(50) PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'student'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50) NOT NULL
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS leave_requests (
            leave_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id VARCHAR(10) NOT NULL,
            leave_type VARCHAR(20) NOT NULL,
            leave_date VARCHAR(10) NOT NULL,
            reason VARCHAR(500),
            status VARCHAR(20) DEFAULT '審核中'
        )
    ''')

    conn.commit()

    # seed 預設帳號
    if not query('SELECT 1 FROM users LIMIT 1'):
        for uid, pw, role in [('student', '123456', 'student'), ('admin', '123456', 'admin')]:
            execute("INSERT INTO users (user_id, password, role) VALUES (?, ?, ?)",
                    (uid, pw, role))

    if not query('SELECT 1 FROM students LIMIT 1'):
        execute("INSERT INTO students (student_id, name) VALUES (?, ?)",
                ('A123456789', '王小明'))

    conn.close()


app = Flask(__name__)
CORS(app)
init_db()


# ============================================================
# 頁面路由
# ============================================================
@app.route('/')
def home():
    return render_template_string(INDEX_PAGE)


@app.route('/index.html')
def home_alt():
    return render_template_string(INDEX_PAGE)


@app.route('/enroll.html')
def enroll_page():
    return render_template_string(ENROLL_PAGE)


@app.route('/api')
def api_info():
    return jsonify({'name': '校務系統 API', 'version': '1.0.0'})


# ============================================================
# 登入
# ============================================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(force=True)
    user_id = data.get('user_id')
    password = data.get('password')

    if not user_id or not password:
        return jsonify({'success': False, 'message': '缺少必要欄位: user_id, password'}), 400

    rows = query('SELECT user_id, role FROM users WHERE user_id = ? AND password = ?',
                 (user_id, password))
    if not rows:
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'}), 401

    user = rows[0]
    return jsonify({'success': True, 'message': '登入成功',
                    'data': {'user_id': user['user_id'], 'role': user['role']}})


# ============================================================
# 學生請假
# ============================================================
@app.route('/api/leave', methods=['POST'])
def create_leave():
    data = request.get_json(force=True)
    student_id = data.get('student_id')
    leave_type = data.get('leave_type')
    leave_date = data.get('leave_date')
    reason = data.get('reason')

    if not student_id or not leave_type or not leave_date or not reason:
        return jsonify({'success': False,
                        'message': '缺少必要欄位: student_id, leave_type, leave_date, reason'}), 400

    if leave_type not in LEAVE_TYPES:
        return jsonify({'success': False,
                        'message': f'無效假別，僅允許: {", ".join(LEAVE_TYPES)}'}), 400

    if not query('SELECT 1 FROM students WHERE student_id = ?', (student_id,)):
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO leave_requests (student_id, leave_type, leave_date, reason, status) VALUES (?, ?, ?, ?, '審核中')",
        (student_id, leave_type, leave_date, reason)
    )
    conn.commit()
    leave_id = cur.lastrowid
    conn.close()

    return jsonify({'success': True, 'message': '請假申請已送出，待管理員審核',
                    'data': {'leave_id': leave_id, 'student_id': student_id,
                             'leave_type': leave_type, 'leave_date': leave_date,
                             'reason': reason, 'status': '審核中'}}), 201


# ============================================================
# 管理員審核
# ============================================================
@app.route('/api/admin/leaves', methods=['GET'])
def list_pending_leaves():
    rows = query(
        '''SELECT l.leave_id, l.student_id, s.name AS student_name,
                  l.leave_type, l.leave_date, l.reason, l.status
           FROM leave_requests l
           LEFT JOIN students s ON l.student_id = s.student_id
           WHERE l.status = '審核中'
           ORDER BY l.leave_id DESC'''
    )
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@app.route('/api/admin/leaves/<int:leave_id>', methods=['PUT'])
def review_leave(leave_id):
    data = request.get_json(force=True)
    new_status = data.get('status')

    if new_status not in ALLOWED_STATUS:
        return jsonify({'success': False,
                        'message': f'無效狀態，僅允許: {", ".join(ALLOWED_STATUS)}'}), 400

    rows = query('SELECT * FROM leave_requests WHERE leave_id = ?', (leave_id,))
    if not rows:
        return jsonify({'success': False, 'message': '找不到該請假單'}), 404
    leave = rows[0]

    if leave['status'] != '審核中':
        return jsonify({'success': False, 'message': '該假單已審核完畢，不可重複審核'}), 400

    execute('UPDATE leave_requests SET status = ? WHERE leave_id = ?', (new_status, leave_id))

    return jsonify({'success': True, 'message': f'審核成功，狀態已更新為「{new_status}」',
                    'data': {'leave_id': leave_id, 'student_id': leave['student_id'],
                             'leave_type': leave['leave_type'], 'leave_date': leave['leave_date'],
                             'status': new_status}})


if __name__ == '__main__':
    print('校務系統啟動中: http://localhost:5000')
    app.run(debug=True, port=5000)