import os
import subprocess
import sys
from subprocess import TimeoutExpired

if getattr(sys, 'frozen', False):
    project_root = sys._MEIPASS
else:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.config import ENABLED_PLUGINS
from core.plugin_system import PluginManager


def inject_process_path():
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    extra = []
    for candidate in (project_root, os.path.join(project_root, "ui")):
        if os.path.isdir(candidate) and candidate not in path_parts:
            extra.append(candidate)
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + path_parts) if path_parts else os.pathsep.join(extra)

ASCII_CAT = r"""
 /\_/\\
( o.o )  DesktopPetML TUI
 > ^ <
"""
PET_ENTRYPOINT = os.path.join(project_root, "ui", "pet.py")


def run_tui():
    inject_process_path()
    print(ASCII_CAT)
    print("Type commands. Examples: cat -show, cat -hide, obsidian daily, obsidian append did code review")
    print("Type 'exit' to quit. PyQt cat is hidden by default in terminal mode.")

    gui_proc = None

    def set_cat_visible(visible: bool):
        nonlocal gui_proc
        if visible:
            if gui_proc and gui_proc.poll() is None:
                print("PyQt cat is already running.")
                return
            env = os.environ.copy()
            env["DPETML_TERMINAL_MODE"] = "0"
            env["DPETML_UI_MODE"] = "gui"
            env["DPETML_DIRECT_START"] = "pet"
            gui_proc = subprocess.Popen([sys.executable, PET_ENTRYPOINT], env=env)
            print("Started PyQt cat.")
        else:
            if gui_proc and gui_proc.poll() is None:
                gui_proc.terminate()
                try:
                    gui_proc.wait(timeout=3)
                except TimeoutExpired:
                    gui_proc.kill()
                print("Stopped PyQt cat.")
            else:
                print("PyQt cat already hidden.")

    manager = PluginManager(enabled_plugins=ENABLED_PLUGINS, context={"set_cat_visible": set_cat_visible})
    print(f"Loaded plugins: {', '.join(manager.loaded_plugin_names) if manager.loaded_plugin_names else 'none'}")

    while True:
        try:
            cmd = input("cat> ").strip()
        except (EOFError, KeyboardInterrupt):
            cmd = "exit"

        if cmd.lower() in ("exit", "quit"):
            break

        handled, response = manager.handle_command(cmd)
        if handled:
            if response:
                print(response)
            continue

        print("Unknown command. Try: cat -show | cat -hide | obsidian ...")

    if gui_proc and gui_proc.poll() is None:
        gui_proc.terminate()


if __name__ == "__main__":
    run_tui()
