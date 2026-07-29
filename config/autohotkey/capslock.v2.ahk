#Requires AutoHotkey v2.0
#SingleInstance Force

; ------------------------------------
; Caps lock to Esc and Control on hold
; ------------------------------------

SetCapsLockState("alwaysoff")
Esc::CapsLock
Capslock::
{
  Send("{LControl Down}")
  KeyWait("CapsLock")
  Send("{LControl Up}")
  if ( A_PriorKey = "CapsLock" )
  {
      Send("{Esc}")
  }
}
