Set WshShell = CreateObject("WScript.Shell")
' Run start_silent.bat which handles git pull, pip install, and start.bat
' Redirect output to latest.log for debugging
WshShell.Run "cmd /c start_silent.bat > latest.log 2>&1", 0, False
