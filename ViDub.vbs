' ViDub launcher: runs the server hidden (no console window) and opens the browser.
Option Explicit
Dim fso, sh, dir, py, http, running
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

' Already running? -> just open the page
running = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP")
http.Open "GET", "http://127.0.0.1:7860/api/version", False
http.Send
If Err.Number = 0 Then If http.Status = 200 Then running = True
Err.Clear
On Error GoTo 0
If running Then
  sh.Run "http://localhost:7860", 1, False
  WScript.Quit
End If

py = ""
If fso.FileExists(dir & "\.venv\Scripts\pythonw.exe") Then
  py = dir & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists("E:\WorkSpace\Python\InstallNew\pythonw.exe") Then
  py = "E:\WorkSpace\Python\InstallNew\pythonw.exe"
End If
If py = "" Then
  MsgBox "ViDub chua duoc cai. Bam dup file Cai_dat.bat truoc.", 48, "ViDub"
  WScript.Quit
End If

sh.Environment("Process")("PYTHONIOENCODING") = "utf-8"
sh.Environment("Process")("PYTHONUTF8") = "1"
' 0 = hidden window; app.py opens the browser itself
sh.Run """" & py & """ """ & dir & "\app.py""", 0, False
