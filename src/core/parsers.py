import re
import chardet

# "00:00:01,000 --> 00:00:02,000", with "." also accepted as the millisecond separator
# and anything after the end time (cue settings such as "X1:40") ignored.
TIMING_PATTERN = re.compile(
    r'^\s*(\d+:\d{1,2}:\d{1,2}[,.]\d+)\s*-->\s*(\d+:\d{1,2}:\d{1,2}[,.]\d+)'
)
BLOCK_SEPARATOR = re.compile(r'\n[ \t]*\n')


def _decode(raw_data):
    encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
    try:
        content = raw_data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        content = raw_data.decode('latin-1')
    return content.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')


def _parse_block(block, fallback_index):
    """Parse one cue: an optional index line, the timing line, then the text lines."""
    lines = block.strip('\n').split('\n')
    for position, line in enumerate(lines[:2]):
        timing = TIMING_PATTERN.match(line)
        if not timing:
            continue
        index = fallback_index
        if position == 1 and lines[0].strip().isdigit():
            index = int(lines[0].strip())
        text = ' '.join(part.strip() for part in lines[position + 1:] if part.strip())
        return {
            'index': index,
            'start_time': srt_time_to_milliseconds(timing.group(1)),
            'end_time': srt_time_to_milliseconds(timing.group(2)),
            'text': text,
        }
    return None


def parse_srt(srt_file):
    """Parse an SRT file into cues.

    Cues are split on blank lines rather than on "a newline followed by digits",
    so a text line that starts with a number stays part of its cue.
    """
    with open(srt_file, 'rb') as f:
        content = _decode(f.read())

    subtitles = []
    for block in BLOCK_SEPARATOR.split(content):
        if not block.strip():
            continue
        cue = _parse_block(block, len(subtitles) + 1)
        if cue is not None:
            subtitles.append(cue)
    return subtitles


def srt_time_to_milliseconds(srt_time):
    try:
        h, m, s_ms = srt_time.split(':')
        s, ms = s_ms.replace(',', '.').split('.')
        total_ms = (
            int(h) * 3600 + int(m) * 60 + int(s)
        ) * 1000 + int(ms.ljust(3, '0')[:3])
        return int(total_ms)
    except ValueError:
        return 0

def milliseconds_to_srt_time(milliseconds):
    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"
