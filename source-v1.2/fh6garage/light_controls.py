"""Explicit colors for utility panels under Windows dark application palettes."""

LIGHT_CONTROLS_STYLE = """
QWidget { background: #f7f8fb; color: #171924; }
QScrollArea, QTabWidget::pane { background: #f7f8fb; border: 0; }
QGroupBox { background: #ffffff; border: 1px solid #dfe1e8;
    border-radius: 8px; margin-top: 16px; padding: 12px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #303341; }
QLabel, QCheckBox { background: transparent; color: #303341; }
QPushButton { background: #ffffff; color: #303341; border: 1px solid #dfe1e8;
    border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #f2efff; border-color: #9c8cf5; }
QPushButton:disabled { background: #eceef2; color: #777c8c; border-color: #dfe1e8; }
QComboBox, QSpinBox, QListWidget { background: #ffffff; color: #171924;
    border: 1px solid #dfe1e8; border-radius: 5px; padding: 5px; }
QComboBox QAbstractItemView { background: #ffffff; color: #171924;
    selection-background-color: #eee9ff; selection-color: #5f39d8; }
QTabBar { background: #f7f8fb; }
QTabBar::tab { background: #ffffff; color: #303341; border: 1px solid #dfe1e8;
    border-radius: 6px; padding: 7px 12px; margin-right: 4px; }
QTabBar::tab:selected { background: #eee9ff; color: #5f39d8; border-color: #9c8cf5; }
QCheckBox::indicator { width: 14px; height: 14px; background: #ffffff;
    border: 1px solid #969cad; border-radius: 3px; }
QCheckBox::indicator:checked { background: #6e4bf2; border-color: #6e4bf2; }
"""
