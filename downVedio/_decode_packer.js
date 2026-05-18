// Decode the packer JS from 91porna
const fs = require('fs');
const https = require('https');
const http = require('http');

const url = 'https://91porna.com/comic/index/detail?video_key=319648';

const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://91porna.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9',
};

function get(url) {
    return new Promise((resolve, reject) => {
        const proto = url.startsWith('https') ? https : http;
        proto.get(url, { headers }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => resolve(data));
        }).on('error', reject);
    });
}

async function main() {
    const html = await get(url);

    // Find all eval(function(p,a,c,k,e,d)...) patterns
    const packerRegex = /eval\(function\(p,a,c,k,e,d\)\{([\s\S]*?)\}\(([^)]+)\)\)/g;
    let match;
    while ((match = packerRegex.exec(html)) !== null) {
        const body = match[1];
        const args = match[2];

        // Parse the args
        // args is like: 'packed_code',54,54,'key1|key2|...'
        // Extract the packed string
        const argMatch = args.match(/^'([\s\S]*)',(\d+),(\d+),'([\s\S]*)'(?:,(\d+),(\{[\s\S]*\}))?$/);
        if (!argMatch) {
            console.log('Could not parse args, first 500 chars:', args.substring(0, 500));
            continue;
        }

        const packedCode = argMatch[1];
        const base = parseInt(argMatch[2]);
        const count = parseInt(argMatch[3]);
        const keyStr = argMatch[4];
        const keys = keyStr.split('|');

        console.log('Packed code length:', packedCode.length);
        console.log('Base:', base, 'Count:', count);
        console.log('Keys count:', keys.length);

        // Decode: the packer replaces indices with base-54 encoded words
        // The encoding function e(c):
        //   if c < base: return ''
        //   else: e(parseInt(c/base))
        //   + ((c % base) > 35 ? chr(c%base+29) : (c%base).toString(36))

        // For decoding, we need to:
        // 1. Find each "word" in the packed code
        // 2. Convert it from base-54 to get the index
        // 3. If index >= base, replace with keys[index-base]

        function decodeWord(w) {
            let result = 0;
            for (let ch of w) {
                let digit;
                if (ch >= '0' && ch <= '9') digit = ch.charCodeAt(0) - 48;
                else if (ch >= 'a' && ch <= 'z') digit = ch.charCodeAt(0) - 87;
                else if (ch >= 'A' && ch <= 'Z') digit = ch.charCodeAt(0) - 29;
                else return null;
                result = result * base + digit;
            }
            return result;
        }

        let decoded = packedCode.replace(/[0-9a-zA-Z_$]+/g, (word) => {
            // Skip if it's a known JS keyword or contains $
            if (word.includes('$') || word.includes('_')) {
                // Check first chars
            }
            const val = decodeWord(word);
            if (val === null || val < base) return word;
            const idx = val - base;
            if (idx < keys.length) return keys[idx];
            return word;
        });

        // Decode escape sequences
        decoded = decoded.replace(/\\'/g, "'");
        decoded = decoded.replace(/\\"/g, '"');
        decoded = decoded.replace(/\\\\/g, '\\');
        decoded = decoded.replace(/\\n/g, '\n');
        decoded = decoded.replace(/\\t/g, '\t');
        decoded = decoded.replace(/\\r/g, '\r');

        console.log('\n=== Decoded JS ===');
        console.log(decoded.substring(0, 3000));

        // Extract video URLs
        const urlPattern = /https?:\/\/[^\s'"<>]+/g;
        const urls = decoded.match(urlPattern) || [];
        console.log('\n=== URLs in decoded JS ===');
        urls.forEach(u => console.log(u));

        // Look for m3u8, mp4, embed patterns
        console.log('\n=== Key patterns ===');
        for (const pattern of ['m3u8', 'mp4', 'embed', 'player', 'src=', 'script']) {
            const regex = new RegExp(`.{0,80}${pattern}.{0,80}`, 'gi');
            const matches = decoded.match(regex);
            if (matches) {
                matches.forEach(m => console.log(`  [${pattern}]: ${m}`));
            }
        }
    }
}

main().catch(console.error);
