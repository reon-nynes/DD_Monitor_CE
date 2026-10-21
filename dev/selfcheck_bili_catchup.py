"""B 站追帧离线回归：使用合成属性和 Qt 定时器，不打开媒体或读取账号。"""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DDM_NO_SAVE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from ddm.bili import BILI_PROFILES
from ddm.player import TilePlayer


class BilibiliCatchupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = QWidget()
        self.player = TilePlayer(self.widget)
        self.commands = []
        self.core = SimpleNamespace(
            speed=1.0, time_pos=10.0, video_params={"w": 1920, "h": 1080},
            demuxer_cache_state={"cache-end": 14.0},
            vo_configured=True, paused_for_cache=False, seeking=False,
            eof_reached=False, idle_active=False,
            command=lambda *args: self.commands.append(args), terminate=lambda: None,
        )
        self.player.player = self.core
        self.binding = patch.object(self.player, "bind")
        self.binding.start()

    def tearDown(self):
        self.player.release()
        self.binding.stop()
        self.widget.close()
        self.widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def play(self, profile="app", url="https://cdn.example.test/live.flv"):
        self.player.play(url, profile)
        self.player._check()

    def tick(self, buffered):
        self.core.demuxer_cache_state = {"cache-end": self.core.time_pos + buffered}
        self.player._catchup_watch.timeout.emit()

    def test_timer_catches_up_without_seeking_or_reloading(self):
        self.play()
        loop = QEventLoop()
        QTimer.singleShot(650, loop.quit)
        loop.exec()
        self.assertEqual(self.core.speed, 1.3, "积压 4 秒时应自动加速至 1.3 倍")
        self.assertEqual([c for c in self.commands if c[0] != "stop"],
                         [("loadfile", "https://cdn.example.test/live.flv", "replace")])

    def test_audio_clock_and_placeholder_window_do_not_enable_catchup(self):
        self.play()
        self.core.video_params = None
        self.tick(8)
        self.assertEqual(self.core.speed, 1.0, "音频前进和占位窗口不能代替真实视频帧")

    def test_audio_only_stream_is_not_reported_as_video_playback(self):
        self.core.video_params = None
        self.play()
        for _ in range(6):
            self.core.time_pos += 1
            self.player._check()
        self.assertEqual(self.player.state, "error", "有声无画面也必须进入原有重连流程")
        self.assertIsNone(self.player._picture_signature())


    def test_speed_tiers_and_recovery_follow_forward_buffer(self):
        self.play()
        for buffered, expected in ((4.0, 1.3), (3.5, 1.2), (2.6, 1.2),
                                   (2.5, 1.1), (1.6, 1.1), (1.5, 1.0),
                                   (0.1, 1.0), (0.0, 1.0)):
            with self.subTest(buffered=buffered):
                self.tick(buffered)
                self.assertEqual(self.core.speed, expected)

    def test_each_bilibili_codec_profile_is_supported(self):
        for profile in BILI_PROFILES:
            with self.subTest(profile=profile):
                self.play(profile)
                self.tick(4)
                self.assertEqual(self.core.speed, 1.3)

    def test_other_platforms_and_local_media_keep_their_speed(self):
        for profile, url in ((p, "https://cdn.example.test/live.m3u8") for p in
                             ("huya", "douyu", "douyin", "custom", "web-plugin")):
            with self.subTest(profile=profile):
                self.play(profile, url)
                self.core.speed = 0.9
                self.tick(8)
                self.assertEqual(self.core.speed, 0.9)
                self.assertFalse(self.player._catchup_watch.isActive())
        self.play("web", "sample.flv")
        self.tick(8)
        self.assertEqual(self.core.speed, 0.9)

    def test_preview_does_not_adjust_speed(self):
        self.player.silent = True
        self.play()
        self.tick(8)
        self.assertEqual(self.core.speed, 1.0)
        self.assertFalse(self.player._catchup_watch.isActive())

    def test_pause_resets_speed_and_resume_can_catch_up(self):
        self.play()
        self.tick(4)
        self.player.set_paused(True)
        self.assertEqual(self.core.speed, 1.0)
        self.tick(8)
        self.assertTrue(self.core.pause, "追帧不能擅自解除用户暂停")
        self.assertEqual(self.core.speed, 1.0)
        self.player.set_paused(False)
        self.tick(4)
        self.assertEqual(self.core.speed, 1.3)

    def test_buffering_seeking_and_end_restore_normal_speed(self):
        self.play()
        for flag in ("paused_for_cache", "seeking", "eof_reached", "idle_active"):
            with self.subTest(flag=flag):
                self.tick(4)
                setattr(self.core, flag, True)
                self.tick(4)
                self.assertEqual(self.core.speed, 1.0)
                setattr(self.core, flag, False)
        self.tick(4)
        self.core.vo_configured = False
        self.tick(4)
        self.assertEqual(self.core.speed, 1.0)

    def test_connecting_frozen_and_error_states_do_not_accelerate(self):
        self.play()
        for state in ("connecting", "frozen", "buffering", "error"):
            with self.subTest(state=state):
                self.player._set_state("playing")
                self.tick(4)
                self.player._set_state(state)
                self.tick(4)
                self.assertEqual(self.core.speed, 1.0)

    def test_speed_write_failure_is_retried_on_next_tick(self):
        self.play()
        original = self.player._set
        with patch.object(self.player, "_set", side_effect=RuntimeError("media switching")):
            self.tick(4)
        self.assertEqual(self.core.speed, 1.0)
        self.tick(4)
        self.assertEqual(self.core.speed, 1.3)
        with patch.object(self.player, "_set", wraps=original) as writes:
            self.tick(4)
            self.assertEqual(writes.call_count, 0, "速率不变时不重复写入内核")

    def test_missing_invalid_or_discontinuous_timestamps_reset_speed(self):
        self.play()
        for position, cache in ((10, {}), (None, {"cache-end": 20}),
                                (10, None), (10, {"cache-end": None}),
                                (10, {"cache-end": 8}), (float("nan"), {"cache-end": 20}),
                                (10, {"cache-end": float("inf")}),
                                ("bad", {"cache-end": 20}), (True, {"cache-end": 20}),
                                (10, [])):
            with self.subTest(position=position, cache=cache):
                self.core.time_pos = 10
                self.tick(4)
                self.core.time_pos, self.core.demuxer_cache_state = position, cache
                self.player._catchup_watch.timeout.emit()
                self.assertEqual(self.core.speed, 1.0)

    def test_stop_and_channel_switch_do_not_leak_speed(self):
        self.play()
        self.tick(4)
        self.player.stop()
        self.assertEqual(self.core.speed, 1.0)
        self.assertFalse(self.player._catchup_watch.isActive())
        self.play()
        self.tick(4)
        self.play("douyu")
        self.assertEqual(self.core.speed, 1.0)
        self.assertFalse(self.player._catchup_watch.isActive())

    def test_release_stops_timer_and_queued_callback_is_harmless(self):
        self.play()
        self.tick(4)
        self.player.release()
        self.assertEqual(self.core.speed, 1.0)
        self.assertFalse(self.player._catchup_watch.isActive())
        commands = list(self.commands)
        self.player._check_live_catchup()
        self.assertEqual(self.commands, commands)


if __name__ == "__main__":
    unittest.main()
