import re
import chardet

def parse_srt(srt_file):
    print('srt_file', srt_file)
    pattern = re.compile(
        r'(\d+)\s+([\d:,]+)\s*-->\s*([\d:,]+)\s*(.*?)\s*(?=\n\d+|\Z)',
        re.DOTALL
    )

    with open(srt_file, 'rb') as f:
        raw_data = f.read()

    result = chardet.detect(raw_data)
    encoding = result['encoding']
    if not encoding:
        encoding = 'utf-8'

    try:
        content = raw_data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        content = raw_data.decode('latin-1')

    content = content.replace('\r\n', '\n').replace('\r', '\n')

    matches = re.findall(pattern, content)
    subtitles = []
    for match in matches:
        index = int(match[0])
        start_time = srt_time_to_milliseconds(match[1])
        end_time = srt_time_to_milliseconds(match[2])
        text = match[3].replace('\n', ' ').strip()
        subtitles.append({
            'index': index,
            'start_time': start_time,
            'end_time': end_time,
            'text': text
        })
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
