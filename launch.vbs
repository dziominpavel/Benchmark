' launch.vbs — скрытый запуск ELO Benchmark сервера
'
' Запускает python tools/server.py в фоне, без видимого консольного окна,
' перенаправляет stdout/stderr в data/logs/server.log, сохраняет PID запускающего
' cmd в data/logs/server.pid и через 2 секунды открывает http://localhost:5000.

Option Explicit

Dim fso, WshShell, root, logDir, logFile, pidFile
Dim procCmd, WMI, procs, p
Dim i, found

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
logDir = root & "\data\logs"
logFile = logDir & "\server.log"
pidFile = logDir & "\server.pid"

' Создаём папку для логов
If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)

' Останавливаем предыдущий запуск (иначе DeleteFile лога даёт Permission denied)
Call KillExistingServer()
WScript.Sleep 300

' Очищаем старые файлы (лог может быть ещё на мгновение залочен — повторяем)
If Not SafeDelete(logFile) Then
    MsgBox "Не удалось очистить server.log — файл занят другим процессом." & vbCrLf & _
           "Закройте сервер через stop.bat и повторите запуск.", vbExclamation, "ELO Benchmark"
    WScript.Quit 1
End If
If fso.FileExists(pidFile) Then
    On Error Resume Next
    fso.DeleteFile pidFile
    On Error GoTo 0
End If

' Запускаем сервер в скрытой консоли через cmd /c.
' cmd ждёт завершения python, а stdout/stderr пишутся в data/logs/server.log.
' Маркер BENCHMARK_SILENT_LAUNCHER помогает найти cmd в WMI.
procCmd = "cmd /c " & Chr(34) & "cd /d " & Chr(34) & root & Chr(34) & " && " & Chr(34) & root & "\.venv\Scripts\python.exe" & Chr(34) & " tools/server.py > " & Chr(34) & "data/logs/server.log" & Chr(34) & " 2>&1 && rem BENCHMARK_SILENT_LAUNCHER" & Chr(34)

WshShell.Run procCmd, 0, False

' Даём процессу стартовать
WScript.Sleep 500

Set WMI = GetObject("winmgmts:\\.\root\cimv2")
found = False

' Ищем cmd с маркером и сохраняем его PID.
' stop.bat использует taskkill /T /PID, чтобы остановить всё дерево процессов.
Dim pidStream, cmdProc
For i = 1 To 10
    Set procs = WMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='cmd.exe' AND CommandLine LIKE '%BENCHMARK_SILENT_LAUNCHER%'")
    For Each cmdProc In procs
        found = True
        Set pidStream = fso.CreateTextFile(pidFile, True, False)
        pidStream.Write cmdProc.ProcessId
        pidStream.Close
        Exit For
    Next
    If found Then Exit For
    WScript.Sleep 100
Next

' Запасной вариант: ищем недавний python.exe с server.py в командной строке
If Not found Then
    Dim launchTime, pd, latestProc
    launchTime = ""
    Set procs = WMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe' AND CommandLine LIKE '%server.py%'")
    For Each p In procs
        pd = p.CreationDate
        If launchTime = "" Or pd > launchTime Then
            launchTime = pd
            Set latestProc = p
            found = True
        End If
    Next
    If found Then
        Set p = fso.CreateTextFile(pidFile, True, False)
        p.Write latestProc.ProcessId
        p.Close
    End If
End If

' Ждём, пока сервер стартует, и открываем браузер
WScript.Sleep 2000
WshShell.Run "http://localhost:5000", 1, False

' --- helpers ---

Sub KillExistingServer()
    Dim sh, pid, line, procs, proc
    Set sh = CreateObject("WScript.Shell")

    ' По pid-файлу
    If fso.FileExists(pidFile) Then
        Set line = fso.OpenTextFile(pidFile, 1)
        If Not line.AtEndOfStream Then pid = Trim(line.ReadAll)
        line.Close
        If Len(pid) > 0 Then
            On Error Resume Next
            sh.Run "cmd /c taskkill /PID " & pid & " /T /F", 0, True
            On Error GoTo 0
        End If
    End If

    ' Сироты без pid-файла / после неудачного stop
    On Error Resume Next
    Set procs = GetObject("winmgmts:\\.\root\cimv2").ExecQuery( _
        "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='cmd.exe' OR Name='python.exe'")
    For Each proc In procs
        If Not IsNull(proc.CommandLine) Then
            If InStr(proc.CommandLine, "BENCHMARK_SILENT_LAUNCHER") > 0 _
               Or InStr(proc.CommandLine, "tools/server.py") > 0 _
               Or InStr(proc.CommandLine, "tools\server.py") > 0 Then
                sh.Run "cmd /c taskkill /PID " & proc.ProcessId & " /T /F", 0, True
            End If
        End If
    Next
    On Error GoTo 0
End Sub

Function SafeDelete(path)
    Dim n
    SafeDelete = True
    If Not fso.FileExists(path) Then Exit Function
    For n = 1 To 10
        On Error Resume Next
        fso.DeleteFile path
        If Err.Number = 0 Then
            On Error GoTo 0
            Exit Function
        End If
        Err.Clear
        On Error GoTo 0
        WScript.Sleep 200
    Next
    SafeDelete = False
End Function
