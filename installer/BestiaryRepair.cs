// Exact-build workaround: retain the Bestiary, bypass its optional HUD widget.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Security.Cryptography;
using System.Diagnostics;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Runtime.InteropServices;

class BestiaryRepair {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateHardLink(string link,string existing,IntPtr reserved);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAlloc(IntPtr address,UIntPtr size,uint allocation,uint protection);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualFree(IntPtr address,UIntPtr size,uint freeType);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] delegate void WidgetCall();
    const string OriginalHash="06ac689bb7c9324f51ad822e4b1b469fd8cf1e4d7a621e529516522fa66445dd";
    const string DllRel="mods/The Dragonborn's Bestiary/SKSE/Plugins/DragonbornsBestiary.dll";
    const string IniName="Dragonborns Bestiary.ini";
    static string Hash(byte[] b) { using(var s=SHA256.Create()) return BitConverter.ToString(s.ComputeHash(b)).Replace("-", "").ToLowerInvariant(); }
    static string P(string root,string rel) { return Path.Combine(root,rel.Replace('/',Path.DirectorySeparatorChar)); }
    static void Safe(string path) {
        for(var p=new FileInfo(path);p!=null;p=p.Directory==null?null:new FileInfo(p.Directory.FullName))
            if((File.Exists(p.FullName)||Directory.Exists(p.FullName)) && (File.GetAttributes(p.FullName)&FileAttributes.ReparsePoint)!=0)
                throw new Exception("Linked folder refused: "+p.FullName);
    }
    static byte[] Patched(byte[] original) {
        if(Hash(original)!=OriginalHash) throw new Exception("This Bestiary version is different. No files were changed. Please send the repair log.");
        var b=(byte[])original.Clone();
        // File offsets corresponding to RVA 4D600 SetPosition and 4D8C0 Show.
        // Both are void functions with no arguments; RET precedes their prologues.
        foreach(int off in new[]{0x4ca00,0x4ccc0}) {
            if(b[off]!=0x48 || b[off+1]!=0x89 || b[off+2]!=0x5c) throw new Exception("Instruction check failed.");
            b[off]=0xc3;
        }
        return b;
    }
    static void Backup(string path,byte[] expected) {
        Safe(path);
        if(File.Exists(path)) { if(!File.ReadAllBytes(path).SequenceEqual(expected)) throw new Exception("Backup differs: "+path); return; }
        using(var f=new FileStream(path,FileMode.CreateNew,FileAccess.Write)) f.Write(expected,0,expected.Length);
        if(!File.ReadAllBytes(path).SequenceEqual(expected)) throw new Exception("Backup verification failed.");
    }
    static void Replace(string path,byte[] data) {
        Safe(path);
        string temp=Path.Combine(Path.GetDirectoryName(path),Guid.NewGuid().ToString("N")+".tmp");
        try { File.WriteAllBytes(temp,data); File.Replace(temp,path,null); }
        finally { if(File.Exists(temp)) File.Delete(temp); }
        if(!File.ReadAllBytes(path).SequenceEqual(data)) throw new Exception("Write verification failed: "+path);
    }
    static string WinningFile(string root,string relative) {
        string overwrite=P(root,"overwrite/"+relative);
        if(File.Exists(overwrite)) return overwrite;
        foreach(string line in File.ReadAllLines(P(root,"profiles/LoreRim LAN Test/modlist.txt"))) {
            if(!line.StartsWith("+")) continue;
            string name=line.Substring(1);
            if(name=="."||name==".."||name.IndexOfAny(new[]{'/', '\\', ':'})>=0) throw new Exception("Invalid mod list.");
            string candidate=P(Path.Combine(root,"mods",name),relative);
            if(File.Exists(candidate)) return candidate;
        }
        string stock=P(root,"Stock Game/Data/"+relative);
        if(File.Exists(stock))return stock;
        throw new Exception("Bestiary file was not found in the multiplayer profile: "+relative);
    }
    static byte[] DisabledIni(byte[] original) {
        string text=new UTF8Encoding(false,true).GetString(original);
        var section=Regex.Match(text,"(?im)^\uFEFF?\\[General\\][^\\r\\n]*\\r?\\n(?<body>[\\s\\S]*?)(?=^\\[|\\z)");
        if(!section.Success) throw new Exception("Bestiary settings have no General section.");
        string body=section.Groups["body"].Value;
        var setting=new Regex(@"(?im)^(\s*iEnableWidget\s*=\s*)[01]([ \t]*(?:[;#][^\r\n]*)?)(?=\r?$)");
        if(setting.Matches(body).Count!=1) throw new Exception("Unexpected Bestiary widget setting.");
        string changed=setting.Replace(body,"${1}0${2}");
        return Encoding.UTF8.GetBytes(text.Substring(0,section.Groups["body"].Index)+changed+text.Substring(section.Groups["body"].Index+body.Length));
    }
    static void Repair(string root,bool restore,bool checkProcesses) {
        root=Path.GetFullPath(root).TrimEnd('\\'); Safe(root);
        var marker=new JavaScriptSerializer().DeserializeObject(File.ReadAllText(P(root,"LORERIM_LAB.json"))) as System.Collections.Generic.Dictionary<string,object>;
        string source=Path.GetFullPath(Convert.ToString(marker["source"])).TrimEnd('\\');
        if(root.Equals(source,StringComparison.OrdinalIgnoreCase)||root.StartsWith(source+"\\",StringComparison.OrdinalIgnoreCase)||source.StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase))
            throw new Exception("Choose the separate LoreRim multiplayer folder, not the original installation.");
        if(checkProcesses && Process.GetProcesses().Any(p=>new[]{"SkyrimSE","SkyrimTogether","ModOrganizer"}.Contains(p.ProcessName,StringComparer.OrdinalIgnoreCase)))
            throw new Exception("Close Skyrim and Mod Organizer on this computer, then run the repair again.");
        string dll=P(root,DllRel), ini=WinningFile(root,IniName), backup=P(root,"bestiary-widget-repair-backup");
        if(!WinningFile(root,"SKSE/Plugins/DragonbornsBestiary.dll").Equals(dll,StringComparison.OrdinalIgnoreCase)) throw new Exception("Another mod overrides the Bestiary DLL. Repair refused.");
        Safe(dll);Safe(ini);Safe(backup);
        string db=P(backup,"DragonbornsBestiary.dll.original"), ib=P(backup,"settings.original"), record=P(backup,"settings-path.txt");
        Safe(db);Safe(ib);Safe(record);
        byte[] current=File.ReadAllBytes(dll), original=File.Exists(db)?File.ReadAllBytes(db):current, patched=Patched(original);
        if(!current.SequenceEqual(original)&&!current.SequenceEqual(patched)) throw new Exception("Bestiary DLL changed since the backup. Repair refused.");
        if(File.Exists(record)&&File.ReadAllText(record)!=ini) throw new Exception("The winning Bestiary settings file changed. Repair refused.");
        byte[] currentIni=File.ReadAllBytes(ini),originalIni=File.Exists(ib)?File.ReadAllBytes(ib):currentIni,disabled=DisabledIni(originalIni);
        if(!currentIni.SequenceEqual(originalIni)&&!currentIni.SequenceEqual(disabled)) throw new Exception("Bestiary settings changed since the backup. Repair refused.");
        // All checks precede mutation. Replacing a file breaks any hard link and leaves its original untouched.
        Directory.CreateDirectory(backup); Backup(db,original);Backup(ib,originalIni);
        if(!File.Exists(record)) File.WriteAllText(record,ini);
        byte[] wantedDll=restore?original:patched, wantedIni=restore?originalIni:disabled;
        try { Replace(ini,wantedIni); Replace(dll,wantedDll); }
        catch { Replace(ini,currentIni); Replace(dll,current); throw; }
        if(!File.ReadAllBytes(dll).SequenceEqual(wantedDll)||!File.ReadAllBytes(ini).SequenceEqual(wantedIni)) throw new Exception("Final verification failed.");
    }
    static void SelfTest(string dll) {
        var original=File.ReadAllBytes(dll); var patched=Patched(original);
        if(original.Where((b,i)=>b!=patched[i]).Count()!=2) throw new Exception("Wrong patch extent.");
        foreach(int off in new[]{0x4ca00,0x4ccc0}) {
            IntPtr memory=VirtualAlloc(IntPtr.Zero,(UIntPtr)4096,0x3000,0x40);
            if(memory==IntPtr.Zero)throw new Exception("Native test allocation failed.");
            try { Marshal.Copy(patched,off,memory,16);((WidgetCall)Marshal.GetDelegateForFunctionPointer(memory,typeof(WidgetCall)))(); }
            finally {VirtualFree(memory,UIntPtr.Zero,0x8000);}
        }
        string temp=Path.Combine(Path.GetTempPath(),"LoreRimRepairTest-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try {
            string target=P(temp,DllRel);Directory.CreateDirectory(Path.GetDirectoryName(target)); File.WriteAllBytes(target,original);
            string shadow=P(temp,"original-installation.dll");if(!CreateHardLink(shadow,target,IntPtr.Zero))throw new Exception("Hard-link test setup failed.");
            string ini=P(temp,"mods/Test/"+IniName);Directory.CreateDirectory(Path.GetDirectoryName(ini));
            var iniBytes=Encoding.UTF8.GetBytes("[General]\r\niEnableWidget = 1\r\niKeycode=37\r\n[Other]\r\nvalue=1\r\n");File.WriteAllBytes(ini,iniBytes);
            string profile=P(temp,"profiles/LoreRim LAN Test");Directory.CreateDirectory(profile);File.WriteAllText(P(profile,"modlist.txt"),"+Test\r\n+The Dragonborn's Bestiary\r\n");
            File.WriteAllText(P(temp,"LORERIM_LAB.json"),"{\"source\":\"C:/NotThisTest\"}");
            Repair(temp,false,false);Repair(temp,false,false);
            if(!File.ReadAllBytes(target).SequenceEqual(patched)||!File.ReadAllText(ini).Contains("iEnableWidget = 0")||!File.ReadAllText(ini).Contains("iKeycode=37")) throw new Exception("Apply failed.");
            if(!File.ReadAllBytes(shadow).SequenceEqual(original))throw new Exception("Shared original changed.");
            Repair(temp,true,false);Repair(temp,true,false);
            if(!File.ReadAllBytes(target).SequenceEqual(original)||!File.ReadAllBytes(ini).SequenceEqual(iniBytes)) throw new Exception("Restore failed.");
            File.WriteAllText(ini,"[General]\r\niEnableWidget=1\r\nchanged=1\r\n");
            bool refused=false;try { Repair(temp,false,false); } catch { refused=true; }
            if(!refused||!File.ReadAllBytes(target).SequenceEqual(original)) throw new Exception("Changed-settings gate failed.");
            byte[] corrupt=(byte[])original.Clone();corrupt[100]^=1;refused=false;
            try {Patched(corrupt);}catch{refused=true;}if(!refused)throw new Exception("Hash gate failed.");
            var bom=Encoding.UTF8.GetPreamble().Concat(iniBytes).ToArray();if(!DisabledIni(bom).Take(3).SequenceEqual(Encoding.UTF8.GetPreamble()))throw new Exception("BOM lost.");
            Console.WriteLine("PASS: exact two-byte patch; both repaired native entries return safely; apply/retry; byte-exact restore/retry; shared-original preservation; changed-settings refusal before DLL write; unknown-DLL refusal; UTF-8 BOM preserved.");
        } finally { // This directory was freshly created with a random name by this self-test.
            if(Path.GetFullPath(temp).StartsWith(Path.GetFullPath(Path.GetTempPath()),StringComparison.OrdinalIgnoreCase)&&Path.GetFileName(temp).StartsWith("LoreRimRepairTest-")) Directory.Delete(temp,true);
        }
    }
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();
        try {
            if(args.Length==2&&args[0]=="--self-test"){SelfTest(args[1]);return 0;}
            bool restore=args.Contains("--restore");
            string root=args.FirstOrDefault(s=>!s.StartsWith("--"));
            if(root==null) {
                foreach(string drive in new[]{"D:","C:","G:","E:","L:"}) {
                    string candidate=drive+"\\LoreRim-LAN\\LoreRim";
                    if(File.Exists(P(candidate,"LORERIM_LAB.json"))){root=candidate;break;}
                }
            }
            if(root==null) using(var picker=new FolderBrowserDialog()) {picker.Description="Choose her multiplayer LoreRim folder (usually D:\\LoreRim-LAN\\LoreRim)";if(picker.ShowDialog()!=DialogResult.OK)return 0;root=picker.SelectedPath;}
            Repair(root,restore,true);
            MessageBox.Show(restore?"Original Bestiary widget files restored.":"Bestiary popup repair installed.\n\nThe Bestiary journal and creature tracking stay enabled. Only its HUD popups are disabled.\n\nOpen Play LoreRim Together and check whether the title screen loads. This is a workaround awaiting her game test.","LoreRim Bestiary Repair",MessageBoxButtons.OK,MessageBoxIcon.Information);
            return 0;
        } catch(Exception e) {
            if(args.Contains("--self-test")){Console.Error.WriteLine(e);return 1;}
            string log=Path.Combine(Path.GetTempPath(),"LoreRim-Bestiary-Repair.log"); File.WriteAllText(log,e.ToString());
            MessageBox.Show(e.Message+"\n\nDetails saved to: "+log,"Repair could not finish",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;
        }
    }
}
