"""Prepare a private disabled client configuration; never installs it."""
import configparser
import os
from pathlib import Path
from .store import Denied

def write_native_config(store,cid,pid,credential,save_directory,destination):
    actor=store.authenticate(credential)
    if actor['campaign']!=cid or actor['id']!=pid:raise Denied('Credential does not match the requested campaign player')
    directory=Path(save_directory)
    if not directory.is_absolute() or not directory.is_dir():raise ValueError('An existing absolute save directory is required')
    profile=directory.parent
    if not (profile/'plugins.txt').is_file() or not (profile/'modlist.txt').is_file():raise ValueError('Select the MO2 profile saves directory')
    epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
    config=configparser.ConfigParser(interpolation=None)
    config.optionxform=str
    config['Campaign']={'Enabled':'0','Id':cid,'Epoch':epoch,'Checkpoint':store.campaign(cid)['head'] or '',
                        'Revision':str(store.campaign(cid)['revision']),'Credential':credential,'SaveDirectory':str(directory),'ProfileDirectory':str(profile)}
    destination=Path(destination)
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-16') as stream:
        stream.write('; Staged configuration. Enable and install only with the approved matching client/companion update.\n')
        config.write(stream)
    return {'file':str(destination),'enabled':False,'installed':False}
