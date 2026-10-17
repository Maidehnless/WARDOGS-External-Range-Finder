Option Explicit
' WARDOGS Range Finder launcher v1.2.0.
' Keep this file beside wd_rf.py. No separate installer BAT is needed.
Dim shell, fso, folder, appFile, probeFile, pythonExe, guiExe
Dim setupCode, setupResult, powershell, result
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
appFile = fso.BuildPath(folder, "wd_rf.py")
If Not fso.FileExists(appFile) Then
    MsgBox "Place wd_rf.py in the same folder as RUN ME.vbs, then try again.", vbExclamation, "WARDOGS Range Finder"
    WScript.Quit 1
End If
probeFile = fso.BuildPath(fso.GetSpecialFolder(2), fso.GetTempName)
pythonExe = FindPython()
If pythonExe = "" Then
    setupCode = ""
    setupCode = setupCode & "$ErrorActionPreference = 'Stop'" & vbCrLf
    setupCode = setupCode & "$installer = $null" & vbCrLf
    setupCode = setupCode & "$exitCode = 1" & vbCrLf
    setupCode = setupCode & "try {" & vbCrLf
    setupCode = setupCode & "    $Host.UI.RawUI.WindowTitle = 'WARDOGS Range Finder - Python Setup'" & vbCrLf
    setupCode = setupCode & "    Write-Host 'Installing Python with Tkinter. Windows will request administrator permission.'" & vbCrLf
    setupCode = setupCode & "    $arch = $env:PROCESSOR_ARCHITECTURE" & vbCrLf
    setupCode = setupCode & "    if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }" & vbCrLf
    setupCode = setupCode & "    switch ($arch.ToUpperInvariant()) {" & vbCrLf
    setupCode = setupCode & "        'AMD64' { $file = 'python-3.13.16-amd64.exe'; $hash = 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b' }" & vbCrLf
    setupCode = setupCode & "        'ARM64' { $file = 'python-3.13.16-arm64.exe'; $hash = '696e2226062c6ec3622c13f143d28336a856968518e49cb4f4c62513215a4f5d' }" & vbCrLf
    setupCode = setupCode & "        'X86' { $file = 'python-3.13.16.exe'; $hash = '394ca84150ea428db952cb617c1163c49fbc30e47ec53048c26e6ae44265df07' }" & vbCrLf
    setupCode = setupCode & "        default { throw ('Unsupported Windows architecture: ' + $arch) }" & vbCrLf
    setupCode = setupCode & "    }" & vbCrLf
    setupCode = setupCode & "    $installer = Join-Path $env:TEMP ('wardogs-python-' + [Guid]::NewGuid().ToString('N') + '.exe')" & vbCrLf
    setupCode = setupCode & "    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12" & vbCrLf
    setupCode = setupCode & "    Write-Host 'Downloading Python 3.13.16 from python.org...'" & vbCrLf
    setupCode = setupCode & "    Invoke-WebRequest -Uri ('https://www.python.org/ftp/python/3.13.16/' + $file) -OutFile $installer -UseBasicParsing -TimeoutSec 180" & vbCrLf
    setupCode = setupCode & "    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ine $hash) { throw 'Python installer checksum did not match. Installation cancelled.' }" & vbCrLf
    setupCode = setupCode & "    Write-Host 'Download verified. Installing Python and Tkinter...'" & vbCrLf
    setupCode = setupCode & "    $arguments = '/quiet InstallAllUsers=1 Include_launcher=1 InstallLauncherAllUsers=1 PrependPath=1 Include_tcltk=1 Include_pip=1 Include_test=0'" & vbCrLf
    setupCode = setupCode & "    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Verb RunAs -Wait -PassThru" & vbCrLf
    setupCode = setupCode & "    $exitCode = $process.ExitCode" & vbCrLf
    setupCode = setupCode & "    if ($exitCode -notin @(0, 3010)) { throw ('Python installer exited with code ' + $exitCode) }" & vbCrLf
    setupCode = setupCode & "    Write-Host 'Python setup finished. Starting the Range Finder...'" & vbCrLf
    setupCode = setupCode & "} catch {" & vbCrLf
    setupCode = setupCode & "    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red" & vbCrLf
    setupCode = setupCode & "    $exitCode = 1" & vbCrLf
    setupCode = setupCode & "    [void](Read-Host 'Press Enter to close')" & vbCrLf
    setupCode = setupCode & "} finally {" & vbCrLf
    setupCode = setupCode & "    if ($installer -and (Test-Path -LiteralPath $installer)) {" & vbCrLf
    setupCode = setupCode & "        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue" & vbCrLf
    setupCode = setupCode & "    }" & vbCrLf
    setupCode = setupCode & "}" & vbCrLf
    setupCode = setupCode & "exit $exitCode" & vbCrLf
    powershell = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
    setupResult = RunCommand(Quote(powershell) & " -NoProfile -EncodedCommand " & EncodePowerShell(setupCode), 1, True)
    If setupResult <> 0 And setupResult <> 3010 Then
        DeleteProbe
        MsgBox "Python setup did not complete. Run this launcher again when you are ready to retry.", vbExclamation, "WARDOGS Range Finder"
        WScript.Quit 1
    End If
    pythonExe = FindPython()
    If pythonExe = "" Then
        DeleteProbe
        MsgBox "Python setup finished, but a compatible Python with Tkinter could not be started. Restart Windows, then try again.", vbExclamation, "WARDOGS Range Finder"
        WScript.Quit 1
    End If
