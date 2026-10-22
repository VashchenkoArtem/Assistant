import json
import os
import platform
import re
import subprocess
from collections.abc import Iterable
from typing import NamedTuple

from utils.text_similarity import partial_similarity, similarity


OPEN_VERB = re.compile(
    r"\b(?:відкрий|відкрити|відкривай|відкривати)\b",
    re.IGNORECASE,
)
TARGET_KIND = re.compile(
    r"^(?P<kind>файл(?:и|ів)?|документ(?:и|ів)?|"
    r"папк(?:а|у|и)?|каталог(?:и|у)?|директорі(?:я|ю|ї))\s*",
    re.IGNORECASE,
)
NEW_WINDOW_PHRASE = re.compile(
    r"\b(?:у|в)\s+(?:новому|окремому)\s+вікні\b",
    re.IGNORECASE,
)
LOCATION_ALIASES = {
    "робочий стіл": "Desktop",
    "робочого столу": "Desktop",
    "завантаження": "Downloads",
    "завантаженнях": "Downloads",
    "завантажень": "Downloads",
    "документ": "Documents",
    "документа": "Documents",
    "документу": "Documents",
    "документи": "Documents",
    "документів": "Documents",
    "документах": "Documents",
    "зображення": "Pictures",
    "зображеннях": "Pictures",
    "фото": "Pictures",
    "музика": "Music",
    "відео": "Videos",
    "desktop": "Desktop",
    "downloads": "Downloads",
    "download": "Downloads",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
    "домашня папка": "~",
    "мій комп'ютер": "shell:MyComputerFolder",
    "цей комп'ютер": "shell:MyComputerFolder",
    "this pc": "shell:MyComputerFolder",
    "кошик": "shell:RecycleBinFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "провідник": "explorer",
    "file explorer": "explorer",
    "explorer": "explorer",
}
SEARCH_FOLDER_NAMES = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")
MAX_SEARCH_DEPTH = 4
MAX_RESULTS = 5
SIMILARITY_THRESHOLD = 0.6


class ExplorerTab(NamedTuple):
    path: str
    name: str
    hwnd: int
    tab_index: int


def _clean_target(value: str) -> str:
    return value.strip().strip("\"'«»").rstrip(" \t.,!?;:")


def parse_open_target_command(text: str) -> tuple[str, str, bool] | None:
    verb_match = OPEN_VERB.search(text)
    if verb_match is None:
        return None

    target = _clean_target(text[verb_match.end():])
    new_window = bool(NEW_WINDOW_PHRASE.search(target))
    target = _clean_target(NEW_WINDOW_PHRASE.sub("", target))
    kind_match = TARGET_KIND.match(target)
    if kind_match is not None:
        kind = "file" if kind_match.group("kind").lower().startswith(
            ("файл", "документ")
        ) else "folder"
        target = _clean_target(target[kind_match.end():])
        return kind, target, new_window

    normalized_target = re.sub(r"\s+", " ", target.lower()).strip()
    if normalized_target in LOCATION_ALIASES:
        return "folder", target, new_window
    return None


def _folder_bases() -> tuple[str, ...]:
    home = os.path.expanduser("~")
    bases = (home, os.environ.get("OneDrive", ""), os.path.join(home, "OneDrive"))
    return tuple(dict.fromkeys(base for base in bases if base))


def _standard_folder_path(name: str) -> str | None:
    for base in _folder_bases():
        candidate = os.path.join(base, name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _search_roots() -> list[str]:
    roots = []
    for name in SEARCH_FOLDER_NAMES:
        path = _standard_folder_path(name)
        if path is not None:
            roots.append(path)
    return list(dict.fromkeys(roots))


def _iter_targets(root: str) -> Iterable[str]:
    root_depth = root.rstrip(os.sep).count(os.sep)
    for current_path, directories, files in os.walk(root):
        depth = current_path.rstrip(os.sep).count(os.sep) - root_depth
        directories[:] = [
            name for name in directories
            if not name.startswith(".") and name.casefold() not in {
                "appdata", "node_modules", "venv", "__pycache__"
            }
        ]
        if depth >= MAX_SEARCH_DEPTH:
            directories.clear()

        for name in directories:
            yield os.path.join(current_path, name)
        for name in files:
            yield os.path.join(current_path, name)


def _matches_target_name(path: str, target_name: str) -> bool:
    name = os.path.basename(path)
    return (
        name.casefold() == target_name.casefold()
        or os.path.splitext(name)[0].casefold() == target_name.casefold()
    )


def _normalized_name(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _is_expected_kind(path: str, expected_kind: str | None) -> bool:
    return (
        (expected_kind != "file" or os.path.isfile(path))
        and (expected_kind != "folder" or os.path.isdir(path))
    )


def find_file_targets(
    target: str,
    roots: Iterable[str] | None = None,
    expected_kind: str | None = None,
) -> list[str]:
    cleaned_target = _clean_target(target)
    if not cleaned_target:
        return []

    alias = LOCATION_ALIASES.get(re.sub(r"\s+", " ", cleaned_target.lower()))
    if alias == "explorer":
        return [alias] if expected_kind != "file" else []
    if alias == "shell:MyComputerFolder" or alias == "shell:RecycleBinFolder":
        if expected_kind == "file":
            return []
        return [alias] if platform.system() == "Windows" else [os.path.expanduser("~")]
    if alias == "~":
        if expected_kind == "file":
            return []
        home = os.path.expanduser("~")
        return [home] if os.path.isdir(home) else []
    if alias:
        if expected_kind == "file":
            return []
        path = _standard_folder_path(alias)
        return [path] if path else []

    expanded_target = os.path.expandvars(os.path.expanduser(cleaned_target))
    if os.path.exists(expanded_target):
        if expected_kind == "file" and not os.path.isfile(expanded_target):
            return []
        if expected_kind == "folder" and not os.path.isdir(expanded_target):
            return []
        return [os.path.abspath(expanded_target)]

    target_name = os.path.basename(cleaned_target.rstrip("\\/"))
    if not target_name:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for root in roots if roots is not None else _search_roots():
        if not os.path.isdir(root):
            continue
        for path in _iter_targets(root):
            if not _matches_target_name(path, target_name):
                continue
            if not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path not in seen:
                seen.add(canonical_path)
                found.append(path)
                if len(found) >= MAX_RESULTS:
                    return found
    return found


def find_similar_file_targets(
    target: str,
    roots: Iterable[str] | None = None,
    expected_kind: str | None = None,
) -> list[str]:
    target_name = os.path.basename(_clean_target(target).rstrip("\\/"))
    query = _normalized_name(os.path.splitext(target_name)[0])
    if len(query) < 3:
        return []

    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    ranked_paths: set[str] = set()
    for root in roots if roots is not None else _search_roots():
        if not os.path.isdir(root):
            continue
        for path in _iter_targets(root):
            if not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path in seen:
                continue
            seen.add(canonical_path)

            candidate_name = os.path.basename(path)
            if os.path.isfile(path):
                candidate_name = os.path.splitext(candidate_name)[0]
            candidate = _normalized_name(candidate_name)
            if len(candidate) < 3:
                continue

            score = max(
                similarity(query, candidate),
                partial_similarity(query, candidate),
            )
            if candidate.startswith(query):
                score = max(score, 0.9)
            if score >= SIMILARITY_THRESHOLD:
                ranked.append((score, path))
                ranked_paths.add(canonical_path)

    if expected_kind != "file":
        for alias, folder_name in LOCATION_ALIASES.items():
            if folder_name not in SEARCH_FOLDER_NAMES:
                continue

            path = _standard_folder_path(folder_name)
            if path is None or not _is_expected_kind(path, expected_kind):
                continue
            canonical_path = os.path.normcase(os.path.abspath(path))
            if canonical_path in ranked_paths:
                continue

            candidate = _normalized_name(alias)
            if len(candidate) < 3:
                continue
            score = max(
                similarity(query, candidate),
                partial_similarity(query, candidate),
            )
            if candidate.startswith(query):
                score = max(score, 0.9)
            if score >= SIMILARITY_THRESHOLD:
                ranked.append((score, path))
                ranked_paths.add(canonical_path)

    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [path for _score, path in ranked[:MAX_RESULTS]]


def open_target(path: str, new_window: bool = False) -> None:
    if path == "explorer":
        if platform.system() == "Windows":
            args = ["explorer.exe"]
            if new_window:
                args.append("/n")
            subprocess.Popen(args)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", os.path.expanduser("~")])
        else:
            subprocess.Popen(["xdg-open", os.path.expanduser("~")])
        return

    if platform.system() == "Windows":
        if os.path.isdir(path):
            if new_window:
                open_folder_in_new_window(path)
            else:
                open_folder_in_new_tab(path)
        else:
            os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_folder_in_new_tab(path: str) -> None:
    if platform.system() != "Windows":
        raise NotImplementedError("Вкладки Провідника підтримуються лише у Windows")

    script = f"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class AssistantExplorerInput
{{
    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardInput
    {{
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }}

    [StructLayout(LayoutKind.Sequential)]
    private struct MouseInput
    {{
        public int X;
        public int Y;
        public uint Data;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }}

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {{
        [FieldOffset(0)]
        public KeyboardInput Keyboard;
        [FieldOffset(0)]
        public MouseInput Mouse;
    }}

    [StructLayout(LayoutKind.Sequential)]
    private struct Input
    {{
        public uint Type;
        public InputUnion Union;
    }}

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, Input[] inputs, int size);

    private static void SendKey(ushort virtualKey, ushort scanCode, uint flags)
    {{
        var input = new Input
        {{
            Type = 1,
            Union = new InputUnion
            {{
                Keyboard = new KeyboardInput
                {{
                    VirtualKey = virtualKey,
                    ScanCode = scanCode,
                    Flags = flags,
                    ExtraInfo = UIntPtr.Zero
                }}
            }}
        }};
        if (SendInput(1, new[] {{ input }}, Marshal.SizeOf(typeof(Input))) != 1)
            throw new InvalidOperationException("Не вдалося надіслати клавішу у Провідник.");
    }}

    public static void SendShortcut(ushort key)
    {{
        SendKey(0x11, 0, 0);
        SendKey(key, 0, 0);
        SendKey(key, 0, 2);
        SendKey(0x11, 0, 2);
    }}

    public static void TypeText(string text)
    {{
        foreach (char character in text)
        {{
            SendKey(0, character, 4);
            SendKey(0, character, 6);
        }}
    }}

    public static void PressKey(ushort key)
    {{
        SendKey(key, 0, 0);
        SendKey(key, 0, 2);
    }}
}}
'@

$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {{
    $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
}})
if ($windows.Count -eq 0) {{
    Write-Output 'no-window'
    exit 0
}}

$foreground = [AssistantExplorerInput]::GetForegroundWindow().ToInt64()
$window = $windows | Where-Object {{ [int64]$_.HWND -eq $foreground }} |
    Select-Object -First 1
if (-not $window) {{ $window = $windows[0] }}
if (-not [AssistantExplorerInput]::SetForegroundWindow([IntPtr]$window.HWND)) {{
    throw "Не вдалося активувати вікно Провідника."
}}

Start-Sleep -Milliseconds 150
[AssistantExplorerInput]::SendShortcut(0x54)
Start-Sleep -Milliseconds 300
[AssistantExplorerInput]::SendShortcut(0x4C)
[AssistantExplorerInput]::SendShortcut(0x41)
[AssistantExplorerInput]::TypeText($env:ASSISTANT_EXPLORER_TARGET)
[AssistantExplorerInput]::PressKey(0x0D)
Write-Output 'opened-tab'
"""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        env={**os.environ, "ASSISTANT_EXPLORER_TARGET": os.path.abspath(path)},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Не вдалося відкрити вкладку Провідника"
        raise RuntimeError(message)

    outcome = result.stdout.strip()
    if outcome == "no-window":
        subprocess.Popen(["explorer.exe", path])
    elif outcome != "opened-tab":
        raise RuntimeError("PowerShell повернув неочікувану відповідь під час відкриття вкладки")


def open_folder_in_new_window(path: str) -> None:
    if platform.system() != "Windows":
        open_target(path)
        return
    subprocess.Popen(["explorer.exe", "/n", path])


def _run_explorer_script(script: str) -> str:
    if platform.system() != "Windows":
        raise NotImplementedError("Керування Провідником підтримується лише у Windows")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Не вдалося керувати Провідником"
        raise RuntimeError(message)
    return result.stdout.strip()


def _active_explorer_window_script(action: str) -> str:
    return f"""
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices;
public static class AssistantExplorerWindow {{
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}}'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {{
    $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
}})
$foreground = [AssistantExplorerWindow]::GetForegroundWindow().ToInt64()
$matchingWindows = @($windows | Where-Object {{ [int64]$_.HWND -eq $foreground }})
if ($matchingWindows.Count -eq 0) {{
    Write-Output 'no-window'
    exit 0
}}
$window = $matchingWindows[0]
if ($matchingWindows.Count -gt 1) {{
    $root = [System.Windows.Automation.AutomationElement]::FromHandle(
        [IntPtr]$foreground
    )
    $tabViewCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        'TabView'
    )
    $tabView = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        $tabViewCondition
    )
    if (-not $tabView) {{
        throw "Не вдалося визначити активну вкладку Провідника."
    }}

    $tabItemCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TabItem
    )
    $tabItems = @($tabView.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $tabItemCondition
    ))
    $selectedTabIndex = -1
    for ($index = 0; $index -lt $tabItems.Count; $index++) {{
        $selection = $tabItems[$index].GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern
        )
        if ($selection.Current.IsSelected) {{
            $selectedTabIndex = $index
            break
        }}
    }}

    if ($selectedTabIndex -lt 0) {{
        throw "Не вдалося визначити активну вкладку Провідника."
    }}
    if ($tabItems.Count -eq $matchingWindows.Count) {{
        $window = $matchingWindows[$selectedTabIndex]
    }} else {{
        $selectedTabName = $tabItems[$selectedTabIndex].Current.Name
        $namedWindows = @($matchingWindows | Where-Object {{
            $_.Document.Folder.Self.Name -eq $selectedTabName
        }})
        if ($namedWindows.Count -ne 1) {{
            throw "Не вдалося зіставити активну вкладку Провідника з її папкою."
        }}
        $window = $namedWindows[0]
    }}
}}
{action}
"""


def get_active_explorer_path() -> str | None:
    script = _active_explorer_window_script(
        "Write-Output $window.Document.Folder.Self.Path"
    )
    path = _run_explorer_script(script)
    if not path or path == "no-window":
        return None
    return os.path.normpath(path)


def get_active_explorer_subfolders() -> list[str] | None:
    current_path = get_active_explorer_path()
    if current_path is None:
        return None

    if os.path.isdir(current_path):
        with os.scandir(current_path) as entries:
            folders = [
                entry.path
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            ]
    else:
        script = _active_explorer_window_script(
            """
$items = @($window.Document.Folder.Items() | Where-Object { $_.IsFolder })
$paths = @($items | ForEach-Object { [string]$_.Path })
ConvertTo-Json -InputObject $paths -Compress
"""
        )
        output = _run_explorer_script(script)
        if output == "no-window":
            return None
        try:
            folders = json.loads(output)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Провідник повернув некоректний список підпапок"
            ) from error
        if not isinstance(folders, list) or not all(
            isinstance(path, str) for path in folders
        ):
            raise RuntimeError("Провідник повернув некоректний список підпапок")

    return sorted(
        folders,
        key=lambda path: (
            os.path.basename(path.rstrip("\\/"))
            or os.path.splitdrive(path)[0]
            or path
        ).casefold(),
    )


def navigate_explorer_to(path: str) -> bool:
    script = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class AssistantExplorerNavigate
{
    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardInput
    {
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MouseInput
    {
        public int X;
        public int Y;
        public uint Data;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)]
        public KeyboardInput Keyboard;
        [FieldOffset(0)]
        public MouseInput Mouse;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Input
    {
        public uint Type;
        public InputUnion Union;
    }

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, Input[] inputs, int size);

    private static void SendKey(ushort virtualKey, ushort scanCode, uint flags)
    {
        var input = new Input
        {
            Type = 1,
            Union = new InputUnion
            {
                Keyboard = new KeyboardInput
                {
                    VirtualKey = virtualKey,
                    ScanCode = scanCode,
                    Flags = flags,
                    ExtraInfo = UIntPtr.Zero
                }
            }
        };
        if (SendInput(1, new[] { input }, Marshal.SizeOf(typeof(Input))) != 1)
            throw new InvalidOperationException("Не вдалося ввести шлях у Провідник.");
    }

    public static void NavigateTo(string path)
    {
        SendKey(0x11, 0, 0);
        SendKey(0x4C, 0, 0);
        SendKey(0x4C, 0, 2);
        SendKey(0x11, 0, 2);
        foreach (char character in path)
        {
            SendKey(0, character, 4);
            SendKey(0, character, 6);
        }
        SendKey(0x0D, 0, 0);
        SendKey(0x0D, 0, 2);
    }
}
'@

$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {
    $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
})
if ($windows.Count -eq 0) {
    Write-Output 'no-window'
    exit 0
}

$foreground = [AssistantExplorerNavigate]::GetForegroundWindow().ToInt64()
$window = $windows | Where-Object { [int64]$_.HWND -eq $foreground } |
    Select-Object -First 1
if (-not $window) { $window = $windows[0] }
if (-not [AssistantExplorerNavigate]::SetForegroundWindow([IntPtr]$window.HWND)) {
    throw "Не вдалося активувати вікно Провідника."
}

Start-Sleep -Milliseconds 150
[AssistantExplorerNavigate]::NavigateTo($env:ASSISTANT_EXPLORER_TARGET)
Write-Output 'navigated'
"""
    output = _run_explorer_script_with_env(
        script,
        {"ASSISTANT_EXPLORER_TARGET": os.path.abspath(path)},
    )
    return output == "navigated"


def navigate_explorer_back() -> bool:
    script = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class AssistantExplorerBack
{
    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardInput
    {
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MouseInput
    {
        public int X;
        public int Y;
        public uint Data;
        public uint Flags;
        public uint Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)]
        public KeyboardInput Keyboard;
        [FieldOffset(0)]
        public MouseInput Mouse;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Input
    {
        public uint Type;
        public InputUnion Union;
    }

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, Input[] inputs, int size);

    private static Input CreateKeyInput(ushort virtualKey, uint flags)
    {
        return new Input
        {
            Type = 1,
            Union = new InputUnion
            {
                Keyboard = new KeyboardInput
                {
                    VirtualKey = virtualKey,
                    Flags = flags,
                    ExtraInfo = UIntPtr.Zero
                }
            }
        };
    }

    public static void SendBackShortcut()
    {
        var inputs = new[]
        {
            CreateKeyInput(0x12, 0),
            CreateKeyInput(0x25, 0),
            CreateKeyInput(0x25, 2),
            CreateKeyInput(0x12, 2)
        };
        if (SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(Input))) != inputs.Length)
            throw new InvalidOperationException("Не вдалося надіслати команду «назад» у Провідник.");
    }
}
'@

$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {
    $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
})
if ($windows.Count -eq 0) {
    Write-Output 'no-window'
    exit 0
}

$foreground = [AssistantExplorerBack]::GetForegroundWindow().ToInt64()
$window = $windows | Where-Object { [int64]$_.HWND -eq $foreground } |
    Select-Object -First 1
if (-not $window) { $window = $windows[0] }
if (-not [AssistantExplorerBack]::SetForegroundWindow([IntPtr]$window.HWND)) {
    throw "Не вдалося активувати вікно Провідника."
}

Start-Sleep -Milliseconds 150
[AssistantExplorerBack]::SendBackShortcut()
Write-Output 'shortcut-sent'
"""
    return _run_explorer_script(script) == "shortcut-sent"


def get_open_explorer_tabs() -> list[ExplorerTab]:
    script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {
    $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
})
$tabs = @()
foreach ($group in @($windows | Group-Object { [string]$_.HWND })) {
    $hwnd = [int64]$group.Name
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$hwnd)
    $tabViewCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        'TabView'
    )
    $tabView = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        $tabViewCondition
    )
    if (-not $tabView) {
        throw "Не вдалося прочитати вкладки вікна Провідника."
    }
    $tabItemCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TabItem
    )
    $tabItems = @($tabView.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $tabItemCondition
    ))
    if ($tabItems.Count -ne $group.Group.Count) {
        throw "Не вдалося зіставити відкриті папки з вкладками Провідника."
    }
    for ($index = 0; $index -lt $group.Group.Count; $index++) {
        $window = $group.Group[$index]
        $tabs += [pscustomobject]@{
            Path = [string]$window.Document.Folder.Self.Path
            Name = [string]$window.Document.Folder.Self.Name
            Hwnd = $hwnd
            TabIndex = $index
        }
    }
}
ConvertTo-Json -InputObject @($tabs) -Compress
"""
    try:
        output = _run_explorer_script(script)
        data = json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError("Провідник повернув некоректний список вкладок") from error

    if not isinstance(data, list):
        raise RuntimeError("Провідник повернув некоректний список вкладок")

    tabs = []
    for item in data:
        if not isinstance(item, dict):
            raise RuntimeError("Провідник повернув некоректний список вкладок")
        path = item.get("Path")
        name = item.get("Name")
        hwnd = item.get("Hwnd")
        tab_index = item.get("TabIndex")
        if (
            not isinstance(path, str)
            or not isinstance(name, str)
            or not isinstance(hwnd, int)
            or not isinstance(tab_index, int)
        ):
            raise RuntimeError("Провідник повернув некоректні дані вкладки")
        tabs.append(ExplorerTab(path, name, hwnd, tab_index))
    return tabs


