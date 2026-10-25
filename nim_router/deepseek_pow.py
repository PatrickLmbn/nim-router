import base64
import json
import struct
from pathlib import Path
from typing import Optional

_WASM_PATH = Path(__file__).parent.parent / "wasm" / "sha3_wasm_v1.wasm"

_RATE = 136
_PAD = 0x06
_SUFFIX = 0x80
_MASK = 0xFFFFFFFFFFFFFFFF
_ALGORITHM = "DeepSeekHashV1"
_DEFAULT_TARGET_PATH = "/api/v0/chat/completion"

_ROTATIONS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)

_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)


def _permute(state: list[int]) -> list[int]:
    a = list(state)
    for round_index in range(1, 24):
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & _MASK) for x in range(5)]
        for i in range(25):
            a[i] ^= d[i % 5]
        b = [0] * 25
        for i in range(25):
            x, y = i % 5, i // 5
            n = _ROTATIONS[x][y]
            lane = a[i]
            rotated = lane if n == 0 else (((lane << n) | (lane >> (64 - n))) & _MASK)
            b[y + 5 * ((2 * x + 3 * y) % 5)] = rotated
        for i in range(25):
            x, y = i % 5, i // 5
            a[i] = b[i] ^ ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]) & _MASK
        a[0] ^= _ROUND_CONSTANTS[round_index]
    return a


def _digest(data: bytes) -> bytes:
    block = bytearray(data)
    block.append(_PAD)
    while len(block) % _RATE:
        block.append(0)
    block[-1] |= _SUFFIX
    state = [0] * 25
    for i in range(_RATE // 8):
        state[i] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
    state = _permute(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


def solve_python(challenge: str, prefix: str, difficulty: int) -> int:
    target = challenge.strip().lower()
    for nonce in range(difficulty):
        if _digest(f"{prefix}{nonce}".encode()).hex() == target:
            return nonce
    raise RuntimeError(f"DeepSeek PoW: no solution below difficulty {difficulty}")


class _WasmSolver:

    def __init__(self, path: Path) -> None:
        import wasmtime
        self._wasmtime = wasmtime
        self._engine = wasmtime.Engine()
        self._module = wasmtime.Module.from_file(self._engine, str(path))

    def _solve_once(self, challenge: str, prefix: str, difficulty: int) -> int:
        wasmtime = self._wasmtime
        store = wasmtime.Store(self._engine)
        instance = wasmtime.Instance(store, self._module, [])
        exports = instance.exports(store)
        memory = exports["memory"]
        solve = exports["wasm_solve"]
        stack = exports["__wbindgen_add_to_stack_pointer"]
        allocate = exports["__wbindgen_export_0"]

        def write(data: bytes) -> int:
            ptr = int(allocate(store, len(data), 1)) & 0xFFFFFFFF
            memory.write(store, data, ptr)
            return ptr

        challenge_ptr = write(challenge.encode())
        prefix_ptr = write(prefix.encode())
        ret = int(stack(store, -16)) & 0xFFFFFFFF
        solve(store, ret, challenge_ptr, len(challenge), prefix_ptr, len(prefix), float(difficulty))
        status = struct.unpack("<i", bytes(memory.read(store, ret, ret + 4)))[0]
        answer = struct.unpack("<d", bytes(memory.read(store, ret + 8, ret + 16)))[0]
        stack(store, 16)
        if status != 1:
            raise RuntimeError("DeepSeek PoW: wasm solver found no solution in range")
        return int(answer)

    def solve(self, challenge: str, prefix: str, difficulty: int) -> int:
        try:
            return self._solve_once(challenge, prefix, difficulty)
        except Exception:
            return self._solve_once(challenge, prefix, difficulty)


_solver: Optional[_WasmSolver] = None
_solver_unavailable = False


def _get_solver() -> Optional[_WasmSolver]:
    global _solver, _solver_unavailable
    if _solver is not None or _solver_unavailable:
        return _solver
    if not _WASM_PATH.exists():
        _solver_unavailable = True
        return None
    try:
        _solver = _WasmSolver(_WASM_PATH)
    except Exception:
        _solver_unavailable = True
        return None
    return _solver


def challenge_prefix(challenge: dict) -> str:
    return f"{challenge.get('salt')}_{challenge.get('expire_at')}_"


def solve_challenge(challenge: dict) -> int:
    algorithm = str(challenge.get("algorithm") or _ALGORITHM)
    if algorithm != _ALGORITHM:
        raise RuntimeError(f"DeepSeek PoW: unsupported algorithm {algorithm}")
    target = str(challenge.get("challenge") or "")
    salt = str(challenge.get("salt") or "")
    expire_at = challenge.get("expire_at")
    difficulty = int(float(challenge.get("difficulty") or 0))
    if not target or not salt or not expire_at or difficulty <= 0:
        raise RuntimeError("DeepSeek PoW: incomplete challenge payload")
    prefix = challenge_prefix(challenge)
    solver = _get_solver()
    if solver is not None:
        return solver.solve(target, prefix, difficulty)
    return solve_python(target, prefix, difficulty)


def build_pow_header(challenge: dict, target_path: str = _DEFAULT_TARGET_PATH) -> str:
    payload = {
        "algorithm": str(challenge.get("algorithm") or _ALGORITHM),
        "challenge": str(challenge.get("challenge") or ""),
        "salt": str(challenge.get("salt") or ""),
        "answer": solve_challenge(challenge),
        "signature": str(challenge.get("signature") or ""),
        "target_path": target_path,
    }
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
