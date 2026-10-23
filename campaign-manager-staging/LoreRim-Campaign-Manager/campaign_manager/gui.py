"""Small desktop front end for file backups. No game-control buttons are exposed."""
import json
import os
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from .store import Store
from .checkpoints import capture, checkpoint, export_checkpoint, profile_manifest

def run(data_root):
    root = tk.Tk()
    root.title('LoreRim Campaign Manager — staged build')
    root.geometry('900x620')
    root.minsize(760, 500)
    state = {'campaign': None, 'players': [], 'busy': False}
    results = queue.Queue()
    data_root = Path(data_root)
    title = ttk.Frame(root, padding=18); title.pack(fill='x')
    ttk.Label(title, text='LoreRim Campaign Manager', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
    ttk.Label(title, text='File backups and campaign records • Skyrim integration is not connected', foreground='#a04b00').pack(anchor='w', pady=(5, 0))
    selection = ttk.Frame(root, padding=(18, 0, 18, 10)); selection.pack(fill='x')
    ttk.Label(selection, text='Campaign').pack(side='left')
    campaign_box = ttk.Combobox(selection, state='readonly', width=50); campaign_box.pack(side='left', padx=10)
    ttk.Label(selection, text='Player').pack(side='left')
    player_box = ttk.Combobox(selection, state='readonly', width=24); player_box.pack(side='left', padx=10)
    actions = ttk.Frame(root, padding=(18, 0)); actions.pack(fill='x')
    details = tk.Text(root, wrap='word', padx=12, pady=12, font=('Segoe UI', 10), state='disabled')
    details.pack(fill='both', expand=True, padx=18, pady=12)
    status = tk.StringVar(value='Ready. Live saves are never overwritten.')
    ttk.Label(root, textvariable=status, padding=(18, 5, 18, 14)).pack(anchor='w')

    def display(value):
        details.configure(state='normal'); details.delete('1.0', 'end'); details.insert('end', value); details.configure(state='disabled')

    def refresh():
        store = Store(data_root)
        try:
            campaigns = [dict(r) for r in store.db.execute('SELECT id,name FROM campaign ORDER BY rowid')]
            campaign_box['values'] = [r['name'] for r in campaigns]
            if campaigns:
                index = campaign_box.current()
                if index < 0: index = 0; campaign_box.current(0)
                state['campaign'] = campaigns[index]['id']
                data = store.summary(state['campaign'])
                state['players'] = data['players']
                player_box['values'] = [r['name'] for r in data['players']]
                if data['players'] and player_box.current() < 0: player_box.current(0)
                snapshots = [dict(r) for r in store.db.execute('SELECT id,player,revision,parent FROM snapshot WHERE campaign=? ORDER BY created DESC', (state['campaign'],))]
                display('Staged campaign: ' + data['name'] + '\n\n'
                        + f"Players: {len(data['players'])}    File checkpoints: {len(data['checkpoints'])}\n"
                        + f"Follower records: {len(data['followers'])}    Item records: {len(data['items'])}\n\n"
                        + 'These are database records, not evidence that Skyrim is enforcing ownership.\n'
                        + 'Captures preserve an existing .ess/.skse pair and selected profile files.\n'
                        + 'Checkpoint validation checks files, lineage and supplied fingerprints; it cannot certify quest/world agreement.\n\n'
                        + 'Recent captures:\n' + '\n'.join(f"{r['id']}  — revision {r['revision']}" for r in snapshots[:8]))
            else:
                display('Create a staged campaign, then add both players.\n\nSelect the MO2 profile folder and a runtime fingerprint JSON when creating the campaign. Both captures must use the same compatibility manifest.\n\nNo game files will be replaced. Follower, dialogue and item enforcement require the pending native adapters.')
        finally:
            store.close()

    def current_player():
        if player_box.current() < 0 or not state['players']:
            raise ValueError('Add and select a player first')
        return state['players'][player_box.current()]['id']

    def worker(task):
        if state['busy']:
            return
        state['busy'] = True
        status.set('Working…')
        def execute():
            store = None
            try:
                store = Store(data_root)
                results.put((True, task(store)))
            except Exception as error:
                results.put((False, str(error)))
            finally:
                if store: store.close()
        threading.Thread(target=execute, daemon=True).start()

    def pick_manifest():
        profile = filedialog.askdirectory(title='Select the MO2 profile folder')
        if not profile: return None
        runtime = filedialog.askopenfilename(title='Select the runtime/protocol fingerprint JSON', filetypes=[('JSON', '*.json')])
        if not runtime: return None
        return profile, json.loads(Path(runtime).read_text(encoding='utf-8-sig'))

    def create():
        try:
            name = simpledialog.askstring('New campaign', 'Campaign name:')
            if not name: return
            manifest = pick_manifest()
            if manifest:
                profile, runtime = manifest
                worker(lambda store: store.create_campaign(name, profile_manifest(profile, runtime)))
        except Exception as error:
            messagebox.showerror('Cannot create campaign', str(error))

    def add():
        if not state['campaign']:
            messagebox.showinfo('Campaign required', 'Create a campaign first.'); return
        name = simpledialog.askstring('Add player', 'Player name:')
        if not name: return
        cid = state['campaign']
        def task(store):
            directory = data_root / 'credentials'; directory.mkdir(exist_ok=True)
            credential_file = directory / (str(uuid.uuid4()) + '.json')
            fd = os.open(credential_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            credentials = store.add_player(cid, name, as_leader=not store.campaign(cid)['leader'])
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(credentials, stream, indent=2)
            return {'player': credentials['player'], 'credential_file': str(credential_file)}
        worker(task)

    def capture_save():
        try:
            cid, pid = state['campaign'], current_player()
            save = filedialog.askopenfilename(title='Select the existing .ess save to back up', filetypes=[('Skyrim save', '*.ess')])
            if not save: return
            manifest = pick_manifest()
            if manifest:
                profile, runtime = manifest
                worker(lambda store: capture(store, cid, pid, save, profile, runtime, str(uuid.uuid4())))
        except Exception as error:
            messagebox.showerror('Cannot capture save', str(error))

    def pair():
        cid = state['campaign']
        if not cid: return
        label = simpledialog.askstring('Pair checkpoint', 'Label for these file backups:')
        if not label: return
        def task(store):
            campaign = store.campaign(cid)
            rows = store.db.execute('SELECT * FROM snapshot WHERE campaign=? AND revision=? AND parent IS ? ORDER BY created DESC',
                                    (cid, campaign['revision'], campaign['head'])).fetchall()
            latest = {}
            for row in rows: latest.setdefault(row['player'], row['id'])
            return checkpoint(store, cid, campaign['leader'], list(latest.values()), label, str(uuid.uuid4()))
        worker(task)

    def export():
        cid = state['campaign']
        if not cid: return
        parent = filedialog.askdirectory(title='Select a folder for a NEW export subfolder')
        if not parent: return
        destination = Path(parent) / ('LoreRim-Checkpoint-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        def task(store):
            head = store.campaign(cid)['head']
            if not head: raise ValueError('Create a paired checkpoint first')
            return export_checkpoint(store, cid, head, destination)
        worker(task)

    def recovery():
        cid = state['campaign']
        if not cid: return
        parent = filedialog.askdirectory(title='Select a folder for a NEW recovery copy')
        if not parent: return
        destination = Path(parent) / ('LoreRim-Recovery-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        def task(store):
            from .recovery import prepare_recovery
            campaign = store.campaign(cid)
            if not campaign['head']: raise ValueError('Create a paired checkpoint first')
            return prepare_recovery(store, cid, campaign['leader'], campaign['head'], destination)
        worker(task)

    recovery_actions = ttk.Frame(root, padding=(18, 0))
    recovery_actions.pack(before=details, fill='x')
    ttk.Button(recovery_actions, text='Prepare paired recovery copy', command=recovery).pack(side='left')
    ttk.Label(recovery_actions, text='Restores checkpoint records into a new folder; installation remains separate.').pack(side='left', padx=10)

    for text, command in [('New campaign', create), ('Add player', add), ('Capture save pair', capture_save), ('Pair checkpoint', pair), ('Export copy', export), ('Refresh', refresh)]:
        ttk.Button(actions, text=text, command=command).pack(side='left', padx=(0, 6), pady=5)
    campaign_box.bind('<<ComboboxSelected>>', lambda _: (player_box.set(''), refresh()))

    def poll():
        try:
            ok, result = results.get_nowait()
            state['busy'] = False
            if ok:
                status.set('Saved. Live game files were not changed.')
                refresh()
                messagebox.showinfo('Operation completed', json.dumps(result, indent=2))
            else:
                status.set('Operation did not complete.')
                messagebox.showerror('Cannot complete operation', result)
        except queue.Empty:
            pass
        root.after(100, poll)
    def closing():
        if state['busy']:
            messagebox.showinfo('Operation in progress', 'Wait for the current backup or database operation to finish.'); return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', closing)
    refresh(); poll(); root.mainloop()
