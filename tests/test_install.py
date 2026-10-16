"""Installer checks use temporary directories only."""

import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse


spec = importlib.util.spec_from_file_location("installer", Path(__file__).resolve().parents[1] / "scripts/install_gtk_theme.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_install_update_and_preserve_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / "OtherTheme"
            other.mkdir()
            (other / "keep").write_text("untouched")
            target, backup = installer.install(root)
            self.assertIsNone(backup)
            for name in installer.REQUIRED:
                if b'url("' not in (installer.SOURCE / name).read_bytes():
                    self.assertEqual((target / name).read_bytes(), (installer.SOURCE / name).read_bytes())
            (target / "local-edit").write_text("preserve me")
            target, backup = installer.install(root)
            self.assertEqual((backup / "local-edit").read_text(), "preserve me")
            self.assertFalse((target / "local-edit").exists())
            self.assertEqual((other / "keep").read_text(), "untouched")

    def test_resources_resolve_through_user_css_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, _ = installer.install(root / "themes with spaces")
            aliases = root / "config/gtk-4.0"
            aliases.mkdir(parents=True)
            alias = aliases / "gtk.css"
            alias.symlink_to(target / "gtk-4.0/gtk.css")
            self.assertIn(target.as_uri(), alias.read_text())
            references = []
            for css in target.rglob("*.css"):
                for uri in re.findall(r'url\("([^\"]+)"\)', css.read_text()):
                    parsed = urlparse(uri)
                    self.assertEqual(parsed.scheme, "file")
                    resource = Path(unquote(parsed.path))
                    self.assertTrue(resource.is_relative_to(target), resource)
                    self.assertTrue(resource.is_file(), resource)
                    references.append(resource)
            self.assertIn(target / "shared/widgets.css", references)
            self.assertIn(target / "assets/check.svg", references)

    def test_reject_unsafe_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "Hikaide"
            target.symlink_to(installer.SOURCE, target_is_directory=True)
            with self.assertRaises(ValueError):
                installer.install(root)
            target.unlink()
            target.mkdir()
            (target / "keep").write_text("unrelated data")
            with self.assertRaises(ValueError):
                installer.install(root)
            self.assertEqual((target / "keep").read_text(), "unrelated data")
        with self.assertRaises(ValueError):
            installer.install(installer.SOURCE.parent)

    def test_incomplete_source_does_not_touch_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(installer, "SOURCE", root / "missing"):
                with self.assertRaises(ValueError):
                    installer.install(root / "themes")
            self.assertFalse((root / "themes").exists())

    def test_failed_update_restores_previous_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, _ = installer.install(root)
            (target / "local-edit").write_text("keep")
            rename = Path.rename

            def fail_staged(source, destination):
                if source.parent.name.startswith(".hikaide-install-"):
                    raise OSError("simulated replacement failure")
                return rename(source, destination)

            with patch.object(Path, "rename", fail_staged):
                with self.assertRaises(OSError):
                    installer.install(root)
            self.assertEqual((target / "local-edit").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
