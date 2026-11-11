# Generates the 6 template JSON specs. Reference rhythm/loudness numbers come from data/ref_stats.json
# (numeric stats measured from public reference Shorts; no video files are included).
import json,os
B=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS=json.load(open(os.path.join(B,'data','ref_stats.json'),encoding='utf-8'))
def meas(ids): return [STATS[i] for i in ids]
FONTS={'latin':{'sans_black':'Tpl Noto Sans Black','sans_xb':'Tpl Montserrat ExtraBold','sans_cond':'Tpl Noto Sans Condensed ExtraBold','sans_med':'Tpl Noto Sans Medium','serif_bold':'Tpl Noto Serif Bold','serif_med':'Tpl Noto Serif Medium','serif_italic':'Tpl Noto Serif Italic'},
       'zh':{'sans_black':'Tpl Noto Sans SC ExtraBold','sans_xb':'Tpl Noto Sans SC ExtraBold','sans_cond':'Tpl Noto Sans SC ExtraBold','sans_med':'Tpl Noto Sans SC Medium','serif_bold':'Tpl Noto Serif SC Bold','serif_med':'Tpl Noto Serif SC Bold','serif_italic':'Tpl Noto Serif SC Bold'}}
COMMON_AUDIO={'target_lufs':-14,'true_peak_db':-1,'music_source_rule':'只用免版税且授权清楚的音乐（YouTube 音频库、可商用 CC0），不用参考视频里的音乐','duck':'人声出现时音乐自动再压低 6–8 dB（sidechain）'}
SAFE={'note':'Shorts 界面遮挡区（通用经验，非本次测量）：底部约 380px 放频道名/标题，右侧约 140px 放按钮，顶部约 200px 放搜索栏。口播字幕一律放在下方字幕带 y 1300–1560（中心线），左右各留 140px，避开右侧按钮和底部约 360px 的界面区。人脸区（9:16 全屏近景约 y 420–1150）禁止放任何字幕或大字。','caption_band_y':[1300,1560],'face_zone_fullbleed':[420,1150],'title_safe_y':[200,1560],'right_margin_px':140}
T=[]
T.append({'id':'A_threeband_card','name_zh':'三段式访谈卡','name_en':'Three-band interview card',
 'refs':meas(['Do2w0JowqaE','PSQBGQEXnjI','0iV0-M4R0Xg','Tec67BGxpFc','qwovFEWpvvI','PUtQftpDknk']),
 'use_when':'任何横屏（16:9）素材都可以用：讲法开示、访谈、法会/活动现场、纪录片段，也包括横屏的插画或动画。适合 20–90 秒、完整说清一个点的内容；不想裁掉画面时首选。',
 'avoid_when':'主体在画面里很小、又需要看清表情时，可以先推近，或改用 B / D。',
 'layout':{'mode':'threeband','bg':'blur','bg_blur':28,'bg_darken':-0.28,
   'nameplate':{'y':330,'h':64,'style':'白底黑字小牌，大写，居中（Do2w）'},
   'title':{'y_top':420,'max_lines':2,'line_h':96,'max_chars_latin':22,'max_chars_zh':11,'align':'center'},
   'video':{'y':660,'h':608,'aspect':'16:9','note':'实测参考：视频带 y≈540–1360（Do2w）、555–1359（qwov）、561–1098（0iV0）'},
   'caption':{'y_center':1390},'watermark':{'y':1600},'face_zone':[680,1150]},
 'timeline':[{'t':'0–0.5s','what':'标题、名牌、视频同时出现，不做开场动画（参考里 6 条都是第 1 帧就有标题）'},
   {'t':'0.5s–结尾前 1.5s','what':'单镜头不切（参考 4/6 条全片 1 个镜头），只靠字幕推进'},
   {'t':'最后 1–1.5s','what':'可选结尾卡：讲者正面静照＋频道名（Character Fuel 两条都在 17.5s 切到人物静照）'}],
 'rhythm':{'cuts':'0（单镜头）','shot_len_s':'整段','zoom':'无；可选整段 1.00→1.04 极慢推近（推断：参考中未见明显推近）','measured':'Do2w/PSQB/0iV0/qwov 均为 1 个镜头；Tec67、PUtQ 各 2 个'},
 'captions':{'font':'sans_med','size':54,'case':'sentence','color':'#FFFFFF','highlight':'#FFFFFF','outline':0,'shadow':2,'box':False,'max_words':5,'max_chars_latin':26,'max_chars_zh':12,'y_center':1390,'animation':'phrase','inferred':'字幕逐句出现（推断自相邻帧）；Do2w 是单词逐个出现在黑底条里，可设 max_words=1'},
 'title':{'font':'sans_xb','size':72,'case':'upper','color':'#FFFFFF','highlight':'#7CFF5A','highlight_alt':'#3FD6E8','note':'1–2 个关键词换色（Do2w 绿、PSQB/0iV0 青）'},
 'audio':dict(COMMON_AUDIO,music='可选',music_db_under_voice=-18,measured_note='Do2w 无音乐床（停顿处 -40 dB 以下，13 次静音）；PSQB/0iV0 有持续低音乐床，安静处电平约比人声峰值低 12–13 dB（推断）。'),
 'copy':{'title_formula':'一句话说出这段的结论或问题（不超过 2 行），关键词 1–2 个换色；名牌写「SPEAKER NAME」','example_zh':'放下不是放弃｜讲者开示（示例结构，标题须与原话意思一致）','example_id':'MELEPASKAN BUKAN BERARTI MENYERAH（待译者核对）','example_mn':'ТАВЬЖ ЯВУУЛАХ НЬ БУУЖ ӨГӨХ БИШ（待译者核对）','caption_rule':'字幕逐字忠实于讲者原话的译文，不删关键限定词'},
 'do':['标题写这段真正讲的内容','名牌用法名全称','横屏素材保持完整，不硬裁'],
 'dont':['标题夸大（「改变命运」「必看」）','用参考视频的画面或背景音乐','白底名牌里写未经核实的头衔']})
