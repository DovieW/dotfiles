#SingleInstance Force
#Requires AutoHotkey v2.0
#UseHook
A_MenuMaskKey := "vkE8"
SetWorkingDir A_ScriptDir
#Include *i private_hotstrings.v2.ahk

global LastMinimizedHwnd := 0

; ------------------------------------
; KILL TASK (doesn't work?)
; ------------------------------------

#+q:: {
    hwnd := WinGetID("A")                      ; get active window handle
    pid  := WinGetPID("ahk_id " hwnd)          ; get process ID
    RunWait "taskkill /PID " pid " /F", , "Hide"  ; force-kill the process
}

; ------------------------------------
; Minimize/Restore Window with Alt+Down / Alt+Up
; ------------------------------------

!Down:: {
    global LastMinimizedHwnd

    LastMinimizedHwnd := WinExist("A")
    WaitForModsUp()

    if LastMinimizedHwnd
        WinMinimize("ahk_id " LastMinimizedHwnd)

    ReleaseStickyModifiers()
}

; Doesn't work?
!Up:: {
    global LastMinimizedHwnd

    WaitForModsUp()

    if LastMinimizedHwnd && WinExist("ahk_id " LastMinimizedHwnd) {
        WinRestore("ahk_id " LastMinimizedHwnd)
        WinActivate("ahk_id " LastMinimizedHwnd)
    }

    ReleaseStickyModifiers()
}

; ------------------------------------
; Move window to virtual desktop
; ------------------------------------

!#Left:: {
    hWnd := WinExist("A") ; Get the unique ID of the active window
    WaitForModsUp()

    if hWnd {
        WinSetExStyle("^0x80", "ahk_id " hWnd)
        SendEvent "^#{Left}"
        Sleep 100
        WinSetExStyle("^0x80", "ahk_id " hWnd)
        WinActivate("ahk_id " hWnd)
    }

    ReleaseStickyModifiers()
}

!#Right:: {
    hWnd := WinExist("A") ; Get the unique ID of the active window
    WaitForModsUp()

    if hWnd {
        WinSetExStyle("^0x80", "ahk_id " hWnd)
        SendEvent "^#{Right}"
        Sleep 100
        WinSetExStyle("^0x80", "ahk_id " hWnd)
        WinActivate("ahk_id " hWnd)
    }

    ReleaseStickyModifiers()
}

; ------------------------------------
; Paste into an RDP window, with a delayed backup shortcut.
; ------------------------------------

ScrollLock::
{
    SendText A_Clipboard
}
^!+p:: ; Ctrl + Alt + Shift + P
{
    WaitForModsUp()
    Sleep 3000 ; Wait 3 seconds
    SendText A_Clipboard
    ReleaseStickyModifiers()
}

WaitForModsUp(timeout := 0.5) {
    for key in ["LControl", "RControl", "LAlt", "RAlt", "LWin", "RWin", "LShift", "RShift"] {
        KeyWait key, "T" timeout
    }

    ReleaseStickyModifiers()
}

ReleaseStickyModifiers() {
    SendEvent "{LCtrl up}{RCtrl up}{LAlt up}{RAlt up}{LWin up}{RWin up}{LShift up}{RShift up}"
}

; ------------------------------------
; Delete line of text
; ------------------------------------

^+Backspace:: {      ; Ctrl+Shift+Backspace hotkey
    WaitForModsUp()
    SendEvent "{Home}{Shift down}{End}{Shift up}{Del}"
    ReleaseStickyModifiers()
}

^!+Esc::ReleaseStickyModifiers()

; ------------------------------------
; Open Bitwarden from Task Tray with Ctrl+Shift+`
; ------------------------------------

; method 1
;^+`::TrayIcon_Button("Bitwarden.exe")
; method 2
;^+`:: {
;    DetectHiddenWindows True
;    if WinExist("ahk_class Chrome_WidgetWin_1 ahk_exe Bitwarden.exe") {
;        WinActivate
;    }
;}
; method 3
;TrayIcon_Click(TooltipTextOrExeName) {
    ;trayWindow := "ahk_class Shell_TrayWnd"
    ;trayNotify := "TrayNotifyWnd"
    ;sysPager := "SysPager"
    ;notifyIconOverflow := "NotifyIconOverflowWindow"

    ;for winClass in [trayWindow, notifyIconOverflow] {
        ;hwndTray := WinExist("ahk_class " winClass)
        ;if !hwndTray
            ;continue

        ;ControlGet hwndNotify, Hwnd,, TrayNotifyWnd, ahk_id %hwndTray%
        ;ControlGet hwndPager, Hwnd,, SysPager, ahk_id %hwndNotify%
        ;ControlGet hwndToolbar, Hwnd,, ToolbarWindow32, ahk_id %hwndPager%

        ;if !hwndToolbar
            ;continue

        ;iconCount := SendMessage(0x418, 0, 0, , "ahk_id " hwndToolbar)  ; TB_BUTTONCOUNT
;
        ;loop iconCount {
            ;index := A_Index - 1
            ;SendMessage(0x417, index, 0, , "ahk_id " hwndToolbar)  ; TB_GETBUTTON

            ;VarSetStrCapacity(btn, 32)
            ;NumPut("UInt", index, btn, 0)
            ;SendMessage(0x417, index, &btn, , "ahk_id " hwndToolbar)
;
            ;SendMessage(0x419, index, 0, , "ahk_id " hwndToolbar)  ; TB_GETBUTTONTEXT
            ;ToolTipText := ""  ; You would fetch the tooltip text here, but v2 is more complex

            ; For now, simulate a click on the icon by index:
            ; You’ll likely need Acc or ImageSearch if matching tooltip fails

            ; You can simulate a click at this point with DllCall("SendMessage", …)
        ;}
    ;}
;}
