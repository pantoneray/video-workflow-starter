#!/usr/bin/env python3
"""Apply a Shorts editing template to a clip + whisperX word timestamps.

Usage:
  python3 apply_template.py --template ../specs/B_word_highlight_quote.json \
      --video in.mp4 --words words.json --lang id --out out.mp4 \
      [--title "..."] [--title-hl "WORD1,WORD2"] [--name "SPEAKER NAME"] [--name-sub "..."] \
      [--kicker "• Bagian 1 •"] [--background-mode illustration|footage] [--overlay "ANICCA"] [--music bed.mp3] [--emph "word1,word2"] \
      [--preview 3.0] [--ass-only]

words.json = whisperX output: {"segments":[{"words":[{"word":"..","start":0.1,"end":0.4}, ...]}, ...]}
lang: id | mn | zh   (zh uses Noto Sans SC / Noto Serif SC; id/mn use Latin/Cyrillic fonts)
Learn-style only: never feed other creators' footage/music into a published render.
"""
import argparse, json, os, subprocess, re
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); FONTDIR=os.path.join(ROOT,'fonts')
W,H=1080,1920

CAPTION_BAND=(1300,1560)  # v1.1 hard rule: spoken captions only in the lower band (center y), never over the face zone

def bg_mode(t,a):
    # E only: 'illustration' (full-bleed art) or 'footage' (live-action 9:16 shifted down under a shaded title band)
    return (getattr(a,'background_mode',None) or t.get('background_mode') or 'illustration')

def ass_color(hex_, alpha=0):
    h=hex_.lstrip('#'); r,g,b=h[0:2],h[2:4],h[4:6]
    return f'&H{alpha:02X}{b}{g}{r}'.upper()
