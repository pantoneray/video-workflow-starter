import re

def seconds(t):
    h,m,s = t.replace(',', '.').split(':')
    return int(h)*3600+int(m)*60+float(s)

def srt(p):
    cues=[]
    for block in re.split(r'\n\s*\n',p.read_text(encoding='utf-8-sig').strip()):
        lines=block.splitlines()
        if len(lines)<3: raise ValueError('Incomplete SRT block')
        a,b=lines[1].split(' --> ')
        cues.append(dict(cue=int(lines[0]),start=a,end=b,start_s=seconds(a),end_s=seconds(b),text='\n'.join(lines[2:])))
    issues=[]
    for i,c in enumerate(cues):
        if c['end_s']<=c['start_s']: issues.append({'cue':c['cue'],'kind':'nonpositive_duration'})
        if i and c['start_s']<cues[i-1]['end_s']: issues.append({'cue':c['cue'],'kind':'overlap','seconds':round(cues[i-1]['end_s']-c['start_s'],3)})
        if i and c['cue']!=cues[i-1]['cue']+1: issues.append({'cue':c['cue'],'kind':'sequence'})
    return cues,issues

