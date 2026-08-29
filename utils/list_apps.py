import platform, os


def search_dirs_and_extentions():
    system = platform.system()
    if system == "Windows":
        search_dirs = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
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

    search_dirs, extensions = search_dirs_and_extentions()

    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        
        for current_path, inside_dirs, files in os.walk(search_dir):
            for file in files:
                if not file.lower().endswith(extensions):
                    continue 
                name = os.path.splitext(file)[0]

                full_path = os.path.join(current_path, name)

                installed_apps.setdefault(name, full_path)
            if current_path.count(os.sep) > search_dir.count(os.sep) + 3:
                inside_dirs.clear()
    
    return installed_apps
        
