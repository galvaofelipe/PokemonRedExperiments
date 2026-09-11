import hashlib


def derive_seed(suite_version: str, state_name: str, index: int) -> int:
    payload = f"{suite_version}:{state_name}:{index}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


def derive_seeds(suite_version: str, state_name: str, count: int) -> list[int]:
    return [derive_seed(suite_version, state_name, i) for i in range(count)]
