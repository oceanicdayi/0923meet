"""Anonymous ("anyone with the link") Drive folder review, without credentials.

Same preprocessing as drive_runner.py, but for the case where the source
folder is link-shared and no Drive OAuth credentials are available: the file
list is read from the folder's public HTML payload and originals are fetched
over plain HTTPS. Nothing is uploaded -- all artifacts stay in the local work
directory, so the caller keeps the results instead of a Drive output folder.

Anonymous access gives no md5Checksum, so downloads are verified against the
byte size advertised in the folder listing only.
"""
from pathlib import Path
import datetime, json, re, shutil, time

import requests

from .pipeline import digest, process_video, write_json

FOLDER_URL = 'https://drive.google.com/drive/folders/{}'
DOWNLOAD_URL = 'https://drive.usercontent.google.com/download?id={}&export=download&confirm=t'
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36'
FOLDER_MIME = 'application/vnd.google-apps.folder'

_ESCAPE = re.compile(r'\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|(.))')
_SIMPLE = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', '0': '\0'}


def _unescape(raw):
    """Decode the JS single-quoted string literal holding the folder listing."""
    out = bytearray()
    position = 0
    for m in _ESCAPE.finditer(raw):
        out += raw[position:m.start()].encode('utf-8')
        position = m.end()
        hex_byte, hex_point, literal = m.groups()
        if hex_byte is not None:
            out.append(int(hex_byte, 16))
        elif hex_point is not None:
            out += chr(int(hex_point, 16)).encode('utf-8')
        else:
            out += _SIMPLE.get(literal, literal).encode('utf-8')
    out += raw[position:].encode('utf-8')
    return out.decode('utf-8')


def _timestamp(epoch_ms):
    if not epoch_ms:
        return ''
    return datetime.datetime.fromtimestamp(epoch_ms / 1000, datetime.timezone.utc).isoformat()


def discover_public(folder_id, session=None):
    """List a link-shared folder's files by parsing the folder page payload.

    Raises rather than returning a partial list: an incomplete listing would
    silently drop recordings from the run.
    """
    session = session or requests.Session()
    response = session.get(FOLDER_URL.format(folder_id), headers={'User-Agent': USER_AGENT},
                           timeout=(30, 120))
    response.raise_for_status()
    page = response.text
    payload = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'(.*?)';", page, re.S)
    if not payload:
        title = re.search(r'<title>(.*?)</title>', page, re.S)
        raise PermissionError('No public file listing in the folder page (not link-shared?): '
                              + (title.group(1).strip() if title else 'unknown page'))
    data = json.loads(_unescape(payload.group(1)))
    if data[1] is not None:
        raise RuntimeError('Folder listing is paginated; anonymous listing would be incomplete. '
                            'Use drive_runner.py with credentials for this folder.')
    folder_title = re.search(r'<title>(.*?)</title>', page, re.S)
    records = []
    for entry in data[0]:
        fid, _parents, name, mime = entry[0], entry[1], entry[2], entry[3]
        if mime == FOLDER_MIME:
            raise RuntimeError(f'Subfolder {name!r} found; anonymous listing cannot recurse reliably. '
                                'Use drive_runner.py with credentials for this folder.')
        records.append({'id': fid, 'name': name, 'mimeType': mime,
                        'size': str(entry[13]) if entry[13] is not None else None,
                        'createdTime': _timestamp(entry[10]), 'modifiedTime': _timestamp(entry[9]),
                        'webViewLink': f'https://drive.google.com/file/d/{fid}/view',
                        'relative_source_path': '/' + name,
                        'capabilities': {'canDownload': True},
                        'listing_source': 'public_folder_html'})
    return sorted(records, key=lambda f: (f.get('createdTime', ''), f['id'])), (
        folder_title.group(1).strip() if folder_title else folder_id)


