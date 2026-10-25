' stop.vbs — останавливает ELO Benchmark сервер (по pid-файлу и по маркеру процесса)

Option Explicit

Dim fso, sh, root, pidFile, stopped
Dim pid, stream, procs, proc, cl

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pidFile = root & "\data\logs\server.pid"
stopped = False

If fso.FileExists(pidFile) Then
    Set stream = fso.OpenTextFile(pidFile, 1)
    If Not stream.AtEndOfStream Then pid = Trim(stream.ReadAll)
    stream.Close
    If Len(pid) > 0 Then
        If KillPid(pid) Then stopped = True
    End If
    On Error Resume Next
    fso.DeleteFile pidFile
    On Error GoTo 0
End If

Set procs = GetObject("winmgmts:\\.\root\cimv2").ExecQuery( _
    "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='cmd.exe' OR Name='python.exe'")
For Each proc In procs
    cl = ""
    On Error Resume Next
    cl = proc.CommandLine
    On Error GoTo 0
    If Len(cl) > 0 Then
        If InStr(cl, "BENCHMARK_SILENT_LAUNCHER") > 0 _
           Or InStr(cl, "tools/server.py") > 0 _
           Or InStr(cl, "tools\server.py") > 0 Then
            If KillPid(CStr(proc.ProcessId)) Then stopped = True
        End If
    End If
Next

If stopped Then
    WScript.Echo "Сервер остановлен."
    WScript.Quit 0
End If

WScript.Echo "Сервер не запущен."
WScript.Quit 1

Function KillPid(processId)
    Dim rc
    rc = sh.Run("cmd /c taskkill /PID " & processId & " /T /F", 0, True)
    KillPid = (rc = 0)
End Function
