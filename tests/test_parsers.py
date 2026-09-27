import pytest

from src.core.parsers import milliseconds_to_srt_time, parse_srt, srt_time_to_milliseconds


def _write(tmp_path, text, encoding="utf-8"):
    path = tmp_path / "subtitles.srt"
    path.write_bytes(text.encode(encoding))
    return str(path)


def test_parses_basic_cues(tmp_path):
    srt = _write(tmp_path, "1\n00:00:01,000 --> 00:00:02,500\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n")

    subs = parse_srt(srt)

    assert subs == [
        {"index": 1, "start_time": 1000, "end_time": 2500, "text": "Hello"},
        {"index": 2, "start_time": 3000, "end_time": 4000, "text": "World"},
    ]


def test_keeps_continuation_lines_that_start_with_a_digit(tmp_path):
    srt = _write(tmp_path, "1\n00:00:01,000 --> 00:00:02,000\nI owe you\n20 dollars.\n\n2\n00:00:03,000 --> 00:00:04,000\nNext\n")

    subs = parse_srt(srt)

    assert [s["text"] for s in subs] == ["I owe you 20 dollars.", "Next"]


def test_accepts_dot_millisecond_separator(tmp_path):
    srt = _write(tmp_path, "1\n00:00:05.000 --> 00:00:06.250\nDot separated\n")

    subs = parse_srt(srt)

    assert len(subs) == 1
    assert (subs[0]["start_time"], subs[0]["end_time"]) == (5000, 6250)


def test_handles_crlf_bom_and_extra_blank_lines(tmp_path):
    text = "﻿1\r\n00:00:01,000 --> 00:00:02,000\r\nFirst\r\n\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nSecond\r\n"
    srt = _write(tmp_path, text)

    subs = parse_srt(srt)

    assert [(s["index"], s["text"]) for s in subs] == [(1, "First"), (2, "Second")]


def test_ignores_cue_settings_after_the_timing(tmp_path):
    srt = _write(tmp_path, "1\n00:00:01,000 --> 00:00:02,000 X1:40 X2:600 Y1:20 Y2:50\nPositioned\n")

    assert parse_srt(srt)[0]["text"] == "Positioned"


def test_numbers_cues_without_an_index_line(tmp_path):
    srt = _write(tmp_path, "00:00:01,000 --> 00:00:02,000\nNo index\n\n00:00:03,000 --> 00:00:04,000\nAlso none\n")

    assert [(s["index"], s["text"]) for s in parse_srt(srt)] == [(1, "No index"), (2, "Also none")]


def test_keeps_cues_with_empty_text(tmp_path):
    srt = _write(tmp_path, "1\n00:00:01,000 --> 00:00:02,000\n\n2\n00:00:03,000 --> 00:00:04,000\nAfter\n")

    assert [s["text"] for s in parse_srt(srt)] == ["", "After"]


def test_skips_blocks_without_timing(tmp_path):
    srt = _write(tmp_path, "garbage header\n\n1\n00:00:01,000 --> 00:00:02,000\nKept\n")

    assert [s["text"] for s in parse_srt(srt)] == ["Kept"]


def test_decodes_non_utf8_files(tmp_path):
    srt = _write(tmp_path, "1\n00:00:01,000 --> 00:00:02,000\n你好，世界。这是一段比较长的中文字幕，用来测试编码检测。\n", encoding="gb18030")

    assert parse_srt(srt)[0]["text"].startswith("你好")


@pytest.mark.parametrize("value, expected", [
    ("00:00:01,000", 1000),
    ("01:02:03,456", 3723456),
    ("00:00:01.5", 1500),
    ("0:00:01,000", 1000),
    ("bad", 0),
])
def test_srt_time_to_milliseconds(value, expected):
    assert srt_time_to_milliseconds(value) == expected


def test_milliseconds_round_trip():
    assert milliseconds_to_srt_time(3723456) == "01:02:03,456"
    assert srt_time_to_milliseconds(milliseconds_to_srt_time(3723456)) == 3723456