def ts(t):
    t=max(0,t); h=int(t//3600); m=int(t%3600//60); s=t%60
    return f'{h}:{m:02d}:{s:05.2f}'
def esc(s): return s.replace('{','(').replace('}',')').replace('\n','\\N')

def load_words(p):
    d=json.load(open(p,encoding='utf-8-sig')); out=[]
    segs=d['segments'] if isinstance(d,dict) else d
    for sg in segs:
        for w in sg.get('words',[]):
            if 'start' in w and 'end' in w:
                out.append({'w':w['word'].strip(),'s':float(w['start']),'e':float(w['end'])})
    return out

TRAIL_PUNCT=',.;:，。、；：…'  # v1.4: dropped from the end of each caption chunk; ? and ! are kept
def strip_trailing(c):
    if c:
        last=dict(c[-1]); last['w']=last['w'].rstrip(TRAIL_PUNCT) or last['w']; c=c[:-1]+[last]
    return c

def chunk(words,max_words,max_chars,zh=False):
    chunks=[];cur=[]
    def clen(c): return sum(len(x['w']) for x in c)+(0 if zh else len(c)-1)
    for i,w in enumerate(words):
        gap = w['s']-cur[-1]['e'] if cur else 0
        if cur and (len(cur)>=max_words or clen(cur+[w])>max_chars or gap>0.6):
            chunks.append(cur);cur=[]
        cur.append(w)
        if re.search(r'[.!?。！？，,;；:]$',w['w']) and len(cur)>=1:
            chunks.append(cur);cur=[]
    if cur: chunks.append(cur)
    return [strip_trailing(c) for c in chunks]

def build_ass(t,words,a,dur):
    zh=a.lang=='zh'; F=t['fonts']['zh' if zh else 'latin']; cap=t['captions']
    sep='' if zh else ' '
    def case(s,c):
        if zh: return s
        return s.upper() if c=='upper' else s.lower() if c=='lower' else s
    styles=[]
    def style(name,font,size,color,outline=0,shadow=0,align=5,bold=0,box=False,boxcol='#000000',italic=0,marginv=0):
        bs=3 if box else 1
        back=ass_color(boxcol,0x30) if box else ass_color('#000000',0x60)
        outc=ass_color(boxcol,0x10) if box else ass_color('#000000')
        styles.append(f'Style: {name},{font},{size},{ass_color(color)},{ass_color(color)},{outc},{back},{bold},{italic},0,0,100,100,0,0,{bs},{outline if not box else 12},{shadow},{align},140,140,{marginv},1')
    style('Cap',F[cap['font']],cap['size'],cap['color'],cap.get('outline',0),cap.get('shadow',0),box=cap.get('box',False),boxcol=cap.get('box_color','#000000'))
    ev=[]
    hide_until=min(dur,a.overlay_dur) if (t['id'].startswith('F_') and a.overlay) else 0  # v1.1: F big words share the lower band, so spoken captions wait until they leave
    def add(start,end,text,st='Cap',layer=0):
        if st=='Cap' and start<hide_until:
            start=hide_until
            if end<=start: return
        ev.append(f'Dialogue: {layer},{ts(start)},{ts(end)},{st},,0,0,0,,{text}')
    y=cap['y_center']
    lo,hi=CAPTION_BAND
    if not lo<=y<=hi:
        print(f'WARNING caption y_center {y} outside lower band {lo}-{hi}; clamped (rule: 字幕一律靠下，不得遮挡人脸)')
        y=min(max(y,lo),hi)
    # v1.4 hard rule: the main caption is always horizontally centered on x = W/2 (540). Never move it
    # sideways to dodge the right-side buttons; the symmetric 140 px side margins already keep text inside x 140-940.
    pos=f'{{\\an5\\pos({W//2},{y})}}'
    hl=ass_color(cap.get('highlight',cap['color'])); fut=ass_color(cap.get('future_color',cap['color']))
    base=ass_color(cap['color']); emph=set(x.strip().lower() for x in (a.emph or '').split(',') if x.strip())
    chunks=chunk(words,cap['max_words'],cap['max_chars_zh' if zh else 'max_chars_latin'],zh)
    anim=cap['animation']
    for ci,c in enumerate(chunks):
        cend=c[-1]['e']+0.15
        if ci+1<len(chunks): cend=min(cend,chunks[ci+1][0]['s'])
        cend=max(cend,c[-1]['e'])
        if anim=='phrase':
            txt=sep.join(esc(case(w['w'],cap['case'])) for w in c)
            add(c[0]['s'],cend,pos+'{\\fad(60,40)}'+txt)
        elif anim in ('word_pop','karaoke_fade'):
            for wi,w in enumerate(c):
                s=w['s']; e=c[wi+1]['s'] if wi+1<len(c) else cend
                parts=[]
                for wj,x in enumerate(c):
                    tx=esc(case(x['w'],cap['case']))
                    if anim=='word_pop':
                        if wj==wi or x['w'].lower().strip('.,!?') in emph:
                            pop='{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}' if wj==wi else ''
                            parts.append(f'{{\\c{hl}}}{pop}{tx}{{\\c{base}\\fscx100\\fscy100}}')
                        else: parts.append(tx)
                    else:
                        parts.append(tx if wj<=wi else f'{{\\c{fut}}}{tx}{{\\c{base}}}')
                add(s,e,pos+sep.join(parts))
        elif anim=='karaoke_fill':
            # \kf fills from SecondaryColour to PrimaryColour; set primary=highlight, secondary=base
            txt=''; prev=c[0]['s']
            for x in c:
                k=int(round((x['e']-prev)*100)); prev=x['e']
                txt+=f'{{\\kf{k}}}'+esc(case(x['w'],cap['case']))+sep
            add(c[0]['s'],cend,pos+f'{{\\1c{hl}\\2c{base}}}'+txt.rstrip())
    L=t['layout']
    if t['id'].startswith('A_') and a.title:
        ti=t['title']; style('Title',F[ti['font']],ti['size'] if not zh else int(ti['size']*1.05),ti['color'],0,3)
        hlset=set(x.strip().upper() for x in (a.title_hl or '').split(',') if x.strip())
        words_t=case(a.title,ti['case']).split(' ') if not zh else [case(a.title,ti['case'])]
        tt=' '.join((f'{{\\c{ass_color(ti["highlight"])}}}{esc(w)}{{\\c{ass_color(ti["color"])}}}' if w.strip('.,!?').upper() in hlset else esc(w)) for w in words_t)
        if zh:  # Chinese has no spaces: highlight substrings instead of whole words
            tt=esc(case(a.title,ti['case']))
            for h in hlset: tt=tt.replace(h,f'{{\\c{ass_color(ti["highlight"])}}}{h}{{\\c{ass_color(ti["color"])}}}')
        add(0,dur,f'{{\\an8\\pos({W//2},{L["title"]["y_top"]})\\q0}}'+tt,'Title',2)
        if a.name:
            style('Name',F['sans_xb'],34,'#111111',0,0,box=True,boxcol='#FFFFFF')
            add(0,dur,f'{{\\an5\\pos({W//2},{L["nameplate"]["y"]})}}'+esc(a.name.upper()),'Name',3)
    if t['id'].startswith('C_') and a.name:
        style('NameC',F['serif_bold'],50,'#FFFFFF',0,3,align=1); style('NameSub',F['sans_med'],26,'#E0E0E0',0,2,align=1)
        n=L['nameplate']; st=a.name_in
        add(st,st+2.8,f'{{\\an1\\pos({n["x"]},{n["y"]})\\fad(200,250)}}'+esc(a.name),'NameC',3)
        if a.name_sub: add(st,st+2.8,f'{{\\an7\\pos({n["x"]},{n["y"]+8})\\fad(200,250)}}'+esc(a.name_sub.upper()),'NameSub',3)
    if t['id'].startswith('E_'):
        hd=t['header']; style('Kicker',F['serif_bold'],hd['kicker_size'],hd['color'],0,2); style('Header',F['serif_bold'],hd['size'],hd['color'],0,3)
        y0=L['header']['y']
        if bg_mode(t,a)=='footage': y0=t['background_modes']['footage']['header_y']
        if a.kicker: add(0,dur,f'{{\\an8\\pos({W//2},{y0})}}'+esc(a.kicker),'Kicker',2)
        if a.title: add(0,dur,f'{{\\an8\\pos({W//2},{y0+50})}}'+esc(a.title if zh else a.title.upper()),'Header',2)
    if t['id'].startswith('F_') and a.overlay:
        ov=t['overlay']; style('Big',F[ov['font_big']],ov['size_big'],'#FFFFFF',0,4); style('Small',F[ov['font_small']],ov['size_small'],ov['accent'],0,3,italic=0)
        parts=[p for p in a.overlay.split('|')]
        y0=L['overlay']['y_top']; step=0.35
        yy=y0
        for i,p in enumerate(parts):
            stl='Big' if i%2==0 else 'Small'
            lh=int((ov['size_big'] if stl=='Big' else ov['size_small'])*1.25)
            add(i*step,min(dur,a.overlay_dur),f'{{\\an8\\pos({W//2},{yy})\\fad(80,200)\\fscx120\\fscy120\\t(0,120,\\fscx100\\fscy100)}}'+esc(p),stl,3); yy+=lh
    head=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
'''
    return head+'\n'.join(styles)+'\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'+'\n'.join(ev)+'\n'

def probe(v):
    d=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','stream=width,height,codec_type:format=duration','-of','json',v],capture_output=True,text=True).stdout)
    vs=[s for s in d['streams'] if s['codec_type']=='video'][0]
    return vs['width'],vs['height'],float(d['format']['duration']),any(s['codec_type']=='audio' for s in d['streams'])

def zoom_expr(t,dur,words):
    r=t['rhythm']; L=t['layout']
    if L['mode']=='illustrated' and 'ken_burns' in r:
        kb=r['ken_burns']; P=kb['per_shot_s']; return f"{kb['zoom_from']}+({kb['zoom_to']}-{kb['zoom_from']})*mod(it,{P})/{P}"
    pi=r.get('punch_in')
    if not pi: return '1'
    # toggle zoom at word starts nearest to every_s boundaries
    starts=[w['s'] for w in words] or [0]
    marks=[];k=pi['every_s']
    while k<dur:
        marks.append(min(starts,key=lambda s:abs(s-k))); k+=pi['every_s']
    marks=sorted(set(marks)); terms=[]
    for i in range(0,len(marks),2):
        a=marks[i]; b=marks[i+1] if i+1<len(marks) else dur+1
        terms.append(f'between(it,{a:.2f},{b:.2f})')
    return f"1+{pi['scale']-1:.3f}*({'+'.join(terms) or '0'})"

def filter_path(path):
    # FFmpeg filter quoting is separate from shell quoting, including Windows drives.
    return str(path).replace('\\', '/').replace(':', '\\:').replace("'", "'\\''")

def main():
    ap=argparse.ArgumentParser()
    for k in ['template','video','words','out','lang','title','title-hl','name','name-sub','kicker','overlay','music','emph']: ap.add_argument('--'+k)
    ap.add_argument('--background-mode',choices=['illustration','footage'],help='E only; default from spec')
    ap.add_argument('--name-in',type=float,default=4.0); ap.add_argument('--overlay-dur',type=float,default=3.0)
    ap.add_argument('--preview',type=float); ap.add_argument('--ass-only',action='store_true')
    ap.add_argument('--preserve-text',action='store_true',help='Keep approved capitalization and punctuation')
    ap.add_argument('--static-camera',action='store_true',help='Disable template zoom and punch-in')
    ap.add_argument('--ffmpeg',default='ffmpeg')
    a=ap.parse_args(); a.lang=a.lang or 'id'
    t=json.load(open(a.template,encoding='utf-8')); words=load_words(a.words)
    if a.preserve_text:
        t['captions']['case']='original'
        global strip_trailing
        strip_trailing=lambda c:c
    if a.static_camera:
        t['rhythm'].pop('punch_in',None)
        t['rhythm'].pop('ken_burns',None)
    iw,ih,dur,has_audio=probe(a.video)
    ass=os.path.splitext(a.out)[0]+'.ass'; open(ass,'w',encoding='utf-8').write(build_ass(t,words,a,dur))
    if a.ass_only: print(ass); return
    L=t['layout']; fps=t['canvas']['fps']; extra_inputs=[]
    cover=f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if L['mode']=='threeband':
        vh=L['video']['h']; vy=L['video']['y']
        fg=f"crop='min(iw,ih*16/9)':'min(ih,iw*9/16)',scale={W}:{vh}"
        bg=f"{cover},boxblur={L['bg_blur']}:2,eq=brightness={L['bg_darken']}" if L.get('bg')=='blur' else f"{cover},drawbox=c=black:t=fill"
        vf=f"[0:v]split[a][b];[a]{bg}[bg];[b]{fg}[fg];[bg][fg]overlay=0:{vy},fps={fps}"
    elif t.get('background_modes') and bg_mode(t,a)=='footage':
        fm=t['background_modes']['footage']; off=fm['top_offset']; sh=fm['top_shade_h']; fe=fm.get('feather',160)
        from PIL import Image
        base=os.path.splitext(a.out)[0]
        m=Image.new('L',(W,H),255)
        m.paste(Image.linear_gradient('L').resize((W,fe)),(0,0)); m.save(base+'_fgmask.png')
        g=Image.linear_gradient('L').resize((W,sh)).point(lambda v:int((255-v)*0.6)); sd=Image.new('RGBA',(W,sh),(0,0,0,0)); sd.putalpha(g); sd.save(base+'_shade.png')
        extra_inputs+=['-loop','1','-i',base+'_fgmask.png','-loop','1','-i',base+'_shade.png']
        z=zoom_expr(t,dur,words)
        vf=(f"[0:v]split[a][b];[a]{cover},boxblur=28:2,eq=brightness=-0.25[bg];[b]{cover},format=rgba[fg0];[1:v]format=gray[mk];[fg0][mk]alphamerge[fg];"
            f"[bg][fg]overlay=0:{off}[c];[c][2:v]overlay=0:0,fps={fps},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
    else:
        z=zoom_expr(t,dur,words)
        vf=f"[0:v]{cover},fps={fps},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    vf+=f",ass='{filter_path(ass)}':fontsdir='{filter_path(FONTDIR)}',format=yuv420p[v]"
    cmd=[a.ffmpeg,'-nostdin','-v','error','-n','-i',a.video]+extra_inputs; mi=1+len(extra_inputs)//4
    au=t['audio']; tgt=au['target_lufs']; tp=au['true_peak_db']
    if a.music and au.get('music_db_under_voice') is not None and has_audio:
        cmd+=['-stream_loop','-1','-i',a.music]
        db=au['music_db_under_voice']
        af=(f"[0:a]aresample=48000,asplit[v1][v2];[{mi}:a]aresample=48000,volume={db}dB[m];"
            f"[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
            f"[v1][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I={tgt}:TP={tp}:LRA=11[a]")
    elif has_audio:
        af=f"[0:a]aresample=48000,loudnorm=I={tgt}:TP={tp}:LRA=11[a]"
    else: af=None
    fc=vf+(';'+af if af else '')
    cmd+=['-filter_complex',fc,'-map','[v]']+(['-map','[a]'] if af else [])
    cmd+=['-t',f'{dur:.3f}','-c:v','libx264','-preset','medium','-crf','20','-c:a','aac','-b:a','192k','-movflags','+faststart',a.out]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=1800)
    if r.returncode: print(r.stderr); raise SystemExit(1)
    print('rendered',a.out)
    if a.preview is not None:
        png=os.path.splitext(a.out)[0]+'.png'
        subprocess.run([a.ffmpeg,'-nostdin','-v','error','-n','-ss',str(a.preview),'-i',a.out,'-frames:v','1',png],check=True,timeout=120); print('preview',png)
if __name__=='__main__': main()
