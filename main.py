# -*- coding: utf-8 -*-
"""
屏幕使用时间监控小工具 (iOS 风格 - 真毛玻璃)
===================================================
模仿 iOS "屏幕使用时间" 的 Windows 桌面应用。
后台自动监控所有活动窗口使用时长，以 iOS 风格毛玻璃卡片展示。

特性:
  - 自动识别电脑上所有应用（从 exe 文件属性提取真实名称）
  - 真正的磨砂毛玻璃效果（截屏模糊 + Windows Acrylic 双重保障）
  - 景深感：前景卡片与模糊背景之间有前后层次
  - 边缘内发光描边，模拟玻璃厚度
  - 蓝紫渐变强调色 (#5AC8FA → #AF52DE)
  - 进度条带柔光晕染
  - 列表项悬停 <10% 叠加层

依赖安装:
    pip install PyQt6 psutil pywin32

运行:
    python main.py
"""

import sys
import os
import time
import sqlite3
import ctypes
import datetime
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# 第三方库导入（带异常保护）
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QScrollArea, QFrame, QPushButton, QGraphicsBlurEffect,
        QGraphicsDropShadowEffect
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QRectF, QThread, pyqtSignal
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPixmap,
        QLinearGradient
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

# --- iOS 色彩体系 ---
# 基底色: 深色模式 #1C1C1E
COLOR_BASE_DARK = QColor(28, 28, 30)         # #1C1C1E
COLOR_BASE_LIGHT = QColor(242, 242, 247)     # #F2F2F7

# 叠加层（半透明材质，严禁纯色不透明）
COLOR_CARD_BG = QColor(255, 255, 255, 18)        # 卡片: 白色 7% 透明度
COLOR_CARD_HOVER = QColor(255, 255, 255, 12)     # 悬停: 白色 <5%
COLOR_LIST_ITEM_BG = QColor(255, 255, 255, 8)    # 列表项: 白色 3%
COLOR_LIST_ITEM_HOVER = QColor(255, 255, 255, 18) # 列表悬停: 白色 7%

# 强调色: 蓝紫渐变 #5AC8FA → #AF52DE
COLOR_ACCENT_START = QColor(90, 200, 250)    # #5AC8FA
COLOR_ACCENT_END = QColor(175, 82, 222)      # #AF52DE

# 文字
COLOR_TEXT = QColor(255, 255, 255, 255)
COLOR_TEXT_SECONDARY = QColor(152, 152, 157, 255)
COLOR_TEXT_TERTIARY = QColor(99, 99, 102, 255)

# 分隔线: 0.5px 极细，白色低透明度
COLOR_SEPARATOR = QColor(255, 255, 255, 20)

# 进度条背景
COLOR_PROGRESS_BG = QColor(255, 255, 255, 15)

# 窗口边缘内发光
COLOR_EDGE_GLOW = QColor(255, 255, 255, 25)

# 毛玻璃叠加色（深色模式）
COLOR_FROSTED_TINT = QColor(28, 28, 30, 200)

# 应用图标圆点配色池（iOS 系统色）
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

# --- 尺寸 ---
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 720
WINDOW_RADIUS = 22          # 主窗口大圆角
CARD_RADIUS = 16            # 卡片圆角
LIST_RADIUS = 12            # 列表圆角
ICON_RADIUS_RATIO = 0.22    # 图标圆角比例 (22%)
ICON_SIZE = 38              # 图标尺寸
LIST_ITEM_HEIGHT = 54       # 列表项高度 (52-56px)
LIST_PADDING = 20           # 列表左右内边距

# --- 配置 ---
TARGET_MINUTES = 8 * 60     # 目标时长 8 小时
MONITOR_INTERVAL = 2        # 监控间隔（秒）
IDLE_THRESHOLD = 300        # 闲置阈值（5 分钟）
BLUR_RADIUS = 45            # 毛玻璃模糊半径
BLUR_PADDING = 60           # 截屏扩展边距（防止模糊边缘透明）
BG_REFRESH_INTERVAL = 800   # 背景刷新间隔（毫秒）

DB_PATH = Path.home() / ".screentime" / "screentime.db"

# 桌面/锁屏窗口标题（不计入使用时间）
IDLE_TITLES = {"", "Windows 输入体验", "设置", "任务栏", "Program Manager",
               "MSCTFIME UI", "Default IME"}


# ===========================================================================
# 数据库管理
# ===========================================================================

