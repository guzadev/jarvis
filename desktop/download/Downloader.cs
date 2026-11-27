// Build with the Windows .NET Framework compiler. No provider key is requested.
using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Diagnostics;
[assembly: AssemblyTitle("Jarvis para Windows")]
[assembly: AssemblyProduct("Jarvis")]
[assembly: AssemblyVersion("0.1.4.0")]
[assembly: AssemblyFileVersion("0.1.4.0")]

public sealed class ReleaseFile { public string name; public string sha256; public long bytes; }
public sealed class ReleaseManifest { public string version; public long installed_bytes; public ReleaseFile[] files; }

public static class Program {
    public static ReleaseManifest LoadManifest() {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("release-manifest.json"))
        using (StreamReader reader = new StreamReader(stream)) {
            ReleaseManifest manifest = new JavaScriptSerializer().Deserialize<ReleaseManifest>(reader.ReadToEnd());
            if (manifest == null || !Regex.IsMatch(manifest.version ?? "", @"^\d+\.\d+\.\d+$") || manifest.files == null || manifest.files.Length < 2 || manifest.files.Length > 100)
                throw new InvalidDataException("El manifiesto de instalación no es válido.");
            if (manifest.installed_bytes < 1 || manifest.installed_bytes > 200L * 1024 * 1024 * 1024)
                throw new InvalidDataException("El tamaño de instalación no es válido.");
            foreach (ReleaseFile file in manifest.files) {
                if (file == null || !Regex.IsMatch(file.name ?? "", @"^Jarvis-Windows-Instalador(?:-\d+\.bin|\.exe)$") || !Regex.IsMatch(file.sha256 ?? "", @"^[a-f0-9]{64}$") || file.bytes < 1 || file.bytes >= 2147483648L)
                    throw new InvalidDataException("Un archivo de instalación no es válido.");
            }
            if (manifest.files.Select(f => f.name).Distinct(StringComparer.OrdinalIgnoreCase).Count() != manifest.files.Length || !manifest.files.Any(f => f.name == "Jarvis-Windows-Instalador.exe"))
                throw new InvalidDataException("Falta el instalador o hay nombres repetidos.");
            return manifest;
        }
    }
    [STAThread]
    public static void Main(string[] args) {
        try {
            ReleaseManifest manifest = LoadManifest();
            if (args.Length == 2 && args[0] == "--check-manifest") {
                File.WriteAllText(args[1], new JavaScriptSerializer().Serialize(new { ok = true, version = manifest.version, files = manifest.files.Length, bytes = manifest.files.Sum(f => f.bytes), installed_bytes = manifest.installed_bytes }));
                return;
            }
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new DownloadForm(manifest));
        } catch (Exception error) {
            if (args.Length == 2 && args[0] == "--check-manifest") { Environment.ExitCode = 1; return; }
            MessageBox.Show(error.Message, "Jarvis", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Environment.ExitCode = 1;
        }
    }
}

