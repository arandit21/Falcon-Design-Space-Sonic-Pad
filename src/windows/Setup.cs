using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;

class Setup {
    static string ChooseDirectory(string initial) {
        using (var dialog = new Form { Text = "Falcon — установка патча Sonic Pad", ClientSize = new Size(620, 320), Font = new Font("Segoe UI", 10), FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, MinimizeBox = false, StartPosition = FormStartPosition.CenterScreen, BackColor = Color.White }) {
            dialog.Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("falcon.ico")) using (var icon = new Icon(stream, new Size(48,48))) {
                var picture = new PictureBox { Image = icon.ToBitmap(), Left = 24, Top = 24, Size = new Size(48,48), SizeMode = PictureBoxSizeMode.Zoom };
                dialog.Controls.Add(picture);
                dialog.Controls.Add(new Label { Text = "Falcon Design Space · Sonic Pad", Font = new Font("Segoe UI", 16, FontStyle.Bold), Left = 88, Top = 24, AutoSize = true });
                dialog.Controls.Add(new Label { Text = "Подключение по сети, камера, русский язык и калибровка", Left = 88, Top = 58, AutoSize = true, ForeColor = Color.DimGray });
                dialog.Controls.Add(new Label { Text = "Папка установки", Left = 24, Top = 110, AutoSize = true });
                var path = new TextBox { Text = initial, Left = 24, Top = 138, Width = 462 };
                var browse = new Button { Text = "Обзор…", Left = 496, Top = 136, Width = 100, Height = 30 };
                dialog.Controls.Add(path); dialog.Controls.Add(browse);
                browse.Click += (s,e) => { using (var picker = new FolderBrowserDialog { Description = "Выбери папку для установки патча Falcon", SelectedPath = path.Text, ShowNewFolderButton = true }) if (picker.ShowDialog(dialog) == DialogResult.OK) path.Text = picker.SelectedPath; };
                dialog.Controls.Add(new Label { Text = "Можно выбрать папку существующей FDS или отдельную папку.\nДля Program Files нужны права администратора.\nНа рабочем столе будет создан ярлык с иконкой Falcon.", Left = 24, Top = 182, AutoSize = true, ForeColor = Color.DimGray });
                var install = new Button { Text = "Установить", Left = 370, Top = 266, Width = 110, Height = 32 };
                var cancel = new Button { Text = "Отмена", Left = 490, Top = 266, Width = 106, Height = 32, DialogResult = DialogResult.Cancel };
                dialog.Controls.Add(install); dialog.Controls.Add(cancel); dialog.AcceptButton = install; dialog.CancelButton = cancel;
                install.Click += (s,e) => { try { if (!Path.IsPathRooted(path.Text.Trim())) throw new Exception("Выбери полный путь к папке."); path.Text = Path.GetFullPath(path.Text.Trim()); dialog.DialogResult = DialogResult.OK; dialog.Close(); } catch (Exception error) { MessageBox.Show(error.Message, "Папка установки"); } };
                return dialog.ShowDialog() == DialogResult.OK ? path.Text : null;
            }
        }
    }
    [STAThread]
    static int Main(string[] args) {
        bool silent = Array.IndexOf(args, "/silent") >= 0;
        bool rollback = Array.IndexOf(args, "/rollback") >= 0;
        string root = Environment.GetEnvironmentVariable("FALCON_INSTALL_ROOT");
        if (String.IsNullOrEmpty(root)) root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Falcon Design Space", "Sonic Pad");
        if (rollback && File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "install.py"))) root = AppDomain.CurrentDomain.BaseDirectory;
        try {
            Application.EnableVisualStyles();
            if (Process.GetProcessesByName("FalconDesignSpace").Length > 0 || Process.GetProcessesByName("FalconSonicPad").Length > 0)
                throw new Exception("Сначала закрой Falcon Design Space и окно подключения Sonic Pad.");
            if (rollback) {
                if (MessageBox.Show("Восстановить настройки FDS из резервной копии перед установкой патча? Установленная программа и файлы патча останутся на диске.", "Falcon — восстановление", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
            }
            if (!silent && !rollback) { root = ChooseDirectory(root); if (root == null) return 0; }
            Form form = null;
            if (!silent) {
                form = new Form { Text = "Установка Falcon — Sonic Pad", ClientSize = new Size(430, 95), FormBorderStyle = FormBorderStyle.FixedDialog, ControlBox = false, StartPosition = FormStartPosition.CenterScreen };
                form.Controls.Add(new Label { Text = rollback ? "Восстанавливаем настройки FDS…" : "Устанавливаем патч и сохраняем настройки камеры…", Left = 15, Top = 15, AutoSize = true });
                form.Controls.Add(new ProgressBar { Left = 15, Top = 48, Width = 400, Style = ProgressBarStyle.Marquee });
                form.Show(); Application.DoEvents();
            }
            if (!rollback) {
                string original = Path.Combine(root, "FalconDesignSpace.exe");
                if (!File.Exists(original)) original = Path.Combine(Directory.GetParent(root).FullName, "FalconDesignSpace.exe");
                if (!File.Exists(original)) original = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Falcon Design Space", "FalconDesignSpace.exe");
                if (!File.Exists(original)) throw new Exception("Не найдена установленная Falcon Design Space 1.8.0.");
                foreach (var pair in new string[][] {
                    new [] {"Qt5Core.dll", "8d2ff4ce9096ddccc4f4cd62c2e41fc854cfd1b0d6e8d296645a7f5fd4ae565a"},
                    new [] {"Qt5SerialPort.dll", "dd712a412e2d5fd5f879d38bb70d9e79007fea402192d57924e2ee742de7831d"},
                    new [] {"Qt5Gui.dll", "5e7d2d41b8b92a880e83b8cc0ca173f5da61218604186196787ee1600956be1e"},
                    new [] {"Qt5Multimedia.dll", "1a59ae2a9ff768ad6bfb888fe3dd2544e238f0b28da83cf375ebd803ce713dc4"}
                }) {
                    using (var hash = System.Security.Cryptography.SHA256.Create()) using (var input = File.OpenRead(Path.Combine(Path.GetDirectoryName(original), pair[0]))) {
                        if (BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant() != pair[1]) throw new Exception("Несовместимая версия FDS: " + pair[0] + ". Нужна Falcon Design Space 1.8.0.");
                    }
                }
                Directory.CreateDirectory(root);
                string boundary = Path.GetFullPath(root) + Path.DirectorySeparatorChar;
                using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")) using (var zip = new ZipArchive(stream)) {
                    foreach (var entry in zip.Entries) {
                        string target = Path.GetFullPath(Path.Combine(root, entry.FullName));
                        if (!target.StartsWith(boundary, StringComparison.OrdinalIgnoreCase)) throw new Exception("Недопустимый путь в пакете.");
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(target); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        using (var input = entry.Open()) using (var output = File.Create(target)) input.CopyTo(output);
                        if (form != null) Application.DoEvents();
                    }
                }
                File.WriteAllText(Path.Combine(root, "fds_directory.txt"), Path.GetDirectoryName(original), new System.Text.UTF8Encoding(false));
                string self = Assembly.GetExecutingAssembly().Location;
                string installedSetup = Path.Combine(root, "Восстановление.exe");
                if (!String.Equals(Path.GetFullPath(self), Path.GetFullPath(installedSetup), StringComparison.OrdinalIgnoreCase)) File.Copy(self, installedSetup, true);
            }
            var info = new ProcessStartInfo(Path.Combine(root, "python", "python.exe"), "\"" + Path.Combine(root, "install.py") + "\"" + (rollback ? " --rollback" : "")) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = System.Text.Encoding.UTF8, StandardErrorEncoding = System.Text.Encoding.UTF8 };
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            using (var process = Process.Start(info)) {
                string text = process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd(); process.WaitForExit();
                if (process.ExitCode != 0) throw new Exception(text);
            }
            if (!rollback && !silent) {
                if (form != null) form.Hide();
                if (MessageBox.Show("Настроить подключение Sonic Pad сейчас? На свежей установке потребуется один раз ввести IP и root-пароль в открывшемся окне. Пароль не сохраняется. Повторная настройка доступна в меню Пуск.", "Первое подключение", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes) {
                    using (var pairing = Process.Start(new ProcessStartInfo(Path.Combine(root, "python", "python.exe"), "\"" + Path.Combine(root, "first_setup.py") + "\"") { WorkingDirectory = root, UseShellExecute = true })) {
                        while (!pairing.HasExited) { Application.DoEvents(); System.Threading.Thread.Sleep(100); }
                    }
                }
            }
            try { File.Delete(Path.Combine(root, "Ошибка установки.txt")); } catch { }
            if (form != null) form.Close();
            if (!silent) MessageBox.Show(rollback ? "Настройки восстановлены. Оригинальная FDS доступна через прежний ярлык." : "Готово. На рабочем столе появился ярлык «Falcon — Sonic Pad».\n\nПатч, камера и русский интерфейс установлены. Существующая калибровка сохранена. Запускай программу этим ярлыком.", "Falcon — Sonic Pad", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        } catch (Exception error) {
            try { Directory.CreateDirectory(root); File.WriteAllText(Path.Combine(root, "Ошибка установки.txt"), error.ToString(), System.Text.Encoding.UTF8); } catch { }
            if (!silent) MessageBox.Show("Установка не завершена.\n\n" + error.Message, "Falcon — ошибка установки", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
