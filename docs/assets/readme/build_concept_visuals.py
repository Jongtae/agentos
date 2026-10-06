"""Build original, localized README concept SVGs (not operating evidence).

Run: python3 docs/assets/readme/build_concept_visuals.py
Desktop and narrow layouts share all content; no fonts or external assets.
"""
from pathlib import Path
from html import escape
import unicodedata
import re

ROOT = Path(__file__).resolve().parent
DATA = {
'en': {
 'comparison':'Three interaction models', 'illustration':'Concept illustration',
 'names':['Assistant','Computer agent','Personal AgentOS'],
 'verbs':['Answers','Acts','Stays with the owner'],
 'quotes':['“What is NVIDIA trading at?”','“Add these headphones to my Amazon cart.”','“We’re almost out of coffee.” → later: “Get the same one as last time.”'],
 'flows':[['Question','Search','Answer'],['Explicit command','Browser / tool','Action','Authority if needed','Handoff'],['Conversation over time','Context','Judgment','Continuing work','Authority if needed','Continuous Presence']],
 'holds':['Current conversation + answer','Task + browser/tool state','Owner context + work persist'],
 'disclaimer':'NASDAQ / Amazon illustrate interaction, not shipped integrations.',
 'architecture':'Presence architecture', 'owner':'Owner','conversation':'Natural conversation','pa':'PA · Personal Agent',
 'owned':'Personal AgentOS · owner-controlled state','states':['Memory','Context','Work','Authority','Evidence','Events'],
 'judgment':'Judgment / orchestration','replaceable':'Replaceable execution capabilities', 'ai':'AI models','tools':'Tools / services / skills',
 'same':'Same PA. Different AI.', 'retain':'The relationship and state stay with the owner.',
 'usage':'A conversation over time','direction':'Representative interaction · product direction',
 'times':['Earlier','Hours later','Later'],
 'utterances':['“We’re almost out of coffee.”','“I’m heading out now. Is there somewhere on the way I can pick it up?”','“No time. Just get the same one as last time.”'],
 'under':['Eligible prior context','Time / route / availability','Prior choice / authority when needed'],
 'ongoing':'One continuing Work, resolved beneath the conversation',
 'usage_note':'Illustrative, condensed; not one observed live run.',
},
'ko': {
 'comparison':'상호작용이 달라지는 방식','illustration':'개념 설명용 그림',
 'names':['Assistant','Computer agent','Personal AgentOS'],'verbs':['질문에 답한다','명령을 실행한다','소유자와 함께한다'],
 'quotes':['“NVIDIA 지금 주가가 얼마야?”','“이 헤드폰을 Amazon 장바구니에 담아줘.”','“커피 거의 다 떨어졌네.” → 나중에 “지난번에 사던 걸로 사줘.”'],
 'flows':[['질문','검색','답변'],['명시적인 명령','브라우저 / 도구','행동','필요할 때 권한','인계'],['시간에 걸친 대화','맥락','판단','이어지는 작업','필요할 때 권한','지속되는 Presence']],
 'holds':['현재 대화와 답변','작업과 브라우저·도구 상태','소유자의 맥락과 작업이 지속'],
 'disclaimer':'NASDAQ / Amazon은 상호작용 예시이며, 배포된 통합 기능 주장이 아닙니다.',
 'architecture':'Presence: 소유자 중심의 구조','owner':'소유자','conversation':'자연스러운 대화','pa':'PA · 개인 비서',
 'owned':'Personal AgentOS · 소유자가 통제하는 상태','states':['기억','맥락','작업','권한','증거','이벤트'],
 'judgment':'판단 / 조율','replaceable':'교체 가능한 실행 기능','ai':'AI 모델','tools':'도구 / 서비스 / 스킬',
 'same':'같은 PA, 다른 AI.','retain':'관계와 상태는 소유자에게 남습니다.',
 'usage':'시간에 걸쳐 이어지는 대화','direction':'대표 상호작용 · 제품 방향',
 'times':['처음에','몇 시간 뒤','나중에'],
 'utterances':['“커피 거의 다 떨어졌네.”','“이제 나가려고. 가는 길에 살 만한 데 있을까?”','“시간 없네. 지난번에 사던 걸로 그냥 사줘.”'],
 'under':['저장 가능한 이전 맥락','시간 / 경로 / 영업 여부','이전 선택 / 필요할 때 권한'],
 'ongoing':'대화 아래에서 맥락을 연결하며 이어가는 하나의 Work',
 'usage_note':'축약한 설명용 예시이며, 하나의 실제 관찰 실행이 아닙니다.',
},
'ja': {
 'comparison':'対話のあり方が変わる','illustration':'概念を説明する図',
 'names':['Assistant','Computer agent','Personal AgentOS'],'verbs':['質問に答える','命令を実行する','所有者と共にあり続ける'],
 'quotes':['「NVIDIA の今の株価は？」','「このヘッドホンを Amazon のカートに入れて。」','「コーヒーがもう少ない。」→ 後で「前と同じものを買っておいて。」'],
 'flows':[['質問','検索','回答'],['明示的な命令','ブラウザー / ツール','行動','必要な時に権限','引き継ぎ'],['時間をまたぐ会話','文脈','判断','継続する作業','必要な時に権限','継続する Presence']],
 'holds':['現在の会話と回答','作業とブラウザー・ツールの状態','所有者の文脈と作業を維持'],
 'disclaimer':'NASDAQ / Amazon は対話の説明例であり、提供済みの連携機能を示しません。',
 'architecture':'Presence：所有者が管理する構造','owner':'所有者','conversation':'自然な会話','pa':'PA · 個人のアシスタント',
 'owned':'Personal AgentOS · 所有者が管理する状態','states':['記憶','文脈','作業','権限','証拠','イベント'],
 'judgment':'判断 / オーケストレーション','replaceable':'交換可能な実行機能','ai':'AI モデル','tools':'ツール / サービス / スキル',
 'same':'同じ PA。別の AI。','retain':'関係と状態は所有者の手元に残ります。',
 'usage':'時間をまたいで続く会話','direction':'代表的な対話 · 製品の方向性',
 'times':['はじめに','数時間後','その後'],
 'utterances':['「コーヒーがもう少ない。」','「今から出る。途中で買えるところある？」','「時間ないな。前と同じものを買っておいて。」'],
 'under':['保存できる以前の文脈','時間 / 経路 / 営業状況','以前の選択 / 必要な時に権限'],
 'ongoing':'会話の下で文脈をつなぎ、一つの Work を継続',
 'usage_note':'説明用にまとめた例であり、一回の実観測ではありません。',
},
'zh-CN': {
 'comparison':'交互方式如何改变','illustration':'概念说明图',
 'names':['Assistant','Computer agent','Personal AgentOS'],'verbs':['回答问题','执行命令','持续陪伴所有者'],
 'quotes':['“NVIDIA 现在的股价是多少？”','“把这款耳机加入我的 Amazon 购物车。”','“咖啡快没了。” → 之后：“买上次那款就好。”'],
 'flows':[['问题','搜索','回答'],['明确命令','浏览器 / 工具','行动','需要时取得权限','交接'],['跨越时间的对话','上下文','判断','持续工作','需要时取得权限','持续的 Presence']],
 'holds':['当前对话与回答','任务和浏览器、工具状态','所有者的上下文与工作持续保留'],
 'disclaimer':'NASDAQ / Amazon 是交互示例，并不代表已发布的集成功能。',
 'architecture':'Presence：所有者控制的结构','owner':'所有者','conversation':'自然对话','pa':'PA · 个人助手',
 'owned':'Personal AgentOS · 所有者控制的状态','states':['记忆','上下文','工作','权限','证据','事件'],
 'judgment':'判断 / 编排','replaceable':'可替换的执行能力','ai':'AI 模型','tools':'工具 / 服务 / 技能',
 'same':'同一个 PA。不同的 AI。','retain':'关系与状态仍由所有者掌控。',
 'usage':'相隔数小时，仍是同一段对话','direction':'代表性交互 · 产品方向',
 'times':['起初','数小时后','之后'],
 'utterances':['“咖啡快没了。”','“我现在出门，顺路有地方可以买到吗？”','“没时间了，买上次那款就好。”'],
 'under':['符合保存条件的既有上下文','时间 / 路线 / 营业情况','先前选择 / 需要时取得权限'],
 'ongoing':'在对话之下连接上下文，延续同一个 Work',
 'usage_note':'经过浓缩的说明示例，并非一次真实观测的运行。',
}}