def public_download(session, meta, target):
    """Resumable anonymous download, validated against the advertised size."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = int(meta['size']) if meta.get('size') else None
    if target.exists() and (expected is None or target.stat().st_size == expected):
        return target
    part = target.with_suffix(target.suffix + '.part')
    if part.exists() and expected is not None and part.stat().st_size > expected:
        part.unlink()
    url = DOWNLOAD_URL.format(meta['id'])
    for attempt in range(5):
        position = part.stat().st_size if part.exists() else 0
        if expected is not None and position == expected:
            break
        headers = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
        if position:
            headers['Range'] = f'bytes={position}-'
        response = session.get(url, headers=headers, stream=True, timeout=(30, 300))
        if response.status_code in (429, 500, 502, 503, 504):
            response.close()
            time.sleep(min(2 ** attempt, 16))
            continue
        response.raise_for_status()
        if 'text/html' in (response.headers.get('Content-Type') or ''):
            response.close()
            raise PermissionError('Drive returned an HTML interstitial instead of file bytes; '
                                   'the file is probably not link-shared.')
        if position and response.status_code != 206:
            response.close()
            part.unlink()
            continue
        with response, open(part, 'ab' if position else 'wb') as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)
        if expected is None or part.stat().st_size == expected:
            break
        time.sleep(min(2 ** attempt, 16))
    else:
        raise RuntimeError(f'Download did not reach the expected size for {meta["name"]!r}.')
    if expected is not None and part.stat().st_size != expected:
        raise RuntimeError(f'Size mismatch for {meta["name"]!r}: '
                            f'{part.stat().st_size} of {expected} bytes.')
    part.replace(target)
    return target


def execute_public_review(folder_id, work, model, model_name, run_tag='v1', make_clips=False,
                          frame_interval=15, only_ids=None):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    source, folder_title = discover_public(folder_id, session)
    write_json(work / 'source_manifest.json',
               {'folder_id': folder_id, 'folder_title': folder_title, 'access': 'anonymous',
                'run_tag': run_tag, 'model': model_name, 'files': source})
    print(f'Source folder: {folder_title} ({len(source)} files)', flush=True)
    records = []
    for i, item in enumerate(source, 1):
        label = f'F{i:02}'
        key = label + '_' + item['id']
        folder = work / 'processed' / key
        folder.mkdir(parents=True, exist_ok=True)
        entry = {'label': label, 'source': item, 'content_analysis_complete': False}
        if only_ids and item['id'] not in only_ids:
            entry.update({'status': 'not_selected',
                          'reason': 'Run ALL files before claiming complete coverage.'})
            records.append(entry)
            continue
        print('\nStarting', label, item['name'], flush=True)
        try:
            mime = item['mimeType']
            if not (mime.startswith('video/') or mime.startswith('audio/') or mime.startswith('text/')
                    or mime in ['application/json', 'application/octet-stream']):
                raise RuntimeError(f'Unsupported type requires separate reader: {mime}')
            suffix = Path(item['name']).suffix or ('.mp4' if mime.startswith('video/') else '.bin')
            original = public_download(session, item, work / 'originals' / (item['id'] + suffix))
            entry['download_complete'] = True
            entry['sha256'] = digest(original)
            entry['md5_verified'] = False
            entry['download_verified_by'] = 'byte_size' if item.get('size') else 'nothing'
            normalized = {'id': item['id'], 'title': item['name'], 'size': item.get('size'),
                          'mime_type': mime, 'url': item.get('webViewLink')}
            if mime.startswith('video/') or mime.startswith('audio/'):
                entry['processing'] = process_video(original, folder, normalized, model, model_name,
                                                    clips=make_clips, interval=frame_interval, ocr=True)
            elif mime.startswith('text/') or mime == 'application/json':
                shutil.copy2(original, folder / 'original_text.bin')
                (folder / 'text.txt').write_text(original.read_bytes().decode('utf-8-sig'),
                                                  encoding='utf-8')
                entry.update({'text_decoded': True, 'status': 'awaiting_content_review'})
            else:
                raise RuntimeError('Stored but unsupported for semantic review; explicit reader needed.')
            entry['artifacts_dir'] = str(folder)
        except Exception as error:
            entry.update({'status': 'failed', 'error': str(error)})
            print('Needs attention:', label, str(error), flush=True)
        records.append(entry)
        write_json(work / 'processing_manifest.json', records)
    write_json(work / 'processing_manifest.json', records)
    return records, {'folder_title': folder_title, 'local_output': str(work)}
