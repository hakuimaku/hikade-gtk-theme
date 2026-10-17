"""Check cached GTK3 file-list icons with a private symbolic icon theme."""

from pathlib import Path
import sys
import tempfile

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


def descendants(widget):
    """Walk the chooser's internal widgets."""
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():  # Descend through internal containers.
            yield from descendants(child)


with tempfile.TemporaryDirectory(prefix="hikaide-chooser-") as directory:
    # A unique folder shape distinguishes the selected theme from Adwaita.
    root = Path(directory)  # Isolated icon and file fixtures.
    icons = root / "icons/HikaideChooserTest/scalable/places"  # Private theme artwork.
    icons.mkdir(parents=True)
    (icons.parent.parent / "index.theme").write_text(
        "[Icon Theme]\nName=HikaideChooserTest\nInherits=hicolor\nDirectories=scalable/places\n"
        "[scalable/places]\nSize=16\nType=Scalable\nMinSize=8\nMaxSize=512\nContext=Places\n")
    (icons / "folder-symbolic.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
        '<rect x="4" y="4" width="8" height="8" fill="#2e3436"/></svg>')
    (root / "files/Folder").mkdir(parents=True)
    Gtk.IconTheme.get_default().prepend_search_path(str(root / "icons"))
    Gtk.Settings.get_default().set_property("gtk-icon-theme-name", "HikaideChooserTest")
    window = Gtk.Window()  # Map the chooser on the private display.
    chooser = Gtk.FileChooserWidget(action=Gtk.FileChooserAction.OPEN)  # Populate a real file list.
    chooser.set_current_folder(str(root / "files"))
    window.add(chooser)
    window.show_all()
    loop = GLib.MainLoop()  # Allow asynchronous directory loading.
    failures = []  # Propagate callback failures to the test process.

    def finish():
        """Inspect the actual surface cached in the file-list model."""
        try:
            tree = next(widget for widget in descendants(chooser)  # Locate the chooser's file list.
                        if isinstance(widget, Gtk.TreeView) and Gtk.Buildable.get_name(widget) == "browse_files_tree_view")
            model = tree.get_model()  # Read the loaded directory rows.
            assert model is not None and len(model) == 1
            surfaces = [model[0][column] for column in range(model.get_n_columns())  # Extract cached icon surfaces.
                        if model.get_column_type(column).name == "CairoSurface"]
            assert len(surfaces) == 1 and surfaces[0] is not None, surfaces
            surface = surfaces[0]  # Inspect the rendered folder icon.
            surface.write_to_png(sys.argv[1])
            # Native ARGB words preserve channel order on either byte order.
            pixels = memoryview(surface.get_data()).cast("I")  # Native ARGB pixel values.
            stride = surface.get_stride() // 4  # Pixel words per surface row.
            assert pixels[8 * stride + 3] == pixels[8 * stride + 12] == 0
            assert pixels[4 * stride + 4] == pixels[8 * stride + 8] == 0xFFD8D8D8
            print("PASS GTK3 chooser: selected theme's symbolic folder cached and recolored")
        except Exception as error:
            failures.append(error)
        finally:
            window.destroy()
            loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(1000, finish)
    loop.run()
    if failures:
        raise failures[0]
