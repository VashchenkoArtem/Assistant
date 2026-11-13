import os
import platform
import subprocess

from utils.file_explorer.powershell import (
    POWERSHELL_SHELL_HELPERS,
    POWERSHELL_WIN32_HELPERS,
)


def open_target(path: str, new_window: bool = False) -> None:
    if path == "ms-settings:":
        if platform.system() != "Windows":
            raise NotImplementedError("Налаштування Windows доступні лише у Windows")
        os.startfile(path)
        return

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

    script = POWERSHELL_WIN32_HELPERS + POWERSHELL_SHELL_HELPERS + r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$target = $env:ASSISTANT_EXPLORER_TARGET
if ([string]::IsNullOrWhiteSpace($target)) {
    throw "Змінна середовища ASSISTANT_EXPLORER_TARGET не задана."
}

$shell = New-Object -ComObject Shell.Application
$windows = @()
$heldComWindows = @{}
try {
    $windows = @(Get-ExplorerShellWindows $shell)

    if ($windows.Count -eq 0) {
        Write-Output 'no-window'
        exit 0
    }

    $foreground = [AssistantExplorerWindow]::GetForegroundWindow()
    $foregroundRoot = [IntPtr]::Zero
    if ($foreground -ne [IntPtr]::Zero) {
        $foregroundRoot = [AssistantExplorerWindow]::GetAncestor(
            $foreground,
            [AssistantExplorerWindow]::GA_ROOT
        )
        if ($foregroundRoot -eq [IntPtr]::Zero) {
            $foregroundRoot = $foreground
        }
    }

    $targetRoot = [IntPtr]::Zero
    if ($foregroundRoot -ne [IntPtr]::Zero) {
        foreach ($candidate in $windows) {
            $candidateHwnd = [IntPtr][int64]$candidate.HWND
            $candidateRoot = [AssistantExplorerWindow]::GetAncestor(
                $candidateHwnd,
                [AssistantExplorerWindow]::GA_ROOT
            )
            if ($candidateRoot -eq [IntPtr]::Zero) {
                $candidateRoot = $candidateHwnd
            }
            if ($candidateRoot -eq $foregroundRoot) {
                $targetRoot = $candidateRoot
                break
            }
        }
    }
    if ($targetRoot -eq [IntPtr]::Zero) {
        $firstHwnd = [IntPtr][int64]$windows[0].HWND
        $targetRoot = [AssistantExplorerWindow]::GetAncestor(
            $firstHwnd,
            [AssistantExplorerWindow]::GA_ROOT
        )
        if ($targetRoot -eq [IntPtr]::Zero) {
            $targetRoot = $firstHwnd
        }
    }

    $existingComIds = @{}
    foreach ($existingWindow in $windows) {
        $unknown = [System.Runtime.InteropServices.Marshal]::GetIUnknownForObject(
            $existingWindow
        )
        try {
            $existingComIds[$unknown.ToInt64()] = $true
            $heldComWindows[$unknown.ToInt64()] = $existingWindow
        } finally {
            [void][System.Runtime.InteropServices.Marshal]::Release($unknown)
        }
    }

    $rootElement = [System.Windows.Automation.AutomationElement]::FromHandle(
        $targetRoot
    )
    $buttonCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    )
    $buttons = $rootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $buttonCondition
    )
    $newTabButton = $null
    foreach ($button in $buttons) {
        $automationId = $button.Current.AutomationId
        $name = $button.Current.Name
        if (
            $automationId -in @('NewTabButton', 'AddTabButton', 'AddButton') -or
            $name -match '^(New tab|Add New Tab|Нова вкладка|Новая вкладка)(\s*\(.*\))?$'
        ) {
            $newTabButton = $button
            break
        }
    }
    if (-not $newTabButton) {
        throw "Не вдалося знайти кнопку створення вкладки Провідника."
    }

    $invokePattern = $null
    if (-not $newTabButton.TryGetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern,
        [ref]$invokePattern
    )) {
        throw "Кнопка нової вкладки Провідника не підтримує InvokePattern."
    }
    $invokePattern.Invoke()

    $newWindow = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while (-not $newWindow -and [DateTime]::UtcNow -lt $deadline) {
        $currentWindows = @(Get-ExplorerShellWindows $shell)
        foreach ($candidate in $currentWindows) {
            $candidateHwnd = [IntPtr][int64]$candidate.HWND
            $candidateRoot = [AssistantExplorerWindow]::GetAncestor(
                $candidateHwnd,
                [AssistantExplorerWindow]::GA_ROOT
            )
            if ($candidateRoot -eq [IntPtr]::Zero) {
                $candidateRoot = $candidateHwnd
            }
            if ($candidateRoot -ne $targetRoot) {
                continue
            }

            $unknown = [System.Runtime.InteropServices.Marshal]::GetIUnknownForObject(
                $candidate
            )
            try {
                $identity = $unknown.ToInt64()
            } finally {
                [void][System.Runtime.InteropServices.Marshal]::Release($unknown)
            }
            if (-not $existingComIds.ContainsKey($identity)) {
                $newWindow = $candidate
                $heldComWindows[$identity] = $candidate
                break
            }
        }
        if (-not $newWindow) {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $newWindow) {
        throw "Не вдалося визначити створену вкладку Провідника."
    }

    $newWindow.Navigate2($target)
    Write-Output 'opened-tab'
} finally {
    foreach ($heldWindow in $heldComWindows.Values) {
        if ($heldWindow -and [System.Runtime.InteropServices.Marshal]::IsComObject($heldWindow)) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($heldWindow)
        }
    }
    if ($shell -and [System.Runtime.InteropServices.Marshal]::IsComObject($shell)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}
"""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$utf8 = New-Object System.Text.UTF8Encoding($false)\n"
                "[Console]::OutputEncoding = $utf8\n"
                "$OutputEncoding = $utf8\n"
                + script
            ),
        ],
        env={**os.environ, "ASSISTANT_EXPLORER_TARGET": os.path.abspath(path)},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Не вдалося відкрити папку в новій вкладці Провідника.")

    outcome = result.stdout.strip()
    if outcome == "no-window":
        subprocess.Popen(["explorer.exe", path])
    elif outcome != "opened-tab":
        raise RuntimeError("PowerShell повернув неочікувану відповідь під час відкриття вкладки")


def open_folder_in_new_window(path: str) -> None:
    if platform.system() != "Windows":
        open_target(path)
        return
    subprocess.Popen(["explorer.exe", "/n,", "/e,", os.path.abspath(path)])
