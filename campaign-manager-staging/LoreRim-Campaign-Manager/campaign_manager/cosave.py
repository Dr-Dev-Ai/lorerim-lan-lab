"""Read/write only this companion's record in the documented SKSE chunk format.

Format source: ianpatt/skse64/skse64/Serialization.cpp (Header/PluginHeader/ChunkHeader).
Other plugins' payloads are never interpreted or changed.
"""
import os
import shutil
import struct
import uuid
from pathlib import Path
from .store import Conflict

PLUGIN_ID=0x4c524350
RECORD_ID=0x4c524944
IDENTITY=struct.Struct('<I37s37s37s37sQ')
MAX_COSAVE=256*1024*1024

def guid(value, empty=False):
    if empty and value=='':return ''
    if not isinstance(value,str):raise ValueError('UUID string required')
    try:normalized=str(uuid.UUID(value))
    except (ValueError,AttributeError) as error:raise ValueError('Canonical UUID required') from error
    if value!=normalized:raise ValueError('Canonical UUID required')
    return normalized

def decode_record(data):
    if len(data)!=IDENTITY.size:raise Conflict('Invalid campaign identity record size')
    version,*values,revision=IDENTITY.unpack(data)
    if version!=1:raise Conflict('Unsupported campaign identity version')
    result={'version':version,'revision':revision}
    for key,raw in zip(('character','campaign','epoch','checkpoint'),values):
        if raw[36]!=0:raise Conflict('Unterminated campaign identity field')
        try:value=raw.split(b'\0',1)[0].decode('ascii');guid(value,empty=key!='character')
        except (ValueError,UnicodeError) as error:raise Conflict('Invalid campaign identity UUID') from error
        # Require canonical zero padding; hidden suffixes cannot alter comparisons.
        if raw!=value.encode().ljust(37,b'\0'):raise Conflict('Noncanonical campaign identity padding')
        result[key]=value
    return result

def encode_record(value):
    fields=[guid(value[key],empty=key!='character').encode() for key in ('character','campaign','epoch','checkpoint')]
    revision=value['revision']
    if type(revision) is not int or not 0<=revision<2**64:raise ValueError('Invalid native revision')
    return IDENTITY.pack(1,*fields,revision)

def locate(path):
    path=Path(path)
    info=path.stat(follow_symlinks=False)
    import stat
    if not stat.S_ISREG(info.st_mode) or not 20<=info.st_size<=MAX_COSAVE:raise Conflict('Invalid SKSE co-save file')
    found=None;seen_plugin=False
    with path.open('rb') as stream:
        header=stream.read(20)
        signature,version,_,_,plugins=struct.unpack('<4sIIII',header)
        if signature!=b'SKSE' or version!=1 or plugins>100000:raise Conflict('Unsupported SKSE co-save header')
        for _ in range(plugins):
            raw=stream.read(12)
            if len(raw)!=12:raise Conflict('Truncated SKSE plugin header')
            plugin,chunks,length=struct.unpack('<III',raw)
            end=stream.tell()+length
            if end>info.st_size or chunks>1000000:raise Conflict('Invalid SKSE plugin extent')
            if plugin!=PLUGIN_ID:
                stream.seek(end);continue
            if seen_plugin:raise Conflict('Duplicate campaign plugin section')
            seen_plugin=True
            for _ in range(chunks):
                raw=stream.read(12)
                if len(raw)!=12:raise Conflict('Truncated SKSE chunk header')
                kind,record_version,size=struct.unpack('<III',raw)
                offset=stream.tell()
                if offset+size>end:raise Conflict('Campaign chunk escapes its plugin section')
                if kind==RECORD_ID:
                    if found or record_version!=1 or size!=IDENTITY.size:raise Conflict('Duplicate or unsupported campaign identity record')
                    found={'offset':offset,'identity':decode_record(stream.read(size))}
                else:stream.seek(size,1)
            if stream.tell()!=end:raise Conflict('Campaign plugin chunk count/length mismatch')
        if stream.tell()!=info.st_size:raise Conflict('SKSE plugin count/length mismatch')
    return found

def read_identity(path):
    found=locate(path)
    if found is None:raise Conflict('No campaign identity in this co-save; initialize and reload a campaign save first')
    return found['identity']

def rebranch(source,destination,epoch,checkpoint,revision):
    """Rewrite the fixed-size owned record into a NEW copy, preserving other bytes."""
    found=locate(source)
    if not found:raise Conflict('Co-save has no campaign identity')
    value=dict(found['identity']);value.update(epoch=guid(epoch),checkpoint=guid(checkpoint,empty=True),revision=revision)
    payload=encode_record(value)
    destination=Path(destination)
    try:
        with Path(source).open('rb') as src, destination.open('xb') as dst:
            shutil.copyfileobj(src,dst)
            dst.seek(found['offset']);dst.write(payload);dst.flush();os.fsync(dst.fileno())
    except BaseException:
        # Never remove a destination that existed before this call.
        raise
    if read_identity(destination)!=value:raise Conflict('Rebranched co-save failed verification')
    return value
