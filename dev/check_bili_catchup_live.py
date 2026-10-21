"""公开直播只读验收：有视频解码、帧推进与 D3D11 画面，不读取账号或发送弹幕。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DDM_NO_SAVE', '1')

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget
from ddm import bili
from ddm.player import TilePlayer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('room', help='显式指定正在直播的公开 B 站房间号')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    assert args.room.isdigit() and args.timeout > 0
    assert not any(bili._cookies().values()), '验收不使用登录信息'
    url, quality, profile, headers = bili.play_url(args.room, 250)
    app = QApplication([])
    window = QWidget()
    surface = QFrame(window)
    surface.setAttribute(Qt.WA_NativeWindow)
    QVBoxLayout(window).addWidget(surface)
    window.resize(640, 400)
    window.show()
    player = TilePlayer(surface)
    player.set_muted(True)
    try:
        player.play(url, profile, headers)
        previous_frame = None
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(1000, loop.quit)
            loop.exec()
            params = player._prop('video-params')
            frame = player._prop('estimated-frame-number')
            if (params and frame is not None and previous_frame is not None
                    and frame > previous_frame and player.state == 'playing'):
                raw = player.player.command('screenshot-raw', 'window')
                assert raw['format'] == 'bgr0'
                image = QImage(raw['data'], raw['w'], raw['h'], raw['stride'],
                               QImage.Format_RGB32).copy()
                colors = {image.pixel(x, y) for y in range(0, image.height(), 10)
                          for x in range(0, image.width(), 10)}
                assert len(colors) > 4, '窗口没有可辨识的视频画面'
                output = ROOT / 'work' / f'bili-catchup-live-{args.room}'
                output.parent.mkdir(parents=True, exist_ok=True)
                assert image.save(str(output.with_suffix('.png')))
                result = dict(room=args.room, profile=profile, quality=quality,
                              decoder=player.actual_decoder, codec=player.actual_codec,
                              width=params['w'], height=params['h'],
                              first_frame=previous_frame, last_frame=frame,
                              colors=len(colors), speed=player._prop('speed'))
                output.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                print('PASS', json.dumps(result), flush=True)
                return
            previous_frame = frame
        raise AssertionError(f'未观察到真实视频画面：state={player.state}, profile={profile}')
    finally:
        player.release()
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
