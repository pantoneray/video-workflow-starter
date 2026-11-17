"""Read-only Notion connection check; does not install an approval watcher."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid


def read_client(token, *, opener=urllib.request.urlopen, sleep=time.sleep):
    def get(path):
        for attempt in range(3):
            request = urllib.request.Request('https://api.notion.com/v1'+path,
                headers={'Authorization': 'Bearer '+token, 'Notion-Version': '2022-06-28'})
            try:
                with opener(request, timeout=20) as response:
                    return json.load(response), None
            except urllib.error.HTTPError as exc:
                code = exc.code
                exc.close()
                if code not in (429,500,502,503,504) or attempt == 2:
                    return None, {'http_status': code, 'reason': 'notion_request_failed'}
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    return None, {'reason': 'network_unavailable'}
            except (ValueError, TypeError):
                return None, {'reason': 'invalid_api_response'}
            sleep(2**attempt)
    return get


def check(page_id, *, token=None, opener=urllib.request.urlopen, sleep=time.sleep):
    page_id = str(uuid.UUID(page_id))
    token = token if token is not None else os.environ.get('NOTION_API_KEY', '')
    base = {'page_id': page_id, 'writes': 0, 'model_calls': 0,
            'write_permission': 'not_tested', 'approval_adapter': 'not_enabled',
            'account_note': 'API bot identity is not the browser logged-in user'}
    if not token:
        return {**base, 'state': 'not_configured', 'reason': 'NOTION_API_KEY_missing'}
    get = read_client(token, opener=opener, sleep=sleep)
    bot, error = get('/users/me')
    if error:
        return {**base, 'state': 'failed', 'stage': 'identity', **error}
    if not isinstance(bot, dict) or bot.get('type') != 'bot':
        return {**base, 'state': 'failed', 'reason': 'unexpected_identity'}
    base['bot_id'] = bot.get('id');base['workspace_name'] = bot.get('bot', {}).get('workspace_name')
    page, error = get('/pages/'+page_id)
    if error:
        return {**base, 'state': 'failed', 'stage': 'page_access', **error,
                'action': 'Check workspace and share this page with the connection; 404 does not prove deletion'}
    if not isinstance(page, dict):
        return {**base, 'state': 'failed', 'reason': 'unexpected_api_shape'}
    if page.get('archived') or page.get('in_trash'):
        return {**base, 'state': 'failed', 'reason': 'page_archived_or_trashed'}
    blocks, error = get('/blocks/'+page_id+'/children?page_size=1')
    if error:
        return {**base, 'state': 'failed', 'stage': 'content_read', **error}
    if page.get('object') != 'page' or not isinstance(blocks, dict) or blocks.get('object') != 'list' or not isinstance(blocks.get('results'), list):
        return {**base, 'state': 'failed', 'reason': 'unexpected_api_shape'}
    return {**base, 'state': 'read_access_verified', 'page_url': page.get('url'),
            'content_probe_only': True, 'full_page_read': False,
            'next': 'Register the unique review round and verify adapter before enabling continuation'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page-id',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args()
    path=Path(args.out)
    # Reserve before network I/O to avoid overwriting historical receipts.
    with path.open('x',encoding='utf-8') as stream:
        result=check(args.page_id)
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
