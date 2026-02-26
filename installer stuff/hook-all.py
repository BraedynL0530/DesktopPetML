from PyInstaller.utils.hooks import collect_all

# Collect all modules that might be missing
modules = ['rapidfuzz', 'pyautogui', 'speech_recognition', 'sklearn', 'joblib', 'pygetwindow', 'ollama']

datas = []
binaries = []
hiddenimports = []

for module in modules:
    try:
        module_datas, module_binaries, module_hiddenimports = collect_all(module)
        datas.extend(module_datas)
        binaries.extend(module_binaries)
        hiddenimports.extend(module_hiddenimports)
    except Exception:
        # Skip if module not found
        pass