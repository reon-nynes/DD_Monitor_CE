"""Public tile extensions: attachment, isolation, layout and disposal."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('DDM_NO_SAVE', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QLineEdit
from ddm import plugins as api
from ddm.widgets import Tile

APP = QApplication.instance() or QApplication([])


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.manager = api.PluginManager()
        self.tiles = []
        self.controls = []

    def tearDown(self):
        self.manager.unload()
        for tile in self.tiles:
            tile.close()
            tile.deleteLater()
        APP.processEvents()

    def tile(self, room=None):
        tile = Tile(room or {})
        self.tiles.append(tile)
        tile.show()
        self.manager.attach_tile(tile)
        return tile

    def register(self, owner='demo', priority=0, broken=False):
        controls = self.controls
        class Control(api.TileControl):
            def __init__(self, ctx):
                super().__init__(QLineEdit(ctx.parent), minimum_width=90)
                self.ctx, self.rooms, self.stops = ctx, [], 0
                controls.append(self)
            def set_room(self, room):
                self.rooms.append(dict(room))
                room['mutated'] = True
                self.widget.setVisible(str(room.get('room_id', '')).isdigit())
                if broken:
                    raise ValueError('test update failure')
            def shutdown(self):
                self.stops += 1
        self.manager.register_tile_control(owner, 'edit', Control, priority=priority)

    def test_existing_new_and_initially_empty_tiles_receive_one_control(self):
        first = self.tile()
        self.register()
        self.manager.attach_tile(first)
        second = self.tile({'room_id': '12'})
        self.assertEqual(len(self.controls), 2)
        first.set_room({'room_id': '11'})
        self.assertEqual(self.controls[0].rooms, [{}, {'room_id': '11'}])
        self.assertFalse(self.controls[0].widget.isHidden())

    def test_every_assignment_is_delivered_as_a_copy(self):
        self.register()
        tile = self.tile({'room_id': '12'})
        for room in (None, {'room_id': '12', 'title': 'new'}, {'room_id': '13'}, {'room_id': '12'}):
            tile.set_room(room)
            self.assertNotIn('mutated', tile.room)
            self.assertEqual(self.controls[0].rooms[-1].get('room_id'), (room or {}).get('room_id'))
            self.assertEqual(self.controls[0].ctx.room.get('room_id'), (room or {}).get('room_id'))
        self.assertEqual(len(self.controls), 1)

    def test_failed_load_rolls_back_controls(self):
        self.tile({'room_id': '12'})
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / 'bad'
            folder.mkdir()
            (folder / 'plugin.py').write_text('from ddm.plugins import *\n'
                'from PySide6.QtWidgets import QLineEdit\n'
                'class Bad(Plugin):\n'
                ' def on_load(self, c):\n'
                '  c.register_tile_control("bad", lambda x: TileControl(QLineEdit(x.parent)))\n'
                '  raise ValueError("intentional")\nplugin=Bad()\n', encoding='utf-8')
            self.manager.plugins_dir = root
            self.manager.load()
        self.assertEqual(len(self.manager.plugins), 0)
        self.assertEqual(self.tiles[0]._plugin_controls.entries, [])

    def test_provider_exceptions_do_not_block_others(self):
        self.register('bad', broken=True)
        self.register('good')
        tile = self.tile({'room_id': '12'})
        tile.set_room({'room_id': '13'})
        self.assertEqual(self.controls[-1].rooms[-1]['room_id'], '13')

    def test_remove_and_unload_shutdown_once(self):
        self.register()
        tile = self.tile({'room_id': '12'})
        self.manager.detach_tile(tile)
        self.manager.detach_tile(tile)
        self.manager.unload()
        self.assertEqual(self.controls[0].stops, 1)

    def test_no_extension_layout_is_preserved(self):
        tile = self.tile({'room_id': '12'})
        tile.resize(360, 240)
        APP.processEvents()
        self.assertFalse(tile.volume_slider.isHidden())
        self.assertFalse(tile.danmaku_settings_button.isHidden())
        self.assertLess(tile.fullscreen_button.geometry().right(), tile.width())

    def test_priority_overflow_recovers_on_widening(self):
        self.register('low', priority=0)
        self.register('high', priority=100)
        tile = self.tile({'room_id': '12'})
        tile.resize(200, 200)
        APP.processEvents()
        entries = tile._plugin_controls.entries
        self.assertEqual(entries[0].owner, 'high')
        self.assertFalse(entries[0].wrapper.isHidden())
        self.assertTrue(entries[1].wrapper.isHidden())
        tile.resize(900, 400)
        APP.processEvents()
        self.assertTrue(all(not e.wrapper.isHidden() for e in entries))
        tile.set_room({'room_id': 'demo:12'})
        tile.resize(950, 400)
        APP.processEvents()
        self.assertTrue(all(e.control.widget.isHidden() for e in entries))

    def test_compact_controls_fit_200_360_900(self):
        self.register()
        tile = self.tile({'room_id': '12'})
        for width in (200, 360, 900):
            tile.resize(width, 260)
            APP.processEvents()
            control = self.controls[0].widget
            self.assertGreaterEqual(control.width(), 90)
            self.assertTrue(tile.volume_button.isVisible())
            self.assertTrue(tile.fullscreen_button.isVisible())
            self.assertLess(tile.fullscreen_button.geometry().right(), width)
            self.assertLessEqual(control.parentWidget().geometry().right(), tile.fullscreen_button.x())

    def test_short_status_does_not_reserve_empty_space_before_input(self):
        self.register()
        tile = self.tile({'room_id': '12'})
        tile.resize(900, 400)
        tile.set_status('已开播')
        APP.processEvents()
        label = tile.status_label
        natural = label.fontMetrics().horizontalAdvance(label.text())
        wrapper = tile._plugin_controls.entries[0].wrapper
        self.assertLessEqual(label.width(), natural + 8)
        self.assertLessEqual(wrapper.x() - label.x() - natural, 16)


if __name__ == '__main__':
    unittest.main()