End If
DeleteProbe

' Run the update check to completion before loading the application's code.
' Then use the exact interpreter we checked, without relying on a refreshed PATH.
guiExe = fso.BuildPath(fso.GetParentFolderName(pythonExe), "pythonw.exe")
If Not fso.FileExists(guiExe) Then guiExe = pythonExe
result = RunCommand(Quote(guiExe) & " " & Quote(appFile) & " --check-updates", 0, True)
If result <> 0 And result <> 10 Then
    MsgBox "The update check could not complete. The installed version will be opened.", vbExclamation, "WARDOGS Range Finder"
End If
result = RunCommand(Quote(guiExe) & " " & Quote(appFile) & " --skip-update", 0, True)
If result <> 0 Then
    MsgBox "The Range Finder could not run successfully. Try running wd_rf.py directly to see the error.", vbExclamation, "WARDOGS Range Finder"
End If
WScript.Quit result

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function

Function RunCommand(command, windowStyle, waitForExit)
    On Error Resume Next
    Err.Clear
    RunCommand = shell.Run(command, windowStyle, waitForExit)
    If Err.Number <> 0 Then
        RunCommand = -1
        Err.Clear
    End If
    On Error GoTo 0
End Function

Function FindPython()
    Dim candidate, found, base
    FindPython = ""
    For Each candidate In Array("py -3", "py -3.13")
        found = ProbePython(candidate)
        If found <> "" Then
            FindPython = found
            Exit Function
        End If
    Next
    ' Explicit paths also work immediately after installation, before PATH refreshes.
    For Each base In Array("%ProgramW6432%\Python313", "%ProgramFiles%\Python313", "%LocalAppData%\Programs\Python\Python313")
        candidate = shell.ExpandEnvironmentStrings(base) & "\python.exe"
        If fso.FileExists(candidate) Then
            found = ProbePython(Quote(candidate))
            If found <> "" Then
                FindPython = found
                Exit Function
            End If
        End If
    Next
End Function

Function ProbePython(command)
    Dim code, exitCode, stream, found
    ProbePython = ""
    DeleteProbe
    code = "import sys, tkinter, pathlib; assert (3, 10) <= sys.version_info[:2] < (4, 0); r=tkinter.Tk(); r.withdraw(); r.update_idletasks(); r.destroy(); pathlib.Path(sys.argv[1]).write_text(sys.executable, encoding='utf-16')"
    exitCode = RunCommand(command & " -c " & Quote(code) & " " & Quote(probeFile), 0, True)
    If exitCode <> 0 Or Not fso.FileExists(probeFile) Then Exit Function
    On Error Resume Next
    Set stream = fso.OpenTextFile(probeFile, 1, False, -1)
    found = Trim(stream.ReadAll)
    stream.Close
    If Err.Number = 0 Then
        If fso.FileExists(found) Then ProbePython = found
    End If
    Err.Clear
    On Error GoTo 0
End Function

Sub DeleteProbe()
    On Error Resume Next
    If fso.FileExists(probeFile) Then fso.DeleteFile probeFile, True
    Err.Clear
    On Error GoTo 0
End Sub

Function EncodePowerShell(text)
    Dim stream, node, bytes
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "unicode"
    stream.Open
    stream.WriteText text
    stream.Position = 0
    stream.Type = 1
    stream.Position = 2  ' Skip the UTF-16 byte-order mark.
    bytes = stream.Read
    stream.Close
    Set node = CreateObject("MSXML2.DOMDocument.6.0").createElement("base64")
    node.DataType = "bin.base64"
    node.nodeTypedValue = bytes
    EncodePowerShell = Replace(Replace(node.Text, vbCr, ""), vbLf, "")
End Function
