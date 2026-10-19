"""无控制台启动也要保存 Qt 警告与致命错误现场。"""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DDM_NO_SAVE"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QtMsgType, qInstallMessageHandler, qWarning  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from ddm import app as app_module  # noqa: E402
from ddm.dialogs import SettingsDialog  # noqa: E402


def main():
    app = QApplication.instance() or QApplication([])
    original_stderr = sys.stderr
    installed = []
    window = dialog = None
    handle = None
    def install(handler):
        installed.append(handler)
        return qInstallMessageHandler(handler)
    with tempfile.TemporaryDirectory() as directory:
        try:
            sys.stderr = None  # pythonw.exe 的运行环境
            previous = qInstallMessageHandler(None)
            with patch.object(app_module.config_module, "REPO", directory), \
                    patch.object(app_module, "qInstallMessageHandler", side_effect=install):
                path = app_module.setup_file_log()
            qWarning("quality switch diagnostic")
            with patch.object(app_module.faulthandler, "dump_traceback") as dump:
                installed[0](QtMsgType.QtFatalMsg, None, "fatal quality switch diagnostic")
                dump.assert_called_once()
                assert dump.call_args.kwargs["all_threads"]
                handle = dump.call_args.kwargs["file"]
            contents = Path(path).read_text(encoding="utf-8")
            assert "[Qt QtWarningMsg] quality switch diagnostic" in contents
            assert "[Qt QtFatalMsg] fatal quality switch diagnostic" in contents
            assert '[窗口几何诊断]' not in contents, 'ordinary warnings must not add stacks'
            def resize_geometry_probe():
                qWarning('QWindowsWindow::setGeometry: Unable to set geometry synthetic')
            resize_geometry_probe()
            contents = Path(path).read_text(encoding="utf-8")
            assert '[窗口几何诊断]' in contents, 'geometry warnings need their Python calling path'
            assert 'in resize_geometry_probe' in contents, 'log must identify the triggering operation'
            with patch.object(app_module.QTimer, 'singleShot'), \
                    patch.object(app_module.MainWindow, 'refresh_account'), \
                    patch.object(app_module.MainWindow, 'sync_danmaku'):
                window = app_module.MainWindow([], [], state={
                    'plugins_enabled': [], 'settings': {'auto_update': False}})
            dialog = SettingsDialog({}, {}, window, preview=True)
            window.show(); dialog.show(); app.processEvents()
            for widget, name in ((window, 'DDMMainWindow'), (dialog, 'DDMSettingsDialog')):
                native_name = widget.windowHandle().objectName()
                qWarning(f'QWindowsWindow::setGeometry: Unable to set geometry on QWidgetWindow/"{native_name}"')
                contents = Path(path).read_text(encoding="utf-8")
                assert name in contents, f'native warning cannot identify {name}: {native_name}'
        finally:
            if dialog is not None:
                dialog.close()
            if window is not None:
                window.close()
            app.processEvents()
            qInstallMessageHandler(previous)
            sys.stderr = original_stderr
            if handle is not None:
                handle.close()
    print("PASS: console-free Qt logs, targeted geometry calling paths and named native windows")


if __name__ == "__main__":
    main()
