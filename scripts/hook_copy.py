"""Create a source-bound A/B review proposal by moving one complete sentence.

No model call, translation, rendering or approval. Sentence boundaries cannot
prove semantic independence; reviewers must check pronouns and qualifications.
"""
import argparse
import json
import math
from pathlib import Path
import re
from review_html import render, verify_source
from review_protocol import validate_round
from translation_review import version_digest
from speech_plan import effective_count


def sentence_ranges(text):
    # Preserve punctuation, closing quotes and whitespace exactly.
    spans=[]; start=0
    for match in re.finditer(r'[。！？!?；;]+[”’"\']*|\.(?=\s|$)', text):
        stop=match.end()
        if text[start:stop].strip():spans.append((start,stop))
        start=stop
    if text[start:].strip():spans.append((start,len(text)))
    elif spans and start<len(text):spans[-1]=(spans[-1][0],len(text))
    if not spans:raise ValueError('source has no reviewable sentence')
    return spans


def copy_proposal(source, hook_index, *, characters_per_minute, rate_basis):
    verify_source(source)
    if not isinstance(rate_basis,str) or not rate_basis.strip():
        raise ValueError('speech rate basis is required; do not invent measured timing')
    if not math.isfinite(characters_per_minute) or characters_per_minute<=0:
        raise ValueError('invalid source-language character rate')
    original=source['original_exact'];spans=sentence_ranges(original)
    if type(hook_index) is not int or not 0<=hook_index<len(spans):
        raise ValueError('hook index must select one complete sentence')
    order=[hook_index]+[i for i in range(len(spans)) if i!=hook_index]
    mapping=[];parts=[];cursor=0
    for n in order:
        start,end=spans[n];part=original[start:end];parts.append(part)
        mapping.append({'source_sentence':n,'A_start':start,'A_end':end,
                        'B_start':cursor,'B_end':cursor+len(part),'text':part,'changed_characters':False})
        cursor+=len(part)
    produced=''.join(parts)
    # Every source character must appear exactly once. No shortening to hit 3s.
    ordered=sorted(mapping,key=lambda x:x['A_start'])
    if ''.join(x['text'] for x in ordered)!=original:raise ValueError('source coverage incomplete')
    count = effective_count
    hook=original[slice(*spans[hook_index])]
    hook_s=60*count(hook)/characters_per_minute
    total_s=60*count(original)/characters_per_minute
    warnings=['完整句边界不等于语义独立：必须核对指代、否定、限定和前后逻辑']
    if not 2<=hook_s<=4:warnings.append('完整钩子与约3秒目标不符：请选择其他完整候选或交审核，不自动截句')
    if not 30<=total_s<=45:warnings.append('源文估算时长不在30–45秒内；仍须以目标语实际音频核验，不能用估算冒充实测')
    return {'source':source,'A':original,'B':produced,'original_A_sha256':version_digest(original),
            'production_B_sha256':version_digest(produced),'mapping':mapping,'hook_mode':'copy_frontload',
            'hook_sentence_index':hook_index,'hook_text':hook,'packaging_preview_enabled':False,
            'duration':{'kind':'source_text_estimate_not_measured_audio','characters_per_minute':characters_per_minute,
                        'basis':rate_basis,'counting_rule':'letters_and_digits_only_no_spaces_or_punctuation',
                        'hook_effective_characters':count(hook),'total_effective_characters':count(original),
                        'hook_seconds_estimate':round(hook_s,3),
                        'total_seconds_estimate':round(total_s,3),'hook_target_seconds':3,
                        'whole_video_target_seconds':[30,45],'duplicated_text_seconds':0},
            'warnings':warnings,'requires_new_translation_review_if_B_selected':produced!=original,
            'previous_approval_reusable':False,'approval':'pending'}


def review_round(proposal, *, task_id, item_id, batch, version, round_id, language='zh-CN'):
    current={'schema_version':1,'task_id':task_id,'stage':'T1','language':language,'batch':batch,
             'version':version,'round_id':round_id,'entry':'local_html',
             'items':[{'id':item_id,'version':version,'content':proposal,
                       'required_checks':['原文出处与前后文核对','调序保留否定、限定和指代关系',
                                          '钩子与正文时长依据核对','明确选择A或B且不叠加包装钩子'],
                       'approval_blockers':[]}]}
    validate_round(current)
    return current


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,help='Verified excerpt JSON with file/hash/character range/context')
    p.add_argument('--hook-index',type=int,help='Zero-based full sentence; omit to list candidates only')
    p.add_argument('--characters-per-minute',type=float)
    p.add_argument('--rate-basis')
    p.add_argument('--task-id');p.add_argument('--item-id');p.add_argument('--batch')
    p.add_argument('--version');p.add_argument('--round-id');p.add_argument('--out')
    a=p.parse_args();source=json.loads(Path(a.source).read_text(encoding='utf-8'));verify_source(source)
    if a.hook_index is None:
        print(json.dumps({'state':'candidates_not_selected','sentences':[{'index':i,'start':s,'end':e,'text':source['original_exact'][s:e]}
              for i,(s,e) in enumerate(sentence_ranges(source['original_exact']))]},ensure_ascii=False,indent=2));return
    if any(getattr(a,k) is None for k in ('characters_per_minute','rate_basis','task_id','item_id','batch','version','round_id','out')):
        p.error('selected proposal requires rate basis, stable IDs, new version/round and exclusive output directory')
    proposal=copy_proposal(source,a.hook_index,characters_per_minute=a.characters_per_minute,rate_basis=a.rate_basis)
    current=review_round(proposal,task_id=a.task_id,item_id=a.item_id,batch=a.batch,version=a.version,round_id=a.round_id)
    page=render(current);out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    (out/'round.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'T1.html').write_text(page,encoding='utf-8')
    print(json.dumps({'state':'review_proposal_only','round':str(out/'round.json'),'page':str(out/'T1.html'),
                      'warnings':proposal['warnings'],'external_actions':False},ensure_ascii=False))

if __name__=='__main__':main()