public sealed class DownloadForm : Form {
    private readonly ReleaseManifest manifest;
    private readonly TextBox destination = new TextBox();
    private readonly Label status = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Button browse = new Button();
    private readonly Button start = new Button();
    private readonly Button cancel = new Button();
    private CancellationTokenSource cancellation;
    public DownloadForm(ReleaseManifest release) {
        manifest = release; Text = "Instalar Jarvis para Windows"; ClientSize = new Size(650, 350);
        StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        Font = new Font("Segoe UI", 10); BackColor = Color.FromArgb(3, 14, 21); ForeColor = Color.FromArgb(211, 240, 248);
        Label heading = new Label { Text = "J.A.R.V.I.S.", Font = new Font("Segoe UI", 23), Bounds = new Rectangle(28, 22, 590, 44) };
        Label intro = new Label { Text = "Descarga los componentes y abre el instalador completo.\nWindows x64 · Voz local: requiere una GPU NVIDIA compatible con CUDA.", Bounds = new Rectangle(30, 78, 590, 52) };
        destination.Bounds = new Rectangle(30, 145, 482, 28); destination.ReadOnly = true; destination.Text = DefaultFolder();
        browse.Text = "Carpeta…"; browse.Bounds = new Rectangle(524, 143, 96, 32);
        browse.Click += delegate { using (FolderBrowserDialog picker = new FolderBrowserDialog()) { picker.Description = "Elegí una carpeta con espacio para descargar Jarvis"; picker.SelectedPath = destination.Text; if (picker.ShowDialog(this) == DialogResult.OK) destination.Text = picker.SelectedPath; } };
        progress.Bounds = new Rectangle(30, 195, 590, 19); progress.Maximum = 1000;
        status.Text = "Versión " + manifest.version + " · " + (manifest.files.Sum(f => f.bytes) / 1073741824.0).ToString("0.0") + " GB de descarga. No necesitás instalar Python.";
        status.Bounds = new Rectangle(30, 225, 590, 48);
        start.Text = "Descargar e instalar"; start.Bounds = new Rectangle(30, 290, 230, 36);
        cancel.Text = "Cancelar descarga"; cancel.Bounds = new Rectangle(420, 290, 200, 36); cancel.Enabled = false;
        start.Click += async delegate { await Download(); }; cancel.Click += delegate { if (cancellation != null) cancellation.Cancel(); };
        FormClosing += delegate { if (cancellation != null) cancellation.Cancel(); };
        Controls.AddRange(new Control[] { heading, intro, destination, browse, progress, status, start, cancel });
    }
    private string DefaultFolder() {
        string root = Path.GetPathRoot(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
        long free = -1;
        foreach (DriveInfo drive in DriveInfo.GetDrives()) {
            try { if (drive.IsReady && drive.DriveType == DriveType.Fixed && drive.AvailableFreeSpace > free) { root = drive.RootDirectory.FullName; free = drive.AvailableFreeSpace; } } catch (IOException) { }
        }
        return Path.Combine(root, "Jarvis-Instalador-" + manifest.version);
    }
    private static string HashFile(string file) {
        using (SHA256 sha = SHA256.Create()) using (FileStream stream = File.OpenRead(file))
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    private static async Task<HttpResponseMessage> AssetResponse(HttpClient client, string url, CancellationToken token) {
        Uri target = new Uri(url);
        string[] hosts = new string[] { "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com" };
        for (int hop = 0; hop <= 5; hop++) {
            if (target.Scheme != Uri.UriSchemeHttps || !hosts.Contains(target.Host, StringComparer.OrdinalIgnoreCase) || target.Port != 443 || !String.IsNullOrEmpty(target.UserInfo))
                throw new InvalidDataException("La descarga no proviene de un destino HTTPS de GitHub autorizado.");
            HttpResponseMessage response = await client.GetAsync(target, HttpCompletionOption.ResponseHeadersRead, token);
            int code = (int)response.StatusCode;
            if (code >= 300 && code < 400) {
                Uri next = response.Headers.Location; response.Dispose();
                if (next == null || hop == 5) throw new InvalidDataException("La descarga tiene demasiadas redirecciones o un destino inválido.");
                target = new Uri(target, next); continue;
            }
            return response;
        }
        throw new InvalidDataException("No se pudo resolver la descarga de GitHub.");
    }
    private async Task Download() {
        start.Enabled = browse.Enabled = false; cancel.Enabled = true; cancellation = new CancellationTokenSource();
        CancellationToken token = cancellation.Token;
        try {
            string folder = Path.GetFullPath(destination.Text); Directory.CreateDirectory(folder);
            long total = manifest.files.Sum(f => f.bytes), completed = 0;
            DriveInfo target = new DriveInfo(Path.GetPathRoot(folder));
            long reusable = manifest.files.Where(f => File.Exists(Path.Combine(folder, f.name))).Sum(f => new FileInfo(Path.Combine(folder, f.name)).Length);
            if (target.AvailableFreeSpace < total - reusable + manifest.installed_bytes + 1073741824L)
                throw new IOException("Elegí una unidad con más espacio libre para la descarga y la instalación.");
            using (HttpClient client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseCookies = false, UseDefaultCredentials = false })) {
                client.Timeout = TimeSpan.FromHours(4); client.DefaultRequestHeaders.UserAgent.ParseAdd("Jarvis-Windows-Installer/" + manifest.version);
                foreach (ReleaseFile file in manifest.files) {
                    token.ThrowIfCancellationRequested(); string path = Path.Combine(folder, file.name);
                    status.Text = "Comprobando " + file.name + "…";
                    if (File.Exists(path) && new FileInfo(path).Length == file.bytes && await Task.Run(() => HashFile(path)) == file.sha256) { completed += file.bytes; continue; }
                    string url = "https://github.com/guzadev/jarvis/releases/download/v" + manifest.version + "/" + Uri.EscapeDataString(file.name);
                    using (HttpResponseMessage response = await AssetResponse(client, url, token)) {
                        response.EnsureSuccessStatusCode(); long received = 0;
                        using (Stream input = await response.Content.ReadAsStreamAsync())
                        using (FileStream output = new FileStream(path + ".partial", FileMode.Create, FileAccess.Write, FileShare.None, 1048576, true))
                        using (SHA256 sha = SHA256.Create()) {
                            byte[] buffer = new byte[1048576]; int count;
                            while ((count = await input.ReadAsync(buffer, 0, buffer.Length, token)) > 0) {
                                received += count; if (received > file.bytes) throw new InvalidDataException("La descarga supera el tamaño publicado.");
                                await output.WriteAsync(buffer, 0, count, token); sha.TransformBlock(buffer, 0, count, buffer, 0);
                                progress.Value = Math.Min(1000, (int)((completed + received) * 1000.0 / total));
                                status.Text = "Descargando " + file.name + " · " + ((completed + received) / 1073741824.0).ToString("0.0") + " / " + (total / 1073741824.0).ToString("0.0") + " GB";
                            }
                            sha.TransformFinalBlock(new byte[0], 0, 0);
                            string actual = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                            if (received != file.bytes || actual != file.sha256) throw new InvalidDataException("La descarga no coincide con la huella publicada. Podés volver a intentar.");
                        }
                    }
                    token.ThrowIfCancellationRequested();
                    if (File.Exists(path)) File.Delete(path); File.Move(path + ".partial", path); completed += file.bytes;
                }
            }
            token.ThrowIfCancellationRequested(); progress.Value = 1000; status.Text = "Descarga verificada. Abriendo el instalador de Jarvis…";
            Process.Start(new ProcessStartInfo(Path.Combine(folder, "Jarvis-Windows-Instalador.exe")) { WorkingDirectory = folder, UseShellExecute = true });
            Close();
        } catch (OperationCanceledException) { if (!IsDisposed) status.Text = "Descarga cancelada. Los archivos completos se conservan para reintentar."; }
        catch (Exception error) { if (!IsDisposed) MessageBox.Show(this, error.Message, "No se completó la descarga", MessageBoxButtons.OK, MessageBoxIcon.Information); }
        finally { if (!IsDisposed) { start.Enabled = browse.Enabled = true; cancel.Enabled = false; } cancellation.Dispose(); cancellation = null; }
    }
}