T.append({'id':'B_word_highlight_quote','name_zh':'逐词高亮金句','name_en':'Word-by-word highlight',
 'refs':meas(['Idhxi63qmR0','Gp1rmnGpdm4','xIF62ixaeaw','WsB3oVYnE_A']),
 'use_when':'任何以一句核心金句为主的 15–45 秒短片都可以用：开示、问答片段、旁白配空镜或插画。近景人物效果最好。Shorts 主力模板。',
 'avoid_when':'内容长、节奏慢、需要静观的段落（改用 D）。',
 'layout':{'mode':'fullbleed','caption':{'y_center':1440},'watermark':{'y':1620},'face_zone':[420,1150],'note':'v1.1：参考视频字幕中心在 y≈950–1000（Idhxi），但讲者素材会遮脸，已下移到 1440（v1.1 规则）'},
 'timeline':[{'t':'0–1.5s','what':'第一句就是钩子（问题或反常识），字幕第 1 帧就出现'},{'t':'1.5s–','what':'每 2.4–2.8s 一个镜头变化：换机位、推近或插入空镜'},{'t':'结尾','what':'最后一句收在完整句子上，不加 CTA 口播'}],
 'rhythm':{'shot_len_s':[1.5,3.0],'measured':'镜头中位：Idhxi 2.38s、xIF6 2.78s；Gp1r 有大量 <0.5s 闪切（粒子特效）','punch_in':{'scale':1.12,'every_s':2.6,'note':'没有第二机位时，用 100%↔112% 交替推近模拟换镜（推断：参考多为真换镜）'},'broll':'可插入 1.5–3s 寺院/自然空镜（自己拍或可商用素材），不用炫光科幻特效'},
 'captions':{'font':'sans_black','size':84,'case':'sentence','color':'#FFFFFF','highlight':'#FFE14D','outline':6,'shadow':0,'max_words':3,'max_chars_latin':18,'max_chars_zh':7,'y_center':1440,'animation':'word_pop','inferred':'当前读到的词变黄并轻微放大（推断：相邻帧里黄色词随语音移动）'},
 'audio':dict(COMMON_AUDIO,music='是',music_db_under_voice=-18,measured_note='4 条全部有持续音乐床，无 -40 dB 静音；安静处电平比人声峰值低约 7–17 dB（推断，是音乐床电平的上限估计）。我们建议更克制：低 18 dB。'),
 'copy':{'title_formula':'问题式或「X 不是 Y」式，一句','example_zh':'烦恼来时，先别急着赶走它（示例结构）','example_id':'Saat pikiran gelisah, jangan buru-buru mengusirnya（待译者核对）','example_mn':'Сэтгэл түгшихэд яаран хөөж бүү зайлуул（待译者核对）','caption_rule':'每屏 1–3 个词；高亮词选句中核心名词/动词，不高亮否定词以免改变意思'},
 'do':['高亮颜色全片统一','字幕不挡脸','节奏靠镜头变化而不是特效'],
 'dont':['炫光、粒子、脑电波类特效（与佛法调性不符）','把「可能」「有时」等限定词删掉','一屏超过 3 个词']})
