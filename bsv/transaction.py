import math
from contextlib import suppress
from io import BytesIO
from typing import List, Optional, Union, Dict, Any

from typing_extensions import Literal

from .constants import SIGHASH, Network
from .hash import hash256
from .keys import PrivateKey
from .script.script import Script
from .script.type import ScriptType, P2PKH, OpReturn, Unknown
from .service.provider import Provider, BroadcastResult
from .service.service import Service
from .unspent import Unspent
from .utils import unsigned_to_varint


class InsufficientFunds(ValueError):
    pass


class TransactionBytesIO(BytesIO):

    def read_bytes(self, byte_length: Optional[int] = None) -> bytes:
        """
        Read and return up to size bytes.
        If the argument is omitted, None, or negative, data is read and returned until EOF is reached
        An empty bytes object is returned if the stream is already at EOF.
        """
        return self.read(byte_length)

    def read_int(self, byte_length: int, byteorder: Literal['big', 'little'] = 'little') -> int:
        """
        :returns: None if the stream is already at EOF
        """
        octets = self.read_bytes(byte_length)
        assert octets
        return int.from_bytes(octets, byteorder=byteorder)

    def read_varint(self) -> int:
        """
        :returns: None if the stream is already at EOF
        """
        octets = self.read_bytes(1)
        assert octets
        octets = ord(octets)
        if octets <= 0xfc:
            return octets
        elif octets == 0xfd:
            return self.read_int(2)
        elif octets == 0xfe:
            return self.read_int(4)
        else:
            return self.read_int(8)


SEQUENCE = 0xffffffff
VERSION = 1
LOCKTIME = 0
FEE_RATE = 0.5  # satoshi per byte


class TxInput:

    def __init__(self,
                 unspent: Optional[Unspent] = None,
                 private_keys: Optional[List[PrivateKey]] = None,
                 unlocking_script: Optional[Script] = None,
                 sequence: int = SEQUENCE,
                 sighash: SIGHASH = SIGHASH.ALL_FORKID):
        self.txid: str = unspent.txid if unspent else ('00' * 32)
        self.vout: int = unspent.vout if unspent else 0
        self.value: int = unspent.value if unspent else 0
        self.height: int = unspent.height if unspent else -1
        self.confirmations: int = unspent.confirmations if unspent else 0
        self.private_keys: List[PrivateKey] = private_keys or (unspent.private_keys if unspent else [])
        self.script_type: ScriptType = unspent.script_type if unspent else Unknown
        self.locking_script: Script = unspent.locking_script if unspent else Script()

        self.unlocking_script: Script = unlocking_script
        self.sequence: int = sequence
        self.sighash: SIGHASH = sighash

    def serialize(self) -> bytes:
        stream = BytesIO()
        stream.write(bytes.fromhex(self.txid)[::-1])
        stream.write(self.vout.to_bytes(4, 'little'))
        stream.write(self.unlocking_script.byte_length_varint() if self.unlocking_script else b'\x00')
        stream.write(self.unlocking_script.serialize() if self.unlocking_script else b'')
        stream.write(self.sequence.to_bytes(4, 'little'))
        return stream.getvalue()

    def __str__(self) -> str:
        return f'<TxInput outpoint={self.txid}:{self.vout} value={self.value} locking_script={self.locking_script}>'

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_hex(cls, stream: Union[str, bytes, TransactionBytesIO]) -> Optional['TxInput']:
        with suppress(Exception):
            if not isinstance(stream, TransactionBytesIO):
                stream = TransactionBytesIO(stream if isinstance(stream, bytes) else bytes.fromhex(stream))
            txid = stream.read_bytes(32)[::-1]
            assert len(txid) == 32
            vout = stream.read_int(4)
            assert vout is not None
            script_length = stream.read_varint()
            assert script_length is not None
            unlocking_script_bytes = stream.read_bytes(script_length)
            sequence = stream.read_int(4)
            assert sequence is not None
            unspent = Unspent(txid=txid.hex(), vout=vout, value=0, locking_script=Script())
            return TxInput(unspent=unspent, unlocking_script=Script(unlocking_script_bytes), sequence=sequence)
        return None


