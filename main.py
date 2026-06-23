# -*- coding: utf-8 -*-
"""
屏幕使用时间监控小工具 (iOS 风格)
===================================
一个模仿 iOS "屏幕使用时间" 的 Windows 桌面应用，
后台监控活动窗口使用时长，并以 iOS 风格卡片展示。

依赖安装:
    pip install PyQt6 psutil pywin32

运行:
    python main.py

作者: AI Assistant
日期: 2026-06-23
"""

import sys
import os
import time
import sqlite3
import ctypes
import random
import datetime
import threading
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 第三方库导入（带异常保护）
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QScrollArea, QFrame, QPushButton, QGraphicsBlurEffect,
        QSizePolicy, QSpacerItem
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QRectF, QPoint, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPixmap, QIcon,
        QLinearGradient, QRadialGradient, QFontDatabase
    )
except ImportError:
    print("请先安装依赖: pip install PyQt6 psutil pywin32")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("请先安装依赖: pip install psutil")
    sys.exit(1)

try:
    import win32gui
    import win32process
    import win32api
    import win32con
    import win32ui
    HAS_WIN32 = True
except ImportError:
    print("警告: pywin32 未安装，部分功能不可用。请运行: pip install pywin32")
    HAS_WIN32 = False

try:
    import winreg
except ImportError:
    winreg = None


# ===========================================================================
# 常量与配置
# ===========================================================================

APP_NAME_MAP = {
    "chrome.exe": "Chrome 浏览器",
    "msedge.exe": "Edge 浏览器",
    "firefox.exe": "Firefox 浏览器",
    "wechat.exe": "微信",
    "WeChat.exe": "微信",
    "qq.exe": "QQ",
    "QQ.exe": "QQ",
    "dingtalk.exe": "钉钉",
    "DingTalk.exe": "钉钉",
    "code.exe": "Visual Studio Code",
    "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA",
    "pycharm64.exe": "PyCharm",
    "webstorm64.exe": "WebStorm",
    "explorer.exe": "文件资源管理器",
    "notepad.exe": "记事本",
    "notepad++.exe": "Notepad++",
    "WINWORD.EXE": "Microsoft Word",
    "EXCEL.EXE": "Microsoft Excel",
    "POWERPNT.EXE": "Microsoft PowerPoint",
    "OUTLOOK.EXE": "Microsoft Outlook",
    "ONENOTE.EXE": "Microsoft OneNote",
    "slack.exe": "Slack",
    "Telegram.exe": "Telegram",
    "Discord.exe": "Discord",
    "spotify.exe": "Spotify",
    "vlc.exe": "VLC 播放器",
    "PotPlayerMini64.exe": "PotPlayer",
    "mpc-hc64.exe": "MPC-HC",
    "photoshop.exe": "Adobe Photoshop",
    "Illustrator.exe": "Adobe Illustrator",
    "Figma.exe": "Figma",
    "terminal64.exe": "Windows Terminal",
    "WindowsTerminal.exe": "Windows Terminal",
    "cmd.exe": "命令提示符",
    "powershell.exe": "PowerShell",
    "pwsh.exe": "PowerShell 7",
    "steam.exe": "Steam",
    "EpicGamesLauncher.exe": "Epic Games",
    "Typora.exe": "Typora",
    "Obsidian.exe": "Obsidian",
    "Notion.exe": "Notion",
    "Feishu.exe": "飞书",
    "Lark.exe": "飞书",
    "wps.exe": "WPS Office",
    "et.exe": "WPS 表格",
    "wpp.exe": "WPS 演示",
    "pdfxedit.exe": "PDF-XChange Editor",
    "Acrobat.exe": "Adobe Acrobat",
    "Snipaste.exe": "Snipaste",
    "Everything.exe": "Everything",
    "7zFM.exe": "7-Zip",
    "WinRAR.exe": "WinRAR",
}

# 系统级进程（不计入屏幕使用时间）
SYSTEM_PROCESSES = {
    "explorer.exe",   # 文件资源管理器单独记录，但桌面空闲不计
    "LockApp.exe",
    "LogonUI.exe",
    "SearchHost.exe",
    "StartMenuExperienceHost.exe",
    "ShellExperienceHost.exe",
    "ApplicationFrameHost.exe",
}

# 桌面/锁屏窗口标题关键词
IDLE_TITLES = {"", "Windows 输入体验", "设置", "任务栏", "Program Manager"}

