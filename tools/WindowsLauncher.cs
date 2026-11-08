// Zoom Copilot windowless launcher. Distributed under the project's GPL-3.0 license.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Zoom Copilot")]
[assembly: AssemblyDescription("Zoom Copilot desktop launcher")]
[assembly: AssemblyProduct("Zoom Copilot")]
[assembly: AssemblyVersion("2.0.1.0")]
[assembly: AssemblyFileVersion("2.0.1.0")]
[assembly: AssemblyCopyright("Copyright (C) 2026 Sombra-1")]

internal static class WindowsLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string folder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        try
        {
            string script = Path.Combine(folder, "launch.pyw");
            if (!File.Exists(script))
                throw new InvalidOperationException("Keep Zoom Copilot.exe beside launch.pyw and the app folders.");
            List<string> candidates = new List<string>();
            if (args.Length == 2 && args[0] == "--python")
                candidates.Add(args[1]);
            else if (args.Length != 0)
                throw new InvalidOperationException("Unsupported launcher arguments.");
            candidates.Add(Path.Combine(folder, "venv", "Scripts", "pythonw.exe"));
            candidates.Add(Path.Combine(folder, ".venv", "Scripts", "pythonw.exe"));
            AddRegisteredPython(candidates);
            foreach (string item in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
            {
                if (!String.IsNullOrWhiteSpace(item))
                    candidates.Add(Path.Combine(item.Trim('"'), "pythonw.exe"));
            }
            foreach (string executable in candidates)
            {
                if (!File.Exists(executable))
                    continue;
                ProcessStartInfo info = new ProcessStartInfo(executable);
                info.Arguments = "\"" + script + "\"";
                info.WorkingDirectory = folder;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                using (Process child = Process.Start(info)) { }
                return 0;
            }
            throw new InvalidOperationException("Run setup.bat to install Python 3.11+ and the app dependencies.");
        }
        catch (Exception error)
        {
            string message = error is InvalidOperationException ? error.Message : "Could not start Zoom Copilot. Run setup.bat to check the installation.";
            MessageBox.Show(message, "Zoom Copilot", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void AddRegisteredPython(List<string> candidates)
    {
        foreach (RegistryHive hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
        foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            try
            {
                using (RegistryKey parent = RegistryKey.OpenBaseKey(hive, view))
                using (RegistryKey core = parent.OpenSubKey(@"Software\Python\PythonCore"))
                {
                    if (core == null) continue;
                    foreach (string name in core.GetSubKeyNames())
                    {
                        Version version;
                        if (!Version.TryParse(name.Split('-')[0], out version) || version < new Version(3, 11))
                            continue;
                        using (RegistryKey install = core.OpenSubKey(name + @"\InstallPath"))
                        {
                            if (install == null) continue;
                            string direct = install.GetValue("WindowedExecutablePath") as string;
                            string directory = install.GetValue(null) as string;
                            if (!String.IsNullOrEmpty(direct)) candidates.Add(direct);
                            if (!String.IsNullOrEmpty(directory)) candidates.Add(Path.Combine(directory, "pythonw.exe"));
                        }
                    }
                }
            }
            catch (System.Security.SecurityException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
