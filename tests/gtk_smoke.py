"""Parse both theme variants and render real GTK widgets (one GTK version per process)."""

from pathlib import Path
import sys

import gi

version, output = sys.argv[1:]
gi.require_version("Gtk", version)
from gi.repository import Gio, GLib, Gtk

ROOT = Path(__file__).resolve().parents[1]
errors = []
providers = []
if not Gtk.init_check():
    raise SystemExit("A GTK display is required; use tests/run_checks.py for isolated Broadway tests")
for name in ("gtk.css", "gtk-dark.css"):
    provider = Gtk.CssProvider()
    provider.connect("parsing-error", lambda p, section, error: errors.append(str(error)))
    provider.load_from_path(str(ROOT / "themes/Hikaide" / f"gtk-{version}" / name))
    providers.append(provider)
assert not errors, errors

gtk3 = version == "3.0"
window = Gtk.Window(title=f"Hikaide — GTK {version} widgets")
window.set_default_size(760, 650)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
for side in ("top", "bottom", "start", "end"):
    getattr(box, f"set_margin_{side}")(12)


def add(parent, child):
    if gtk3:
        parent.add(child)
    else:
        parent.append(child)
    return child


if gtk3:
    window.add(box)
else:
    window.set_child(box)
add(box, Gtk.Label(label="Hikaide · quiet monochrome surfaces", xalign=0))
buttons = add(box, Gtk.Box(spacing=8))
normal = add(buttons, Gtk.Button(label="Normal"))
focused = add(buttons, Gtk.Button(label="Keyboard focus"))
checked = add(buttons, Gtk.ToggleButton(label="Checked"))
checked.set_active(True)
disabled = add(buttons, Gtk.Button(label="Disabled"))
disabled.set_sensitive(False)
entry = add(box, Gtk.Entry(text="Editable location / filename"))
entry.set_placeholder_text("Location")
entry.set_tooltip_text("Dark tooltip with readable text")
controls = add(box, Gtk.Box(spacing=8))
check = add(controls, Gtk.CheckButton(label="Checked"))
check.set_active(True)
mixed = add(controls, Gtk.CheckButton(label="Mixed"))
mixed.set_inconsistent(True)
if gtk3:
    radio = add(controls, Gtk.RadioButton(label="Radio"))
else:
    radio = add(controls, Gtk.CheckButton(label="Radio"))
    radio.set_group(Gtk.CheckButton())
radio.set_active(True)
switch = add(controls, Gtk.Switch())
switch.set_active(True)
add(controls, Gtk.SpinButton.new_with_range(0, 100, 1))
scale = add(box, Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1))
scale.set_value(45)
progress = add(box, Gtk.ProgressBar())
progress.set_fraction(0.65)
progress.set_show_text(True)
notebook = add(box, Gtk.Notebook())
notebook.append_page(Gtk.Label(label="Active tab content"), Gtk.Label(label="Files"))
notebook.append_page(Gtk.Label(label="Second tab content"), Gtk.Label(label="Details"))
listing = add(box, Gtk.ListBox())
for title in ("Idle row", "Selected row", "A long filename remains readable in a dark view"):
    add(listing, Gtk.Label(label=title, xalign=0))
listing.select_row(listing.get_row_at_index(1))
if not gtk3:
    strings = Gtk.StringList.new(["GTK4 ListView row", "Another virtualized row"])
    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", lambda f, item: item.set_child(Gtk.Label(xalign=0)))
    factory.connect("bind", lambda f, item: item.get_child().set_text(item.get_item().get_string()))
    add(box, Gtk.ListView(model=Gtk.SingleSelection(model=strings), factory=factory))
    add(box, Gtk.DropDown.new_from_strings(["GTK4 dropdown", "Alternative"]))
else:
    model = Gtk.ListStore(str, str)
    model.append(["Detailed list", "Readable cell renderer"])
    model.append(["Selected file", "Grayscale selection"])
    tree = add(box, Gtk.TreeView(model=model))
    for i, title in enumerate(("Name", "Description")):
        tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i))
    tree.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
scroller = add(box, Gtk.ScrolledWindow())
scroller.set_min_content_height(70)
text = Gtk.TextView()
text.get_buffer().set_text("Scrollable text\n" * 30)
if gtk3:
    scroller.add(text)
else:
    scroller.set_child(text)
menu_button = add(box, Gtk.MenuButton(label="Popover menu"))
menu = Gio.Menu()
menu.append("Menu action", "app.example")
if gtk3:
    popover = Gtk.Popover.new_from_model(menu_button, menu)
    menu_button.set_popover(popover)
else:
    menu_button.set_menu_model(menu)
focused.grab_focus()
loop = GLib.MainLoop()
failure = []


def finish():
    try:
        assert not errors, errors
        if gtk3:
            import cairo
            bg = window.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
            assert abs(bg.red - 16 / 255) < 0.001 and bg.red == bg.green == bg.blue
            for state in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT, Gtk.StateFlags.ACTIVE, Gtk.StateFlags.INSENSITIVE):
                context = normal.get_style_context()
                context.save()
                context.set_state(state)
                fg = context.get_color(state)
                assert fg.red == fg.green == fg.blue, (state, fg)
                assert fg.red >= 0.46, (state, fg)
                context.restore()
            context = normal.get_style_context()
            context.save()
            context.set_state(Gtk.StateFlags.FOCUSED)
            focus_bg = context.get_background_color(Gtk.StateFlags.FOCUSED)
            context.restore()
            assert focus_bg.red > context.get_background_color(Gtk.StateFlags.NORMAL).red
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, window.get_allocated_width(), window.get_allocated_height())
            window.draw(cairo.Context(surface))
            surface.write_to_png(output)
        else:
            gi.require_version("Gsk", "4.0")
            gi.require_version("Graphene", "1.0")
            from gi.repository import Graphene, Gsk
            window.allocate(760, 650, -1, None)
            snapshot = Gtk.Snapshot()
            found, background = window.get_style_context().lookup_color("haku_base")
            assert found and abs(background.red - 16 / 255) < 0.001
            snapshot.append_color(background, Graphene.Rect().init(0, 0, 760, 650))
            window.snapshot_child(box, snapshot)
            node = snapshot.to_node()
            assert node is not None
            renderer = Gsk.Renderer.new_for_surface(window.get_surface())
            try:
                texture = renderer.render_texture(node, None)
                assert texture.save_to_png(output)
            finally:
                renderer.unrealize()
            color = normal.get_color()
            assert color.red == color.green == color.blue and abs(color.red - 216 / 255) < 0.001
        print(f"GTK {version}: both CSS variants parsed; widget render and assertions passed")
    except Exception as error:
        failure.append(error)
    finally:
        window.destroy()
        loop.quit()
    return GLib.SOURCE_REMOVE


if gtk3:
    window.show_all()
else:
    window.present()
GLib.timeout_add(500, finish)
loop.run()
if failure:
    raise failure[0]
