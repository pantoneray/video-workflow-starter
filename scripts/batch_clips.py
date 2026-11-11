"""Folder scanning and reviewed batch export, reusing existing stages."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from scan_long import run
from slice import probe_video
from select_candidates import choose

ROOT = Path(__file__).resolve().parent

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def scan_folder(folder, out, rules, count, workers=1, per_video=0, order='quality'):
    folder, out = Path(folder).resolve(), Path(out).resolve()
    if not folder.is_dir() or count < 1 or not 1 <= workers <= 4 or per_video < 0:
        raise ValueError('Invalid folder, count, workers (1–4), or per-video limit')
    if out == folder or folder in out.parents:
        raise ValueError('Output must be outside the source folder')
    sources, errors = [], []
    for p in sorted(folder.rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.mp4','.mov','.mkv','.m4v','.avi','.webm'}:
            try:
                duration,w,h = probe_video(p)
                sources.append({'source':str(p),'duration':duration,'pixels':w*h,'short_side':min(w,h)})
            except Exception as e: errors.append({'source':str(p),'error':str(e)})
    if order == 'quality': sources.sort(key=lambda s:(-s['short_side'],-s['pixels'],s['source']))
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'count':count,'per_video':per_video,'order':order,'workers':workers,'sources':sources,'errors':errors,
                'note':'Resolution priority is only a proxy; actual clarity and actions require continuous visual review.'}
    save(out/'batch.json',manifest)
    def work(pair):
        i,s = pair
        target=out/f'video-{i:04d}'
        try:
            report=run(s['source'],rules,target)
            return dict(s,report=str((target/'coverage.json').resolve()),candidates=len(report['candidates']),state='awaiting_review')
        except Exception as e:return dict(s,state='failed',error=str(e))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        manifest['sources']=list(pool.map(work,enumerate(sources,1)))
    save(out/'batch.json',manifest)
    return manifest

def export(batch, selections, out):
    batch=Path(batch).resolve(); data=json.loads(batch.read_text()); entries=json.loads(Path(selections).read_text())
    out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=False)
    allowed={str(Path(s['report']).resolve()):s for s in data['sources'] if s.get('report')}
    by_report={}
    for entry in entries:
        key=str(Path(entry['report']).resolve())
        if key not in allowed or key in by_report:raise ValueError('Unknown or duplicate source report')
        by_report[key]=entry
    plans=[]; remaining=data['count']
    # Validate every selected review before rendering any media.
    for source_index,(key,s) in enumerate(allowed.items()):
        if key not in by_report:continue
        e=by_report[key]; ids=e['candidate_ids']
        cuts=out/f'validated-{source_index:04d}.json'
        choose(SimpleNamespace(candidates=key,candidate_id=ids,review_file=e['review_file'],visual_reviewed=True,out=str(cuts)))
        validated=json.loads(cuts.read_text())
        limit=min(remaining,data['per_video'] or remaining)
        selected=validated[:limit]
        if selected:
            save(cuts,selected); plans.append((s['source'],cuts,len(selected)));remaining-=len(selected)
    results=[]
    for i,(source,cuts,n) in enumerate(plans,1):
        target=out/f'video-{i:04d}'
        subprocess.run([sys.executable,str(ROOT/'slice.py'),'--input',source,'--cuts',str(cuts),'--out',str(target)],check=True,timeout=max(3600,n*3600),stdout=subprocess.DEVNULL)
        results.append({'source':source,'manifest':str(target/'manifest.json'),'count':n})
    receipt={'requested':data['count'],'exported':sum(x['count'] for x in results),'shortfall':remaining,'results':results}
    save(out/'batch-result.json',receipt);return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('scan');s.add_argument('--folder',required=True);s.add_argument('--out',required=True);s.add_argument('--rules',required=True)
    s.add_argument('--count',type=int,required=True);s.add_argument('--workers',type=int,default=1);s.add_argument('--per-video',type=int,default=0);s.add_argument('--order',choices=['quality','name'],default='quality')
    s=sub.add_parser('export');s.add_argument('--batch',required=True);s.add_argument('--selections',required=True);s.add_argument('--out',required=True)
    a=vars(p.parse_args());action=a.pop('action'); result=scan_folder(**a) if action=='scan' else export(**a)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
