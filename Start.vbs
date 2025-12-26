Set WshShell = CreateObject("WScript.Shell")
' Run start_silent.bat which handles git pull, pip install, and start.bat
WshShell.Run "cmd /c start_silent.bat", 0, False