# iOS 风格配色
COLOR_BG = QColor(28, 28, 30, 220)          # 深色半透明背景
COLOR_CARD = QColor(44, 44, 46, 200)        # 卡片背景
COLOR_CARD_HOVER = QColor(58, 58, 60, 220)  # 悬停高亮
COLOR_SEPARATOR = QColor(84, 84, 88, 128)   # 分隔线
COLOR_TEXT = QColor(255, 255, 255, 255)     # 主文字
COLOR_TEXT_SECONDARY = QColor(152, 152, 157, 255)  # 次要文字
COLOR_ACCENT = QColor(10, 132, 255, 255)    # iOS 蓝
COLOR_ACCENT_GRADIENT = QColor(88, 86, 214, 255)   # iOS 紫
COLOR_PROGRESS_BG = QColor(58, 58, 60, 180)  # 进度条背景
COLOR_RED = QColor(255, 69, 58, 255)
COLOR_ORANGE = QColor(255, 159, 10, 255)
COLOR_GREEN = QColor(48, 209, 88, 255)

# 应用图标圆点配色池
ICON_COLORS = [
    QColor(10, 132, 255),    # 蓝
    QColor(88, 86, 214),     # 紫
    QColor(255, 99, 132),    # 粉红
    QColor(255, 159, 10),    # 橙
    QColor(48, 209, 88),     # 绿
    QColor(255, 69, 58),     # 红
    QColor(100, 210, 255),   # 青蓝
    QColor(175, 82, 222),    # 紫红
    QColor(94, 92, 230),     # 蓝紫
    QColor(255, 55, 95),     # 玫红
    QColor(52, 199, 89),     # 翠绿
    QColor(255, 149, 0),     # 橙黄
    QColor(0, 199, 190),     # 青绿
    QColor(88, 86, 214),     # 靛蓝
]

WINDOW_WIDTH = 420
WINDOW_HEIGHT = 720
TARGET_MINUTES = 8 * 60  # 目标时长 8 小时
MONITOR_INTERVAL = 2     # 监控间隔（秒）
IDLE_THRESHOLD = 300     # 闲置阈值（5 分钟）

DB_PATH = Path.home() / ".screentime" / "screentime.db"


# ===========================================================================
# 数据库管理
# ===========================================================================