T.append({'id':'C_dialogue_switch','name_zh':'双机位对谈切换','name_en':'Two-camera dialogue',
 'refs':meas(['00sgwEA_lQw','6UW1Dkwm_LI','eToQBgPbSfo']),
 'use_when':'两人或多人的对话都可以用：问答、对谈、访谈、连线。只有单机位时用推近模拟换镜；旁白里引用提问也可以用。',
 'avoid_when':'纯独白、没有问答结构时（改用 B / D / E）。',
 'layout':{'mode':'fullbleed','nameplate':{'x':80,'y':1290,'style':'衬线体姓名＋小号大写头衔，左下，首次出场 2–3 秒'},'caption':{'y_center':1500},'face_zone':[420,1150],'note':'v1.1：名牌下移到 y≈1230–1330；实测：字幕 y≈1460–1550（00sg），名牌 y≈1150–1250'},
 'timeline':[{'t':'0–4s','what':'提问者的问题作开场钩子（00sg 前 4s 是主持人提问）'},{'t':'4s','what':'切到讲者，名牌出现 2–3s'},{'t':'中段','what':'回答为主，偶尔切回提问者反应镜头'},{'t':'最后 1.5–2s','what':'纯色品牌结尾卡（00sg 结尾是黑底品牌字）'}],
 'rhythm':{'shot_len_s':[3.5,6.0],'measured':'镜头中位：00sg 4.09s、6UW1 4.50s、eToQ 5.92s','punch_in':{'scale':1.08,'every_s':4.5}},
 'captions':{'font':'sans_med','size':46,'case':'sentence','color':'#FFFFFF','highlight':'#FFFFFF','outline':0,'shadow':3,'box':False,'max_words':7,'max_chars_latin':34,'max_chars_zh':14,'y_center':1500,'animation':'phrase','inferred':'整句出现、整句消失（推断）'},
 'audio':dict(COMMON_AUDIO,music='否',music_db_under_voice=None,measured_note='00sg、6UW1 有多次 -40 dB 以下的静音，判断为无音乐床（推断）；eToQ 有低音乐床。佛法问答建议不加音乐。'),
 'copy':{'title_formula':'把提问者的问题原样作标题','example_zh':'弟子问：痛苦和受苦有什么区别？（示例结构）','example_id':'Murid bertanya: apa beda rasa sakit dan penderitaan?（待译者核对）','example_mn':'Шавь асуув: өвдөлт ба зовлон хоёр ямар ялгаатай вэ?（待译者核对）','caption_rule':'问与答都按原话翻译；提问者若非公开人物，不写姓名'},
 'do':['名牌写清讲者姓名与身份','保留回答的完整逻辑'],
 'dont':['把不同场合的回答剪成一问一答','未经同意露出提问者正脸（隐私）']})
