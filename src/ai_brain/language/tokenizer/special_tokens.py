from __future__ import annotations

PAD_TOKEN = "<|pad|>"
BOS_TOKEN = "<|bos|>"
EOS_TOKEN = "<|eos|>"
UNK_TOKEN = "<|unk|>"
PROMPT_TOKEN = "<|prompt|>"
ANSWER_TOKEN = "<|answer|>"
END_TOKEN = "<|end|>"

SPECIAL_TOKENS: tuple[str, ...] = (
    PAD_TOKEN,
    BOS_TOKEN,
    EOS_TOKEN,
    UNK_TOKEN,
    PROMPT_TOKEN,
    ANSWER_TOKEN,
    END_TOKEN,
)

SPECIAL_TOKEN_IDS: dict[str, int] = {
    token: index for index, token in enumerate(SPECIAL_TOKENS)
}