class DatabaseManager:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_records (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT    NOT NULL,
                    app_name    TEXT    NOT NULL,
                    total_minutes INTEGER DEFAULT 0,
                    icon_path   TEXT,
                    UNIQUE(date, app_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
            conn.close()

    def upsert_usage(self, date_str: str, app_name: str, minutes: int, icon_path: str = ""):
        """插入或更新某应用某天的使用时长"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT INTO usage_records (date, app_name, total_minutes, icon_path)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, app_name)
                DO UPDATE SET total_minutes = total_minutes + ?,
                              icon_path = ?
            """, (date_str, app_name, minutes, icon_path, minutes, icon_path))
            conn.commit()
            conn.close()

    def get_today_usage(self, date_str: str) -> dict:
        """获取某天所有应用的使用时长，返回 {app_name: minutes}"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute(
                "SELECT app_name, total_minutes FROM usage_records WHERE date = ? ORDER BY total_minutes DESC",
                (date_str,)
            )
            result = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return result

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
            """, (key, value, value))
            conn.commit()
            conn.close()

    def reset_today(self, date_str: str):
        """重置某天数据"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM usage_records WHERE date = ?", (date_str,))
            conn.commit()
            conn.close()


# ===========================================================================
# 工具函数
# ===========================================================================

def get_display_name(proc_name: str) -> str:
    """获取应用显示名称"""
    if proc_name in APP_NAME_MAP:
        return APP_NAME_MAP[proc_name]
    # 去掉 .exe 后缀，首字母大写
    name = proc_name.replace(".exe", "").replace(".EXE", "")
    return name.capitalize()


def get_icon_color(proc_name: str) -> QColor:
    """根据进程名生成稳定的图标颜色"""
    hash_val = sum(ord(c) for c in proc_name)
    return ICON_COLORS[hash_val % len(ICON_COLORS)]


def extract_exe_icon(exe_path: str, size: int = 32) -> QPixmap | None:
    """尝试从 exe 提取图标，失败返回 None"""
    if not HAS_WIN32 or not exe_path or not os.path.exists(exe_path):
        return None
    try:
        import win32api
        import win32con
        import win32ui
        large, small = win32api.ExtractIconEx(exe_path, 0, 1, 1)
        if large:
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hdc_mem = hdc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(hdc, size, size)
            hdc_mem.SelectObject(bmp)
            hdc_mem.DrawIcon((0, 0), large[0])
            bmpinfo = bmp.GetInfo()
            bmpstr = bmp.BitmapBits()
            img = QPixmap.fromImage(
                __import__("PyQt6.QtGui", fromlist=["QImage"]).QImage(
                    bmpstr, bmpinfo["bmWidth"], bmpinfo["bmHeight"],
                    __import__("PyQt6.QtGui", fromlist=["QImage"]).QImage.Format.Format_ARGB32
                )
            )
            win32gui.DeleteObject(large[0])
            hdc_mem.DeleteDC()
            hdc.DeleteDC()
            return img
    except Exception:
        pass
    return None


def get_exe_path(proc_name: str) -> str:
    """通过进程名获取 exe 路径"""
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            if proc.info["name"] and proc.info["name"].lower() == proc_name.lower():
                return proc.info["exe"] or ""
    except Exception:
        pass
    return ""


def format_duration(minutes: int) -> str:
    """格式化时长为 'X小时X分钟'"""
    if minutes <= 0:
        return "0分钟"
    hours = minutes // 60
    mins = minutes % 60
    if hours == 0:
        return f"{mins}分钟"
    if mins == 0:
        return f"{hours}小时"
    return f"{hours}小时{mins}分钟"


def is_system_idle() -> bool:
    """检测系统是否处于闲置/锁屏状态"""
    if not HAS_WIN32:
        return False
    try:
        # 检查屏幕保护程序
        result = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(
            win32con.SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(result), 0
        )
        if result.value:
            return True

        # 检查锁屏（LogonUI 进程）
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() in ("logonui.exe", "lockapp.exe"):
                return True

        # 检查最后输入时间（闲置超过阈值）
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        if millis > IDLE_THRESHOLD * 1000:
            return True
    except Exception:
        pass
    return False


# ===========================================================================
# 后台监控线程
# ===========================================================================

class MonitorThread(QThread):
    """后台窗口监控线程"""

    usage_updated = pyqtSignal(str, int)  # (app_name, delta_minutes)
    status_message = pyqtSignal(str)

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self._running = True
        self._current_app = None
        self._current_app_start = None
        self._accumulated_seconds = 0
        self._last_date = datetime.date.today().isoformat()

    def run(self):
        while self._running:
            try:
                # 检查日期变更（跨天归档）
                today = datetime.date.today().isoformat()
                if today != self._last_date:
                    self._flush_current()
                    self._last_date = today

                if is_system_idle():
                    # 系统闲置，暂停计时
                    self._flush_current()
                    self.status_message.emit("系统闲置中")
                else:
                    app_name = self._get_foreground_app()
                    if app_name:
                        if app_name != self._current_app:
                            self._flush_current()
                            self._current_app = app_name
                            self._current_app_start = time.time()
                            self._accumulated_seconds = 0
                        else:
                            self._accumulated_seconds += MONITOR_INTERVAL
                            # 每分钟持久化一次
                            if self._accumulated_seconds >= 60:
                                minutes = int(self._accumulated_seconds // 60)
                                self._accumulated_seconds -= minutes * 60
                                self.db_manager.upsert_usage(
                                    self._last_date, app_name, minutes
                                )
                                self.usage_updated.emit(app_name, minutes)
                    else:
                        self._flush_current()

            except Exception as e:
                # 防止任何异常导致线程崩溃
                self.status_message.emit(f"监控异常: {e}")

            self.msleep(MONITOR_INTERVAL * 1000)

    def _get_foreground_app(self) -> str | None:
        """获取当前前台窗口的进程名"""
        if not HAS_WIN32:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            title = win32gui.GetWindowText(hwnd)
            if title in IDLE_TITLES:
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return None
            try:
                proc = psutil.Process(pid)
                return proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None
        except Exception:
            return None

    def _flush_current(self):
        """将当前应用的累计时间写入数据库"""
        if self._current_app and self._accumulated_seconds >= 1:
            minutes = max(1, round(self._accumulated_seconds / 60))
            try:
                self.db_manager.upsert_usage(self._last_date, self._current_app, minutes)
                self.usage_updated.emit(self._current_app, minutes)
            except Exception:
                pass
        self._current_app = None
        self._accumulated_seconds = 0

    def stop(self):
        """停止监控"""
        self._running = False
        self._flush_current()
        self.wait()


# ===========================================================================
# UI 组件
# ===========================================================================

class CircularProgressBar(QWidget):
    """iOS 风格环形进度条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0       # 0.0 ~ 1.0
        self._text = ""
        self._sub_text = ""
        self.setFixedSize(160, 160)

    def set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def set_text(self, text: str, sub_text: str = ""):
        self._text = text
        self._sub_text = sub_text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(10, 10, self.width() - 20, self.height() - 20)
        pen_width = 10

        # 背景圆环
        bg_pen = QPen(COLOR_PROGRESS_BG, pen_width)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # 进度圆环（渐变）
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, COLOR_ACCENT)
        gradient.setColorAt(1, COLOR_ACCENT_GRADIENT)
        fg_pen = QPen(QBrush(gradient), pen_width)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg_pen)
        start_angle = 90 * 16
        span_angle = int(-self._progress * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)

        # 中心文字
        painter.setPen(COLOR_TEXT)
        font = QFont("SF Pro Display", 22, QFont.Weight.Bold)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)

        # 副文字
        if self._sub_text:
            painter.setPen(COLOR_TEXT_SECONDARY)
            sub_font = QFont("SF Pro Display", 9)
            painter.setFont(sub_font)
            sub_rect = QRectF(rect.x(), rect.y() + 50, rect.width(), rect.height())
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, self._sub_text)


