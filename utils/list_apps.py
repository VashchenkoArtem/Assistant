import json
import os
import platform
import re
import subprocess


TECHNICAL_APP_NAME = re.compile(
    r"^(?:uninstall(?:er)?|unins\d*|setup|installer|install|updater?|"
    r"repair|modify|crashpad_handler|maintenanceservice)(?:$|[._ -])",
    re.IGNORECASE,
)


def is_technical_app(name, path):
    path_name = os.path.splitext(os.path.basename(path))[0]
    return any(
        TECHNICAL_APP_NAME.match(candidate.strip())
        for candidate in (name, path_name)
        if candidate
    )


def _get_windows_store_apps():
    command = (
        "$apps = Get-StartApps | Where-Object { "
        "$_.Name -and $_.AppID -and $_.AppID.Contains('!') "
        "} | Select-Object Name, AppID; "
        "$apps | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not query Windows Store apps: {result.stderr.strip()}"
        )

    output = result.stdout.strip()
    if not output:
        return {}

    entries = json.loads(output)
    if isinstance(entries, dict):
        entries = [entries]

    apps = {}
    for entry in entries:
        name = entry.get("Name")
        app_id = entry.get("AppID")
        if not name or not app_id:
            continue

        app_path = f"appx://{app_id}"
        if not is_technical_app(name, app_path):
            apps[name] = app_path
    return apps


def search_dirs_and_extentions():
    system = platform.system()
    if system == "Windows":
        search_dirs = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
            os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        ]
        extensions = (".exe", ".lnk")
    elif system == "Darwin":
        search_dirs = ["/Applications", os.path.expanduser("~/Applications")]
        extensions = (".app",)
    else:  # Linux
        search_dirs = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]
        extensions = (".desktop",)

    valid_dirs = []

    for dir in search_dirs:
        if dir:
            valid_dirs.append(dir)
    return valid_dirs, extensions


    
def get_list_installed_apps():
    installed_apps = {}

    if platform.system() == "Windows":
        installed_apps.update(_get_windows_store_apps())

    search_dirs, extensions = search_dirs_and_extentions()

    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        
        for current_path, inside_dirs, files in os.walk(search_dir):
            for file in files:
                if not file.lower().endswith(extensions):
                    continue 
                name = os.path.splitext(file)[0]
                full_path = os.path.join(current_path, file)

                if is_technical_app(name, full_path):
                    continue
                installed_apps.setdefault(name, full_path)
            if current_path.count(os.sep) > search_dir.count(os.sep) + 3:
                inside_dirs.clear()
    
    return installed_apps
        
