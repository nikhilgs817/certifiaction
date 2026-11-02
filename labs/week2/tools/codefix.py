import re
LIMIT = 116
def find_comment(line):
    sq = dq = False
    for i, c in enumerate(line):
        if c == "'" and not dq: sq = not sq
        elif c == '"' and not sq: dq = not dq
        elif c == '#' and not sq and not dq and i >= 2 and line[i-1] == ' ' and line[i-2] == ' ' \
                and (i + 1 == len(line) or line[i+1] == ' ') and line[:i].strip():
            return i
    return -1
def fix_block(lines):
    out, left = [], []
    for ln in lines:
        if len(ln) > LIMIT:
            i = find_comment(ln)
            prev = out[-1].rstrip() if out else ''
            if i > 0 and not prev.endswith(('\\', '`', '|')):
                indent = re.match(r'\s*', ln).group(0)
                out.append(indent + ln[i:].strip()); out.append(ln[:i].rstrip()); continue
            left.append(ln)
        out.append(ln)
    return out, left
