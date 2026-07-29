; Home Row Mods for AutoHotkey v2

#Requires AutoHotkey v2.0
#SingleInstance force

; --- Configuration ---
global TAPPING_TERM := 200 ; Tapping term in milliseconds. Adjust as needed.
global ComboKeys := Map()

; --- Left Hand ---
CreateMod("a", "LWin")
CreateMod("s", "LAlt")
CreateMod("d", "LShift")
CreateMod("f", "LCtrl")

; --- Right Hand ---
CreateMod("j", "RCtrl")
CreateMod("k", "RShift")
CreateMod("l", "RAlt")
CreateMod(";", "RWin")

; --- Combos ---
; F + J = Escape
Hotkey "~f", (*) => KeyCombo("j", "{Esc}")
Hotkey "~j", (*) => KeyCombo("f", "{Esc}")

; D + K = Caps Word (Toggle CapsLock)
Hotkey "~d", (*) => KeyCombo("k", "{CapsLock}")
Hotkey "~k", (*) => KeyCombo("d", "{CapsLock}")


; --- Core Functions ---

CreateMod(key, mod) {
    Hotkey("~*" key, (*) => KeyDown(key, mod))
    Hotkey("~*" key " Up", (*) => KeyUp(key, mod))
}

KeyDown(key, mod) {
    global TAPPING_TERM
    if !KeyWait(key, "T" TAPPING_TERM / 1000) { ; Timed out, so treat as modifier
        Send("{" mod " Down}")
    }
}

KeyUp(key, mod) {
    global TAPPING_TERM
    if GetKeyState(mod, "L") { ; If logical state is down, it was used as a modifier
        Send("{" mod " Up}")
    } else { ; Was not used as a modifier, so it's a tap
        if (A_TimeSinceThisHotkey < TAPPING_TERM) {
            if (IsComboActive(key)) {
                return ; Part of a combo, don't send key
            }
            Send("{" key "}")
        }
    }
}

KeyCombo(otherKey, result) {
    if (GetKeyState(otherKey, "P")) {
        Send(result)
        ; Mark keys as part of a combo to prevent tap action
        global ComboKeys
        ComboKeys[A_ThisHotkey.Replace("~*", "")] := true
        ComboKeys[otherKey] := true
        SetTimer ClearComboKeys, -100 ; Clear after a short delay
    }
}

ClearComboKeys() {
    global ComboKeys
    ComboKeys.Clear()
}

IsComboActive(key) {
    global ComboKeys
    try {
        return ComboKeys.Has(key)
    } catch {
        return false
    }
}
