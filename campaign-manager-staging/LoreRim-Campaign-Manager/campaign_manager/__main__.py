import argparse
import json
import os
import uuid
from pathlib import Path
from .store import Store, Conflict, Denied
from .checkpoints import capture, checkpoint, export_checkpoint, profile_manifest

def main():
    parser = argparse.ArgumentParser(description='Staged LoreRim campaign tools — game integration pending')
    parser.add_argument('--data', default=str(Path.home() / 'LoreRimCampaignStaging'))
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fingerprint'); p.add_argument('--build', required=True); p.add_argument('--file', action='append', required=True); p.add_argument('--output', required=True)
    p = sub.add_parser('init'); p.add_argument('--name', required=True); p.add_argument('--profile', required=True); p.add_argument('--runtime', required=True)
    p = sub.add_parser('add-player'); p.add_argument('--campaign', required=True); p.add_argument('--name', required=True); p.add_argument('--leader', action='store_true'); p.add_argument('--credential-out', required=True)
    p = sub.add_parser('capture'); p.add_argument('--credential', required=True); p.add_argument('--save', required=True); p.add_argument('--profile', required=True); p.add_argument('--runtime', required=True); p.add_argument('--extra', action='append', default=[]); p.add_argument('--operation', required=True)
    p = sub.add_parser('checkpoint'); p.add_argument('--credential', required=True); p.add_argument('--snapshot', action='append', required=True); p.add_argument('--label', required=True); p.add_argument('--operation', required=True)
    p = sub.add_parser('export'); p.add_argument('--credential', required=True); p.add_argument('--checkpoint', required=True); p.add_argument('--output', required=True)
    p = sub.add_parser('recover'); p.add_argument('--credential', required=True); p.add_argument('--checkpoint', required=True); p.add_argument('--output', required=True)
    p = sub.add_parser('status'); p.add_argument('--campaign', required=True)
    p = sub.add_parser('serve'); p.add_argument('--port', type=int, default=10579)
    sub.add_parser('gui')
    args = parser.parse_args()
    if args.command == 'fingerprint':
        from .checkpoints import runtime_fingerprint
        manifest = runtime_fingerprint(args.build, args.file)
        path = Path(args.output)
        with path.open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, indent=2)
        print(json.dumps({'file': str(path), 'scope': manifest['scope']}, indent=2))
        return
    if args.command == 'serve':
        from .api import serve
        return serve(args.data, args.port)
    if args.command == 'gui':
        from .gui import run
        return run(args.data)
    store = Store(args.data)
    try:
        if args.command == 'init':
            manifest = profile_manifest(args.profile, json.loads(Path(args.runtime).read_text(encoding='utf-8-sig')))
            result = store.create_campaign(args.name, manifest)
        elif args.command == 'add-player':
            path = Path(args.credential_out)
            # Exclusive creation avoids overwriting a player's previous identity.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                credentials = store.add_player(args.campaign, args.name, args.leader)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(credentials, stream, indent=2)
                result = {'campaign': credentials['campaign'], 'player': credentials['player'], 'credential_file': str(path)}
            except BaseException:
                try: os.close(fd)
                except OSError: pass
                path.unlink(missing_ok=True)
                raise
        elif args.command == 'status':
            result = store.summary(args.campaign)
        else:
            credentials = json.loads(Path(args.credential).read_text(encoding='utf-8-sig'))
            actor = store.authenticate(credentials['token'])
            cid, pid = actor['campaign'], actor['id']
            if args.command == 'capture':
                result = capture(store, cid, pid, args.save, args.profile,
                                 json.loads(Path(args.runtime).read_text(encoding='utf-8-sig')), args.operation, extras=args.extra)
            elif args.command == 'checkpoint':
                result = checkpoint(store, cid, pid, args.snapshot, args.label, args.operation)
            elif args.command == 'recover':
                from .recovery import prepare_recovery
                result = prepare_recovery(store, cid, pid, args.checkpoint, args.output)
            else:
                store.leader(cid, pid)
                result = export_checkpoint(store, cid, args.checkpoint, args.output)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f'Cannot complete operation: {error}\n')
    finally:
        store.close()

if __name__ == '__main__':
    main()
