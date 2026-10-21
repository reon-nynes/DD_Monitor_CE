"""本机合成 FLV + libmpv：追帧消化积压，随后恢复正常速度；不访问真实直播。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault("DDM_NO_SAVE", "1")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from ddm.player import EMBEDDED_OPTIONS, TilePlayer
import mpv


def pump(seconds):
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def main():
    ffmpeg = shutil.which("ffmpeg") or str(REPO / "utils/ffmpeg.exe")
    with tempfile.TemporaryDirectory(prefix="ddm-catchup-") as directory:
        source = Path(directory) / "synthetic.flv"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=160x90:rate=25", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000", "-t", "40",
                        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                        "-g", "25", "-c:a", "aac", "-output_ts_offset", "3600",
                        "-f", "flv", str(source)],
                       check=True, timeout=30, stdout=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        data = source.read_bytes()
    tags = []
    offset = 13  # FLV header + first PreviousTagSize
    while offset < len(data):
        size = int.from_bytes(data[offset + 1:offset + 4], "big")
        timestamp = int.from_bytes(data[offset + 4:offset + 7], "big")
        timestamp += data[offset + 7] << 24
        end = offset + 11 + size + 4
        tags.append((timestamp / 1000, data[offset:end]))
        offset = end
    closing = threading.Event()

    class Stream(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/x-flv")
            self.end_headers()
            self.wfile.write(data[:13])
            started = time.monotonic()
            try:
                for timestamp, tag in tags:
                    # 先给 4 秒积压，随后按真实时间提供数据；连接保持到测试结束。
                    if closing.wait(max(0, timestamp - 3600 - 4 - (time.monotonic() - started))):
                        return
                    self.wfile.write(tag)
                    self.wfile.flush()
                closing.wait(30)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stream)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    player = TilePlayer(widget)
    try:
        # 真正的解复用、时间戳和 speed 属性；无原生窗口、无音频输出。
        player.player = mpv.MPV(vo="null", ao="null", cache=True,
                                demuxer_max_bytes="16MiB", demuxer_max_back_bytes=0,
                                **EMBEDDED_OPTIONS)
        with patch.object(player, "bind"):
            player.play(f"http://127.0.0.1:{server.server_port}/live.flv", "app")
        deadline = time.monotonic() + 30
        accelerated = False
        initial_buffer = None
        while time.monotonic() < deadline:
            pump(0.1)
            speed = player._prop("speed", 1)
            cache = player._prop("demuxer-cache-state", {})
            position = player._prop("time-pos")
            end = cache.get("cache-end")
            if position is None or end is None:
                continue
            buffered = end - position
            if speed > 1:
                accelerated = True
                if initial_buffer is None:
                    initial_buffer = buffered
            elif (accelerated and 0 < buffered <= 1.5 and player.state == "playing"
                  and not player._prop("paused-for-cache", False)):
                assert position > 3, "播放时间必须实际前进"
                print(f"libmpv catchup: PASS, buffer {initial_buffer:.2f}s -> "
                      f"{buffered:.2f}s, speed={speed}, pts={position:.2f}", flush=True)
                player.stop()
                assert player._prop("speed") == 1
                return
        raise AssertionError(f"未完成自动追帧：accelerated={accelerated}, "
                             f"state={player.state}, pts={position}, cache={cache}")
    finally:
        closing.set()
        player.release()
        widget.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        app.processEvents()


if __name__ == "__main__":
    main()