T.append({'id':'D_contemplative_phrase','name_zh':'静观短语字幕','name_en':'Contemplative phrase captions',
 'refs':meas(['T5OAOgB_xA0','ty_QuSlG4s8','uw7otsaTAaA','WsB3oVYnE_A']),
 'use_when':'任何节奏慢、需要留白的内容都可以用：开示、禅修引导、偈颂诵读、寺院或风景空镜配旁白、插画。15–45 秒。',
 'avoid_when':'需要强钩子的话题引流视频（改用 B）。',
 'layout':{'mode':'fullbleed','caption':{'y_center':1440},'watermark':{'y':1620},'face_zone':[420,1150],'note':'v1.1：参考视频字幕中心在 y≈950（T5OA、ty_Q），会遮脸，已下移到 1440（v1.1 规则）'},
 'timeline':[{'t':'0–2s','what':'近景直接开口，第一句 2–3 个词'},{'t':'每 6–13s','what':'近景↔中景跳切一次（ty_Q 6.1s、T5OA 12.8s）'},{'t':'结尾','what':'停在一句完整的话上，留 0.5s 安静'}],
 'rhythm':{'shot_len_s':[6,13],'measured':'镜头中位：ty_Q 6.12s、T5OA 12.83s、uw7o 单镜头 17.9s','punch_in':{'scale':1.15,'every_s':7.0,'note':'无第二机位时用推近跳切模拟'}},
 'captions':{'font':'serif_bold','size':66,'case':'lower','color':'#FFFFFF','future_color':'#9A9A9A','outline':0,'shadow':4,'max_words':3,'max_chars_latin':20,'max_chars_zh':8,'y_center':1440,'animation':'karaoke_fade','inferred':'未读到的词先灰、读到变白（推断自 T5OA 2.5s「the question」灰→3.0s 白）'},
 'audio':dict(COMMON_AUDIO,music='是（极轻）',music_db_under_voice=-22,measured_note='Money Moon 三条音乐床持续，比人声峰值低约 7–14 dB（推断）；我们建议 -22 dB 的环境音/颂钵氛围。'),
 'copy':{'title_formula':'名词短语或一个问题，不加感叹号','example_zh':'我是谁？（示例结构）','example_id':'Siapakah aku?（待译者核对）','example_mn':'Би хэн бэ?（待译者核对）','caption_rule':'小写、短句；中文每屏不超过 8 个字'},
 'do':['留白和停顿','色调偏暖暗'],
 'dont':['快速闪切','鼓点音乐']})
T.append({'id':'E_episode_title_card','name_zh':'故事序号标题卡','name_en':'Episode title card',
 'refs':meas(['m310Ej5tOiY','BGb8tM9xZRc']),
 'use_when':'插画与真人 Shorts 通用：凡是需要「序号＋标题」的系列内容都可以用，包括故事、公案、譬喻、系列开示、问答切片、课程分集。背景用 background_mode 切换：illustration＝自绘或生成的插画、空镜；footage＝真人讲话视频 9:16 铺满。15–90 秒。',
 'avoid_when':'单条、没有系列感，且开头需要强钩子时，可以先接 F 再进 E，或改用 B。',
 'background_mode':'illustration','background_modes':{'illustration':{'desc':'插画、空镜全屏铺满，缓慢推近'},'footage':{'desc':'真人视频 9:16 铺满后整体下移 top_offset，顶部空出的部分用同一画面模糊填充并压暗，标题放在这条带里，不压头部和脸','top_offset':220,'header_y':120,'top_shade_h':440}},
 'layout':{'mode':'illustrated','header':{'y':170,'kicker':'• 第 1 集 •','style':'小号大写衬线标题，金色'},'caption':{'y_center':1480},'face_zone':[420,1150],'note':'v1.1：字幕中心从 1560 上调到 1480，两行时也不进入底部界面区；实测：m310 顶部章节标题 y≈140–300，底部字幕 y≈1500–1650；BGb8 顶部白框标题 y≈320–475、字幕 y≈1520–1660'},
 'timeline':[{'t':'0–2s','what':'第一张图＋章节标题＋故事第一句'},{'t':'每 2.5–12.5s','what':'换一张图（m310 中位 12.5s，BGb8 每句换图约 2.5s）'},{'t':'每张图内','what':'缓慢推近 3–5%（推断）'}],
 'rhythm':{'shot_len_s':[4,12],'measured':'m310 镜头中位 12.55s（11 段）；BGb8 用叠化换图，场景检测只测到 2 次切换，目测约 2.5s 一张','ken_burns':{'zoom_from':1.0,'zoom_to':1.05,'per_shot_s':8}},
 'captions':{'font':'serif_med','size':56,'case':'sentence','color':'#E8E0D0','highlight':'#F2C46B','outline':0,'shadow':4,'max_words':6,'max_chars_latin':30,'max_chars_zh':12,'y_center':1480,'animation':'karaoke_fill','inferred':'已读的词变金色（推断自 m310 相邻帧）'},
 'header':{'font':'serif_bold','size':54,'kicker_size':30,'color':'#F2C46B'},
 'audio':dict(COMMON_AUDIO,music='是',music_db_under_voice=-20,measured_note='m310、BGb8 都有持续音乐床，比人声峰值低约 6–12 dB（推断）。'),
 'copy':{'title_formula':'「故事名｜一句点题」','example_zh':'盲龟遇浮木｜人身难得（示例结构，故事出处须标经名）','example_id':'Kura-kura buta dan kayu terapung | Langkanya terlahir sebagai manusia（待译者核对）','example_mn':'Сохор яст мэлхий ба хөвөгч мод | Хүний биеийн ховор（待译者核对）','caption_rule':'故事出处（经名/论名）写在描述栏'},
 'do':['序号和标题全系列统一格式','插画模式：插画风格全系列统一（同一提示词或画师），在描述栏标明插画为示意图','真人模式：标题放在头顶上方的压暗带里，不压头部和脸'],
 'dont':['把示意图说成历史真实画面','用参考频道的插画','真人模式下把标题压在头上或脸上']})
