Option Explicit

Dim shell, fileSystem, projectPath, appDataPath, logPath, quote, command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectPath = fileSystem.GetParentFolderName(WScript.ScriptFullName)
appDataPath = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\FH6GarageAnalyzer"
logPath = appDataPath & "\launcher.log"
quote = Chr(34)

If Not fileSystem.FolderExists(appDataPath) Then
    fileSystem.CreateFolder(appDataPath)
End If

shell.CurrentDirectory = projectPath
command = "cmd.exe /d /c " & quote & quote & projectPath & "\run.bat" & quote _
    & " --hidden > " & quote & logPath & quote & " 2>&1" & quote

' Window style 0 keeps the launcher console hidden. False allows the script
' host to exit while dependency setup or the GUI continues in the background.
shell.Run command, 0, False