class DatabaseManager:
    """SQLite 数据库管理器（线程安全）"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
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
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM usage_records WHERE date = ?", (date_str,))
            conn.commit()
            conn.close()


# ===========================================================================
# 工具函数
# ===========================================================================

def get_exe_product_name(exe_path: str) -> str | None:
    """从 exe 文件属性自动提取产品名称（ProductName / FileDescription）"""
    if not HAS_WIN32 or not exe_path or not os.path.exists(exe_path):
        return None
    try:
        # 获取翻译表
        trans = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")
        if not trans:
            return None
        lang, codepage = trans[0]
        key_prefix = f"\\StringFileInfo\\{lang:04X}{codepage:04X}"

        # 优先 ProductName
        for field in ("ProductName", "FileDescription", "InternalName"):
            try:
                value = win32api.GetFileVersionInfo(exe_path, f"{key_prefix}\\{field}")
                if value and value.strip():
                    name = value.strip()
                    # 过滤掉通用/无意义名称
                    if name.lower() not in ("", "n/a", "none", "unknown"):
                        return name
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_display_name(proc_name: str, exe_path: str = "") -> str:
    """
    获取应用显示名称（自动识别）:
    1. 先从 exe 文件属性提取 ProductName
    2. 回退到进程名（去掉 .exe 后缀）
    """
    # 尝试从 exe 属性提取真实名称
    if exe_path:
        product_name = get_exe_product_name(exe_path)
        if product_name:
            return product_name

    # 回退: 去掉 .exe 后缀，首字母大写
    name = proc_name
    for suffix in (".exe", ".EXE", ".Exe"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name.capitalize()


def get_icon_color(proc_name: str) -> QColor:
    """根据进程名生成稳定的图标颜色"""
    hash_val = sum(ord(c) for c in proc_name)
    return ICON_COLORS[hash_val % len(ICON_COLORS)]


def extract_exe_icon(exe_path: str, size: int = 38) -> QPixmap | None:
    """从 exe 提取图标，失败返回 None"""
    if not HAS_WIN32 or not exe_path or not os.path.exists(exe_path):
        return None
    try:
        import win32ui
        from PyQt6.QtGui import QImage

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
                QImage(
                    bmpstr, bmpinfo["bmWidth"], bmpinfo["bmHeight"],
                    QImage.Format.Format_ARGB32
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
        # 屏幕保护程序
        result = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(
            win32con.SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(result), 0
        )
        if result.value:
            return True

        # 锁屏进程
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and proc.info["name"].lower() in ("logonui.exe", "lockapp.exe"):
                return True

        # 最后输入时间
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


def get_wallpaper_path() -> str:
    """获取桌面壁纸路径"""
    try:
        buf = ctypes.create_unicode_buffer(260)
        SPI_GETDESKWALLPAPER = 0x73
        ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 260, buf, 0)
        return buf.value
    except Exception:
        return ""


# ===========================================================================
# 后台监控线程
# ===========================================================================

class MonitorThread(QThread):
    """后台窗口监控线程 - 自动识别所有活动应用"""

    usage_updated = pyqtSignal(str, int)
    status_message = pyqtSignal(str)

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self._running = True
        self._current_app = None
        self._accumulated_seconds = 0
        self._last_date = datetime.date.today().isoformat()

    def run(self):
        while self._running:
            try:
                today = datetime.date.today().isoformat()
                if today != self._last_date:
                    self._flush_current()
                    self._last_date = today

                if is_system_idle():
                    self._flush_current()
                    self.status_message.emit("系统闲置中")
                else:
                    app_name = self._get_foreground_app()
                    if app_name:
                        if app_name != self._current_app:
                            self._flush_current()
                            self._current_app = app_name
                            self._accumulated_seconds = 0
                        else:
                            self._accumulated_seconds += MONITOR_INTERVAL
                            if self._accumulated_seconds >= 60:
                                minutes = int(self._accumulated_seconds // 60)
                                self._accumulated_seconds -= minutes * 60
                                self.db_manager.upsert_usage(self._last_date, app_name, minutes)
                                self.usage_updated.emit(app_name, minutes)
                    else:
                        self._flush_current()

            except Exception as e:
                self.status_message.emit(f"监控异常: {e}")

            self.msleep(MONITOR_INTERVAL * 1000)

    def _get_foreground_app(self) -> str | None:
        """获取当前前台窗口的进程名（自动识别任意应用）"""
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
        self._running = False
        self._flush_current()
        self.wait()


# ===========================================================================
# 毛玻璃窗口基类
# ===========================================================================

class FrostedGlassWindow(QWidget):
    """
    真正的 iOS 风格磨砂毛玻璃窗口:
    - 截取窗口后方屏幕内容，应用高斯模糊
    - 叠加半透明深色 tint
    - 边缘 1px 内发光描边
    - 景深感: 前景内容浮于模糊背景之上
    """

    def __init__(self):
        super().__init__()
        self._drag_pos = None
        self._bg_label = None
        self._bg_timer = None

        self._init_window()
        self._init_frosted_background()

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

    def _init_frosted_background(self):
        """初始化毛玻璃背景层"""
        # 背景标签（承载模糊后的截屏）
        self._bg_label = QLabel(self)
        self._bg_label.setScaledContents(True)
        self._bg_label.setGeometry(
            -BLUR_PADDING, -BLUR_PADDING,
            WINDOW_WIDTH + BLUR_PADDING * 2,
            WINDOW_HEIGHT + BLUR_PADDING * 2
        )
        self._bg_label.lower()  # 置于最底层

        # 应用模糊效果
        blur_effect = QGraphicsBlurEffect(self._bg_label)
        blur_effect.setBlurRadius(BLUR_RADIUS)
        blur_effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self._bg_label.setGraphicsEffect(blur_effect)

        # 尝试启用 Windows 原生 Acrylic（双重保障）
        self._enable_native_acrylic()

        # 加载壁纸作为初始/回退背景
        self._load_wallpaper_background()

        # 定时刷新截屏背景
        self._bg_timer = QTimer(self)
        self._bg_timer.timeout.connect(self._capture_screen_background)
        self._bg_timer.start(BG_REFRESH_INTERVAL)

        # 首次延迟捕获（等窗口显示后）
        QTimer.singleShot(200, self._capture_screen_background)

    def _enable_native_acrylic(self):
        """启用 Windows 10/11 原生 Acrylic 模糊"""
        if not HAS_WIN32:
            return
        try:
            hwnd = int(self.winId())

            # --- Windows 11: DWM Acrylic ---
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(ctypes.c_int(2)),  # 2 = Acrylic
                ctypes.sizeof(ctypes.c_int)
            )
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int)
            )
            margins = ctypes.c_int(-1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

        # --- Windows 10: SetWindowCompositionAttribute ---
        try:
            class ACCENTPOLICY(ctypes.Structure):
                _fields_ = [
                    ("AccentState", ctypes.c_uint),
                    ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_uint)
                ]

            class WINCOMPATTRDATA(ctypes.Structure):
                _fields_ = [
                    ("Attribute", ctypes.c_int),
                    ("Data", ctypes.POINTER(ACCENTPOLICY)),
                    ("SizeOfData", ctypes.c_uint)
                ]

            accent = ACCENTPOLICY()
            accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags = 0
            accent.GradientColor = 0xC81C1C1E  # ABGR: alpha=200, RGB=#1C1C1E
            accent.AnimationId = 0

            data = WINCOMPATTRDATA()
            data.Attribute = 19  # WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)

            ctypes.windll.user32.SetWindowCompositionAttribute(
                int(self.winId()), ctypes.byref(data)
            )
        except Exception:
            pass

    def _load_wallpaper_background(self):
        """加载桌面壁纸作为模糊背景（回退方案）"""
        wallpaper = get_wallpaper_path()
        if wallpaper and os.path.exists(wallpaper):
            pixmap = QPixmap(wallpaper)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    WINDOW_WIDTH + BLUR_PADDING * 2,
                    WINDOW_HEIGHT + BLUR_PADDING * 2,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._bg_label.setPixmap(pixmap)

    def _capture_screen_background(self):
        """截取窗口后方屏幕内容并更新模糊背景"""
        if not self.isVisible():
            return
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                return
            geo = self.geometry()
            if geo.width() <= 0 or geo.height() <= 0:
                return

            # 截取比窗口更大的区域（为模糊留余量）
            x = max(0, geo.x() - BLUR_PADDING)
            y = max(0, geo.y() - BLUR_PADDING)
            w = geo.width() + BLUR_PADDING * 2
            h = geo.height() + BLUR_PADDING * 2

            pixmap = screen.grabWindow(0, x, y, w, h)
            if not pixmap.isNull():
                self._bg_label.setPixmap(pixmap)
        except Exception:
            pass

    def paintEvent(self, event):
        """绘制毛玻璃 tint 叠加层 + 边缘内发光"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 裁剪到圆角区域
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, self.width(), self.height()),
            WINDOW_RADIUS, WINDOW_RADIUS
        )
        painter.setClipPath(path)

        # 半透明深色 tint（让模糊背景呈现磨砂深色质感）
        painter.fillRect(self.rect(), COLOR_FROSTED_TINT)

        # 取消裁剪，绘制边缘内发光
        painter.setClipping(False)
        glow_pen = QPen(COLOR_EDGE_GLOW, 1)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
            WINDOW_RADIUS, WINDOW_RADIUS
        )

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

    def moveEvent(self, event):
        """窗口移动时立即刷新背景"""
        super().moveEvent(event)
        QTimer.singleShot(50, self._capture_screen_background)


