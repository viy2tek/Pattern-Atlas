"""Visual tokens and Qt stylesheet for the desktop interface."""

from __future__ import annotations

COLORS = {
    "window": "#f7f8fb",
    "surface": "#ffffff",
    "surface_subtle": "#fbfcff",
    "text": "#13213a",
    "muted": "#61708a",
    "border": "#e1e6ee",
    "border_strong": "#cfd7e3",
    "accent": "#2f73df",
    "accent_hover": "#2868d0",
    "accent_pressed": "#225bb9",
    "focus": "#8db6f8",
}


APP_STYLESHEET = f"""
QMainWindow, QWidget#centralWidget {{
    background: {COLORS['window']};
    color: {COLORS['text']};
    font-family: "Segoe UI";
    font-size: 14px;
}}

QFrame#surface {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}

QFrame#contentSurface {{
    background: {COLORS['surface']};
    border: 0;
    border-radius: 12px;
}}

QFrame#dragOverlay {{
    background: rgba(248, 250, 255, 248);
    border: 3px dashed {COLORS['accent']};
    border-radius: 12px;
}}

QLabel#dragOverlayTitle {{
    color: #173d79;
    background: transparent;
    font-size: 30px;
    font-weight: 700;
}}

QLabel#dragOverlayHint {{
    color: #36547d;
    background: transparent;
    font-size: 15px;
}}

QFrame#dropZone {{
    background: {COLORS['surface_subtle']};
    border: 1px dashed {COLORS['border_strong']};
    border-radius: 10px;
}}

QLabel#dropTitle {{
    color: {COLORS['text']};
    font-size: 17px;
    font-weight: 600;
}}

QLabel#dropHint, QLabel#mutedText, QLabel#statusLabel {{
    color: {COLORS['muted']};
}}

QLabel#sectionTitle {{
    color: {COLORS['text']};
    font-size: 15px;
    font-weight: 600;
}}

QLabel#fieldLabel {{
    color: {COLORS['text']};
    font-weight: 600;
}}

QLineEdit#pathInput {{
    background: transparent;
    border: 0;
    padding: 0 2px;
    color: {COLORS['muted']};
    selection-background-color: {COLORS['accent']};
}}

QFrame#pathFrame {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
}}

QPushButton, QToolButton {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
    color: {COLORS['text']};
    min-height: 38px;
    padding: 0 14px;
}}

QPushButton:hover, QToolButton:hover {{
    background: #f5f8fd;
    border-color: {COLORS['border_strong']};
}}

QPushButton:pressed, QToolButton:pressed {{
    background: #edf3fc;
}}

QPushButton:focus, QToolButton:focus, QLineEdit:focus {{
    border-color: {COLORS['focus']};
}}

QPushButton:disabled, QToolButton:disabled {{
    color: #a5afbf;
    background: #f4f6f9;
}}

QPushButton#primaryButton {{
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
    color: white;
    font-size: 15px;
    font-weight: 600;
}}

QPushButton#primaryButton:hover {{
    background: {COLORS['accent_hover']};
    border-color: {COLORS['accent_hover']};
}}

QPushButton#primaryButton:pressed {{
    background: {COLORS['accent_pressed']};
    border-color: {COLORS['accent_pressed']};
}}

QListWidget#resultList {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
    padding: 4px;
    outline: 0;
}}

QListWidget#resultList::item {{
    padding: 7px 9px;
    border-radius: 5px;
}}

QListWidget#resultList::item:selected {{
    background: #e9f1ff;
    color: {COLORS['text']};
}}
"""
