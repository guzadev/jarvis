#ifndef Payload
  #error Supply /DPayload=<absolute staging directory>
#endif
#ifndef OutputFolder
  #error Supply /DOutputFolder=<absolute build directory>
#endif
#ifndef Version
  #define Version "0.1.4"
#endif

[Setup]
AppId={{9EBB7E41-1CE1-4A4E-9F94-E87A5808CB6C}
AppName=Jarvis
AppVersion={#Version}
DefaultDirName={code:DefaultInstallDirectory}
DefaultGroupName=Jarvis
UninstallDisplayIcon={app}\Jarvis.exe
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
OutputDir={#OutputFolder}
#ifdef ExistingOnly
OutputBaseFilename=Jarvis-Windows-Escritorio
#else
OutputBaseFilename=Jarvis-Windows-Instalador
#endif
Compression=lzma2/fast
SolidCompression=no
#ifdef ExistingOnly
DiskSpanning=no
#else
DiskSpanning=yes
DiskSliceSize=2000000000
SlicesPerDisk=1
#endif
SetupLogging=no
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: checkedonce

[Files]
#ifdef ExistingOnly
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "\backend\*,\data\*,\runtime\*,\dependencies.json,\offline-manifest.json"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "\data\models\jarvis-owned\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\data\models\jarvis-owned\*"; DestDir: "{app}\data\models\jarvis-owned"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs

#endif

[Icons]
Name: "{group}\Jarvis"; Filename: "{app}\Jarvis.exe"
Name: "{userdesktop}\Jarvis"; Filename: "{app}\Jarvis.exe"; Tasks: desktopicon

Name: "{group}\Conectar Claude Code"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\backend\conectar-claude.ps1"""; WorkingDir: "{app}\backend"; IconFilename: "{app}\Jarvis.exe"
Name: "{group}\Leer instrucciones"; Filename: "{app}\LEEME-INSTALADOR.txt"

[Run]
Filename: "{app}\Jarvis.exe"; Description: "Iniciar Jarvis"; Flags: nowait postinstall skipifsilent

[Code]
var
  LocalModelPage: TInputOptionWizardPage;

procedure InitializeWizard;
var
  Note: TNewStaticText;
begin
  LocalModelPage := CreateInputOptionPage(wpSelectDir,
    'Modelos de razonamiento local',
    'Elegí si querés descargar un modelo para ejecutar tareas en esta PC.',
    'La descarga se completa al abrir Jarvis, desde Ollama. Podés cambiar, descargar o quitar modelos después en la app.', True, False);
  LocalModelPage.Add('OpenAI / Claude - sin modelo de razonamiento local');
  LocalModelPage.Add('Qwen3 1.7B - 1,4 GB aprox. - ligero, tareas breves');
  LocalModelPage.Add('Qwen3 4B - 2,5 GB aprox. - tareas cotidianas');
  LocalModelPage.Add('Qwen3 8B - 5,2 GB aprox. - tareas con varios pasos');
  LocalModelPage.Add('Qwen3 14B - 9,3 GB aprox. - mayor consumo');
  LocalModelPage.SelectedValueIndex := 0;
  LocalModelPage.CheckListBox.Height := ScaleY(112);
  Note := TNewStaticText.Create(LocalModelPage);
  Note.Parent := LocalModelPage.Surface;
  Note.Left := 0;
  Note.Top := LocalModelPage.CheckListBox.Top + LocalModelPage.CheckListBox.Height + ScaleY(8);
  Note.Width := LocalModelPage.SurfaceWidth;
  Note.Height := ScaleY(58);
  Note.AutoSize := False;
  Note.WordWrap := True;
  Note.Caption := 'La voz no cambia: Jarvis descarga 5,03 GB de voz y activación desde Hugging Face en la primera apertura. RAM/VRAM y velocidad dependen del equipo.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Model, ChoiceFile: string;
begin
  if CurStep = ssPostInstall then begin
    Model := '';
    case LocalModelPage.SelectedValueIndex of
      1: Model := 'qwen3:1.7b';
      2: Model := 'qwen3:4b';
      3: Model := 'qwen3:8b';
      4: Model := 'qwen3:14b';
    end;
    ChoiceFile := ExpandConstant('{app}\backend\.jarvis-install-choice.json');
    if Model <> '' then
      SaveStringToFile(ChoiceFile, '{"model":"' + Model + '"}', False)
    else
      DeleteFile(ChoiceFile);
  end;
end;

#ifdef ExistingOnly
function InitializeSetup(): Boolean;
begin
  Result := FileExists(ExpandConstant('{userappdata}\JarvisDesktop\installation.json'));
  if not Result then
    SuppressibleMsgBox('Esta PC necesita el instalador completo de Jarvis, que incluye Python y los modelos. Esta ediciÃƒÂ³n usa los componentes de una instalaciÃƒÂ³n registrada.', mbError, MB_OK, IDOK);
end;
#endif

function GetDriveTypeW(Root: string): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function DefaultInstallDirectory(Unused: string): string;
var
  Letter: Integer;
  CurrentRoot, Chosen, Local: string;
  Available, Capacity, Largest: Int64;
begin
  Local := ExpandConstant('{localappdata}');
  Chosen := ExtractFileDrive(Local) + '\';
  Largest := -1;
  for Letter := Ord('A') to Ord('Z') do begin
    CurrentRoot := Chr(Letter) + ':\';
    if GetDriveTypeW(CurrentRoot) = 3 then begin
      if GetSpaceOnDisk64(CurrentRoot, Available, Capacity) then begin
        if (Available > Largest) or
           ((Available = Largest) and (CompareText(CurrentRoot, ExtractFileDrive(Local) + '\') = 0)) then begin
          Largest := Available;
          Chosen := CurrentRoot;
        end;
      end;
    end;
  end;
  if CompareText(Chosen, ExtractFileDrive(Local) + '\') = 0 then
    Result := AddBackslash(Local) + 'Programs\Jarvis'
  else
    Result := Chosen + 'JarvisDesktop\' + GetUserNameString + '\Jarvis';
end;

procedure RemoveOwnLoginEntry;
var
  Names: TArrayOfString;
  I: Integer;
  Value, Exe, Cmd: string;
begin
  Exe := ExpandConstant('{app}\Jarvis.exe');
  if RegGetValueNames(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', Names) then
    for I := 0 to GetArrayLength(Names)-1 do begin
      if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', Names[I], Value) then begin
        Cmd := Trim(Value);
        if (CompareText(Cmd, '"' + Exe + '" --background') = 0) or
           (CompareText(Cmd, '"' + Exe + '" "--background"') = 0) or
           (CompareText(Cmd, Exe + ' --background') = 0) or
           (CompareText(Cmd, '"' + Exe + '"') = 0) or (CompareText(Cmd, Exe) = 0) then
          RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', Names[I]);
      end;
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then RemoveOwnLoginEntry;
end;
