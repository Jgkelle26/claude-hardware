"""Rocky-speak text transformation.

Converts normal English into Rocky's speech patterns from *Project Hail Mary*.
Ported from https://gist.github.com/pedramamini/fa5f6ef99dae79add220188419230642

Usage:
    from mac.rocky_transform import rocky_transform
    text = rocky_transform("I don't understand what you mean")
    # -> "No understand what mean, question?"
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ARTICLES: set[str] = {"a", "an", "the"}

AUXILIARIES: set[str] = {
    "is", "are", "was", "were", "will", "would", "should", "could",
    "do", "does", "did", "has", "have", "had", "am", "been", "being",
}

CONTRACTIONS: dict[str, str] = {
    "don't": "no",
    "doesn't": "no",
    "didn't": "no",
    "won't": "no",
    "wouldn't": "no",
    "shouldn't": "no",
    "couldn't": "no",
    "can't": "no can",
    "isn't": "no",
    "aren't": "no",
    "wasn't": "no",
    "weren't": "no",
    "haven't": "no",
    "hasn't": "no",
    "hadn't": "no",
    "i'm": "I",
    "i've": "I",
    "i'll": "I",
    "i'd": "I",
    "you're": "you",
    "you've": "you",
    "you'll": "you",
    "you'd": "you",
    "he's": "he",
    "she's": "she",
    "it's": "it",
    "we're": "we",
    "we've": "we",
    "we'll": "we",
    "they're": "they",
    "they've": "they",
    "they'll": "they",
    "that's": "that",
    "there's": "there",
    "here's": "here",
    "what's": "what",
    "who's": "who",
    "let's": "we",
}

# Words that trigger triple repetition: source -> repeated base
EMPHASIS: dict[str, str] = {
    "amazing": "amaze",
    "awesome": "amaze",
    "wonderful": "amaze",
    "incredible": "amaze",
    "fantastic": "amaze",
    "excellent": "good",
    "great": "good",
    "perfect": "good",
    "terrible": "bad",
    "horrible": "bad",
    "awful": "bad",
    "dreadful": "bad",
    "beautiful": "good",
    "dangerous": "bad",
    "important": "big",
    "significant": "big",
    "enormous": "big",
    "huge": "big",
    "tiny": "small",
    "interesting": "good",
    "exciting": "good",
    "scary": "bad",
    "frightening": "bad",
    "happy": "good",
    "sad": "bad",
    "angry": "bad",
    "love": "like",
    "hate": "no like",
    "very": "",
    "really": "",
    "extremely": "",
    "absolutely": "",
    "definitely": "",
}

# Phrase-level replacements (applied before word-level processing)
PHRASE_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bi don'?t understand\b", "no understand"),
    (r"\bwhat do you mean\b", "what mean"),
    (r"\bi don'?t know\b", "no know"),
    (r"\bi think\b", "I think-guess"),
    (r"\byou know\b", "you know-understand"),
    (r"\bgoodbye\b", "see later"),
    (r"\bhello\b", "hello hello hello"),
    (r"\bthank you\b", "thank"),
    (r"\bthanks\b", "thank"),
    (r"\bplease\b", ""),
    (r"\bkind of\b", ""),
    (r"\bsort of\b", ""),
    (r"\bactually\b", ""),
    (r"\bbasically\b", ""),
    (r"\bwant to\b", "want"),
    (r"\bneed to\b", "need"),
    (r"\bgoing to\b", "will"),
    (r"\btrying to\b", "try"),
    (r"\bable to\b", "can"),
]


# ---------------------------------------------------------------------------
# Core transformation
# ---------------------------------------------------------------------------

def rocky_transform(text: str) -> str:
    """Convert normal English text into Rocky-speak.

    Processes sentence by sentence, applying:
    1. Phrase-level substitutions
    2. Contraction expansion
    3. Article removal
    4. Auxiliary stripping
    5. Emphasis word repetition
    6. Question suffix formatting
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result: list[str] = []

    for sentence in sentences:
        if not sentence.strip():
            continue
        transformed = _transform_sentence(sentence.strip())
        if transformed:
            result.append(transformed)

    return " ".join(result)


def _transform_sentence(sentence: str) -> str:
    """Transform a single sentence into Rocky-speak."""
    # Detect if it's a question
    is_question = sentence.rstrip().endswith("?")

    # Strip trailing punctuation for processing
    stripped = re.sub(r'[.!?]+$', '', sentence).strip()

    # 1. Phrase-level replacements
    for pattern, replacement in PHRASE_REPLACEMENTS:
        stripped = re.sub(pattern, replacement, stripped, flags=re.IGNORECASE)

    # 2. Process word by word
    words = stripped.split()
    output: list[str] = []

    for word in words:
        lower = word.lower()

        # Expand contractions
        if lower in CONTRACTIONS:
            replacement = CONTRACTIONS[lower]
            if replacement:
                output.append(replacement)
            continue

        # Remove articles (but keep at start of sentence if it's the only content so far)
        if lower in ARTICLES and len(output) > 0:
            continue

        # Remove auxiliaries
        if lower in AUXILIARIES:
            continue

        # Emphasis words -> triple repetition
        if lower in EMPHASIS:
            base = EMPHASIS[lower]
            if base:
                output.append(f"{base} {base} {base}")
            continue

        # Keep the word as-is
        output.append(word)

    result = " ".join(output)

    # Clean up extra whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    if not result:
        return ""

    # Capitalize first letter
    result = result[0].upper() + result[1:]

    # Add question suffix
    if is_question:
        result = result.rstrip("?").rstrip() + ", question?"
    else:
        # Add period if no punctuation
        if not result[-1] in ".!?":
            result += "."

    return result
