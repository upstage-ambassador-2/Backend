from typing import Any, Mapping


PERSONA_TONES = ("매우 격식", "격식", "중립", "친근", "매우 친근")

GENERATION_TONE_LABELS = {
    1: "매우 격식",
    2: "격식",
    3: "중립",
    4: "친근",
    5: "매우 친근",
}

GENERATION_LENGTH_LABELS = {
    1: "매우 짧게",
    2: "짧게",
    3: "보통",
    4: "길게",
    5: "매우 길게",
}

GENERATION_TONE_DESCRIPTIONS = {
    1: "매우 격식 있고 공식적인 톤",
    2: "격식을 갖춘 정중한 업무 톤",
    3: "중립적이고 자연스러운 톤",
    4: "친근하고 따뜻한 톤",
    5: "매우 친근하고 편안한 톤",
}

GENERATION_LENGTH_DESCRIPTIONS = {
    1: "핵심만 담은 매우 짧은 길이",
    2: "짧고 간결한 길이",
    3: "보통 길이",
    4: "맥락을 충분히 담은 긴 길이",
    5: "상세하고 충분한 설명이 있는 매우 긴 길이",
}


def _legacy_percent_to_scale(value: int) -> int:
    if value <= 20:
        return 1
    if value <= 40:
        return 2
    if value <= 60:
        return 3
    if value <= 80:
        return 4
    return 5


def normalize_generation_scale(
    value: Any,
    *,
    labels: Mapping[int, str] | None = None,
    option_name: str = "값",
) -> int:
    """Normalize new 1-5 inputs and legacy 0-100 slider values."""
    if isinstance(value, bool):
        raise ValueError(f"{option_name}은 1~5 단계여야 합니다.")

    if isinstance(value, str):
        stripped = value.strip()
        if labels:
            label_to_value = {label: scale for scale, label in labels.items()}
            if stripped in label_to_value:
                return label_to_value[stripped]
        try:
            numeric = int(stripped)
        except ValueError as exc:
            raise ValueError(f"{option_name}은 1~5 단계여야 합니다.") from exc
    elif isinstance(value, int):
        numeric = value
    else:
        raise ValueError(f"{option_name}은 1~5 단계여야 합니다.")

    if 1 <= numeric <= 5:
        return numeric
    if 0 <= numeric <= 100:
        return _legacy_percent_to_scale(numeric)
    raise ValueError(f"{option_name}은 1~5 단계여야 합니다.")


def generation_tone_label(value: int) -> str:
    return GENERATION_TONE_LABELS[normalize_generation_scale(value, labels=GENERATION_TONE_LABELS, option_name="tone")]


def generation_length_label(value: int) -> str:
    return GENERATION_LENGTH_LABELS[
        normalize_generation_scale(value, labels=GENERATION_LENGTH_LABELS, option_name="length")
    ]


def generation_tone_description(value: int) -> str:
    return GENERATION_TONE_DESCRIPTIONS[
        normalize_generation_scale(value, labels=GENERATION_TONE_LABELS, option_name="tone")
    ]


def generation_length_description(value: int) -> str:
    return GENERATION_LENGTH_DESCRIPTIONS[
        normalize_generation_scale(value, labels=GENERATION_LENGTH_LABELS, option_name="length")
    ]
