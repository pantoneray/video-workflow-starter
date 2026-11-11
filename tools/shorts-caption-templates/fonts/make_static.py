from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
G='/usr/share/fonts/truetype/sand-box/google'
jobs=[
 (f'{G}/Montserrat/Montserrat-VariableFont_wght.ttf',{'wght':800},'Tpl Montserrat ExtraBold','Montserrat-ExtraBold.ttf'),
 (f'{G}/Montserrat/Montserrat-VariableFont_wght.ttf',{'wght':600},'Tpl Montserrat SemiBold','Montserrat-SemiBold.ttf'),
 (f'{G}/Noto Sans/NotoSans-VariableFont_wdth,wght.ttf',{'wght':900,'wdth':100},'Tpl Noto Sans Black','NotoSans-Black.ttf'),
 (f'{G}/Noto Sans/NotoSans-VariableFont_wdth,wght.ttf',{'wght':800,'wdth':75},'Tpl Noto Sans Condensed ExtraBold','NotoSansCondensed-ExtraBold.ttf'),
 (f'{G}/Noto Sans/NotoSans-VariableFont_wdth,wght.ttf',{'wght':500,'wdth':100},'Tpl Noto Sans Medium','NotoSans-Medium.ttf'),
 (f'{G}/Noto Serif/NotoSerif-VariableFont_wdth,wght.ttf',{'wght':700,'wdth':100},'Tpl Noto Serif Bold','NotoSerif-Bold.ttf'),
 (f'{G}/Noto Serif/NotoSerif-VariableFont_wdth,wght.ttf',{'wght':500,'wdth':100},'Tpl Noto Serif Medium','NotoSerif-Medium.ttf'),
 (f'{G}/Noto Serif/NotoSerif-Italic-VariableFont_wdth,wght.ttf',{'wght':500,'wdth':100},'Tpl Noto Serif Italic','NotoSerif-MediumItalic.ttf'),
 ('src/NotoSansSC.ttf',{'wght':800},'Tpl Noto Sans SC ExtraBold','NotoSansSC-ExtraBold.ttf'),
 ('src/NotoSansSC.ttf',{'wght':500},'Tpl Noto Sans SC Medium','NotoSansSC-Medium.ttf'),
 ('src/NotoSerifSC.ttf',{'wght':700},'Tpl Noto Serif SC Bold','NotoSerifSC-Bold.ttf'),
]
for src,axes,fam,out in jobs:
    f=TTFont(src); s=instantiateVariableFont(f,axes)
    n=s['name']
    for rec in list(n.names):
        if rec.nameID in (1,4,16,6,17,3): pass
    n.setName(fam,1,3,1,0x409); n.setName('Regular',2,3,1,0x409); n.setName(fam,4,3,1,0x409)
    n.setName(fam.replace(' ',''),6,3,1,0x409); n.setName(fam,16,3,1,0x409); n.setName('Regular',17,3,1,0x409)
    n.setName(fam+' Regular',3,3,1,0x409)
    s['OS/2'].usWeightClass=400; s['OS/2'].fsSelection=(s['OS/2'].fsSelection & ~0x21)|0x40; s['head'].macStyle=0
    s.save(out)
    cm=s.getBestCmap(); print(out, all(ord(c) in cm for c in 'ӨөҮүÉé') , ord('永') in cm)
