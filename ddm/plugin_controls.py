"""Managed, platform-neutral controls in a tile's flexible bottom-bar slot."""
from copy import deepcopy
from dataclasses import dataclass, field
import traceback
import weakref

from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget


@dataclass
class TileControlContext:
    parent: QWidget
    room: dict
    invalidate_layout: object
    _active: bool = field(default=True, init=False, repr=False)


class TileControl:
    def __init__(self, widget, *, minimum_width=0, preferred_width=240):
        self.widget = widget
        self.minimum_width = max(0, int(minimum_width))
        self.preferred_width = max(self.minimum_width, int(preferred_width))

    def set_room(self, room):
        pass

    def interaction_active(self):
        return False

    def shutdown(self):
        pass


@dataclass
class _Entry:
    owner: str
    key: str
    priority: int
    order: int
    wrapper: QWidget
    context: TileControlContext
    control: TileControl


class TileControls:
    def __init__(self, tile):
        self._tile = weakref.ref(tile)
        self.entries = []
        self._disposed = False

    def invalidate(self):
        tile = self._tile()
        if tile is not None and not self._disposed:
            tile._layout_bottom_controls()

    def add(self, owner, key, factory, priority, order):
        if self._disposed or any(e.owner == owner and e.key == key for e in self.entries):
            return
        tile = self._tile()
        wrapper = QWidget(tile.bottom)
        wrapper.setMinimumWidth(0)
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        ref = weakref.ref(self)
        def invalidate():
            controls = ref()
            if controls is not None and ctx._active:
                controls.invalidate()
        ctx = TileControlContext(wrapper, deepcopy(tile.room), invalidate)
        try:
            control = factory(ctx)
            if not isinstance(control, TileControl) or not isinstance(control.widget, QWidget):
                raise ValueError('tile control factory must return TileControl with a QWidget')
            control.widget.setParent(wrapper)
            layout.addWidget(control.widget)
            control.widget.setMinimumWidth(0)
            entry = _Entry(owner, key, priority, order, wrapper, ctx, control)
            self.entries.append(entry)
            self.entries.sort(key=lambda e: (-e.priority, e.order))
            bar = tile.bottom.layout()
            for item in self.entries:
                bar.removeWidget(item.wrapper)
            index = bar.indexOf(tile.status_label) + 1
            for item in self.entries:
                bar.insertWidget(index, item.wrapper, 1)
                index += 1
            self._deliver(entry, tile.room)
        except Exception:
            ctx._active = False
            traceback.print_exc()
            wrapper.hide()
            wrapper.deleteLater()
        self.invalidate()

    def _deliver(self, entry, room):
        entry.context.room = deepcopy(room)
        try:
            entry.control.set_room(deepcopy(room))
        except Exception:
            traceback.print_exc()

    def set_room(self, room):
        for entry in tuple(self.entries):
            self._deliver(entry, room)
        self.invalidate()

    def applicable(self):
        return [e for e in self.entries if not e.control.widget.isHidden()]

    def allocate(self, width):
        remaining = max(0, width)
        applicable = self.applicable()
        selected = []
        for entry in applicable:
            if remaining >= entry.control.minimum_width:
                selected.append(entry)
                remaining -= entry.control.minimum_width
        for entry in self.entries:
            entry.wrapper.setVisible(entry in selected)
        for entry in selected:
            extra = min(remaining, entry.control.preferred_width - entry.control.minimum_width)
            remaining -= extra
            entry.wrapper.setMinimumWidth(entry.control.minimum_width)
            entry.wrapper.setMaximumWidth(entry.control.minimum_width + extra)
        # The first control absorbs spare room beyond its preferred width.
        if selected and remaining:
            selected[0].wrapper.setMaximumWidth(selected[0].wrapper.maximumWidth() + remaining)

    def interaction_active(self):
        for entry in tuple(self.entries):
            if entry.wrapper.isVisible() and entry.control.widget.isVisible() and entry.control.widget.isEnabled():
                try:
                    if entry.control.interaction_active():
                        return True
                except Exception:
                    traceback.print_exc()
        return False

    def remove_owner(self, owner=None):
        for entry in tuple(self.entries):
            if owner is not None and entry.owner != owner:
                continue
            self.entries.remove(entry)
            entry.context._active = False
            entry.context.invalidate_layout = lambda: None
            try:
                entry.control.shutdown()
            except Exception:
                traceback.print_exc()
            try:
                entry.wrapper.hide()
                entry.wrapper.setParent(None)
                entry.wrapper.deleteLater()
            except RuntimeError:
                pass  # Qt already disposed the tile.
        self.invalidate()

    def shutdown(self):
        if not self._disposed:
            self._disposed = True
            self.remove_owner()
