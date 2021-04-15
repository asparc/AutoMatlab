#NoEnv  ; Recommended for performance and compatibility with future AutoHotkey releases.
; #Warn  ; Enable warnings to assist with detecting common errors.
; SetWorkingDir %A_ScriptDir%  ; Ensures a consistent starting directory.
SendMode Input  ; Recommended for new scripts due to its superior speed and reliability.

; inputs
; %1% - command to run in matlab
; %2% - command type: insert, paste, key
; %3% - return focus to sublime: (0) no, (1) yes
; %4% - sleep time multiplier (might vary across systems)

; Get ID of the Sublime window and Matlab window
SublimeID := WinExist("A")
MatlabID := WinExist("ahk_exe matlab.exe")

; Read command type (as string)
command_type = %2%

; Read sleep time multiplier (as double)
sleep_multiplier = %4%

if (command_type = "paste") {
    ; Copy command to clipboard
    ; (do this first, as this might take some time to complete in the background)
    SavedClip := ClipboardAll
    Clipboard = %1%
}

; Open Matlab window
if WinExist("ahk_id" . MatlabID) {
    WinActivate, ahk_id %MatlabID%
    slp := 100 * sleep_multiplier
    Sleep %slp%
}
else {
    MsgBox,,Sublime AutoMatlab, AutoHotkey cannot find process matlab.exe.
    if (command_type = "paste") {
        Clipboard := SavedClip
        SavedClip := ""
    }
    Exit
}

if (command_type = "key") {
    ; Send keyboard command
    if WinActive("ahk_id" . MatlabID) {
        SendInput %1%
        slp := 100 * sleep_multiplier
        Sleep %slp%
    }
}
else {
    ; Send text command

    ; Focus the Matlab Command window
    if WinActive("ahk_id" . MatlabID) {
        Send ^0
    }

    if (command_type = "paste") {
        ; Paste and submit text command
        slp := 300 * sleep_multiplier
        Sleep %slp%
        if WinActive("ahk_id" . MatlabID) {
            Send ^v
            SendInput {Enter}
            slp := 100 * sleep_multiplier
            Sleep %slp%
        }
    }
    else {
        ; Insert and submit text command
        slp := 200 * sleep_multiplier
        Sleep %slp%
        if WinActive("ahk_id" . MatlabID) {
            SendInput {Text}%1%
            SendInput {Enter}
            slp := 200 * sleep_multiplier
            Sleep %slp%
        }
    }
}

; Return to Sublime window
if WinActive("ahk_id" . MatlabID) {
    if %3% {
        WinActivate, ahk_id %SublimeID%
    }
}

if (command_type = "paste") {
    Clipboard := SavedClip
    SavedClip := ""
}