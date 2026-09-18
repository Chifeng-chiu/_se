"""
database.py - 資料庫連線管理
封裝連線取得與通用查詢/執行函式
"""
import sqlite3
import os
from config import Config

def get_connection():
    """
    建立並回傳 SQLite 連線

    重點設定：
    1. row_factory = sqlite3.Row
       - 讓查詢結果可透過欄位名稱 (row['name']) 取值，易於轉換成 JSON
    2. PRAGMA foreign_keys = ON
       - 啟用外鍵約束，確保資料完整性（避免刪除被參照的資料）
    """
    # 若 data 目錄不存在則自動建立
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, params=()):
    """
    通用查詢函式：執行 SELECT 並回傳 dict 清單
    自動開啟/關閉連線，呼叫端不需處理連線細節
    """
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def execute(sql, params=()):
    """
    通用執行函式：執行 INSERT / UPDATE / DELETE
    自動 commit 並回傳受影響的資料列數
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected