import json
import os
import platform
import re
import subprocess

from utils.file_explorer.models import ExplorerTab, ExplorerWindow
from utils.file_explorer.powershell import POWERSHELL_EXPLORER_HELPERS
from utils.file_explorer.targets import (
    LOCATION_ALIASES,
    _clean_target,
    _normalized_name,
)

POWERSHELL_UTF8_SETUP = (
    "$utf8 = New-Object System.Text.UTF8Encoding($false)\n"
    "[Console]::OutputEncoding = $utf8\n"
    "$OutputEncoding = $utf8\n"
)


def _run_explorer_script(script: str) -> str:
    if platform.system() != "Windows":
        raise NotImplementedError("Керування Провідником підтримується лише у Windows")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            POWERSHELL_UTF8_SETUP + script,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Не вдалося керувати Провідником"
        raise RuntimeError(message)
    return result.stdout.strip()


def _active_explorer_window_script(
    action: str,
    fallback_to_first: bool = False,
) -> str:
    fallback_value = "$true" if fallback_to_first else "$false"
    return f"""
{POWERSHELL_EXPLORER_HELPERS}
$fallbackToFirst = {fallback_value}
$foreground = [AssistantExplorerWindow]::GetForegroundWindow()
if ($foreground -eq [IntPtr]::Zero -and -not $fallbackToFirst) {{
    Write-Output 'no-window'
    exit 0
}}
$foregroundRoot = [IntPtr]::Zero
if ($foreground -ne [IntPtr]::Zero) {{
    $foregroundRoot = [AssistantExplorerWindow]::GetAncestor(
        $foreground,
        [AssistantExplorerWindow]::GA_ROOT
    )
}}

$shell = New-Object -ComObject Shell.Application
$shellWindows = $null
$allWindows = @()
try {{
    $shellWindows = $shell.Windows()
    $allWindows = @($shellWindows)
    $windows = @(Get-ExplorerShellWindows $shell)
    if ($windows.Count -eq 0) {{
        Write-Output 'no-window'
        exit 0
    }}

    $targetRoot = [IntPtr]::Zero
    if ($foregroundRoot -ne [IntPtr]::Zero) {{
        foreach ($candidate in $windows) {{
            $candidateRoot = [AssistantExplorerWindow]::GetAncestor(
                [IntPtr][int64]$candidate.HWND,
                [AssistantExplorerWindow]::GA_ROOT
            )
            if ($candidateRoot -eq $foregroundRoot) {{
                $targetRoot = $candidateRoot
                break
            }}
        }}
    }}
    if ($targetRoot -eq [IntPtr]::Zero) {{
        if (-not $fallbackToFirst) {{
            Write-Output 'no-window'
            exit 0
        }}
        $targetRoot = [AssistantExplorerWindow]::GetAncestor(
            [IntPtr][int64]$windows[0].HWND,
            [AssistantExplorerWindow]::GA_ROOT
        )
        if ($targetRoot -eq [IntPtr]::Zero) {{
            throw "Не вдалося визначити вікно Провідника."
        }}
    }}

    $matchingWindows = @($windows | Where-Object {{
        [AssistantExplorerWindow]::GetAncestor(
            [IntPtr][int64]$_.HWND,
            [AssistantExplorerWindow]::GA_ROOT
        ) -eq $targetRoot
    }})
    if ($matchingWindows.Count -eq 0) {{
        throw "У вибраному вікні немає вкладок Провідника."
    }}
    if ($matchingWindows.Count -eq 1) {{
        $window = $matchingWindows[0]
    }} else {{
        $tabView = Get-ExplorerTabView $targetRoot
        $tabItems = @(Get-ExplorerTabItems $tabView)
        $selectedTabIndex = Get-SelectedExplorerTabIndex $tabItems

        if ($selectedTabIndex -lt 0) {{
            throw "Не вдалося визначити активну вкладку Провідника."
        }}

        $selectedTabName = $tabItems[$selectedTabIndex].Current.Name
        $namedWindows = @()
        foreach ($candidate in $matchingWindows) {{
            $candidateNames = @()
            try {{
                $candidateNames += [string]$candidate.LocationName
            }} catch {{}}
            try {{
                $document = $candidate.Document
                if ($document) {{
                    $folder = $document.Folder
                    if ($folder) {{
                        $self = $folder.Self
                        if ($self) {{
                            $candidateNames += [string]$self.Name
                        }}
                    }}
                }}
            }} catch {{}}
            if ($candidateNames -contains $selectedTabName) {{
                $namedWindows += $candidate
            }}
        }}
        if ($namedWindows.Count -ne 1) {{
            throw "Не вдалося однозначно зіставити активну вкладку '$selectedTabName' з вкладкою Провідника."
        }}
        $window = $namedWindows[0]
    }}

    {action}
}}
finally {{
    foreach ($shellWindow in $allWindows) {{
        if ($shellWindow -and
            [System.Runtime.InteropServices.Marshal]::IsComObject($shellWindow)) {{
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shellWindow)
        }}
    }}
    if ($shellWindows -and
        [System.Runtime.InteropServices.Marshal]::IsComObject($shellWindows)) {{
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shellWindows)
    }}
    if ($shell) {{
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }}
}}
"""


def get_active_explorer_path() -> str | None:
    script = _active_explorer_window_script(
        """
$path = ''
try {
    $document = $window.Document
    if ($document) {
        $folder = $document.Folder
        if ($folder) {
            $self = $folder.Self
            if ($self) {
                $path = [string]$self.Path
            }
        }
    }
} catch {
    $path = ''
}

if (-not $path) {
    try {
        $locationUrl = [string]$window.LocationURL
        if ($locationUrl.StartsWith('file:', [StringComparison]::OrdinalIgnoreCase)) {
            $path = ([Uri]$locationUrl).LocalPath
        }
    } catch {
        $path = ''
    }
}
if (-not $path) {
    $locationName = [string]$window.LocationName
    if (-not $locationName) {
        throw "Не вдалося визначити шлях або назву активної вкладки Провідника."
    }
    $path = "shell:$locationName"
}
Write-Output $path
"""
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
$document = $window.Document
if (-not $document -or -not $document.Folder) {
    throw "Не вдалося отримати вміст активної вкладки Провідника."
}
$items = @($document.Folder.Items() | Where-Object { $_.IsFolder })
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
    script = _active_explorer_window_script(
        """
$target = $env:ASSISTANT_EXPLORER_TARGET
if ([string]::IsNullOrWhiteSpace($target)) {
    throw "Змінна оточення ASSISTANT_EXPLORER_TARGET не задана або порожня."
}

$targetHwnd = [IntPtr][int64]$window.HWND
$targetRoot = [AssistantExplorerWindow]::GetAncestor(
    $targetHwnd,
    [AssistantExplorerWindow]::GA_ROOT
)
if ($targetRoot -eq [IntPtr]::Zero) {
    $targetRoot = $targetHwnd
}
if ([AssistantExplorerWindow]::IsIconic($targetRoot)) {
    [void][AssistantExplorerWindow]::ShowWindow(
        $targetRoot,
        [AssistantExplorerWindow]::SW_RESTORE
    )
}

[void][AssistantExplorerWindow]::SetForegroundWindow($targetRoot)
$window.Navigate($target)
Write-Output 'navigated'
""",
        fallback_to_first=True,
    )
    output = _run_explorer_script_with_env(
        script,
        {"ASSISTANT_EXPLORER_TARGET": os.path.abspath(path)},
    )
    return output == "navigated"


def navigate_explorer_back() -> bool:
    script = _active_explorer_window_script(
        """
try {
    $window.GoBack()
} catch {
    throw "Не вдалося повернутися назад у вибраній вкладці Провідника: $($_.Exception.Message)"
}
Write-Output 'navigated-back'
""",
        fallback_to_first=True,
    )
    return _run_explorer_script(script) == "navigated-back"


def get_open_explorer_tabs() -> list[ExplorerTab]:
    script = POWERSHELL_EXPLORER_HELPERS + r"""
$shell = New-Object -ComObject Shell.Application
$shellWindows = $null
$allWindows = @()
$windows = @()
try {
    $shellWindows = $shell.Windows()
    $allWindows = @($shellWindows)
    $windows = @(Get-ExplorerShellWindows $shell)
    $tabs = @()
    foreach ($group in @($windows | Group-Object { [string]$_.HWND })) {
        $hwnd = [int64]$group.Name
        $tabView = Get-ExplorerTabView ([IntPtr]$hwnd)
        $tabItems = @(Get-ExplorerTabItems $tabView)
        if ($tabItems.Count -eq 0) {
            throw "UI Automation не повернув вкладок для вікна Провідника."
        }

        $comTabs = @()
        for ($comIndex = 0; $comIndex -lt $group.Group.Count; $comIndex++) {
            $window = $group.Group[$comIndex]
            $locationName = ''
            try {
                $locationName = [string]$window.LocationName
            } catch {
                $locationName = ''
            }
            $folderName = ''
            $path = ''
            $document = $null
            try {
                $document = $window.Document
            } catch {
                $document = $null
            }
            if ($document) {
                $folder = $null
                try {
                    $folder = $document.Folder
                } catch {
                    $folder = $null
                }
                if ($folder) {
                    $self = $null
                    try {
                        $self = $folder.Self
                    } catch {
                        $self = $null
                    }
                    if ($self) {
                        try {
                            $folderName = [string]$self.Name
                        } catch {
                            $folderName = ''
                        }
                        try {
                            $path = [string]$self.Path
                        } catch {
                            $path = ''
                        }
                    }
                }
            }
            if (-not $path) {
                $locationUrl = ''
                try {
                    $locationUrl = [string]$window.LocationURL
                } catch {
                    $locationUrl = ''
                }
                if ($locationUrl.StartsWith('file:', [StringComparison]::OrdinalIgnoreCase)) {
                    $path = ([Uri]$locationUrl).LocalPath
                } else {
                    $path = $locationUrl
                }
            }
            if (-not $path) {
                $virtualName = if ($locationName) { $locationName } else { $folderName }
                if (-not $virtualName) {
                    throw "Не вдалося визначити шлях або назву вкладки Провідника."
                }
                $path = "shell:$virtualName"
            }

            $comTabs += [pscustomobject]@{
                Index = $comIndex
                Path = $path
                LocationName = $locationName
                FolderName = $folderName
            }
        }

        $usedComIndexes = @{}
        for ($tabIndex = 0; $tabIndex -lt $tabItems.Count; $tabIndex++) {
            $tabName = [string]$tabItems[$tabIndex].Current.Name
            $candidates = @($comTabs | Where-Object {
                -not $usedComIndexes.ContainsKey($_.Index) -and
                    ($_.LocationName -eq $tabName -or $_.FolderName -eq $tabName)
            })
            if ($candidates.Count -eq 0) {
                if (-not $tabName) {
                    throw "Не вдалося визначити назву вкладки Провідника."
                }
                $tabs += [pscustomobject]@{
                    Path = "shell:$tabName"
                    Name = $tabName
                    Hwnd = $hwnd
                    TabIndex = $tabIndex
                }
                continue
            } elseif ($candidates.Count -gt 1) {
                $candidatePaths = @($candidates | Select-Object -ExpandProperty Path -Unique)
                if ($candidatePaths.Count -gt 1) {
                    throw "Назва вкладки '$tabName' відповідає кільком різним шляхам."
                }
            }

            $candidate = $candidates[0]
            $usedComIndexes[$candidate.Index] = $true
            $tabs += [pscustomobject]@{
                Path = $candidate.Path
                Name = if ($tabName) { $tabName } else { $candidate.LocationName }
                Hwnd = $hwnd
                TabIndex = $tabIndex
            }
        }
    }
    ConvertTo-Json -InputObject @($tabs) -Compress
}
finally {
    foreach ($window in $allWindows) {
        if ($window -and [System.Runtime.InteropServices.Marshal]::IsComObject($window)) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($window)
        }
    }
    if ($shellWindows -and
        [System.Runtime.InteropServices.Marshal]::IsComObject($shellWindows)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shellWindows)
    }
    if ($shell -and [System.Runtime.InteropServices.Marshal]::IsComObject($shell)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}
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


def get_open_explorer_windows() -> list[ExplorerWindow]:
    windows: dict[int, list[ExplorerTab]] = {}
    for tab in get_open_explorer_tabs():
        windows.setdefault(tab.hwnd, []).append(tab)
    return [
        ExplorerWindow(hwnd, tuple(tabs))
        for hwnd, tabs in windows.items()
    ]


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
    script = POWERSHELL_EXPLORER_HELPERS + r"""
Add-Type -AssemblyName System.Windows.Forms
$hwnd = [int64]$env:ASSISTANT_EXPLORER_HWND
$tabIndex = [int]$env:ASSISTANT_EXPLORER_TAB_INDEX
$tabView = Get-ExplorerTabView ([IntPtr]$hwnd)
$tabItems = @(Get-ExplorerTabItems $tabView)
if ($tabIndex -lt 0 -or $tabIndex -ge $tabItems.Count) {
    throw "Вкладка Провідника вже змінилася."
}
$tabItem = $tabItems[$tabIndex]
$closeButtonCondition = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        'CloseButton'
    )),
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    ))
)
$closeButton = $tabItem.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    $closeButtonCondition
)
if ($closeButton) {
    $invokePattern = $null
    if ($closeButton.TryGetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern,
        [ref]$invokePattern
    )) {
        $invokePattern.Invoke()
        Write-Output 'close-invoked'
        exit 0
    }
}

$selectionPattern = $null
if (-not $tabItem.TryGetCurrentPattern(
    [System.Windows.Automation.SelectionItemPattern]::Pattern,
    [ref]$selectionPattern
)) {
    throw "Не вдалося вибрати вкладку Провідника."
}
$selectionPattern.Select()
if (-not [AssistantExplorerWindow]::SetForegroundWindow([IntPtr]$hwnd)) {
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
    if output == "close-invoked":
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
            POWERSHELL_UTF8_SETUP + script,
        ],
        env={**os.environ, **extra_env},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
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

    script = POWERSHELL_EXPLORER_HELPERS + r"""
$shell = New-Object -ComObject Shell.Application
$shellWindows = $null
$allWindows = @()
try {
    $shellWindows = $shell.Windows()
    $allWindows = @(Get-ExplorerShellWindows $shell)
    $handles = @($allWindows | ForEach-Object { [int64]$_.HWND } | Select-Object -Unique)
    foreach ($handle in $handles) {
        if (-not [AssistantExplorerWindow]::PostMessage(
            [IntPtr]$handle,
            0x0010,
            [IntPtr]::Zero,
            [IntPtr]::Zero
        )) {
            throw "Не вдалося надіслати команду закриття вікну Провідника."
        }
    }
    Write-Output $handles.Count
}
finally {
    foreach ($window in $allWindows) {
        if ($window -and [System.Runtime.InteropServices.Marshal]::IsComObject($window)) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($window)
        }
    }
    if ($shellWindows -and
        [System.Runtime.InteropServices.Marshal]::IsComObject($shellWindows)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shellWindows)
    }
    if ($shell -and [System.Runtime.InteropServices.Marshal]::IsComObject($shell)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}
"""
    output = _run_explorer_script(script)
    try:
        return int(output)
    except ValueError as error:
        raise RuntimeError("PowerShell повернув некоректну кількість вікон") from error


def close_explorer_window(hwnd: int) -> bool:
    script = POWERSHELL_EXPLORER_HELPERS + r"""
$targetHwnd = [int64]$env:ASSISTANT_EXPLORER_HWND
$shell = New-Object -ComObject Shell.Application
$shellWindows = $null
$allWindows = @()
try {
    $shellWindows = $shell.Windows()
    $allWindows = @(Get-ExplorerShellWindows $shell)
    $matchingExplorerWindows = @(
        $allWindows | Where-Object { [int64]$_.HWND -eq $targetHwnd }
    )
    if ($matchingExplorerWindows.Count -eq 0) {
        Write-Output 'no-window'
        exit 0
    }
    if (-not [AssistantExplorerWindow]::PostMessage(
        [IntPtr]$targetHwnd,
        0x0010,
        [IntPtr]::Zero,
        [IntPtr]::Zero
    )) {
        throw "Не вдалося надіслати команду закриття вікну Провідника."
    }
    Write-Output 'closed'
}
finally {
    foreach ($window in $allWindows) {
        if ($window -and [System.Runtime.InteropServices.Marshal]::IsComObject($window)) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($window)
        }
    }
    if ($shellWindows -and
        [System.Runtime.InteropServices.Marshal]::IsComObject($shellWindows)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shellWindows)
    }
    if ($shell -and [System.Runtime.InteropServices.Marshal]::IsComObject($shell)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}
"""
    output = _run_explorer_script_with_env(
        script,
        {"ASSISTANT_EXPLORER_HWND": str(hwnd)},
    )
    if output == "closed":
        return True
    if output == "no-window":
        return False
    raise RuntimeError("Провідник повернув неочікувану відповідь під час закриття вікна")
