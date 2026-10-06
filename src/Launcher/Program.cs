using System.Diagnostics;

var dir = new DirectoryInfo(AppContext.BaseDirectory);
while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "RUN_DEMO.cmd"))) dir = dir.Parent;
if (dir is null) throw new FileNotFoundException("RUN_DEMO.cmd was not found above launcher output directory.");
var script = Path.Combine(dir.FullName, "RUN_DEMO.cmd");
var process = Process.Start(new ProcessStartInfo("cmd.exe", $"/c \"{script}\"")
{
    WorkingDirectory = dir.FullName,
    UseShellExecute = false
}) ?? throw new InvalidOperationException("RUN_DEMO launcher process did not start.");
await process.WaitForExitAsync();
return process.ExitCode;