class AppListItemWidget(QWidget):
    """应用列表项（iOS UITableView 风格）"""

    def __init__(self, app_name: str, display_name: str, minutes: int,
                 total_minutes: int, icon_pixmap: QPixmap | None = None,
                 parent=None):
        super().__init__(parent)
        self._app_name = app_name
        self._display_name = display_name
        self._minutes = minutes
        self._total_minutes = total_minutes
        self._icon_pixmap = icon_pixmap
        self._hovered = False
        self.setFixedHeight(64)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # 左侧图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(36, 36)
        if self._icon_pixmap and not self._icon_pixmap.isNull():
            self.icon_label.setPixmap(
                self._icon_pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation)
            )
        else:
            # 首字母彩色圆点
            color = get_icon_color(self._app_name)
            pixmap = QPixmap(36, 36)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, 36, 36, 8, 8)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("SF Pro Display", 14, QFont.Weight.Bold))
            letter = self._display_name[0].upper() if self._display_name else "?"
            painter.drawText(QRectF(0, 0, 36, 36), Qt.AlignmentFlag.AlignCenter, letter)
            painter.end()
            self.icon_label.setPixmap(pixmap)

        layout.addWidget(self.icon_label)

        # 中间名称 + 进度条
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        name_label = QLabel(self._display_name)
        name_label.setStyleSheet("color: rgb(255, 255, 255); font-size: 14px; font-weight: 500;")
        name_label.setFont(QFont("SF Pro Display", 11, QFont.Weight.Medium))
        center_layout.addWidget(name_label)

        # 极细进度条
        progress_bar = QWidget()
        progress_bar.setFixedHeight(3)
        progress_bar.setStyleSheet("background: rgb(58, 58, 60); border-radius: 1px;")
        progress_layout = QHBoxLayout(progress_bar)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        fill = QWidget()
        fill.setFixedHeight(3)
        pct = (self._minutes / self._total_minutes * 100) if self._total_minutes > 0 else 0
        fill_color = get_icon_color(self._app_name).name()
        fill.setStyleSheet(f"background: {fill_color}; border-radius: 1px;")
        fill.setFixedWidth(int(progress_bar.width() * pct / 100) if progress_bar.width() > 0 else 0)

        # 用百分比 stretch
        progress_layout.addWidget(fill)
        spacer = QWidget()
        progress_layout.addWidget(spacer, 100 - int(pct) if pct < 100 else 0)
        center_layout.addWidget(progress_bar)

        layout.addWidget(center_widget, 1)

        # 右侧时长
        time_label = QLabel(format_duration(self._minutes))
        time_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 13px;")
        time_label.setFont(QFont("SF Pro Display", 10))
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(time_label)

    def enterEvent(self, event):
        self._hovered = True
        self.setStyleSheet("background-color: rgba(58, 58, 60, 220); border-radius: 0px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.setStyleSheet("")
        super().leaveEvent(event)


class MainWindow(QWidget):
    """主窗口 - iOS 风格屏幕使用时间"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.monitor_thread = MonitorThread(db_manager)
        self._drag_pos = None
        self._icon_cache = {}  # exe 图标缓存

        self._init_window()
        self._init_ui()
        self._init_monitor()
        self._refresh_data()

    # ---- 窗口初始化 ----

    def _init_window(self):
        """初始化无边框透明窗口"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # 尝试启用 Windows 11 Mica/Acrylic 效果
        self._enable_backdrop_blur()

    def _enable_backdrop_blur(self):
        """启用 Windows 11 系统 Mica/Acrylic 背景效果"""
        if not HAS_WIN32:
            return
        try:
            hwnd = int(self.winId())
            # DWMWA_SYSTEMBACKDROP_TYPE = 38 (Windows 11 22000+)
            # 0 = None, 1 = Mica, 2 = Acrylic, 3 = Tabbed
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(ctypes.c_int(2)),  # Acrylic
                ctypes.sizeof(ctypes.c_int)
            )
            # 启用暗色模式
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int)
            )
            # 扩展到客户区
            margins = ctypes.c_int(-1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                hwnd, ctypes.byref(margins)
            )
        except Exception:
            # 回退：使用 QGraphicsBlurEffect 模拟
            pass

    # ---- UI 构建 ----

    def _init_ui(self):
        # 主容器（圆角背景）
        self.container = QFrame(self)
        self.container.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: rgba(28, 28, 30, 230);
                border-radius: 20px;
                border: 1px solid rgba(84, 84, 88, 80);
            }
        """)
        self.container.setObjectName("container")

        # 模糊效果（回退方案）
        blur_effect = QGraphicsBlurEffect(self.container)
        blur_effect.setBlurRadius(30)
        # 注意：直接对 container 加 blur 会模糊内容，这里仅作为背景层参考

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 顶部导航栏 ----
        nav_widget = self._build_nav_bar()
        main_layout.addWidget(nav_widget)

        # ---- 今日概览卡片 ----
        overview_card = self._build_overview_card()
        main_layout.addWidget(overview_card)

        # ---- 分隔标题 ----
        section_label = QLabel("最常使用")
        section_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 13px; font-weight: 600;")
        section_label.setFont(QFont("SF Pro Display", 10, QFont.Weight.DemiBold))
        section_label.setContentsMargins(20, 16, 20, 8)
        main_layout.addWidget(section_label)

        # ---- 应用列表（滚动区域）----
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(120, 120, 128, 100);
                border-radius: 2px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch()
        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area, 1)

        # ---- 底部状态栏 ----
        self.status_label = QLabel("监控中...")
        self.status_label.setStyleSheet("color: rgb(99, 99, 102); font-size: 11px;")
        self.status_label.setFont(QFont("SF Pro Display", 9))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setContentsMargins(0, 8, 0, 16)
        main_layout.addWidget(self.status_label)

    def _build_nav_bar(self) -> QWidget:
        """构建顶部导航栏"""
        nav = QWidget()
        nav.setFixedHeight(56)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(16, 12, 16, 4)

        # 左侧占位（保持标题居中）
        left_spacer = QWidget()
        left_spacer.setFixedWidth(30)
        nav_layout.addWidget(left_spacer)

        # 居中标题
        title = QLabel("屏幕使用时间")
        title.setStyleSheet("color: rgb(255, 255, 255); font-size: 17px; font-weight: 600;")
        title.setFont(QFont("SF Pro Display", 13, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(title, 1)

        # 右侧刷新按钮（SF Symbols 风格 Unicode）
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setStyleSheet("""
            QPushButton {
                color: rgb(10, 132, 255);
                font-size: 20px;
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                color: rgb(90, 170, 255);
            }
        """)
        refresh_btn.setFont(QFont("SF Pro Display", 14))
        refresh_btn.clicked.connect(self._refresh_data)
        nav_layout.addWidget(refresh_btn)

        return nav

    def _build_overview_card(self) -> QWidget:
        """构建今日概览卡片"""
        card = QFrame()
        card.setObjectName("overviewCard")
        card.setStyleSheet("""
            QFrame#overviewCard {
                background-color: rgba(44, 44, 46, 180);
                border-radius: 16px;
                margin: 8px 16px 0 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(8)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 环形进度条
        self.progress_bar = CircularProgressBar()
        card_layout.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignCenter)

        # 今日总时长文字
        self.total_time_label = QLabel("0分钟")
        self.total_time_label.setStyleSheet("color: rgb(255, 255, 255); font-size: 28px; font-weight: 700;")
        self.total_time_label.setFont(QFont("SF Pro Display", 18, QFont.Weight.Bold))
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.total_time_label)

        # 目标提示
        self.goal_label = QLabel(f"目标 {TARGET_MINUTES // 60} 小时")
        self.goal_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 12px;")
        self.goal_label.setFont(QFont("SF Pro Display", 9))
        self.goal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.goal_label)

        return card

    # ---- 监控初始化 ----

    def _init_monitor(self):
        self.monitor_thread.usage_updated.connect(self._on_usage_updated)
        self.monitor_thread.status_message.connect(self._on_status_message)
        self.monitor_thread.start()

        # 定时刷新 UI
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(30000)  # 每 30 秒刷新

    # ---- 数据刷新 ----

    def _refresh_data(self):
        """刷新今日数据"""
        today = datetime.date.today().isoformat()
        usage = self.db_manager.get_today_usage(today)
        self._render_usage(usage)

    def _render_usage(self, usage: dict):
        """渲染应用列表"""
        total = sum(usage.values())

        # 更新概览
        self.total_time_label.setText(format_duration(total))
        progress = total / TARGET_MINUTES if TARGET_MINUTES > 0 else 0
        self.progress_bar.set_progress(progress)
        self.total_time_label.setText(format_duration(total))

        # 环形进度条中心文字
        hours = total // 60
        mins = total % 60
        if hours > 0:
            self.progress_bar.set_text(f"{hours}h {mins}m", "今日使用")
        else:
            self.progress_bar.set_text(f"{mins}m", "今日使用")

        # 清空旧列表
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 按时长降序排列
        sorted_apps = sorted(usage.items(), key=lambda x: x[1], reverse=True)

        for idx, (app_name, minutes) in enumerate(sorted_apps):
            if minutes <= 0:
                continue
            display_name = get_display_name(app_name)

            # 获取图标
            icon_pixmap = self._get_app_icon(app_name)

            item_widget = AppListItemWidget(
                app_name=app_name,
                display_name=display_name,
                minutes=minutes,
                total_minutes=total if total > 0 else 1,
                icon_pixmap=icon_pixmap
            )

            # 分隔线
            if idx > 0:
                separator = QFrame()
                separator.setFixedHeight(1)
                separator.setStyleSheet("background-color: rgba(84, 84, 88, 60); margin: 0 16px;")
                self.list_layout.addWidget(separator)

            self.list_layout.addWidget(item_widget)

        self.list_layout.addStretch()

    def _get_app_icon(self, app_name: str) -> QPixmap | None:
        """获取应用图标（带缓存）"""
        if app_name in self._icon_cache:
            return self._icon_cache[app_name]

        pixmap = None
        exe_path = get_exe_path(app_name)
        if exe_path:
            pixmap = extract_exe_icon(exe_path, 36)

        self._icon_cache[app_name] = pixmap
        return pixmap

    # ---- 事件回调 ----

    def _on_usage_updated(self, app_name: str, delta_minutes: int):
        """监控数据更新回调"""
        self._refresh_data()

    def _on_status_message(self, message: str):
        self.status_label.setText(message)

    # ---- 窗口拖动 ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ---- 关闭事件 ----

    def closeEvent(self, event):
        self.monitor_thread.stop()
        event.accept()


