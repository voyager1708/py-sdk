"""
binary.py - Utilities for byte/number conversion, varint, and encoding/decoding.
"""
import math
from typing import Union, List, Optional, Literal

def unsigned_to_varint(num: int) -> bytes:
    if num < 0 or num > 0xffffffffffffffff:
        raise OverflowError(f"can't convert {num} to varint")
    if num <= 0xfc:
        return num.to_bytes(1, 'little')
    elif num <= 0xffff:
        return b'\xfd' + num.to_bytes(2, 'little')
    elif num <= 0xffffffff:
        return b'\xfe' + num.to_bytes(4, 'little')
    else:
        return b'\xff' + num.to_bytes(8, 'little')

def unsigned_to_bytes(num: int, byteorder: Literal['big', 'little'] = 'big') -> bytes:
    return num.to_bytes(math.ceil(num.bit_length() / 8) or 1, byteorder)

def to_hex(byte_array: bytes) -> str:
    return byte_array.hex()

def to_bytes(msg: Union[bytes, str], enc: Optional[str] = None) -> bytes:
    if isinstance(msg, bytes):
        return msg
    if not msg:
        return bytes()
    if isinstance(msg, str):
        if enc == 'hex':
            msg = ''.join(filter(str.isalnum, msg))
            if len(msg) % 2 != 0:
                msg = '0' + msg
            return bytes(int(msg[i:i + 2], 16) for i in range(0, len(msg), 2))
        elif enc == 'base64':
            import base64
            return base64.b64decode(msg)
        else:  # UTF-8 encoding
            return msg.encode('utf-8')
    return bytes(msg)

def to_utf8(arr: List[int]) -> str:
    return bytes(arr).decode('utf-8')

def encode(arr: List[int], enc: Optional[str] = None) -> Union[str, List[int]]:
    if enc == 'hex':
        return to_hex(bytes(arr))
    elif enc == 'utf8':
        return to_utf8(arr)
    return arr

def to_base64(byte_array: List[int]) -> str:
    import base64
    return base64.b64encode(bytes(byte_array)).decode('ascii')