"""Convert registered Notion blocks to the existing receipt protocol.

Pure validation only: callers must fetch blocks from the configured page via
the official API. A pasted/exported JSON is not authenticated user approval.
"""
import json
from datetime import datetime
from review_protocol import validate_round, validate_receipt
from translation_review import version_digest


def block_text(block):
    payload = block[block['type']]
    return ''.join(part.get('plain_text', part.get('text', {}).get('content', ''))
                   for part in payload.get('rich_text', []))


def from_blocks(current, registration, blocks):
    binding = validate_round(current)
    if current['entry'] != 'notion' or registration.get('round_sha256') != binding:
        raise ValueError('Notion is not the registered current review entry')
    if not registration.get('page_id') or not registration.get('reviewer_ids'):
        raise ValueError('registered page and explicit reviewer IDs required')
    indexed = {b['id']: b for b in blocks}
    if len(indexed) != len(blocks):
        raise ValueError('duplicate block IDs')
    used = set()
    def get(ident, kind):
        if ident in used:
            raise ValueError('block reused for different review fields')
        used.add(ident)
        block = indexed.get(ident)
        if not block or block.get('type') != kind or block.get('archived') or block.get('in_trash'):
            raise ValueError('registered block missing or wrong type')
        return block
    marker = get(registration['binding_block'], 'code')
    if block_text(marker) != binding:
        raise ValueError('visible round binding changed')
    submitted = get(registration['submit_block'], 'to_do')
    if submitted['to_do'].get('checked') is not True:
        return {'state': 'no_change', 'reason': 'round_not_submitted'}
    if submitted.get('last_edited_by', {}).get('id') not in registration['reviewer_ids']:
        raise ValueError('submission editor is not an authorized reviewer')
    timestamp = submitted.get('last_edited_time', '')
    submitted_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if submitted_at.tzinfo is None:
        raise ValueError('submission timestamp needs timezone')
    receipt = {k: current[k] for k in ('schema_version','round_id','task_id','stage','language','version','entry')}
    receipt.update(content_sha256=binding, submitted_at=timestamp, items=[])
    mappings = registration.get('items', {})
    if set(mappings) != {item['id'] for item in current['items']}:
        raise ValueError('registered item set differs from round')
    for item in current['items']:
        mapping = mappings[item['id']]
        content = get(mapping['content_block'], 'code')
        # The displayed snapshot must equal the trusted round, not only carry a hash label.
        if json.loads(block_text(content)) != item['content']:
            raise ValueError('displayed content changed since registration')
        approved = get(mapping['approved_block'], 'to_do')['to_do'].get('checked')
        rework = get(mapping['rework_block'], 'to_do')['to_do'].get('checked')
        if type(approved) is not bool or type(rework) is not bool or (approved and rework):
            raise ValueError('conflicting or invalid item decision')
        comment = block_text(get(mapping['comment_block'], 'paragraph')).strip()
        if set(mapping.get('checks', {})) != set(item['required_checks']):
            raise ValueError('registered checks incomplete')
        checks = {key:get(ident, 'to_do')['to_do'].get('checked') for key,ident in mapping['checks'].items()}
        decision = {'id':item['id'], 'version':item['version'], 'content_sha256':version_digest(item),
                    'decision':'approved' if approved else 'needs_changes' if rework else 'pending',
                    'comment':comment, 'checks':checks}
        if current['stage'] == 'T1':
            a = get(mapping['select_A_block'], 'to_do')['to_do'].get('checked')
            b = get(mapping['select_B_block'], 'to_do')['to_do'].get('checked')
            if type(a) is not bool or type(b) is not bool or (a and b):
                raise ValueError('conflicting A/B selection')
            decision['selected_text'] = 'A' if a else 'B' if b else ''
        receipt['items'].append(decision)
    # Any later edit requires an explicit re-submit; never accept a stale submit checkbox.
    for ident in used:
        edited = datetime.fromisoformat(indexed[ident]['last_edited_time'].replace('Z', '+00:00'))
        if edited.tzinfo is None or edited > submitted_at:
            raise ValueError('review changed after submission; re-submit required')
    route = validate_receipt(current, receipt, entry='notion')
    return {'state':'validated_not_yet_received', 'receipt':receipt, 'route':route,
            'page_id':registration['page_id'], 'reviewer_id':submitted['last_edited_by']['id']}
