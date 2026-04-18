import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk

import threading
from typing import Dict, Any, List

from engine import PiperEngine
from settings import load_settings, save_settings
from utils import list_voices, list_audio_sinks


class PiperUI(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.piper.control.portable")
        self.settings: Dict[str, Any] = load_settings()
        self.engine = PiperEngine()
        self.tts_thread: threading.Thread | None = None
        self.sink_map: Dict[str, str] = {}

        self.history: List[str] = self.settings.get("history", [])[:10]
        self.favorites: List[str] = self.settings.get("favorites", [])

    def do_activate(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Piper TTS Control")
        self.window.set_default_size(720, 740)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)

        # Text input area
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_editable(True)
        self.text_view.set_cursor_visible(True)
        self.text_view.set_pixels_above_lines(8)
        self.text_view.set_pixels_below_lines(8)
        self.text_view.set_left_margin(12)
        self.text_view.set_right_margin(12)

        self.text_view.set_input_hints(Gtk.InputHints.NONE)
        self.text_view.set_input_purpose(Gtk.InputPurpose.FREE_FORM)

        try:
            font_desc = Pango.FontDescription.from_string("DejaVu Sans 11")
            self.text_view.override_font(font_desc)
        except:
            try:
                self.text_view.override_font(Pango.FontDescription.from_string("Sans 11"))
            except:
                pass

        scroll.set_child(self.text_view)
        main_box.append(scroll)

        # Enter to speak (Shift+Enter for newline)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_textview_key_pressed)
        self.text_view.add_controller(key_ctrl)

        # Audio Settings
        audio_exp = Gtk.Expander(label="Audio Settings", expanded=False)
        audio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        audio_box.set_margin_top(12)
        audio_box.set_margin_bottom(12)
        audio_box.set_margin_start(16)
        audio_box.set_margin_end(16)

        voices = list_voices() or ["No voices available"]
        self.voice_combo = self._create_dropdown(voices, "voice")
        audio_box.append(self._labeled_row("Voice:", self.voice_combo))

        sinks = list_audio_sinks()
        display_names, self.sink_map = self._build_device_list(sinks)
        self.device_combo = self._create_dropdown(display_names, "output_device")
        audio_box.append(self._labeled_row("Output:", self.device_combo))

        audio_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._add_slider(audio_box, "Speed", "speed", 0.7, 1.5, 0.05)
        self._add_slider(audio_box, "Noise", "noise", 0.0, 1.0, 0.05)
        self._add_slider(audio_box, "Volume", "volume", 0.0, 2.0, 0.05)

        audio_exp.set_child(audio_box)
        main_box.append(audio_exp)

        # History & Favorites
        hist_exp = Gtk.Expander(label="History & Favorites", expanded=False)
        hist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hist_box.set_margin_top(12)
        hist_box.set_margin_bottom(12)
        hist_box.set_margin_start(16)
        hist_box.set_margin_end(16)

        hist_box.append(Gtk.Label(label="Recent messages", xalign=0.0))
        self.recent_list = Gtk.ListBox()
        self.recent_list.set_selection_mode(Gtk.SelectionMode.NONE)
        recent_scroll = Gtk.ScrolledWindow()
        recent_scroll.set_child(self.recent_list)
        recent_scroll.set_max_content_height(160)
        hist_box.append(recent_scroll)
        self._refresh_recent()

        hist_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        hist_box.append(Gtk.Label(label="Favorites", xalign=0.0))
        self.fav_list = Gtk.ListBox()
        self.fav_list.set_selection_mode(Gtk.SelectionMode.NONE)
        fav_scroll = Gtk.ScrolledWindow()
        fav_scroll.set_child(self.fav_list)
        fav_scroll.set_max_content_height(160)
        hist_box.append(fav_scroll)
        self._refresh_favorites()

        hist_exp.set_child(hist_box)
        main_box.append(hist_exp)

        # Action buttons with tip icon
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(16)

        speak_btn = Gtk.Button(label="Speak")
        speak_btn.connect("clicked", self.on_speak)

        stop_btn = Gtk.Button(label="Stop")
        stop_btn.connect("clicked", lambda b: self.engine.stop())

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", lambda b: self.text_view.get_buffer().set_text(""))

        self.mute_btn = Gtk.ToggleButton(label="Mute")
        muted = self.settings.get("mute", False)
        self.mute_btn.set_active(muted)
        self.mute_btn.connect("toggled", self.on_mute_toggled)
        if muted:
            self.mute_btn.set_label("Unmute")
            self.mute_btn.add_css_class("destructive-action")

        # Tip button for accents
        tip_btn = Gtk.Button(label="?")
        tip_btn.set_tooltip_text("Tip: For languages with accents (á, ã, ç, õ, etc.), install fcitx5-gtk")

        btn_box.append(speak_btn)
        btn_box.append(stop_btn)
        btn_box.append(clear_btn)
        btn_box.append(self.mute_btn)
        btn_box.append(tip_btn)

        main_box.append(btn_box)

        self.window.set_child(main_box)
        self.window.present()

    def _labeled_row(self, text: str, widget: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(spacing=12)
        lbl = Gtk.Label(label=text, xalign=0.0)
        lbl.set_width_chars(14)
        box.append(lbl)
        box.append(widget)
        widget.set_hexpand(True)
        return box

    def _create_dropdown(self, items: List[str], key: str) -> Gtk.DropDown:
        model = Gtk.StringList()
        for item in items:
            model.append(item)

        dd = Gtk.DropDown(model=model)
        dd.set_factory(self._create_ellipsizing_factory())

        saved = self.settings.get(key)
        if saved in items:
            try:
                dd.set_selected(items.index(saved))
            except ValueError:
                dd.set_selected(0)
        else:
            dd.set_selected(0)

        return dd

    def _create_ellipsizing_factory(self) -> Gtk.SignalListItemFactory:
        factory = Gtk.SignalListItemFactory()

        def setup(_, item):
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_width_chars(45)
            item.set_child(lbl)

        def bind(_, item):
            lbl = item.get_child()
            lbl.set_text(item.get_item().get_string())

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        return factory

    def _build_device_list(self, sinks: List[str]) -> tuple[list[str], dict[str, str]]:
        displays = []
        mapping = {}

        for name in sinks:
            if not name:
                continue

            display = name
            if name == "default":
                display = "System Default"
            elif "analog-stereo" in name.lower():
                display = "Analog Stereo"
            elif "easyeffects" in name.lower():
                display = "EasyEffects"
            elif "virtual" in name.lower():
                display = "Virtual Output"
            else:
                if '.' in name:
                    display = name.split('.')[-1].replace('_', ' ').replace('-', ' ').title()
                if len(display) > 40:
                    display = display[:37] + "…"

            base = display
            i = 1
            while display in mapping:
                display = f"{base} ({i})"
                i += 1

            displays.append(display)
            mapping[display] = name

        if not displays:
            displays = ["Default"]
            mapping["Default"] = "default"

        return displays, mapping

    def _add_slider(self, parent: Gtk.Box, label: str, key: str,
                    minv: float, maxv: float, step: float):
        row = Gtk.Box(spacing=12)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_width_chars(14)
        row.append(lbl)

        val_lbl = Gtk.Label(label=f"{self.settings.get(key, 1.0):.2f}")
        row.append(val_lbl)

        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minv, maxv, step)
        slider.set_value(self.settings.get(key, 1.0))
        slider.set_draw_value(False)
        slider.set_hexpand(True)
        slider.set_size_request(200, -1)
        row.append(slider)

        parent.append(row)

        def on_change(s, *_):
            v = s.get_value()
            val_lbl.set_text(f"{v:.2f}")
            self.settings[key] = round(v, 3)
            save_settings(self.settings)

        slider.connect("value-changed", on_change)

    def _refresh_recent(self):
        while child := self.recent_list.get_first_child():
            self.recent_list.remove(child)

        for text in self.history:
            self._add_history_row(self.recent_list, text, favorite=False)

    def _refresh_favorites(self):
        while child := self.fav_list.get_first_child():
            self.fav_list.remove(child)

        for text in self.favorites:
            self._add_history_row(self.fav_list, text, favorite=True)

    def _add_history_row(self, listbox: Gtk.ListBox, text: str, favorite: bool):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(8)
        box.set_margin_end(8)

        preview = text[:70] + ("…" if len(text) > 70 else "")
        lbl = Gtk.Label(label=preview, ellipsize=Pango.EllipsizeMode.END, xalign=0.0)
        lbl.set_hexpand(True)
        box.append(lbl)

        use_btn = Gtk.Button(label="Use")
        use_btn.connect("clicked", lambda _, t=text: self.text_view.get_buffer().set_text(t))
        box.append(use_btn)

        if not favorite:
            star_btn = Gtk.Button(label="★")
            star_btn.connect("clicked", lambda _, t=text: self._add_favorite(t))
            box.append(star_btn)
        else:
            del_btn = Gtk.Button(label="Delete")
            del_btn.add_css_class("destructive-action")
            del_btn.connect("clicked", lambda _, t=text: self._remove_favorite(t))
            box.append(del_btn)

        row.set_child(box)
        listbox.append(row)

    def _add_favorite(self, text: str):
        if text and text not in self.favorites:
            self.favorites.insert(0, text)
            self.settings["favorites"] = self.favorites
            save_settings(self.settings)
            self._refresh_favorites()

    def _remove_favorite(self, text: str):
        if text in self.favorites:
            self.favorites.remove(text)
            self.settings["favorites"] = self.favorites
            save_settings(self.settings)
            self._refresh_favorites()

    def on_speak(self, button):
        buf = self.text_view.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, False).strip()
        if not text:
            return

        pos = self.voice_combo.get_selected()
        voices = list_voices() or ["en_GB-cori-high"]
        voice = voices[pos] if pos < len(voices) else voices[0]
        self.settings["voice"] = voice

        device = "default"
        pos = self.device_combo.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION and self.sink_map:
            display = self.device_combo.get_selected_item().get_string()
            device = self.sink_map.get(display, "default")
        self.settings["output_device"] = device

        save_settings(self.settings)

        if text in self.history:
            self.history.remove(text)
        self.history.insert(0, text)
        self.history = self.history[:10]
        self.settings["history"] = self.history
        save_settings(self.settings)
        self._refresh_recent()

        if self.tts_thread and self.tts_thread.is_alive():
            return

        self.tts_thread = threading.Thread(
            target=self.engine._run,
            args=(text, self.settings),
            daemon=True
        )
        self.tts_thread.start()

    def on_mute_toggled(self, button: Gtk.ToggleButton):
        muted = button.get_active()
        self.engine.set_mute(muted)
        self.settings["mute"] = muted
        save_settings(self.settings)

        if muted:
            button.set_label("Unmute")
            button.add_css_class("destructive-action")
        else:
            button.set_label("Mute")
            button.remove_css_class("destructive-action")

    def on_textview_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Return:
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False
            self.on_speak(None)
            return True
        return False


def main():
    app = PiperUI()
    app.run()


if __name__ == "__main__":
    main()
