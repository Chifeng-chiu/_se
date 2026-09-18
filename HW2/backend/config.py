"""
config.py - 資料庫連線設定檔
集中管理資料庫位置與環境參數
"""
import os

class Config:
    """資料庫設定：使用 SQLite 存放於 data 目錄下"""

    # 以本檔所在位置為基準，計算資料庫絕對路徑
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'university.db')

    # 系統目前學期（如 113-1），加選課程未指定學期時以此為預設
    CURRENT_SEMESTER = '113-1'