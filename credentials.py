"""Windows current-user DPAPI storage. Never write plaintext API keys to disk."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(payload,decrypt=False):
    if os.name!='nt':
        raise RuntimeError('Secure key storage requires Windows.')
    buffer=ctypes.create_string_buffer(payload)
    source=Blob(len(payload),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    destination=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                 ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(destination)):
        raise RuntimeError('Windows could not unlock the saved key. Enter and save it again on this Windows account.' if decrypt else
                           'Windows could not securely save the key. Your settings were not changed.')
    try:
        return ctypes.string_at(destination.data,destination.length)
    finally:
        kernel.LocalFree(ctypes.cast(destination.data,ctypes.c_void_p))


def key_path(config_path):
    return Path(config_path).with_name('gemini-key.dpapi')


def save_key(config_path,key):
    value=key.strip().encode('utf-8')
    if not value or len(value)>8192:
        raise ValueError('Enter a valid API key in Gemini setup.')
    encrypted=_crypt(value)
    path=key_path(config_path)
    temp=path.with_suffix('.tmp')
    temp.write_bytes(encrypted)
    temp.replace(path)


def load_key(config_path):
    path=key_path(config_path)
    if not path.exists():
        return ''
    if path.stat().st_size>16384:
        raise RuntimeError('Saved key data is invalid. Save the key again in Gemini setup.')
    try:
        return _crypt(path.read_bytes(),decrypt=True).decode('utf-8').strip()
    except UnicodeError:
        raise RuntimeError('Saved key data is invalid. Save the key again in Gemini setup.') from None


def restore_key(config_path):
    if not os.environ.get('GEMINI_API_KEY','').strip():
        value=load_key(config_path)
        if value:
            os.environ['GEMINI_API_KEY']=value


def forget_key(config_path):
    key_path(config_path).unlink(missing_ok=True)
    os.environ.pop('GEMINI_API_KEY',None)
