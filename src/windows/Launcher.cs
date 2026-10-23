using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
using System.Windows.Forms;
using System.Drawing;
using System.Runtime.InteropServices;

class Launcher {
    delegate bool WindowCallback(IntPtr window, IntPtr parameter);
    [DllImport("user32.dll")] static extern bool EnumWindows(WindowCallback callback, IntPtr parameter);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr window, uint message, IntPtr parameter, IntPtr value, uint flags, uint timeout, out IntPtr result);
    static void ApplyWindowIcon(int pid, Icon small, Icon large) {
        EnumWindows((window, parameter) => {
            uint owner; GetWindowThreadProcessId(window, out owner);
            if (owner == pid) {
                IntPtr result;
                SendMessageTimeout(window, 0x80, IntPtr.Zero, small.Handle, 2, 100, out result);
                SendMessageTimeout(window, 0x80, new IntPtr(1), large.Handle, 2, 100, out result);
            }
            return true;
        }, IntPtr.Zero);
    }
    static string UserData(string root) {
        string marker = Path.Combine(root, "user_data_path.txt");
        if (File.Exists(marker)) { string path = File.ReadAllText(marker).Trim(); if (Path.IsPathRooted(path)) return path; }
        return root;
    }
    static void EditAddress(string root) {
        string file = Path.Combine(UserData(root), "connection.ini");
        string current = "192.168.1.36";
        if (File.Exists(file)) foreach (string line in File.ReadAllLines(file)) if (line.Trim().StartsWith("host=")) current = line.Trim().Substring(5);
        using (var dialog = new Form { Text = "Адрес Sonic Pad", ClientSize = new Size(390, 145), FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, MinimizeBox = false, StartPosition = FormStartPosition.CenterScreen }) {
            dialog.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            dialog.Font = new Font("Segoe UI", 9);
            dialog.Controls.Add(new Label { Text = "IP-адрес Sonic Pad", Left = 15, Top = 15, AutoSize = true });
            var input = new TextBox { Text = current, Left = 15, Top = 40, Width = 355 };
            var save = new Button { Text = "Сохранить", Left = 260, Top = 98, Width = 110 };
            dialog.Controls.Add(input); dialog.Controls.Add(save);
            dialog.Controls.Add(new Label { Text = "Адрес применяется при следующем запуске Falcon.", Left = 15, Top = 72, AutoSize = true });
            dialog.AcceptButton = save;
            save.Click += (s,e) => {
                string[] parts = input.Text.Trim().Split('.'); byte[] bytes = new byte[4]; bool valid = parts.Length == 4;
                if (valid) for (int i = 0; i < 4; i++) if (!Byte.TryParse(parts[i], out bytes[i])) valid = false;
                if (!valid) { MessageBox.Show("Введите IP-адрес вида 192.168.1.36.", "Неверный адрес"); return; }
                try { File.WriteAllText(file, "[Connection]\nhost=" + new System.Net.IPAddress(bytes).ToString() + "\n", new System.Text.UTF8Encoding(false)); dialog.Close(); }
                catch (Exception error) { MessageBox.Show("Не удалось сохранить адрес: " + error.Message, "Sonic Pad"); }
            };
            dialog.ShowDialog();
        }
    }
    [STAThread]
    static void Main(string[] args) {
        Application.EnableVisualStyles();
        string root = AppDomain.CurrentDomain.BaseDirectory;
        if (Array.IndexOf(args, "/pairing") >= 0) {
            Process.Start(new ProcessStartInfo(Path.Combine(root, "python", "python.exe"), "\"" + Path.Combine(root, "first_setup.py") + "\"") { WorkingDirectory = root, UseShellExecute = true });
            return;
        }
        if (Array.IndexOf(args, "/settings") >= 0) { EditAddress(root); return; }
        bool first;
        using (var mutex = new Mutex(true, "Local\\FalconSonicPadNativeLauncher", out first)) {
            if (!first) { MessageBox.Show("Falcon через Sonic Pad уже запущен.", "Falcon — Sonic Pad"); return; }
            string logs = Path.Combine(UserData(root), "results");
            Directory.CreateDirectory(logs);
            string logfile = Path.Combine(logs, "Запуск_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log");
            using (var writer = new StreamWriter(logfile, false, new System.Text.UTF8Encoding(false))) {
                writer.AutoFlush = true;
                var form = new Form { Text = "Falcon — Sonic Pad", ClientSize = new Size(410, 90), FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, MinimizeBox = false, ControlBox = false, StartPosition = FormStartPosition.CenterScreen };
                form.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                form.Font = new Font("Segoe UI", 9);
                // Qt may replace the executable icon with its default window icon.
                // Update only the exact FDS process spawned by this launcher.
                var smallIcon = new Icon(Path.Combine(root, "falcon.ico"), 16, 16);
                var largeIcon = new Icon(Path.Combine(root, "falcon.ico"), 48, 48);
                int falconPid = 0;
                var iconTimer = new System.Windows.Forms.Timer { Interval = 1500 };
                iconTimer.Tick += (s,e) => { int pid = Interlocked.CompareExchange(ref falconPid, 0, 0); if (pid > 0) ApplyWindowIcon(pid, smallIcon, largeIcon); };
                iconTimer.Start();
                var label = new Label { Text = "Подключаем Sonic Pad и запускаем Falcon…", AutoSize = true, Left = 18, Top = 15 };
                var progress = new ProgressBar { Left = 18, Top = 45, Width = 374, Style = ProgressBarStyle.Marquee };
                form.Controls.Add(label); form.Controls.Add(progress);
                var process = new Process();
                process.StartInfo = new ProcessStartInfo(Path.Combine(root, "python", "python.exe"), "-u \"" + Path.Combine(root, "production_entry.py") + "\"") { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = System.Text.Encoding.UTF8, StandardErrorEncoding = System.Text.Encoding.UTF8 };
                process.StartInfo.EnvironmentVariables["PYTHONUTF8"] = "1";
                Action<string> output = line => {
                    if (line == null) return;
                    lock (writer) { writer.WriteLine(line); }
                    const string pidPrefix = "Spawned original FDS PID ";
                    int parsedPid;
                    if (line.StartsWith(pidPrefix) && Int32.TryParse(line.Substring(pidPrefix.Length), out parsedPid)) Interlocked.Exchange(ref falconPid, parsedPid);
                    if (line.Contains("Original Falcon Design Space started") && form.IsHandleCreated) form.BeginInvoke((Action)(() => form.Hide()));
                };
                process.OutputDataReceived += (s,e) => output(e.Data);
                process.ErrorDataReceived += (s,e) => output(e.Data);
                form.Shown += (s,e) => {
                    try {
                        process.EnableRaisingEvents = true;
                        process.Exited += (sender,ev) => {
                            if (!form.IsHandleCreated) return;
                            form.BeginInvoke((Action)(() => {
                                process.WaitForExit();
                                if (process.ExitCode != 0 && MessageBox.Show("Не удалось завершить подключение к Sonic Pad.\n\nПроверь питание A1 и подключение Sonic Pad к сети. Закрой другие окна Falcon перед повторным запуском.\n\nЖурнал: " + logfile + "\n\nИзменить IP-адрес Sonic Pad?", "Falcon — ошибка подключения", MessageBoxButtons.YesNo, MessageBoxIcon.Error) == DialogResult.Yes) EditAddress(root);
                                form.Close();
                            }));
                        };
                        process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
                    } catch (Exception error) {
                        writer.WriteLine(error.ToString());
                        MessageBox.Show("Не удалось запустить Falcon. Повтори установку патча.\n\nЖурнал: " + logfile, "Falcon — ошибка запуска", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        form.Close();
                    }
                };
                Application.Run(form);
                iconTimer.Stop(); iconTimer.Dispose(); smallIcon.Dispose(); largeIcon.Dispose();
                process.Dispose();
            }
        }
    }
}
