"""Decode packer JS from 91porna"""
import requests
import re

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://91porna.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})
r = s.get('https://91porna.com/comic/index/detail?video_key=319648', timeout=30)
html = r.text

# Find all packer evals - find the specific pattern
results = []
for m in re.finditer(r'eval\(function\(p,a,c,k,e,d\)\{', html):
    start_idx = m.start()
    body_start = m.end()
    # Find matching closing brace before the args
    depth = 1
    pos = body_start
    while pos < len(html) and depth > 0:
        if html[pos] == '{':
            depth += 1
        elif html[pos] == '}':
            depth -= 1
        pos += 1
    body_end = pos - 1  # position of closing }
    body = html[body_start:body_end]
    # After closing }, should be (args)
    rest = html[pos:].strip()
    if rest.startswith('('):
        # Find matching )
        depth2 = 1
        pos2 = pos + 1
        while pos2 < len(html) and depth2 > 0:
            if html[pos2] == '(':
                depth2 += 1
            elif html[pos2] == ')':
                depth2 -= 1
            elif html[pos2] in "'\"'":
                # Skip strings
                q = html[pos2]
                pos2 += 1
                while pos2 < len(html) and html[pos2] != q:
                    if html[pos2] == '\\':
                        pos2 += 1
                    pos2 += 1
                pos2 += 1
                continue
            pos2 += 1
        args_str = rest[1:pos2 - pos]  # content between ( and )
        results.append((body, args_str))
    else:
        # Maybe no parens
        pass

print(f'Found {len(results)} packer(s)')

for mi, (body, args_str) in enumerate(results):
    print(f'\n{"="*60}')
    print(f'Packer #{mi}')
    print(f'{"="*60}')

    # Parse args: 'packed_code',base,count,'key1|key2|...'
    # Find packed code (first arg, single-quoted string)
    idx = 0
    while idx < len(args_str) and args_str[idx] in ' \t\n':
        idx += 1
    assert args_str[idx] == "'", f"Expected quote at {idx}, got: {args_str[idx:idx+10]}"

    # Extract string handling escapes
    packed_end = idx + 1
    while packed_end < len(args_str):
        if args_str[packed_end] == '\\':
            packed_end += 2
            continue
        if args_str[packed_end] == "'":
            break
        packed_end += 1
    packed_code = args_str[idx+1:packed_end]
    rest = args_str[packed_end+1:].lstrip().lstrip(',')

    # Parse: base, count, 'keys', [additional]
    # Split on commas but respect quotes
    part_parts = []
    i = 0
    current = ''
    in_quote = False
    quote_char = None
    while i < len(rest):
        ch = rest[i]
        if in_quote:
            if ch == '\\':
                current += ch
                i += 1
                if i < len(rest):
                    current += rest[i]
            elif ch == quote_char:
                current += ch
                in_quote = False
            else:
                current += ch
        else:
            if ch in "'\"":
                in_quote = True
                quote_char = ch
                current += ch
            elif ch == ',':
                part_parts.append(current.strip())
                current = ''
            else:
                current += ch
        i += 1
    if current.strip():
        part_parts.append(current.strip())

    base = int(part_parts[0]) if part_parts else 62
    count = int(part_parts[1]) if len(part_parts) > 1 else 0
    keys_str = part_parts[2] if len(part_parts) > 2 else ''
    if keys_str.startswith("'") and keys_str.endswith("'"):
        keys_str = keys_str[1:-1]
    elif keys_str.startswith('"') and keys_str.endswith('"'):
        keys_str = keys_str[1:-1]
    keys = keys_str.split('|')

    print(f'Packed code: {len(packed_code)} chars')
    print(f'Base: {base}, Count: {count}')
    print(f'Keys: {len(keys)} items')
    print(f'First 10 keys: {keys[:10]}')
    print(f'Last 5 keys: {keys[-5:]}')

    # Decode each word
    def decode_word(w, base):
        result = 0
        for ch in w:
            if '0' <= ch <= '9':
                digit = ord(ch) - 48
            elif 'a' <= ch <= 'z':
                digit = ord(ch) - 87
            elif 'A' <= ch <= 'Z':
                digit = ord(ch) - 29
            else:
                return None
            result = result * base + digit
        return result

    def replace_word(m):
        word = m.group(0)
        val = decode_word(word, base)
        if val is None or val < base:
            return word
        idx = val - base
        if 0 <= idx < len(keys):
            return keys[idx]
        return word

    decoded = re.sub(r'[0-9a-zA-Z_][0-9a-zA-Z_]*', replace_word, packed_code)

    # Unescape
    decoded = decoded.replace("\\'", "'")
    decoded = decoded.replace('\\"', '"')
    decoded = decoded.replace('\\\\', '\\')
    decoded = decoded.replace('\\n', '\n')
    decoded = decoded.replace('\\t', '\t')
    decoded = decoded.replace('\\/', '/')

    print(f'\n--- Decoded JS (first 2000 chars) ---')
    print(decoded[:2000])

    # Extract all URLs
    urls = re.findall(r'https?://[^\s"\'<>\\]+', decoded)
    print(f'\n--- URLs ({len(urls)}) ---')
    for u in urls:
        print(f'  {u}')

    # Extract the script src path
    scripts = re.findall(r'src\s*=\s*["\']([^"\']+)["\']', decoded)
    print(f'\n--- Script srcs ---')
    for s in scripts:
        print(f'  {s}')

    # Also search for m3u8 / video patterns in FULL decoded text
    for kw in ['m3u8', '.mp4', '.ts', 'embed', 'video', 'player']:
        results = re.findall(rf'.{{0,100}}{kw}.{{0,100}}', decoded, re.IGNORECASE)
        if results:
            print(f'\n--- {kw} context ---')
            for r in results[:5]:
                print(f'  {r.strip()}')