T.append({'id':'F_editorial_hook','name_zh':'杂志大字钩子','name_en':'Editorial big-type hook',
 'refs':meas(['Dkw7jQZkNqw']),
 'use_when':'钩子模块，可以接在任何模版（A–E）的开头 3–5 秒，或用在关键术语、数字、问题出现时：在下方字幕带打出大字（例如「无常」「菩提心」）。真人、插画、空镜素材都可以用。',
 'avoid_when':'全片使用（信息太密，与开示调性不符）。',
 'layout':{'mode':'fullbleed','overlay':{'y_top':1290,'h':290,'hide_captions_while_visible':True,'style':'衬线斜体小字＋无衬线粗体大字混排，强调色蓝'},'caption':{'y_center':1545,'box':True},'face_zone':[420,1150],'note':'v1.1：参考视频 Dkw7 的大字在顶部 y≈150–500，会压到头部，已整体移到下方：大字 y≈1290–1580（与口播字幕共用下方字幕带，大字显示期间不出字幕），字幕框 y≈1545（v1.1 规则）'},
 'timeline':[{'t':'0–1.0s','what':'大字逐行叠出（I DIDN’T → edit → A SINGLE → SECOND）'},{'t':'2–4s 一次','what':'关键词大字出现 1.5–2.5s 后消失'}],
 'rhythm':{'shot_len_s':[2,3.5],'measured':'Dkw7 镜头中位 2.70s，语速约 7.8 词/秒（最快一条）'},
 'captions':{'font':'serif_italic','size':44,'case':'sentence','color':'#FFFFFF','highlight':'#FFFFFF','outline':0,'shadow':0,'box':True,'box_color':'#202020','max_words':2,'max_chars_latin':16,'max_chars_zh':6,'y_center':1545,'animation':'phrase'},
 'overlay':{'font_big':'sans_black','size_big':92,'font_small':'serif_italic','size_small':50,'accent':'#58B4FF'},
 'audio':dict(COMMON_AUDIO,music='是',music_db_under_voice=-18,measured_note='Dkw7 全程有音乐床，比人声峰值低约 8 dB（推断）。'),
 'copy':{'title_formula':'一个核心术语＋一句解释','example_zh':'【无常】不是悲观，是看清（示例结构）','example_id':'ANICCA — bukan pesimis, tapi melihat dengan jernih（待译者核对）','example_mn':'МӨНХ БУС — гутранги бус, тод харах（待译者核对）','caption_rule':'大字只用原话里出现过的词'},
 'do':['只做钩子模块，配合其他模板'],
 'dont':['全片满屏大字','用电脑界面、产品演示类 B-roll']})
for t in T:
    t['captions']['size'] = {'A': 72, 'B': 84, 'C': 64, 'D': 82, 'E': 74, 'F': 54}[t['id'][0]]
    t.update({'version':'v1.4','canvas':{'w':1080,'h':1920,'fps':30},'safe_area':SAFE,'fonts':FONTS,
      'rules':['字幕一律靠下，不得遮挡人脸：口播字幕中心 y 1300–1560，大字钩子同样放下方','只学风格：不用参考视频的画面、音乐、付费字体','标题不夸大、不误导，不改原意；引文标出处（宗教、知识类内容尤其如此）','标注「推断」的参数来自看帧，不是工具读出的数据']})
    json.dump(t,open(os.path.join(B,'specs',t['id']+'.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print(t['id'],len(t['refs']))
