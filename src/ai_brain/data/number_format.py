from __future__ import annotations


def digits_of_number(n: int) -> list[int]:
    if n < 0:
        raise ValueError("n must be non-negative")
    return [int(digit) for digit in str(n)]


def place_names_for_digits(num_digits: int) -> list[str]:
    if num_digits <= 0:
        raise ValueError("num_digits must be positive")

    base_places = ["U", "T", "H", "K"]
    if num_digits <= len(base_places):
        return list(reversed(base_places[:num_digits]))

    extra = [f"D{index}" for index in range(num_digits - len(base_places), 0, -1)]
    return [*extra, "K", "H", "T", "U"]


def format_role_number(role: str, n: int) -> str:
    digits = digits_of_number(n)
    places = place_names_for_digits(len(digits))
    return " ".join(
        f"{role}_{place} {digit}" for place, digit in zip(places, digits, strict=True)
    )


def format_plain_digit_number(n: int) -> str:
    return " ".join(str(digit) for digit in digits_of_number(n))