class Figure:
 def __init__(self,w,h,title,desc):
  self.w=w; self.out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">',f'<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>', '<style>text{font-family:Arial,"Noto Sans",sans-serif;fill:#243247} .bold{font-weight:700} .muted{fill:#526174} .blue{fill:#245b92}</style>',f'<rect width="{w}" height="{h}" fill="#fff"/>']
 def rect(self,x,y,w,h,fill='#f6f8fa',stroke='#ccd4de',radius=8):
  self.out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
 def text(self,x,y,s,size=18,cls='',anchor='start'):
  self.out.append(f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')
 def lines(self,x,y,s,width,size=18,cls='',gap=None,anchor='start'):
  # Wrap at spaces for Latin and at glyph boundaries for CJK. Conservative
  # widths leave room for system font fallback; browser QA measures each row.
  limit=width/size; rows=[]; row=''; cost=0
  cjk=any(unicodedata.east_asian_width(c) in 'WF' for c in s) and not any('가' <= c <= '힣' for c in s)
  tokens=re.findall(r'[A-Za-z0-9]+|.',s) if cjk else s.split(' ')
  for token in tokens:
   suffix=token if cjk or not row else ' '+token
   weight=sum(1 if unicodedata.east_asian_width(c) in 'WF' else .59 for c in suffix)
   if row and cost+weight>limit:
    tail=''
    if cjk and token in '。，、？！：；”’」』':
     latin=re.search(r'[A-Za-z0-9]+$',row)
     tail=latin.group() if latin else row[-1]
    previous=(row[:-len(tail)] if tail else row).rstrip()
    if previous: rows.append(previous)
    row=tail+token.lstrip();cost=sum(1 if unicodedata.east_asian_width(c) in 'WF' else .59 for c in row)
   else: row+=suffix;cost+=weight
  if row: rows.append(row)
  for i,r in enumerate(rows):self.text(x,y+i*(gap or size*1.4),r,size,cls,anchor)
  return len(rows)*(gap or size*1.4)
 def path(self,d,color='#8492a3',dash=False):self.out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6"'+(' stroke-dasharray="5 4"' if dash else '')+'/>')
 def arrow(self,x,y,x2,y2):
  self.path(f'M{x} {y} L{x2} {y2}')
  if x==x2:self.path(f'M{x2-4} {y2-5} L{x2} {y2} L{x2+4} {y2-5}')
  else:self.path(f'M{x2-5} {y2-4} L{x2} {y2} L{x2-5} {y2+4}')
 def write(self,name): (ROOT/name).write_text('\n'.join(self.out+['</svg>'])+'\n',encoding='utf-8')

def comparison(d,mobile):
 w=420 if mobile else 840; h=1240 if mobile else 748
 f=Figure(w,h,d['comparison'],d['disclaimer'])
 f.lines(20,32,d['comparison'],w-40,24,'bold');f.text(20,66,d['illustration'],16,'muted')
 for i in range(3):
  x=20 if mobile else 20+i*272; y=86+i*356 if mobile else 86; cw=380 if mobile else 256
  f.rect(x,y,cw,340 if mobile else 550, '#f2f7fc' if i==2 else '#f6f8fa', '#96b6d6' if i==2 else '#ccd4de')
  f.text(x+16,y+32,f'{i+1:02}',16,'blue bold');f.text(x+48,y+32,d['names'][i],20,'bold')
  f.lines(x+16,y+63,d['verbs'][i],cw-32,19,'blue bold')
  f.rect(x+14,y+(80 if mobile else 102),cw-28,150 if not mobile else 88,'#ffffff','#dbe2ea',5)
  f.lines(x+26,y+(105 if mobile else 128),d['quotes'][i],cw-52,18)
  start=y+(188 if mobile else 286);step=22 if mobile else 34
  for j,node in enumerate(d['flows'][i]):
   f.out.append(f'<circle cx="{x+24}" cy="{start+j*step-6}" r="3" fill="#245b92"/>')
   if j: f.arrow(x+24,start+(j-1)*step,x+24,start+j*step-13)
   f.text(x+38,start+j*step,node,17 if mobile else 18)
  fy=y+(320 if mobile else 520)
  f.lines(x+16,fy,d['holds'][i],cw-32,16,'bold')
 f.lines(20,h-57,d['disclaimer'],w-40,16,'muted')
 return f

def presence(d,mobile):
 w=420 if mobile else 840;h=830 if mobile else 730
 f=Figure(w,h,d['architecture'],d['retain'])
 f.lines(20,32,d['architecture'],w-40,23,'bold');f.text(20,68,d['illustration'],16,'muted')
 if mobile:
  f.rect(20,90,380,64,'#fff');f.text(44,130,d['owner'],20,'bold');f.text(162,130,'⇄',28,'blue');f.text(206,130,'PA',22,'bold')
  f.text(210,182,d['conversation'],18,'muted','middle');f.arrow(210,194,210,214)
  x=20;y=226;cw=380
 else:
  f.rect(20,132,172,110,'#fff');f.text(106,175,d['owner'],23,'bold','middle')
  f.lines(106,202,d['conversation'],150,16,'muted',anchor='middle')
  f.path('M198 182H268M203 177L198 182L203 187M263 177L268 182L263 187','#245b92')
  x=280;y=90;cw=540
 f.rect(x,y,cw,376,'#f2f7fc','#96b6d6')
 f.lines(x+18,y+32,d['owned'],cw-36,19,'bold')
 f.rect(x+18,y+64,cw-36,56,'#e4edf8','#b4c9df',5);f.text(x+cw/2,y+99,d['pa'],20,'bold','middle')
 f.arrow(x+cw/2,y+125,x+cw/2,y+146)
 cell=(cw-52)/3
 for i,s in enumerate(d['states']):
  cx=x+18+(i%3)*(cell+8);cy=y+156+(i//3)*64
  f.rect(cx,cy,cell,52,'#fff','#ccd8e6',5);f.text(cx+cell/2,cy+33,s,18,'bold','middle')
 f.arrow(x+cw/2,y+276,x+cw/2,y+296)
 f.rect(x+18,y+306,cw-36,52,'#fff','#b4c9df',5);f.text(x+cw/2,y+339,d['judgment'],18,'bold','middle')
 bottom=y+420; center=x+cw/2
 f.arrow(center,y+378,center,bottom-12)
 f.text(center,bottom+12,d['replaceable'],18,'muted','middle')
 f.rect(x,bottom+30,cw,76,'#fff','#8492a3',6)
 f.text(x+cw/2,bottom+59,d['ai'],20,'bold','middle');f.text(x+cw/2,bottom+87,d['tools'],18,'muted','middle')
 f.text(w/2,h-50,d['same'],23,'blue bold','middle');f.text(w/2,h-20,d['retain'],17,'muted','middle')
 return f

def usage(d,mobile):
 w=420 if mobile else 840;h=980 if mobile else 550
 f=Figure(w,h,d['usage'],d['usage_note'])
 f.lines(20,32,d['usage'],w-40,23,'bold');f.text(20,68,d['direction'],16,'muted')
 for i in range(3):
  x=40 if mobile else 20+i*272;y=92+i*244 if mobile else 92;cw=360 if mobile else 256
  f.rect(x,y,cw,220 if mobile else 310,'#fff')
  f.text(x+16,y+30,f'{i+1:02}  {d["times"][i]}',18,'blue bold')
  f.lines(x+16,y+66,d['utterances'][i],cw-32,19,'bold')
  f.path(f'M{x+16} {y+(158 if mobile else 198)}H{x+cw-16}')
  f.lines(x+16,y+(186 if mobile else 226),d['under'][i],cw-32,17,'muted')
  if mobile:
   f.out.append(f'<circle cx="20" cy="{y+26}" r="4" fill="#245b92"/>')
   if i<2:f.arrow(20,y+35,20,y+244+14)
  elif i<2:f.arrow(x+cw+2,y+118,x+cw+14,y+118)
 band=836 if mobile else 422
 f.rect(20,band,w-40,58,'#f2f7fc','#96b6d6',5);f.lines(w/2,band+25,d['ongoing'],w-64,18,'bold',anchor='middle',gap=23)
 f.lines(20,h-(46 if mobile else 23),d['usage_note'],w-40,16,'muted')
 return f

if __name__=='__main__':
 for locale,d in DATA.items():
  for kind,builder in [('interaction-model',comparison),('presence',presence),('continuing-conversation',usage)]:
   for mobile in [False,True]:
    builder(d,mobile).write(f'{kind}.{locale}{".narrow" if mobile else ""}.svg')
