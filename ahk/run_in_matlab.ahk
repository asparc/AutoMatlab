#NoEnv  ; Recommended for performance and compatibility with future AutoHotkey releases.
; #Warn  ; Enable warnings to assist with detecting common errors.
; SetWorkingDir %A_ScriptDir%  ; Ensures a consistent starting directory.
SendMode Input  ; Recommended for new scripts due to its superior speed and reliability.

; Get ID of the Sublime window and Matlab window
SublimeID := WinExist("A")
MatlabID := WinExist("ahk_exe matlab.exe")

; Open Matlab window
if WinExist("ahk_id" . MatlabID) {
    WinActivate, ahk_id %MatlabID%
    Sleep 100
}
else {
    MsgBox,,Sublime AutoMatlab, AutoHotkey cannot find process matlab.exe.
    Exit
}

; Focus the Command window
if WinActive("ahk_id" . MatlabID) {
    Send ^0
    Sleep 200
}

; Insert and submit command
if WinActive("ahk_id" . MatlabID) {
    Send, %1%{Enter}
    Sleep 200
}

; Return to Sublime window
if WinActive("ahk_id" . MatlabID) {
    if %2% {
        WinActivate, ahk_id %SublimeID%
    }
}
