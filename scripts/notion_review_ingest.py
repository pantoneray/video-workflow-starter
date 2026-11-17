"""One-shot official-API receipt ingestion. No Notion writes or model calls."""
import argparse
from html import escape
import json
import os
from pathlib import Path
import uuid
from notion_preflight import read_client
from notion_review_adapter import from_blocks
from review_protocol import validate_round
from review_receipts import Receipts


def uuid_text(value):
    return str(uuid.UUID(value))


def ingest(current, registration, root, *, token=None, get=None):
    binding = validate_round(current)
    if current['entry'] != 'notion' or registration.get('round_sha256') != binding:
        raise ValueError('inactive Notion entry or stale registration')
    token = token if token is not None else os.environ.get('NOTION_API_KEY', '')
    if get is None:
        if not token:
            return {'state':'not_configured', 'reason':'NOTION_API_KEY_missing', 'model_calls':0}
        get = read_client(token)
    page_id = uuid_text(registration['page_id'])
    def read(path):
        value, error = get(path)
        if error:
            raise ValueError('Notion read failed: '+str(error.get('http_status',error.get('reason','unknown'))))
        if not isinstance(value,dict):
            raise ValueError('unexpected Notion response')
        # Notion attaches a unique transport request_id to each GET. It is not
        # review content; all block fields and edit provenance remain compared.
        value = {key: val for key, val in value.items() if key != 'request_id'}
        return value
    page = read('/pages/'+page_id)
    if page.get('object') != 'page' or page.get('archived') or page.get('in_trash'):
        raise ValueError('registered page unavailable')
    def block(ident):
        value = read('/blocks/'+uuid_text(ident))
        if uuid_text(value['id']) != uuid_text(ident):
            raise ValueError('Notion returned a different block')
        parent = value.get('parent', {})
        if parent.get('type') != 'page_id' or uuid_text(parent.get('page_id','')) != page_id:
            raise ValueError('review block moved outside registered page')
        return value
    submitted = block(registration['submit_block'])
    if submitted.get('type') != 'to_do':
        raise ValueError('submission block is not a checkbox')
    if submitted['to_do'].get('checked') is not True:
        return {'state':'no_change','reason':'round_not_submitted','model_calls':0}
    ids = [registration['binding_block'],registration['submit_block']]
    for mapping in registration['items'].values():
        ids.extend(mapping[key] for key in ('content_block','approved_block','rework_block','comment_block'))
        ids.extend(mapping['checks'].values())
        if current['stage']=='T1':
            ids.extend(mapping[key] for key in ('select_A_block','select_B_block'))
    if len(set(ids)) != len(ids) or len(ids)>500:
        raise ValueError('duplicate block mapping or oversized round')
    first = [block(ident) for ident in ids]
    result = from_blocks(current,registration,first)
    if result['state'] == 'no_change':
        return result
    # Re-read registered blocks only, independent of page pagination or unrelated content.
    second = [block(ident) for ident in ids]
    if first != second or submitted != next(b for b in second if b['id']==registration['submit_block']):
        raise ValueError('Notion review changed during capture; no receipt accepted')
    snapshot = '<!doctype html><meta charset="utf-8"><h1>Notion审核原始快照</h1><pre>'+escape(
        json.dumps({'page_id':page_id,'blocks':second},ensure_ascii=False,indent=2))+'</pre>'
    store = Receipts(root)
    try:
        accepted = store.receive(current,result['receipt'],entry='notion',page=snapshot)
        return {'state':accepted['state'],'receipt':accepted,'reviewer_id':result['reviewer_id'],
                'model_calls':0,'notion_writes':0,'next':'existing review-dispatch'}
    finally:
        store.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('round','registration','root'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        result=ingest(json.loads(Path(args.round).read_text()),json.loads(Path(args.registration).read_text()),args.root)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'state':'capture_failed','error_type':type(exc).__name__,
                          'existing_receipts_unchanged':True}));raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
