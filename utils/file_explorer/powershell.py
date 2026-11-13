POWERSHELL_WIN32_HELPERS = r"""
if (-not ([System.Management.Automation.PSTypeName]'AssistantExplorerWindow').Type) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class AssistantExplorerWindow
{
    public const uint GA_ROOT = 2;
    public const int SW_RESTORE = 9;

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern IntPtr GetAncestor(IntPtr hwnd, uint gaFlags);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
}
'@
}
"""

POWERSHELL_SHELL_HELPERS = r"""
function Get-ExplorerShellWindows($Shell) {
    @($Shell.Windows() | Where-Object {
        $_.FullName -and [IO.Path]::GetFileName($_.FullName) -ieq 'explorer.exe'
    })
}
"""

POWERSHELL_EXPLORER_TAB_HELPERS = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-ExplorerTabView([IntPtr]$WindowHandle) {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($WindowHandle)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        'TabView'
    )
    $tabView = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Children,
        $condition
    )
    if (-not $tabView) {
        $tabView = $root.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            $condition
        )
    }
    if (-not $tabView) {
        throw "Не вдалося знайти вкладки Провідника."
    }
    $tabView
}

function Get-ExplorerTabItems($TabView) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TabItem
    )
    @($TabView.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $condition
    ))
}

function Get-SelectedExplorerTabIndex($TabItems) {
    for ($index = 0; $index -lt $TabItems.Count; $index++) {
        $selectionPattern = $null
        if ($TabItems[$index].TryGetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern,
            [ref]$selectionPattern
        ) -and $selectionPattern.Current.IsSelected) {
            return $index
        }
    }
    -1
}
"""

POWERSHELL_EXPLORER_HELPERS = (
    POWERSHELL_WIN32_HELPERS
    + POWERSHELL_SHELL_HELPERS
    + POWERSHELL_EXPLORER_TAB_HELPERS
)
