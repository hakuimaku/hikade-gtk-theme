"""Measure GTK3 transitions over real frame-clock updates, including reduced motion."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

Gtk.init([])
settings = Gtk.Settings.get_default()
settings.set_property("gtk-enable-animations", True)
window = Gtk.Window()
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
window.add(box)
button = Gtk.Button(label="Button fade")
box.add(button)
bar = Gtk.MenuBar()
item = Gtk.MenuItem(label="Menu fade")
bar.append(item)
box.add(bar)
row = Gtk.ListBoxRow()
row.add(Gtk.Label(label="Row fade"))
box.add(row)
targets = (button, item, row)
window.show_all()
loop = GLib.MainLoop()
failure = []
samples = []
idle = []
hover = []


def colors():
    result = []
    for widget in targets:
        color = widget.get_style_context().get_background_color(widget.get_state_flags())
        result.append(color.red * color.alpha + (16 / 255) * (1 - color.alpha))
    return result


def sample():
    samples.append(colors())
    return GLib.SOURCE_CONTINUE


def phase(enter):
    samples.clear()
    for widget in targets:
        if enter:
            widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        else:
            widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)
    timer = GLib.timeout_add(10, sample)

    def finish():
        GLib.source_remove(timer)
        try:
            end = colors()
            if enter:
                hover.extend(end)
            else:
                assert all(abs(a - b) < 0.001 for a, b in zip(end, idle)), (end, idle)
            for index, widget in enumerate(targets):
                low, high = sorted((idle[index], hover[index]))
                assert high - low > 0.02, (type(widget).__name__, low, high)
                assert any(low + 0.001 < frame[index] < high - 0.001 for frame in samples), (type(widget).__name__, "no intermediate color", samples)
            if enter:
                phase(False)
            else:
                settings.set_property("gtk-enable-animations", False)
                for widget in targets:
                    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
                assert all(abs(a - b) < 0.001 for a, b in zip(colors(), hover))
                print("PASS: GTK3 button/menu/row fade in and out; disabled animations remain immediate")
                window.destroy()
                loop.quit()
        except Exception as error:
            failure.append(error)
            window.destroy()
            loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(350, finish)


def begin():
    idle.extend(colors())
    phase(True)
    return GLib.SOURCE_REMOVE


GLib.timeout_add(300, begin)
loop.run()
if failure:
    raise failure[0]
