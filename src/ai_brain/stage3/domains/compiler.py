"""Offline compilation entrypoint; runtime never compiles or downloads packs."""

from ai_brain.stage3.domains.validation import validate_pack


def compile_reviewed_pack(pack):
    validate_pack(pack)
    return pack