class TxOutput:

    def __init__(self,
                 out: Union[str, List[Union[str, bytes]], Script],
                 value: int = 0,
                 script_type: ScriptType = Unknown()):
        self.value = value
        if isinstance(out, str):
            # from address
            self.locking_script: Script = P2PKH.locking(out)
            self.script_type: ScriptType = P2PKH()
        elif isinstance(out, List):
            # from list of pushdata
            self.locking_script: Script = OpReturn.locking(out)
            self.script_type: ScriptType = OpReturn()
        elif isinstance(out, Script):
            # from locking script
            self.locking_script: Script = out
            self.script_type: ScriptType = script_type
        else:
            raise TypeError('unsupported transaction output type')

    def serialize(self) -> bytes:
        return b''.join([
            self.value.to_bytes(8, 'little'),
            self.locking_script.byte_length_varint(),
            self.locking_script.serialize()
        ])

    def __str__(self) -> str:
        return f'<TxOutput value={self.value} locking_script={self.locking_script.hex()}>'

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_hex(cls, stream: Union[str, bytes, TransactionBytesIO]) -> Optional['TxOutput']:
        with suppress(Exception):
            if not isinstance(stream, TransactionBytesIO):
                stream = TransactionBytesIO(stream if isinstance(stream, bytes) else bytes.fromhex(stream))
            value = stream.read_int(8)
            assert value is not None
            script_length = stream.read_varint()
            assert script_length is not None
            locking_script_bytes = stream.read_bytes(script_length)
            return TxOutput(out=Script(locking_script_bytes), value=value)
        return None


