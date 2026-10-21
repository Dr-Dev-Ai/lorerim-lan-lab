using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

class Installer : Form {
    readonly string root = AppDomain.CurrentDomain.BaseDirectory;
    TextBox source = new TextBox(), destination = new TextBox(), host = new TextBox();
    Label status = new Label();
    ProgressBar progress = new ProgressBar();
    Button install = new Button(), play = new Button(), logButton = new Button();
    Button sourceBrowse = new Button(), destinationBrowse = new Button();
    Process worker;
    bool busy;
    string logPath, completedLab;
    const string Profile = "LoreRim LAN Test";

    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length>=2 && args[0]=="--create-shortcuts") {
            try { CreateShortcuts(args[1],args.Length>=3?args[2]:Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory)); }
            catch(Exception e) { Console.Error.WriteLine(e.ToString());Environment.ExitCode=1; }
            return;
        }
        if (args.Contains("--smoke-test")) { Console.WriteLine("Installer UI initialized"); return; }
        Application.Run(new Installer());
    }
    static void CreateShortcuts(string lab,string desktop) {
        if(!File.Exists(Path.Combine(lab,"guided-install-verification.json")))throw new InvalidOperationException("Verified installation required");
        if(!Directory.Exists(desktop))throw new DirectoryNotFoundException("Desktop folder unavailable");
        Type shellType=Type.GetTypeFromProgID("WScript.Shell");
        object shell=Activator.CreateInstance(shellType);
        string[] names={"Play LoreRim Together.lnk","LoreRim Together - How to Join.lnk"};
        for(int i=0;i<names.Length;i++) {
            object link=shellType.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{Path.Combine(desktop,names[i])});
            Type type=link.GetType();
            type.InvokeMember("TargetPath",BindingFlags.SetProperty,null,link,new object[]{Path.Combine(lab,i==0?"ModOrganizer.exe":"HOW TO JOIN.txt")});
            if(i==0) {
                type.InvokeMember("Arguments",BindingFlags.SetProperty,null,link,new object[]{"-p \"LoreRim LAN Test\" \"moshortcut://:LoreRim LAN Test\""});
                type.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,link,new object[]{lab});
            }
            type.InvokeMember("Save",BindingFlags.InvokeMethod,null,link,new object[0]);
        }
    }
    Installer() {
        Text="LoreRim Together Setup";
        ClientSize=new Size(760,615); FormBorderStyle=FormBorderStyle.FixedDialog;
        MaximizeBox=false; StartPosition=FormStartPosition.CenterScreen;
        Font=new Font("Segoe UI",11); BackColor=Color.FromArgb(247,248,250);
        AddLabel("Play LoreRim together",28,22,700,40,21,true);
        AddLabel("Choose your existing LoreRim folder. We'll take care of the rest.",30,72,700,30,11,false);
        AddLabel("1   Where is LoreRim installed?",30,122,690,28,12,true);
        AddLabel("Choose the folder containing ModOrganizer.exe.",30,153,690,25,10,false);
        Place(source,30,183,585,30); Browse(sourceBrowse,"Browse…",source,625,182);
        source.TextChanged += delegate { if (!busy && source.Text.Length>2) {
            try { destination.Text=Path.Combine(Path.GetPathRoot(source.Text),"LoreRim-LAN","LoreRim"); } catch {} }
        };
        AddLabel("2   Where should the multiplayer copy go?",30,229,690,28,12,true);
        AddLabel("Choose a drive with room for another LoreRim copy. Your original stays separate.",30,260,700,25,10,false);
        Place(destination,30,290,585,30); Browse(destinationBrowse,"Browse…",destination,625,289);
        AddLabel("3   Host computer address",30,337,300,28,12,true);
        Place(host,345,336,270,30); host.Text="10.0.0.250";
        AddLabel("Leave this as shown for your current home network.",30,371,700,25,10,false);
        Place(progress,30,420,695,16); progress.Style=ProgressBarStyle.Continuous;
        Place(status,30,448,695,75);status.Text="Ready. Close Skyrim and Mod Organizer before installing. Internet access is needed.";
        status.ForeColor=Color.FromArgb(55,65,81);
        Place(install,535,548,190,42);install.Text="Install";install.BackColor=Color.FromArgb(26,72,105);install.ForeColor=Color.White;
        install.FlatStyle=FlatStyle.Flat;install.Click+=async delegate { await StartInstall(); };
        Place(play,320,548,200,42);play.Text="Play LoreRim Together";play.Visible=false;
        play.Click+=delegate { try { Process.Start(new ProcessStartInfo(Path.Combine(completedLab,"ModOrganizer.exe"),"-p \""+Profile+"\" \"moshortcut://:"+Profile+"\""){WorkingDirectory=completedLab}); } catch(Exception e) { MessageBox.Show(this,e.Message,"Could not launch"); } };
        Place(logButton,30,550,160,38);logButton.Text="Open setup log";logButton.Visible=false;
        logButton.Click+=delegate { if(File.Exists(logPath)) Process.Start("notepad.exe",Quote(logPath)); };
        FormClosing+=delegate(object sender,FormClosingEventArgs e) { if(busy) {
            MessageBox.Show(this,"Installation is still running. Please leave this window open so the copy and checks can finish.","Still installing");e.Cancel=true; }
        };
        Shown+=async delegate { await DetectSource(); };
    }
    void Place(Control c,int x,int y,int w,int h) { c.SetBounds(x,y,w,h); Controls.Add(c); }
    void AddLabel(string text,int x,int y,int w,int h,int size,bool bold) {
        Label l=new Label(){Text=text,Font=new Font("Segoe UI",size,bold?FontStyle.Bold:FontStyle.Regular)};Place(l,x,y,w,h);
    }
    void Browse(Button b,string title,TextBox field,int x,int y) {
        Place(b,x,y,100,32);b.Text=title;b.Click+=delegate {
            using(FolderBrowserDialog dialog=new FolderBrowserDialog()) {
                dialog.Description=field==source?"Select your existing LoreRim folder (contains ModOrganizer.exe)":"Select a location for the separate multiplayer copy";
                dialog.ShowNewFolderButton=field!=source;
                if(Directory.Exists(field.Text))dialog.SelectedPath=field.Text;
                if(dialog.ShowDialog(this)==DialogResult.OK)field.Text=field==source?dialog.SelectedPath:Path.Combine(dialog.SelectedPath,"LoreRim-LAN","LoreRim");
            }
        };
    }
    async Task DetectSource() {
        var result=await Task.Run(()=> {
            foreach(var drive in DriveInfo.GetDrives()) {
                try { if(!drive.IsReady || drive.DriveType!=DriveType.Fixed) continue;
                    foreach(var suffix in new[]{"LoreRim","Modlists\\LoreRim","Wabbajack\\LoreRim","Games\\LoreRim"}) {
                        string p=Path.Combine(drive.RootDirectory.FullName,suffix);
                        if(File.Exists(Path.Combine(p,"ModOrganizer.exe")) && !File.Exists(Path.Combine(p,"LORERIM_LAB.json")))return p;
                    }
                } catch {}
            }
            return "";
        });
        if(source.Text.Length==0 && !busy)source.Text=result;
    }
    static string Quote(string s) {
        if(s.Contains('"') || s.EndsWith("\\"))throw new ArgumentException("Please select a folder instead of a drive root.");
        return "\""+s+"\"";
    }
    async Task StartInstall() {
        if(busy)return;
        if(completedLab!=null) { Close(); return; }
        if(string.IsNullOrWhiteSpace(source.Text)||string.IsNullOrWhiteSpace(destination.Text)) {
            MessageBox.Show(this,"Choose your LoreRim folder and a destination first.","Choose folders");return;
        }
        string python=Path.Combine(root,"runtime","python.exe");
        if(!File.Exists(python)||!File.Exists(Path.Combine(root,"adapter","BSAMemoryMap.dll"))) {
            MessageBox.Show(this,"Extract the complete LoreRim-Together-Installer.zip first, then open Install LoreRim Together.exe from the extracted folder.","Package incomplete");return;
        }
        string destinationPath=destination.Text.Trim();
        try {
            string logDir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"LoreRimLAN","Logs");
            Directory.CreateDirectory(logDir);logPath=Path.Combine(logDir,"setup-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".log");
            string args=Quote(Path.Combine(root,"installer","install_worker.py"))+" --source "+Quote(source.Text.Trim())+" --destination "+Quote(destinationPath)+" --host "+Quote(host.Text.Trim());
            var start=new ProcessStartInfo(python,args){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=root,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
            start.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";start.EnvironmentVariables["PYTHONUNBUFFERED"]="1";
            worker=new Process(){StartInfo=start};busy=true;
            foreach(Control c in new Control[]{source,destination,host,sourceBrowse,destinationBrowse,install})c.Enabled=false;
            progress.Style=ProgressBarStyle.Marquee;status.Text="Checking your installation…";logButton.Visible=true;play.Visible=false;
            worker.Start();
            Task errors=Task.Run(async ()=> { string line;while((line=await worker.StandardError.ReadLineAsync())!=null) { lock(logPath)File.AppendAllText(logPath,line+Environment.NewLine); } });
            string output;
            while((output=await worker.StandardOutput.ReadLineAsync())!=null) {
                lock(logPath)File.AppendAllText(logPath,output+Environment.NewLine);
                try {
                    var item=new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(output);
                    status.Text=(string)item["message"];
                } catch { /* Raw library diagnostics remain available in the log. */ }
            }
            await Task.Run(()=>worker.WaitForExit());await errors;
            progress.Style=ProgressBarStyle.Continuous;
            if(worker.ExitCode==0) {
                progress.Value=100;completedLab=destinationPath;play.Visible=true;install.Text="Done";
                status.Text="Ready to play! A Play LoreRim Together shortcut is on your desktop.\nIn-game: F2 → "+host.Text.Trim()+":10578   Password: LoreRimLab";
                install.Enabled=true;
            } else { progress.Value=0;install.Text="Try again"; }
        } catch(Exception e) {status.Text="Could not finish: "+e.Message;progress.Style=ProgressBarStyle.Continuous;install.Text="Try again";}
        finally {
            busy=false;
            foreach(Control c in new Control[]{source,destination,host,sourceBrowse,destinationBrowse})c.Enabled=completedLab==null;
            install.Enabled=true;
        }
    }
}