# ===========================================================================
# UI 组件
# ===========================================================================

class CircularProgressBar(QWidget):
    """iOS 风格环形进度条（带柔光晕染）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._text = ""
        self._sub_text = ""
        self.setFixedSize(170, 170)

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

        rect = QRectF(15, 15, self.width() - 30, self.height() - 30)
        pen_width = 10

        # 背景圆环
        bg_pen = QPen(COLOR_PROGRESS_BG, pen_width)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._progress > 0:
            start_angle = 90 * 16
            span_angle = int(-self._progress * 360 * 16)

            # --- 柔光晕染层（多层半透明弧模拟发光）---
            for i in range(4):
                glow_alpha = 35 - i * 8
                glow_width = pen_width + (i + 1) * 4
                glow_pen = QPen(QColor(90, 200, 250, glow_alpha), glow_width)
                glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(glow_pen)
                painter.drawArc(rect, start_angle, span_angle)

            # --- 主进度弧（蓝紫渐变）---
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, COLOR_ACCENT_START)
            gradient.setColorAt(1, COLOR_ACCENT_END)
            fg_pen = QPen(QBrush(gradient), pen_width)
            fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(fg_pen)
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
            sub_rect = QRectF(rect.x(), rect.y() + 55, rect.width(), rect.height())
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, self._sub_text)


class MiniProgressBar(QWidget):
    """极细进度条（自定义绘制，百分比自适应）"""

    def __init__(self, percentage: float, color: QColor, parent=None):
        super().__init__(parent)
        self._pct = max(0.0, min(100.0, percentage))
        self._color = color
        self.setFixedHeight(3)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # 背景
        painter.setBrush(COLOR_PROGRESS_BG)
        painter.drawRoundedRect(self.rect(), 1.5, 1.5)

        # 填充
        if self._pct > 0:
            fill_w = self.width() * self._pct / 100.0
            fill_rect = QRectF(0, 0, fill_w, self.height())
            painter.setBrush(self._color)
            painter.drawRoundedRect(fill_rect, 1.5, 1.5)


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
        self.setFixedHeight(LIST_ITEM_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(LIST_PADDING, 8, LIST_PADDING, 8)
        layout.setSpacing(14)

        # 左侧图标（圆角矩形底座，22% 圆角）
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon_radius = ICON_SIZE * ICON_RADIUS_RATIO

        if self._icon_pixmap and not self._icon_pixmap.isNull():
            # 真实 exe 图标 → 裁剪为圆角矩形
            pixmap = self._icon_pixmap.scaled(
                ICON_SIZE, ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # 创建圆角遮罩
            rounded = QPixmap(ICON_SIZE, ICON_SIZE)
            rounded.fill(Qt.GlobalColor.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(0, 0, ICON_SIZE, ICON_SIZE), icon_radius, icon_radius)
            p.setClipPath(clip_path)
            p.drawPixmap(0, 0, pixmap)
            p.end()
            self.icon_label.setPixmap(rounded)
        else:
            # 首字母彩色圆角矩形
            color = get_icon_color(self._app_name)
            pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, ICON_SIZE, ICON_SIZE, icon_radius, icon_radius)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("SF Pro Display", 15, QFont.Weight.Bold))
            letter = self._display_name[0].upper() if self._display_name else "?"
            painter.drawText(QRectF(0, 0, ICON_SIZE, ICON_SIZE), Qt.AlignmentFlag.AlignCenter, letter)
            painter.end()
            self.icon_label.setPixmap(pixmap)

        layout.addWidget(self.icon_label)

        # 中间: 名称 + 进度条
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(5)

        name_label = QLabel(self._display_name)
        name_label.setStyleSheet("color: rgb(255, 255, 255); font-size: 14px; font-weight: 500; background: transparent;")
        name_label.setFont(QFont("SF Pro Display", 11, QFont.Weight.Medium))
        center_layout.addWidget(name_label)

        pct = (self._minutes / self._total_minutes * 100) if self._total_minutes > 0 else 0
        progress = MiniProgressBar(pct, get_icon_color(self._app_name))
        center_layout.addWidget(progress)

        layout.addWidget(center, 1)

        # 右侧时长（等宽字体确保对齐）
        time_label = QLabel(format_duration(self._minutes))
        time_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 13px; background: transparent;")
        time_label.setFont(QFont("SF Mono", 10))
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(time_label)

    def enterEvent(self, event):
        self._hovered = True
        # <10% 白色叠加层，无边框变色
        self.setStyleSheet("background-color: rgba(255, 255, 255, 18);")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.setStyleSheet("background-color: rgba(255, 255, 255, 8);")
        super().leaveEvent(event)


class MainWindow(FrostedGlassWindow):
    """主窗口 - iOS 风格屏幕使用时间"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.monitor_thread = MonitorThread(db_manager)
        self._icon_cache = {}
        self._name_cache = {}

        super().__init__()

        self._init_ui()
        self._init_monitor()
        self._refresh_data()

    # ---- UI 构建 ----

    def _init_ui(self):
        # 内容容器（浮于模糊背景之上，营造景深）
        self.container = QFrame(self)
        self.container.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.container.setStyleSheet(f"""
            QFrame#container {{
                background-color: transparent;
                border-radius: {WINDOW_RADIUS}px;
            }}
        """)
        self.container.setObjectName("container")

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部导航
        main_layout.addWidget(self._build_nav_bar())

        # 今日概览卡片
        main_layout.addWidget(self._build_overview_card())

        # 分隔标题
        section_label = QLabel("最常使用")
        section_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 13px; font-weight: 600; background: transparent;")
        section_label.setFont(QFont("SF Pro Display", 10, QFont.Weight.DemiBold))
        section_label.setContentsMargins(LIST_PADDING, 16, LIST_PADDING, 8)
        main_layout.addWidget(section_label)

        # 应用列表容器（圆角卡片）
        list_card = QFrame()
        list_card.setStyleSheet(f"""
            QFrame#listCard {{
                background-color: rgba(255, 255, 255, 8);
                border-radius: {LIST_RADIUS}px;
                margin: 0 {LIST_PADDING}px;
            }}
        """)
        list_card.setObjectName("listCard")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 4px; margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(120, 120, 128, 80); border-radius: 2px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch()
        self.scroll_area.setWidget(self.list_container)
        list_layout.addWidget(self.scroll_area)

        main_layout.addWidget(list_card, 1)

        # 底部状态栏
        self.status_label = QLabel("监控中...")
        self.status_label.setStyleSheet("color: rgb(99, 99, 102); font-size: 11px; background: transparent;")
        self.status_label.setFont(QFont("SF Pro Display", 9))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setContentsMargins(0, 8, 0, 16)
        main_layout.addWidget(self.status_label)

    def _build_nav_bar(self) -> QWidget:
        nav = QWidget()
        nav.setFixedHeight(52)
        nav.setStyleSheet("background: transparent;")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(LIST_PADDING, 10, LIST_PADDING, 4)

        left_spacer = QWidget()
        left_spacer.setFixedWidth(30)
        nav_layout.addWidget(left_spacer)

        title = QLabel("屏幕使用时间")
        title.setStyleSheet("color: rgb(255, 255, 255); font-size: 17px; font-weight: 600; background: transparent;")
        title.setFont(QFont("SF Pro Display", 13, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(title, 1)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setStyleSheet("""
            QPushButton {
                color: rgb(90, 200, 250); font-size: 20px; border: none; background: transparent;
            }
            QPushButton:hover { color: rgb(120, 220, 255); }
        """)
        refresh_btn.setFont(QFont("SF Pro Display", 14))
        refresh_btn.clicked.connect(self._refresh_data)
        nav_layout.addWidget(refresh_btn)

        return nav

    def _build_overview_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("overviewCard")
        card.setStyleSheet(f"""
            QFrame#overviewCard {{
                background-color: rgba(255, 255, 255, 18);
                border-radius: {CARD_RADIUS}px;
                margin: 4px {LIST_PADDING}px 0 {LIST_PADDING}px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(6)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = CircularProgressBar()
        card_layout.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignCenter)

        self.total_time_label = QLabel("0分钟")
        self.total_time_label.setStyleSheet("color: rgb(255, 255, 255); font-size: 28px; font-weight: 700; background: transparent;")
        self.total_time_label.setFont(QFont("SF Pro Display", 18, QFont.Weight.Bold))
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.total_time_label)

        self.goal_label = QLabel(f"目标 {TARGET_MINUTES // 60} 小时")
        self.goal_label.setStyleSheet("color: rgb(152, 152, 157); font-size: 12px; background: transparent;")
        self.goal_label.setFont(QFont("SF Pro Display", 9))
        self.goal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.goal_label)

        return card

    # ---- 监控初始化 ----

    def _init_monitor(self):
        self.monitor_thread.usage_updated.connect(lambda *_: self._refresh_data())
        self.monitor_thread.status_message.connect(self.status_label.setText)
        self.monitor_thread.start()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(30000)

    # ---- 数据刷新 ----

    def _refresh_data(self):
        today = datetime.date.today().isoformat()
        usage = self.db_manager.get_today_usage(today)
        self._render_usage(usage)

    def _render_usage(self, usage: dict):
        total = sum(usage.values())

        # 概览
        progress = total / TARGET_MINUTES if TARGET_MINUTES > 0 else 0
        self.progress_bar.set_progress(progress)

        hours = total // 60
        mins = total % 60
        if hours > 0:
            self.progress_bar.set_text(f"{hours}h {mins}m", "今日使用")
        else:
            self.progress_bar.set_text(f"{mins}m", "今日使用")
        self.total_time_label.setText(format_duration(total))

        # 清空旧列表
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sorted_apps = sorted(usage.items(), key=lambda x: x[1], reverse=True)

        for idx, (app_name, minutes) in enumerate(sorted_apps):
            if minutes <= 0:
                continue

            # 获取 exe 路径（用于图标和名称提取）
            exe_path = get_exe_path(app_name)

            # 自动识别应用名
            display_name = self._get_display_name(app_name, exe_path)

            # 获取图标
            icon_pixmap = self._get_app_icon(app_name, exe_path)

            item_widget = AppListItemWidget(
                app_name=app_name,
                display_name=display_name,
                minutes=minutes,
                total_minutes=total if total > 0 else 1,
                icon_pixmap=icon_pixmap
            )
            item_widget.setStyleSheet("background-color: rgba(255, 255, 255, 8);")

            # 0.5px 极细分隔线（左缩进从文字处开始，图标下方不画线）
            if idx > 0:
                separator = QFrame()
                separator.setFixedHeight(1)
                # 左缩进: padding(20) + icon(38) + spacing(14) = 72px
                separator.setStyleSheet(
                    f"background-color: rgba(255, 255, 255, 20); "
                    f"margin-left: {LIST_PADDING + ICON_SIZE + 14}px; "
                    f"margin-right: {LIST_PADDING}px;"
                )
                self.list_layout.addWidget(separator)

            self.list_layout.addWidget(item_widget)

        self.list_layout.addStretch()

    def _get_display_name(self, app_name: str, exe_path: str) -> str:
        """获取应用显示名（带缓存）"""
        cache_key = f"{app_name}:{exe_path}"
        if cache_key in self._name_cache:
            return self._name_cache[cache_key]

        name = get_display_name(app_name, exe_path)
        self._name_cache[cache_key] = name
        return name

    def _get_app_icon(self, app_name: str, exe_path: str) -> QPixmap | None:
        """获取应用图标（带缓存）"""
        if app_name in self._icon_cache:
            return self._icon_cache[app_name]

        pixmap = None
        if exe_path:
            pixmap = extract_exe_icon(exe_path, ICON_SIZE)

        self._icon_cache[app_name] = pixmap
        return pixmap

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

    # 字体: SF Pro Display → PingFang SC → Microsoft YaHei UI 回退
    font = QFont()
    font.setFamilies(["SF Pro Display", "PingFang SC", "Microsoft YaHei UI", "Segoe UI"])
    font.setPointSize(10)
    app.setFont(font)

    db_manager = DatabaseManager(DB_PATH)
    window = MainWindow(db_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
