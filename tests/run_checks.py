#!/usr/bin/env python3
"""Run GTK/Thunar checks on private Broadway displays, with temporary XDG directories."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def run(command, env, log):
    process = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = process.communicate()
        log.write_text(stdout)
        raise RuntimeError(f"Check timed out; see {log}")
    log.write_text(stdout + f"\nEXIT STATUS: {process.returncode}\n")
    diagnostics = stdout
    if env.get("HIKAIDE_SCENARIO") == "context-menu":
        # GTK3 has no public setter for synthetic events' native seat metadata; retain this warning in the log.
        expected = [line for line in stdout.splitlines() if "): Gdk-WARNING **:" in line and line.endswith("Event with type 8 not holding a GdkSeat. It is most likely synthesized outside Gdk/GTK+")]
        if len(expected) == 1:
            diagnostics = diagnostics.replace(expected[0], "")
    if process.returncode or any(message in diagnostics for message in ("Theme parsing error", "Gtk-CRITICAL", "Gtk-WARNING", "Gdk-CRITICAL", "Gdk-WARNING")):
        raise RuntimeError(f"Check failed: {' '.join(map(str, command))}\n{stdout}")


@contextmanager
def display_server(temporary, env, daemon, display, log_path):
    if not shutil.which(daemon):
        raise RuntimeError(f"Missing {daemon}; install the corresponding GTK tools")
    env["BROADWAY_DISPLAY"] = f":{display}"
    socket = temporary / f"web-{display}.socket"
    socket.unlink(missing_ok=True)
    with log_path.open("w") as server_log:
        server = subprocess.Popen([daemon, "-u", str(socket), f":{display}"], env=env, stdout=server_log, stderr=subprocess.STDOUT)
        try:
            for _ in range(50):
                if "Listening on" in log_path.read_text() or server.poll() is not None:
                    break
                time.sleep(0.05)
            if server.poll() is not None or "Listening on" not in log_path.read_text():
                raise RuntimeError(f"Cannot start {daemon}; see {log_path}")
            yield
        finally:
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thunar", action="store_true", help="also test Thunar's views, menus and workflow dialogs")
    parser.add_argument("--output", type=Path, default=ROOT / ".test-output")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    subprocess.run(["python3", "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], check=True)
    with tempfile.TemporaryDirectory(prefix="hikaide-check-") as directory:
        temporary = Path(directory)
        env = os.environ.copy()
        for variable, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"), ("XDG_RUNTIME_DIR", "runtime")):
            location = temporary / name
            location.mkdir(mode=0o700)
            env[variable] = str(location)
        theme_root = temporary / "data/themes"
        subprocess.run(["python3", str(ROOT / "scripts/install_gtk_theme.py"), "--dest", str(theme_root)], check=True, stdout=subprocess.DEVNULL)
        for version in ("3.0", "4.0"):
            config = temporary / f"config/gtk-{version}"
            config.mkdir()
            (config / "gtk.css").symlink_to(theme_root / f"Hikaide/gtk-{version}/gtk.css")
        env.update(GTK_THEME="Hikaide:dark", GDK_BACKEND="broadway", GSK_RENDERER="cairo", NO_AT_BRIDGE="1", GIO_USE_VFS="local", GIO_USE_VOLUME_MONITOR="unix", GTK_A11Y="none", LC_ALL="C.UTF-8")
        env.pop("GTK_MODULES", None)
        for version, daemon, display in (("3.0", "broadwayd", 31), ("4.0", "gtk4-broadwayd", 41)):
            with display_server(temporary, env, daemon, display, output / f"broadway-{version}.log"):
                run(["python3", str(ROOT / "tests/gtk_smoke.py"), version, str(output / f"gtk-{version}.png")], env, output / f"gtk-{version}.log")
                print(f"PASS GTK {version}", flush=True)
                if version == "3.0":
                    run(["python3", str(ROOT / "tests/gtk_fade.py")], env, output / "gtk-fade.log")
                    print("PASS GTK3 fade timing and reduced motion", flush=True)
            if version == "3.0" and args.thunar:
                failures.extend(thunar_checks(temporary, env, output))
    if failures:
        raise RuntimeError("Failed Thunar scenarios: " + ", ".join(failures) + f"; see {output}")
    print(f"All checks passed. Screenshots and logs: {output}")


def thunar_checks(temporary, env, output):
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "gtk+-3.0"], text=True))
    module = temporary / "thunar-probe.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-Wno-deprecated-declarations", str(ROOT / "tests/thunar_probe.c"), "-o", str(module), *flags, "-ldl"], check=True)
    files = temporary / "files"
    files.mkdir()
    (temporary / "config/gtk-3.0/bookmarks").write_text(f"{files.as_uri()} Projects\n")
    (files / "Documents").mkdir()
    (files / "Empty folder").mkdir()
    for name in ("A long filename for selection and renaming.txt", ".hidden-file", "README.md"):
        (files / name).write_text("Hikaide acceptance fixture\n")
    for i in range(60):
        (files / f"Document {i:02}.txt").write_text("Test fixture\n")
    failures = []
    for scenario in ("empty", "icons", "detailed", "compact", "selected", "multi-select", "backdrop", "hidden", "tabs", "pathbar", "location", "context-menu", "properties", "preferences", "create-folder", "rename", "open-with", "delete-confirm"):
        scenario_env = dict(env, GTK_MODULES=str(module), HIKAIDE_SCENARIO=scenario, HIKAIDE_OUTPUT=str(output))
        target = files / "Empty folder" if scenario == "empty" else files
        try:
            with display_server(temporary, scenario_env, "broadwayd", 31, output / f"broadway-thunar-{scenario}.log"):
                run(["dbus-run-session", "--", "thunar", str(target)], scenario_env, output / f"thunar-{scenario}.log")
            print(f"PASS Thunar {scenario}", flush=True)
        except RuntimeError:
            failures.append(scenario)
            print(f"FAIL Thunar {scenario}; see thunar-{scenario}.log", flush=True)
    return failures


if __name__ == "__main__":
    main()
