import re

from citations import SOURCE_ID


DISPLAY_CITATION = re.compile(
    r"\[" + SOURCE_ID.pattern + r"(?:(?:\s*[,;]\s*|\s+)" + SOURCE_ID.pattern + r")*\]"
    r"|" + SOURCE_ID.pattern
)


def citation_parts(answer, chunks):
    """Build escaped-template parts without changing the raw model answer or its checks."""
    numbers = {chunk["id"]: number for number, chunk in enumerate(chunks, start=1)}
    parts = []
    end = 0
    for match in DISPLAY_CITATION.finditer(answer):
        if match.start() > end:
            parts.append({"text": answer[end:match.start()]})
        for position, source_id in enumerate(SOURCE_ID.findall(match.group())):
            if position:
                parts.append({"text": " "})
            if source_id in numbers:
                parts.append({"number": numbers[source_id]})
            else:
                parts.append({"text": "[unverified source]"})
        end = match.end()
    if end < len(answer):
        parts.append({"text": answer[end:]})
    return parts
