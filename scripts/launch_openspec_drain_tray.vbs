Option Explicit

If WScript.Arguments.Count < 1 Or WScript.Arguments.Count > 2 Then
    WScript.Quit 2
End If

Dim shell, fileSystem, scriptDirectory, trayScript, repoPath, command, exitCode, preserveStop
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

scriptDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
trayScript = fileSystem.BuildPath(scriptDirectory, "openspec_drain_tray.ps1")
repoPath = WScript.Arguments(0)
preserveStop = False
If WScript.Arguments.Count = 2 Then
    If LCase(WScript.Arguments(1)) <> "--preserve-stop" Then
        WScript.Quit 2
    End If
    preserveStop = True
End If
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden" _
    & " -File " & QuoteArgument(trayScript) _
    & " -Repo " & QuoteArgument(repoPath)
If preserveStop Then
    command = command & " -PreserveStop"
End If

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

Function QuoteArgument(value)
    QuoteArgument = Chr(34) & Replace(value, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
