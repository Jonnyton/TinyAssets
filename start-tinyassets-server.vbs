' Silent launcher - no console window flicker
' Runs start-tinyassets-server.bat completely hidden

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c start-tinyassets-server.bat", 0, False