# ===========================================================================
# 开机自启管理
# ===========================================================================

class AutoStartManager:
    """Windows 开机自启管理（通过注册表）"""

    REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "ScreenTimeMonitor"

    @staticmethod
    def is_enabled() -> bool:
        if not winreg:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AutoStartManager.REGISTRY_KEY)
            winreg.QueryValueEx(key, AutoStartManager.APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def enable():
        if not winreg:
            return False
        try:
            exe_path = sys.executable
            script_path = os.path.abspath(__file__)
            if exe_path.endswith("python.exe"):
                value = f'"{exe_path}" "{script_path}"'
            else:
                value = f'"{exe_path}"'

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, AutoStartManager.REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, AutoStartManager.APP_NAME, 0, winreg.REG_SZ, value)
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    @staticmethod
    def disable():
        if not winreg:
            return False
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, AutoStartManager.REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, AutoStartManager.APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False


# ===========================================================================
# 主入口
# ===========================================================================

def main():
    app = QApplication(sys.argv)

    # 设置应用字体（SF Pro Display -> PingFang SC 回退）
    font = QFont()
    font.setFamilies(["SF Pro Display", "PingFang SC", "Microsoft YaHei UI", "Segoe UI"])
    font.setPointSize(10)
    app.setFont(font)

    # 初始化数据库
    db_manager = DatabaseManager(DB_PATH)

    # 创建主窗口
    window = MainWindow(db_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