class Transaction:

    def __init__(self,
                 tx_inputs: Optional[List[TxInput]] = None,
                 tx_outputs: Optional[List[TxOutput]] = None,
                 version: int = VERSION,
                 locktime: int = LOCKTIME,
                 fee_rate: Optional[float] = None,
                 network: Optional[Network] = None,
                 provider: Optional[Provider] = None,
                 **kwargs):
        self.inputs: List[TxInput] = tx_inputs or []
        self.outputs: List[TxOutput] = tx_outputs or []
        self.version: int = version
        self.locktime: int = locktime
        self.fee_rate: float = fee_rate if fee_rate is not None else FEE_RATE

        self.network: Network = network
        self.provider: Provider = provider
        if self.provider:
            self.network = self.provider.network

        self.kwargs: Dict[str, Any] = dict(**kwargs) or {}

    def serialize(self) -> bytes:
        raw = self.version.to_bytes(4, 'little')
        raw += unsigned_to_varint(len(self.inputs))
        for tx_input in self.inputs:
            raw += tx_input.serialize()
        raw += unsigned_to_varint(len(self.outputs))
        for tx_output in self.outputs:
            raw += tx_output.serialize()
        raw += self.locktime.to_bytes(4, 'little')
        return raw

    def add_input(self, tx_input: Union[TxInput, Unspent]) -> 'Transaction':
        if isinstance(tx_input, TxInput):
            self.inputs.append(tx_input)
        elif isinstance(tx_input, Unspent):
            self.inputs.append(TxInput(tx_input))
        else:
            raise TypeError('unsupported transaction input type')
        return self

    def add_inputs(self, tx_inputs: List[Union[TxInput, Unspent]]) -> 'Transaction':
        for tx_input in tx_inputs:
            self.add_input(tx_input)
        return self

    def add_output(self, tx_output: TxOutput) -> 'Transaction':
        self.outputs.append(tx_output)
        return self

    def add_outputs(self, tx_outputs: List[TxOutput]) -> 'Transaction':
        for tx_output in tx_outputs:
            self.add_output(tx_output)
        return self

    def hex(self) -> str:
        return self.serialize().hex()

    raw = hex

    def txid(self) -> str:
        return hash256(self.serialize())[::-1].hex()

    def _digest(self, tx_input: TxInput, hash_prevouts: bytes, hash_sequence: bytes, hash_outputs: bytes) -> bytes:
        """
        BIP-143 https://github.com/bitcoin/bips/blob/master/bip-0143.mediawiki
         1. nVersion of the transaction (4-byte little endian)
         2. hashPrevouts (32-byte hash)
         3. hashSequence (32-byte hash)
         4. outpoint (32-byte hash + 4-byte little endian)
         5. scriptCode of the input (serialized as scripts inside CTxOuts)
         6. value of the output spent by this input (8-byte little endian)
         7. nSequence of the input (4-byte little endian)
         8. hashOutputs (32-byte hash)
         9. nLocktime of the transaction (4-byte little endian)
        10. sighash type of the signature (4-byte little endian)
        """
        stream = BytesIO()
        # 1
        stream.write(self.version.to_bytes(4, 'little'))
        # 2
        stream.write(hash_prevouts)
        # 3
        stream.write(hash_sequence)
        # 4
        stream.write(bytes.fromhex(tx_input.txid)[::-1])
        stream.write(tx_input.vout.to_bytes(4, 'little'))
        # 5
        stream.write(tx_input.locking_script.byte_length_varint())
        stream.write(tx_input.locking_script.serialize())
        # 6
        stream.write(tx_input.value.to_bytes(8, 'little'))
        # 7
        stream.write(tx_input.sequence.to_bytes(4, 'little'))
        # 8
        stream.write(hash_outputs)
        # 9
        stream.write(self.locktime.to_bytes(4, 'little'))
        # 10
        stream.write(tx_input.sighash.to_bytes(4, 'little'))
        return stream.getvalue()

    def digests(self) -> List[bytes]:
        """
        :returns: the digests of unsigned transaction
        """
        _hash_prevouts = hash256(b''.join([
            bytes.fromhex(_in.txid)[::-1] + _in.vout.to_bytes(4, 'little') for _in in self.inputs
        ]))
        _hash_sequence = hash256(b''.join([_in.sequence.to_bytes(4, 'little') for _in in self.inputs]))
        _hash_outputs = hash256(b''.join([tx_output.serialize() for tx_output in self.outputs]))
        digests = []
        for i in range(len(self.inputs)):
            sighash = self.inputs[i].sighash
            # hash previous outs
            if not sighash & SIGHASH.ANYONECANPAY:
                # if anyone can pay is not set
                hash_prevouts = _hash_prevouts
            else:
                hash_prevouts = b'\x00' * 32
            # hash sequence
            if not sighash & SIGHASH.ANYONECANPAY and sighash & 0x1f != SIGHASH.SINGLE and sighash & 0x1f != SIGHASH.NONE:
                # if none of anyone can pay, single, none is set
                hash_sequence = _hash_sequence
            else:
                hash_sequence = b'\x00' * 32
            # hash outputs
            if sighash & 0x1f != SIGHASH.SINGLE and sighash & 0x1f != SIGHASH.NONE:
                # if neither single nor none
                hash_outputs = _hash_outputs
            elif sighash & 0x1f == SIGHASH.SINGLE and i < len(self.outputs):
                # if single and the input index is smaller than the number of outputs
                hash_outputs = hash256(self.outputs[i].serialize())
            else:
                hash_outputs = b'\x00' * 32
            digests.append(self._digest(self.inputs[i], hash_prevouts, hash_sequence, hash_outputs))
        return digests

    def digest(self, index: int) -> bytes:
        """
        :returns: digest of the input specified by index
        """
        assert 0 <= index < len(self.inputs), f'index out of range [0, {len(self.inputs)})'
        return self.digests()[index]

    def sign(self, bypass: bool = True, **kwargs) -> 'Transaction':
        """
        :bypass: if True then ONLY sign inputs which unlocking script is None, otherwise sign all the inputs
        sign all inputs according to their script type
        """
        digests = self.digests()
        for i in range(len(self.inputs)):
            tx_input = self.inputs[i]
            if tx_input.unlocking_script is None or not bypass:
                signatures: List[bytes] = [private_key.sign(digests[i]) for private_key in tx_input.private_keys]
                payload = {'signatures': signatures, 'private_keys': tx_input.private_keys, 'sighash': tx_input.sighash}
                tx_input.unlocking_script = tx_input.script_type.unlocking(**payload, **{**self.kwargs, **kwargs})
        return self

    def total_value_in(self) -> int:
        return sum([tx_input.value for tx_input in self.inputs])

    def total_value_out(self) -> int:
        return sum([tx_output.value for tx_output in self.outputs])

    def fee(self) -> int:
        """
        :returns: actual fee paid of this transaction under the current state
        """
        return self.total_value_in() - self.total_value_out()

    def byte_length(self) -> int:
        """
        :returns: actual byte length of this transaction under the current state
        """
        return len(self.serialize())

    size = byte_length

    def estimated_byte_length(self, **kwargs) -> int:
        """
        :returns: estimated byte length of this transaction after signing
        if transaction has already signed, it will return the same value as function byte_length
        """
        estimated_length = 4 + len(unsigned_to_varint(len(self.inputs))) + len(
            unsigned_to_varint(len(self.outputs))) + 4
        for tx_input in self.inputs:
            if tx_input.unlocking_script is not None:
                # unlocking script already set
                estimated_length += len(tx_input.serialize())
            else:
                estimated_length += 41 + tx_input.script_type.estimated_unlocking_byte_length(
                    private_keys=tx_input.private_keys, **{**self.kwargs, **kwargs})
        for tx_output in self.outputs:
            estimated_length += 8 + len(
                tx_output.locking_script.byte_length_varint()) + tx_output.locking_script.byte_length()
        return estimated_length

    estimated_size = estimated_byte_length

    def estimated_fee(self) -> int:
        """
        :returns: estimated fee of this transaction after signing
        """
        return math.ceil(self.fee_rate * self.estimated_byte_length())

    def add_change(self, change_address: Optional[str] = None) -> 'Transaction':
        # byte length increased after adding a P2PKH change output
        size_increased = 34 + len(unsigned_to_varint(len(self.outputs) + 1)) - len(
            unsigned_to_varint(len(self.outputs)))
        # then we know the estimated byte length after signing, of this transaction with a change output
        fee_expected = math.ceil(self.fee_rate * (self.estimated_byte_length() + size_increased))
        fee_overpaid = self.fee() - fee_expected
        if fee_overpaid > 0:
            change_output: Optional[TxOutput] = None
            if not change_address:
                for tx_input in self.inputs:
                    if tx_input.script_type == P2PKH():
                        change_output = TxOutput(out=tx_input.locking_script, value=fee_overpaid, script_type=P2PKH())
                        break
            else:
                change_output = TxOutput(out=change_address, value=fee_overpaid)
            assert change_output, "can't parse any address from transaction inputs"
            self.add_output(change_output)
        return self

    def broadcast(self, check_fee: bool = True) -> BroadcastResult:
        fee_expected = self.estimated_fee()
        if check_fee and self.fee() < fee_expected:
            raise InsufficientFunds(
                f'require {self.total_value_out() + fee_expected} satoshi but only {self.total_value_in()}')
        return Service(self.network, self.provider).broadcast(self.hex())

    def to_unspent(self, vout: int, **kwargs) -> Optional[Unspent]:
        assert 0 <= vout < len(self.outputs), 'vout out of range'
        out = self.outputs[vout]
        if out.script_type in [OpReturn()]:
            return None
        return Unspent(txid=self.txid(), vout=vout, value=out.value, script_type=out.script_type,
                       locking_script=out.locking_script, **kwargs)

    def to_unspents(self, vouts: Optional[List[int]] = None, args: Optional[List[Dict]] = None) -> List[Unspent]:
        """
        parse all the outputs to unspents if vouts is None or empty, OP_RETURN outputs will be omitted
        """
        vouts = vouts or range(len(self.outputs))
        unspents = []
        for i in range(len(vouts)):
            arg = args[i] if args and 0 <= i < len(args) else {}
            unspent = self.to_unspent(vouts[i], **arg)
            if unspent:
                unspents.append(unspent)
        return unspents

    @classmethod
    def from_hex(cls, stream: Union[str, bytes, TransactionBytesIO]) -> Optional['Transaction']:
        with suppress(Exception):
            if not isinstance(stream, TransactionBytesIO):
                stream = TransactionBytesIO(stream if isinstance(stream, bytes) else bytes.fromhex(stream))
            t = Transaction()
            t.version = stream.read_int(4)
            assert t.version is not None
            inputs_count = stream.read_varint()
            assert inputs_count is not None
            for _ in range(inputs_count):
                _input = TxInput.from_hex(stream)
                assert _input is not None
                t.inputs.append(_input)
            outputs_count = stream.read_varint()
            assert outputs_count is not None
            for _ in range(outputs_count):
                _output = TxOutput.from_hex(stream)
                assert _output is not None
                t.outputs.append(_output)
            t.locktime = stream.read_int(4)
            assert t.locktime is not None
            return t
        return None