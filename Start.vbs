Set WshShell = CreateObject("WScript.Shell")
' Run git pull and start.bat silently (0 = Hide Window)
' We use cmd /c to chain the commands.
' If git pull fails, we still want to start, so we use & or just chain them linearly.
' To be safe against git hanging, we might just start the app, but requested was "first do git pull".
WshShell.Run "cmd /c git pull & start.bat", 0, False
