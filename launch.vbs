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

' Очищаем старые файлы
If fso.FileExists(logFile) Then fso.DeleteFile(logFile)
If fso.FileExists(pidFile) Then fso.DeleteFile(pidFile)

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
