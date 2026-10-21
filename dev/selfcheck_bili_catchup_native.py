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

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

from ddm import bili
from ddm.player import TilePlayer


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
            audio_only = self.path == '/audio.flv'
            self.send_response(200)
            self.send_header("Content-Type", "video/x-flv")
            self.end_headers()
            header = bytearray(data[:13])
            if audio_only:
                header[4] = 4
            self.wfile.write(header)
            started = time.monotonic()
            try:
                for timestamp, tag in tags:
                    if audio_only and tag[0] != 8:
                        continue
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
    surface = QFrame(widget)
    surface.setAttribute(Qt.WA_NativeWindow)
    QVBoxLayout(widget).addWidget(surface)
    widget.resize(640, 400)
    widget.show()
    player = TilePlayer(surface)
    player.set_muted(True)
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        # 拒绝真实仅音频 FLV，保留备用视频通道的请求头；不调用真实 API。
        with patch.object(bili, '_app_play_urls',
                          new=lambda room, qn, codec: ([base + '/audio.flv'], 250)), \
                patch.object(bili, '_web_play_urls',
                             new=lambda room, qn, codec: ([base + '/live.flv'], 250)), \
                patch.object(bili, '_app_hls_play_urls',
                             new=lambda room, qn, codec: ([], 0)):
            url, quality, profile, headers = bili.play_url('1001', 250)
        assert url == base + '/live.flv' and profile == 'web'
        player.play(url, profile, headers)
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
                params = player._prop('video-params', {})
                assert (params.get('w'), params.get('h')) == (160, 90), "必须有真实解码视频"
                assert player._prop('estimated-frame-number', 0) > 50
                raw = player.player.command('screenshot-raw', 'window')
                assert raw['format'] == 'bgr0'
                image = QImage(raw['data'], raw['w'], raw['h'], raw['stride'],
                               QImage.Format_RGB32).copy()
                colors = {image.pixel(x, y) for y in range(0, image.height(), 10)
                          for x in range(0, image.width(), 10)}
                assert len(colors) > 10, "D3D11 窗口必须实际显示合成画面，不能只有声音/占位背景"
                print(f"libmpv catchup: PASS, buffer {initial_buffer:.2f}s -> "
                      f"{buffered:.2f}s, speed={speed}, pts={position:.2f}, "
                      f"video={params['w']}x{params['h']}, colors={len(colors)}", flush=True)
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