def find_open_explorer_folders(folder_name: str) -> list[ExplorerTab]:
    cleaned_name = _clean_target(folder_name)
    normalized_name = re.sub(r"\s+", " ", cleaned_name.casefold()).strip()
    alias = LOCATION_ALIASES.get(normalized_name)
    accepted_names = {_normalized_name(cleaned_name)}
    if alias:
        accepted_names.add(_normalized_name(alias))
        accepted_names.update(
            _normalized_name(alias_name)
            for alias_name, alias_target in LOCATION_ALIASES.items()
            if alias_target == alias
        )

    expanded_name = os.path.expandvars(os.path.expanduser(cleaned_name))
    requested_path = (
        os.path.normcase(os.path.abspath(expanded_name))
        if os.path.exists(expanded_name)
        else None
    )

    return [
        tab
        for tab in get_open_explorer_tabs()
        if (
            requested_path is not None
            and os.path.normcase(os.path.normpath(tab.path)) == requested_path
        )
        or _normalized_name(tab.name) in accepted_names
        or _normalized_name(os.path.basename(tab.path.rstrip("\\/"))) in accepted_names
    ]


def close_explorer_tab(tab: ExplorerTab) -> bool:
    script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AssistantExplorerTabClose
{
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr window);
}
'@
$hwnd = [int64]$env:ASSISTANT_EXPLORER_HWND
$tabIndex = [int]$env:ASSISTANT_EXPLORER_TAB_INDEX
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$hwnd)
$tabViewCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
    'TabView'
)
$tabView = $root.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    $tabViewCondition
)
if (-not $tabView) {
    throw "Не вдалося знайти вкладки Провідника."
}
$tabItemCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::TabItem
)
$tabItems = @($tabView.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    $tabItemCondition
))
if ($tabIndex -lt 0 -or $tabIndex -ge $tabItems.Count) {
    throw "Вкладка Провідника вже змінилася."
}
$selection = $tabItems[$tabIndex].GetCurrentPattern(
    [System.Windows.Automation.SelectionItemPattern]::Pattern
)
$selection.Select()
if (-not [AssistantExplorerTabClose]::SetForegroundWindow([IntPtr]$hwnd)) {
    throw "Не вдалося активувати вікно Провідника."
}
Start-Sleep -Milliseconds 150
[System.Windows.Forms.SendKeys]::SendWait('^{w}')
Write-Output 'close-sent'
"""
    output = _run_explorer_script_with_env(
        script,
        {
            "ASSISTANT_EXPLORER_HWND": str(tab.hwnd),
            "ASSISTANT_EXPLORER_TAB_INDEX": str(tab.tab_index),
        },
    )
    if output == "close-sent":
        return True
    if output == "no-window":
        return False
    raise RuntimeError("Провідник повернув неочікувану відповідь під час закриття вкладки")


def _run_explorer_script_with_env(script: str, extra_env: dict[str, str]) -> str:
    if platform.system() != "Windows":
        raise NotImplementedError("Керування Провідником підтримується лише у Windows")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        env={**os.environ, **extra_env},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Не вдалося керувати Провідником"
        raise RuntimeError(message)
    return result.stdout.strip()


def close_explorer_windows() -> int:
    if platform.system() != "Windows":
        raise NotImplementedError("Закриття вікон Провідника підтримується у Windows")

    script = (
        "$shell = New-Object -ComObject Shell.Application; "
        "$windows = @($shell.Windows() | Where-Object { "
        "$_.FullName -and "
        "[IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe' "
        "}); "
        "$count = $windows.Count; "
        "foreach ($window in $windows) { $window.Quit() }; "
        "Write-Output $count"
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Не вдалося закрити вікна Провідника"
        raise RuntimeError(message)
    try:
        return int(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError("PowerShell повернув некоректну кількість вікон") from error
