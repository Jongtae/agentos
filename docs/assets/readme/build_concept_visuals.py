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
 'times':['Earlier','Hours later','Later','After connecting the account'],
 'utterances':['“We’re almost out of coffee.”','“I’m heading out now. Is there somewhere on the way I can pick it up?”','“No time. Just get the same one as last time.”','“Connected.”'],
 'replies':['“I’ll keep coffee in mind for your next shop.”','“The coffee? Share your route and I’ll look for a convenient stop.”','“The coffee from last time. Connect your shopping account here so I can prepare the order.”','“Back to that coffee. I’ll prepare the order for your review; payment needs your approval.”'],
 'under':['Keep eligible context; sharing a fact does not authorize a purchase.','Resolve “it” from earlier context. Ask for the route only because it is missing.','Resolve the prior choice. Pause the shopping Work for the missing account authority.','Resume the original Work after the handoff. Account access is not payment approval.'],
 'under_title':'What AgentOS resolves','owner_label':'Owner','pa_label':'PA',
 'assumption':'Illustrated conditions: prior coffee choice is available; route and account access are missing.',
 'ongoing':'Context persists. The shopping Work resumes after the handoff.',
 'usage_note':'Reconstructed product direction, not one observed live run or a shipped shopping integration.',
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
 'times':['처음에','몇 시간 뒤','나중에','계정 연결 뒤'],
 'utterances':['“커피 거의 다 떨어졌네.”','“이제 나가려고. 가는 길에 살 만한 데 있을까?”','“시간 없네. 지난번에 사던 걸로 그냥 사줘.”','“연결했어.”'],
 'replies':['“다음에 장 볼 때 커피도 챙기면 되겠네요.”','“커피 말씀이죠? 이동 경로를 알려주시면 들르기 편한 곳을 찾아볼게요.”','“지난번 커피로요. 주문을 준비하려면 구매 계정이 필요해요. 여기서 연결해주세요.”','“그 커피로 이어서 주문을 준비할게요. 결제 전에는 확인받을게요.”'],
 'under':['저장 가능한 맥락을 남긴다. 일상적인 사실 공유가 구매 권한은 아니다.','이전 맥락에서 커피를 이어받는다. 모르는 이동 경로만 필요해진 순간 묻는다.','이전 선택을 찾는다. 구매 계정 권한이 없어 해당 Work를 잠시 멈춘다.','권한 연결 뒤 원래 Work를 재개한다. 계정 연결과 결제 승인은 별개다.'],
 'under_title':'AgentOS가 아래에서 해석하는 것','owner_label':'소유자','pa_label':'PA',
 'assumption':'예시 조건: 지난번 커피 선택은 남아 있고, 이동 경로와 구매 계정 권한은 아직 없습니다.',
 'ongoing':'맥락은 남고, 권한 연결 뒤 원래 구매 Work를 이어갑니다.',
 'usage_note':'제품 방향을 재구성한 예시입니다. 하나의 실제 관찰 실행이나 배포된 구매 기능이 아닙니다.',
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
 'times':['はじめに','数時間後','その後','アカウント接続後'],
 'utterances':['「コーヒーがもう少ない。」','「今から出る。途中で買えるところある？」','「時間ないな。前と同じものを買っておいて。」','「接続したよ。」'],
 'replies':['「次の買い物ではコーヒーも必要ですね。」','「コーヒーですね。移動ルートを教えてもらえれば、立ち寄りやすい店を探します。」','「前回のコーヒーですね。注文の準備には購入用のアカウントが必要です。ここで接続してください。」','「そのコーヒーの注文準備を続けます。支払い前には確認をお願いします。」'],
 'under':['保存できる文脈を残す。日常の事実を共有しても購入権限にはならない。','以前の文脈からコーヒーと理解する。不明な移動ルートを必要な時にだけ聞く。','以前の選択を参照する。購入用のアカウント権限がないため、この Work を一時停止する。','権限の引き継ぎ後に元の Work を再開する。アカウント接続と支払い承認は別。'],
 'under_title':'AgentOS が会話の下で解決すること','owner_label':'所有者','pa_label':'PA',
 'assumption':'この例の条件：前回のコーヒーの選択は残っており、移動ルートとアカウント権限は未取得。',
 'ongoing':'文脈は残り、権限の引き継ぎ後に元の購入 Work を再開。',
 'usage_note':'製品の方向性を再構成した例。一回の実観測や提供済みの購入機能ではありません。',
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
 'times':['起初','数小时后','之后','连接账户后'],
 'utterances':['“咖啡快没了。”','“我现在出门，顺路有地方可以买到吗？”','“没时间了，买上次那款就好。”','“连接好了。”'],
 'replies':['“下次买东西时，也得补上咖啡。”','“是说咖啡吧？告诉我路线，我来找方便顺路停留的店。”','“上次那款咖啡。准备订单需要你的购物账户，请在这里连接。”','“继续准备那款咖啡的订单，付款前会请你确认。”'],
 'under':['保留符合保存条件的上下文。分享日常事实并不等于授权购买。','从先前的上下文理解是在说咖啡。只在需要时询问尚缺的路线。','找到先前的选择。购物账户权限尚缺，暂时暂停这个 Work。','权限交接后恢复原来的 Work。连接账户不等于批准付款。'],
 'under_title':'AgentOS 在对话之下解析什么','owner_label':'所有者','pa_label':'PA',
 'assumption':'示例条件：保留了上次的咖啡选择，但尚不知道路线，也没有购物账户权限。',
 'ongoing':'上下文保留，权限交接后继续原来的购物 Work。',
 'usage_note':'重构的产品方向示例，并非一次真实观测，也不代表已发布的购物功能。',
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
     # Keep a closing-punctuation run with its preceding glyph or Latin
     # token. Moving only the last mark can leave a row containing 。」.
     ending=re.search(r'(?:[A-Za-z0-9]+|[^。，、？！：；”’」』])[。，、？！：；”’」』]*$',row)
     tail=ending.group() if ending else row
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
 f.text(x+cw/2,bottom+59,d['ai']+' · A → B',20,'bold','middle');f.text(x+cw/2,bottom+87,d['tools'],18,'muted','middle')
 f.text(w/2,h-50,d['same'],23,'blue bold','middle');f.text(w/2,h-20,d['retain'],17,'muted','middle')
 return f

def usage(d,mobile):
 # The owner-facing exchange and its architectural interpretation share a row.
 # Compute row heights from the same wrapping used to emit text in every locale.
 w=420 if mobile else 840
 f=Figure(w,3000,d['usage'],d['usage_note'])
 f.lines(20,32,d['usage'],w-40,23,'bold')
 f.text(20,68,d['direction'],16,'muted')
 y=96+f.lines(20,96,d['assumption'],w-40,17,'muted')+18
 for i in range(4):
  x=40 if mobile else 20; cw=360 if mobile else 500
  # Count wrapped text using a disposable figure, then draw the sized cards.
  measure=Figure(w,3000,'','')
  title_h=measure.lines(0,0,d['times'][i],cw-32,19)
  owner_h=measure.lines(0,0,d['utterances'][i],cw-32,20)
  reply_h=measure.lines(0,0,d['replies'][i],cw-32,20)
  note_w=cw-32 if mobile else 240
  note_h=measure.lines(0,0,d['under'][i],note_w,18)
  conversation_h=title_h+owner_h+reply_h+114
  if mobile:
   note_title_h=measure.lines(0,0,d['under_title'],cw-32,17)
   row_h=conversation_h+note_title_h+note_h+26
  else:
   note_title_h=measure.lines(0,0,d['under_title'],note_w,17)
   row_h=max(conversation_h,note_title_h+note_h+56)
  f.rect(x,y,cw,row_h,'#fff')
  cursor=y+28
  cursor+=f.lines(x+16,cursor,d['times'][i],cw-32,19,'blue bold')+8
  f.text(x+16,cursor,d['owner_label'],16,'muted');cursor+=26
  cursor+=f.lines(x+16,cursor,d['utterances'][i],cw-32,20,'bold')+12
  f.text(x+16,cursor,d['pa_label'],16,'blue bold');cursor+=26
  f.lines(x+16,cursor,d['replies'][i],cw-32,20)
  if mobile:
   nx=x;ny=y+conversation_h;nw=cw
   f.rect(nx,ny,nw,row_h-conversation_h,'#f2f7fc','#ccd8e6',5)
  else:
   nx=548;ny=y;nw=272
   f.rect(nx,ny,nw,row_h,'#f2f7fc','#ccd8e6')
   f.arrow(x+cw+4,y+row_h/2,nx-4,y+row_h/2)
  next_y=ny+26+f.lines(nx+16,ny+26,d['under_title'],nw-32,17,'blue bold')+8
  f.lines(nx+16,next_y,d['under'][i],nw-32,18)
  if mobile:
   f.out.append(f'<circle cx="20" cy="{y+24}" r="4" fill="#245b92"/>')
   if i<3:f.arrow(20,y+34,20,y+row_h+36)
  elif i<3:f.arrow(270,y+row_h+4,270,y+row_h+18)
  y+=row_h+24
 band_h=measure.lines(0,0,d['ongoing'],w-72,19)+28
 f.rect(20,y,w-40,band_h,'#f2f7fc','#96b6d6',5)
 f.lines(36,y+28,d['ongoing'],w-72,19,'bold')
 y+=band_h+32
 y+=f.lines(20,y,d['usage_note'],w-40,17,'muted')+12
 # Update both canvas and background once the content height is known.
 f.out[0]=f.out[0].replace('height="3000"',f'height="{int(y)}"').replace(f'viewBox="0 0 {w} 3000"',f'viewBox="0 0 {w} {int(y)}"')
 f.out[3]=f.out[3].replace('height="3000"',f'height="{int(y)}"')
 return f

OVERVIEW = {'en': {'title': 'Personal AgentOS',
        'subtitle': 'One PA. Your work and context stay yours.',
        'illustration_label': 'Interaction model · product direction',
        'comparison_title': 'From answers and commands to continuing work',
        'cards': [{'name': 'Assistant',
                   'verb': 'Answers',
                   'quote': 'What’s the current price of NVIDIA?',
                   'reply': 'I’ll check the current information.',
                   'flow': ['Question', 'Search', 'Answer'],
                   'caption': 'An answer to your question.'},
                  {'name': 'Task agent',
                   'verb': 'Acts',
                   'quote': 'Add these headphones to my Amazon cart.',
                   'reply': 'I’ll open the item in the browser.',
                   'flow': ['Command', 'Browser / tool', 'Action / handoff'],
                   'caption': 'An explicit task, with access as needed.'},
                  {'name': 'Personal AgentOS',
                   'verb': 'Carries work forward',
                   'quote': 'Keep track of next week’s meeting.',
                   'reply': 'I’ll keep the open decision and next step in view.',
                   'flow': ['Intent', 'Open work', 'Next preparation'],
                   'caption': 'Delegated work has a next step over time.'}],
        'architecture_title': 'One PA, with work and authority held by you',
        'owner': 'You',
        'pa': 'PA · the agent you talk to',
        'owned': 'Your environment holds the PA’s state.',
        'links': [('One sourced meeting', 'Invitation + proposal + earlier decisions'),
                  ('Different relationships', 'Calendar: time; project: decision; invite ≠ acceptance'),
                  ('Work continues', 'Prepare brief → receive notes → next step'),
                  ('Authority + evidence', 'Draft ≠ sent; check permission and actual result')],
        'judgment': 'Judgment / orchestration',
        'replaceable_ai': 'Replaceable AI',
        'tools': 'Tools',
        'services': 'Services',
        'same_pa': 'Same PA.',
        'different_ai': 'Different AI.',
        'context_stays': 'Open work and evidence stay with you.',
        'usage_title': 'One conversation, over time',
        'usage': [{'time': 'First',
                   'quote': 'We’re almost out of coffee.',
                   'reply': 'Coffee for the next shop.',
                   'label': 'A small remark becomes context.'},
                  {'time': 'Hours later',
                   'quote': 'I’m heading out now. Is there somewhere on the way I can pick it up?',
                   'reply': 'The coffee? Share your route and I’ll look.',
                   'label': 'Earlier context meets the situation now.'},
                  {'time': 'Later',
                   'quote': 'No time. Just get the same one as last time.',
                   'reply': 'The same coffee. I’ll confirm before payment.',
                   'label': 'Earlier choice · authority when needed'}],
        'usage_note': 'You keep talking. AgentOS connects the context, work and permitted capabilities.',
        'footer': 'Illustrative interaction patterns and product direction. No observed live run or shipped '
                  'integration is claimed.'},
 'ko': {'title': 'Personal AgentOS',
        'subtitle': '하나의 PA. 내 일과 맥락은 내 환경에.',
        'illustration_label': '상호작용 모델 · 제품 방향',
        'comparison_title': '답변과 명령을 넘어, 이어지는 일로',
        'cards': [{'name': 'Assistant',
                   'verb': '답합니다',
                   'quote': '지금 NVIDIA 주가는 얼마야?',
                   'reply': '최신 정보를 확인할게요.',
                   'flow': ['질문', '검색', '답변'],
                   'caption': '질문에 필요한 답을 얻습니다.'},
                  {'name': '실행형 에이전트',
                   'verb': '실행합니다',
                   'quote': '이 헤드폰을 Amazon 장바구니에 넣어줘.',
                   'reply': '브라우저에서 상품을 열어볼게요.',
                   'flow': ['명령', '브라우저·도구', '실행·권한 연결'],
                   'caption': '명시한 일을 하고, 필요한 접근을 요청합니다.'},
                  {'name': 'Personal AgentOS',
                   'verb': '맡긴 일을 이어갑니다',
                   'quote': '다음 주 미팅 좀 챙겨줘.',
                   'reply': '남은 결정과 다음 준비를 이어갈게요.',
                   'flow': ['의도', '남은 일', '다음 준비'],
                   'caption': '맡긴 일의 다음 단계가 이어집니다.'}],
        'architecture_title': '하나의 PA, 내 환경에 남는 일과 권한',
        'owner': '나',
        'pa': 'PA · 나와 대화하는 에이전트',
        'owned': '내 환경이 PA의 상태를 이어갑니다.',
        'links': [('출처가 있는 미팅 하나', '일정 초대 + 제안서 + 이전 결정'),
                  ('서로 다른 관계', '일정: 시간; 프로젝트: 결정; 초대 ≠ 수락'),
                  ('이어지는 일', '준비 자료 → 메모 → 다음 단계'),
                  ('권한과 근거', '초안 ≠ 발송; 허용 범위와 실제 결과 확인')],
        'judgment': '판단·조율',
        'replaceable_ai': '교체 가능한 AI',
        'tools': '도구',
        'services': '서비스',
        'same_pa': '같은 PA.',
        'different_ai': '다른 AI.',
        'context_stays': '남은 일과 근거는 내 환경에 남습니다.',
        'usage_title': '시간이 지나도 이어지는 대화',
        'usage': [{'time': '처음',
                   'quote': '커피 거의 다 떨어졌네.',
                   'reply': '다음에 장 볼 때 커피도 챙기면 되겠네요.',
                   'label': '짧은 일상 이야기가 맥락이 됩니다.'},
                  {'time': '몇 시간 뒤',
                   'quote': '이제 나가려고. 가는 길에 살 만한 데 있을까?',
                   'reply': '커피 말씀이죠? 가는 길을 알려주시면 찾아볼게요.',
                   'label': '앞선 이야기와 지금 상황을 연결합니다.'},
                  {'time': '나중에',
                   'quote': '시간 없네. 지난번에 사던 걸로 그냥 사줘.',
                   'reply': '지난번 커피로요. 결제 전에는 확인받을게요.',
                   'label': '이전 선택 · 필요해진 순간의 권한'}],
        'usage_note': '나는 대화를 이어갑니다. AgentOS가 맥락과 일, 허용된 기능을 연결합니다.',
        'footer': '상호작용과 제품 방향을 설명하는 예시입니다. 실제 관측 실행이나 배포된 연동 기능을 뜻하지 않습니다.'},
 'ja': {'title': 'Personal AgentOS',
        'subtitle': '同じ PA。文脈は手元に。',
        'illustration_label': '対話の形 · 製品の方向性',
        'comparison_title': '答えと指示の先へ、続く仕事',
        'cards': [{'name': 'Assistant',
                   'verb': '答える',
                   'quote': 'NVIDIA の今の株価は？',
                   'reply': '最新の情報を確認します。',
                   'flow': ['質問', '検索', '回答'],
                   'caption': '質問への答えを得る。'},
                  {'name': '実行型エージェント',
                   'verb': '実行する',
                   'quote': 'このヘッドホンを Amazon のカートに入れて。',
                   'reply': 'ブラウザーで商品を開きます。',
                   'flow': ['指示', 'ブラウザー・ツール', '実行・権限の確認'],
                   'caption': '指示された仕事を、必要な権限で進める。'},
                  {'name': 'Personal AgentOS',
                   'verb': '任せた仕事を引き継ぐ',
                   'quote': '来週の会議、気にかけておいて。',
                   'reply': '未決のことと次の準備を引き継ぎます。',
                   'flow': ['意図', '残る仕事', '次の準備'],
                   'caption': '任せた仕事は時間をまたいで続く。'}],
        'architecture_title': '一人の PA、仕事と権限は自分の環境に',
        'owner': 'あなた',
        'pa': 'PA · 会話するエージェント',
        'owned': '自分の環境が PA の状態を保つ。',
        'links': [('出典のある一つの会議', '予定の招待 + 提案書 + 以前の決定'),
                  ('異なる関係', '予定: 時間; プロジェクト: 決定; 招待 ≠ 受諾'),
                  ('続く仕事', '事前資料 → メモ → 次の段階'),
                  ('権限と根拠', '下書き ≠ 送信; 許可と実際の結果を確認')],
        'judgment': '判断・調整',
        'replaceable_ai': '交換可能な AI',
        'tools': 'ツール',
        'services': 'サービス',
        'same_pa': '同じ PA。',
        'different_ai': '変わる AI。',
        'context_stays': '残る仕事と根拠は自分の環境に。',
        'usage_title': '時間がたっても、話は続く',
        'usage': [{'time': 'はじめに',
                   'quote': 'コーヒー、もうなくなりそう。',
                   'reply': '次の買い物ではコーヒーも必要ですね。',
                   'label': '何気ない一言が文脈になる。'},
                  {'time': '数時間後',
                   'quote': '今から出るんだけど、途中で買えるところあるかな？',
                   'reply': 'コーヒーですね。通る道を教えてもらえれば探します。',
                   'label': '前の話と今の状況がつながる。'},
                  {'time': 'その後',
                   'quote': '時間ないな。前と同じものを買っておいて。',
                   'reply': '前回のコーヒーですね。支払い前に確認します。',
                   'label': '前の選択 · 必要になった時に権限確認'}],
        'usage_note': '自分は話を続ける。AgentOS が文脈と仕事、許可された機能をつなぐ。',
        'footer': '対話の形と製品の方向性を説明する例です。実際に観測した動作や提供済みの連携機能ではありません。'},
 'zh-CN': {'title': 'Personal AgentOS',
           'subtitle': '同一个 PA，工作与上下文由你掌控。',
           'illustration_label': '交互方式 · 产品方向',
           'comparison_title': '从回答和执行，到持续推进工作',
           'cards': [{'name': 'Assistant',
                      'verb': '回答问题',
                      'quote': 'NVIDIA 现在的股价是多少？',
                      'reply': '我来查一下最新信息。',
                      'flow': ['提问', '搜索', '回答'],
                      'caption': '为一个问题找到答案。'},
                     {'name': '任务型智能体',
                      'verb': '执行指令',
                      'quote': '把这款耳机放进我的 Amazon 购物车。',
                      'reply': '我先在浏览器里打开商品。',
                      'flow': ['指令', '浏览器与工具', '执行与权限交接'],
                      'caption': '完成明确的任务，按需获取权限。'},
                     {'name': 'Personal AgentOS',
                      'verb': '持续推进受托工作',
                      'quote': '下周的会议帮我留意一下。',
                      'reply': '我会记下未决事项，准备下一步。',
                      'flow': ['意图', '未完工作', '下一步准备'],
                      'caption': '受托的工作跨越时间继续。'}],
           'architecture_title': '同一个 PA，工作与权限由你掌控',
           'owner': '你',
           'pa': 'PA · 与你对话的智能体',
           'owned': '你的环境保留 PA 的状态。',
           'links': [('一场有来源的会议', '日程邀请 + 提案 + 此前的决定'),
                     ('不同的关系', '日程: 时间; 项目: 决定; 邀请 ≠ 接受'),
                     ('持续中的工作', '会前材料 → 会议记录 → 下一步'),
                     ('权限与证据', '草稿 ≠ 发送; 核对授权与实际结果')],
           'judgment': '判断与协调',
           'replaceable_ai': '可替换的 AI',
           'tools': '工具',
           'services': '服务',
           'same_pa': '同一个 PA。',
           'different_ai': '不同的 AI。',
           'context_stays': '未完工作与证据留在你的环境中。',
           'usage_title': '时间过去，对话继续',
           'usage': [{'time': '起初', 'quote': '咖啡快没了。', 'reply': '下次买东西时，也得补上咖啡。', 'label': '随口一句，成为后续的上下文。'},
                     {'time': '几小时后',
                      'quote': '我准备出门了，路上有地方可以买到吗？',
                      'reply': '是说咖啡吧？告诉我路线，我来找找。',
                      'label': '接上前文，结合现在的情况。'},
                     {'time': '之后',
                      'quote': '没时间了，就买上次那款吧。',
                      'reply': '上次那款咖啡。付款前会请你确认。',
                      'label': '先前的选择 · 需要时再请求权限'}],
           'usage_note': '你继续说话，AgentOS 连接上下文、工作与获准的能力。',
           'footer': '交互方式与产品方向的示例，并非实际观测的运行，也不代表已发布的集成功能。'}}

class OverviewFigure(Figure):
 def measure(self, text, width, size=22, gap=None):
  return Figure(1, 1, '', '').lines(0, 0, text, width, size, gap=gap or size*1.35)
 def label(self, x, top, text, width, size=22, cls='', anchor='start'):
  return self.lines(x, top+size, text, width, size, cls, gap=size*1.35, anchor=anchor)
 def circle(self,x,y,r,fill,stroke='none'):
  self.out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}"/>')
 def icon(self,kind,x,y,size=48,color='#245b92'):
  shapes={
   'search':'<path d="M8 45V18m0 27h37M15 35l9-10 9 4 10-15"/><circle cx="43" cy="18" r="10"/><path d="m50 26 8 9"/>',
   'cart':'<path d="M14 29v-7a18 18 0 0 1 36 0v7M14 21h7v17h-7zm29 0h7v17h-7zM8 42h8l5 12h26l6-12H23"/><circle cx="25" cy="60" r="2"/><circle cx="44" cy="60" r="2"/>',
   'coffee':'<path d="M12 26h31v18a10 10 0 0 1-10 10H22a10 10 0 0 1-10-10zM43 29h7a8 8 0 0 1 0 16h-7M8 59h41M19 19c-8-8 6-10 0-17M31 19c-8-8 6-10 0-17"/>',
   'owner':'<circle cx="32" cy="17" r="10"/><path d="M13 57v-9a19 19 0 0 1 38 0v9"/>',
   'pa':'<circle cx="32" cy="32" r="24"/><circle cx="32" cy="32" r="9"/><path d="M32 0v8m0 48v8M0 32h8m48 0h8"/>',
   'memory':'<path d="M16 12h34v42H16zM10 20h12m-12 12h12m-12 12h12M29 22h13m-13 9h13m-13 9h9"/>',
   'context':'<circle cx="32" cy="32" r="8"/><circle cx="12" cy="12" r="5"/><circle cx="52" cy="15" r="5"/><circle cx="13" cy="52" r="5"/><circle cx="51" cy="51" r="5"/><path d="m16 16 10 10m12 0 10-8M17 48l9-10m12 0 9 9"/>',
   'work':'<rect x="12" y="10" width="40" height="46" rx="5"/><path d="m20 24 3 3 5-7m5 5h11M20 38h7m6 0h11M20 47h7m6 0h11"/>',
   'authority':'<path d="M32 6 52 14v16c0 13-9 21-20 28-11-7-20-15-20-28V14z"/><circle cx="32" cy="28" r="6"/><path d="M32 34v10"/>',
   'evidence':'<path d="M14 8h27l9 9v40H14zM41 8v12h9M22 29h19m-19 8h13m-13 8 6 6 13-13"/>',
   'events':'<circle cx="32" cy="32" r="24"/><path d="M32 16v17l11 7M6 32h5m42 0h5M32 6v5m0 42v5"/>',
   'model':'<rect x="16" y="16" width="32" height="32" rx="6"/><path d="M24 6v10m16-10v10M24 48v10m16-10v10M6 24h10M6 40h10m32-16h10M48 40h10M26 26h12v12H26z"/>',
   'tools':'<path d="m12 8 11 11-6 6L6 14c-4 14 6 23 18 17l25 25 7-7-25-25C37 12 28 2 16 6l10 10-7 7"/>',
   'services':'<path d="M16 45a12 12 0 0 1-3-24 17 17 0 0 1 32-3 13 13 0 0 1 3 27H16zM22 52v8m20-8v8"/>',
  }
  self.out.append(f'<g transform="translate({x} {y}) scale({size/64})" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">{shapes[kind]}</g>')
 def dialogue_height(self,text,width):
  return self.measure(text,width-66,22)+26
 def dialogue(self,x,y,width,text,reply=False):
  height=self.dialogue_height(text,width)
  self.icon('pa' if reply else 'owner',x,y+13,24,'#257a69' if reply else '#53657a')
  self.rect(x+36,y,width-36,height,'#ffffff' if reply else '#edf4fb','#d3dedf' if reply else '#edf4fb',12)
  self.label(x+50,y+13,text,width-66,22)
  return height
 def section(self,y,number,title,width):
  self.circle(40,y+21,20,'#e9f0f6')
  self.text(40,y+28,number,18,'blue bold','middle')
  return max(42,self.label(74,y,title,width-98,28,'bold'))+22
 def finish(self,height):
  self.out[0]=self.out[0].replace('height="6000"',f'height="{height}"').replace('0 0 '+str(self.w)+' 6000',f'0 0 {self.w} {height}')
  self.out[3]=self.out[3].replace('height="6000"',f'height="{height}"')
  return self


def overview(d,mobile):
 w=420 if mobile else 1120
 f=OverviewFigure(w,6000,d['title'],d['footer'])
 margin=20 if mobile else 28
 usable=w-2*margin
 y=24
 y+=f.label(margin,y,d['title'],usable,34,'bold')+8
 y+=f.label(margin,y,d['subtitle'],usable,23,'blue')+14
 y+=f.label(margin,y,d['illustration_label'],usable,20,'muted')+32
 y+=f.section(y,'01',d['comparison_title'],w)
 cw=usable if mobile else (usable-40)/3
 card_heights=[]
 for card in d['cards']:
  height=188
  height+=f.dialogue_height(card['quote'],cw-36)+12
  height+=f.dialogue_height(card['reply'],cw-36)+22
  height+=f.measure(' → '.join(card['flow']),cw-40,20)+20
  card_heights.append(height)
 desktop_height=max(card_heights)
 for index,card in enumerate(d['cards']):
  x=margin if mobile else margin+index*(cw+20)
  top=y if mobile else y
  ch=card_heights[index] if mobile else desktop_height
  accent='#257a69' if index==2 else '#245b92'
  fill='#eff7f3' if index==2 else '#f7f9fc'
  f.rect(x,top,cw,ch,fill,'#b7d1c5' if index==2 else '#d4dce5',16)
  f.circle(x+cw/2,top+56,39,'#e0eee6' if index==2 else '#e9eff7')
  f.icon(['search','cart','work'][index],x+cw/2-30,top+24,60,accent)
  f.label(x+20,top+110,card['name'],cw-40,25,'bold')
  f.label(x+20,top+148,card['verb'],cw-40,22,'blue bold')
  cy=top+188
  cy+=f.dialogue(x+18,cy,cw-36,card['quote'])+12
  cy+=f.dialogue(x+18,cy,cw-36,card['reply'],True)+22
  f.label(x+20,cy,' → '.join(card['flow']),cw-40,20,'blue bold')
  if mobile:y+=ch+20
 if not mobile:y+=desktop_height
 y+=32
 y+=f.section(y,'02',d['architecture_title'],w)
 if mobile:
  owner_x=110; pa_x=300
  f.icon('owner',owner_x-23,y,46,'#53657a')
  f.icon('pa',pa_x-23,y,46,'#257a69')
  f.path(f'M{owner_x+38} {y+24}H{pa_x-38}','#8296a9')
  f.path(f'M{owner_x+45} {y+18}L{owner_x+38} {y+24}L{owner_x+45} {y+30}M{pa_x-45} {y+18}L{pa_x-38} {y+24}L{pa_x-45} {y+30}','#8296a9')
  f.label(owner_x,y+54,d['owner'],130,22,'bold','middle')
  f.label(pa_x,y+54,d['pa'],175,20,'bold','middle')
  conversation_bottom=y+54+max(f.measure(d['owner'],130,22),f.measure(d['pa'],175,20))
  sy=conversation_bottom+44
  ox=margin; ow=usable
  f.path(f'M{pa_x} {conversation_bottom+12}V{sy-12}H{w/2}V{sy}','#8296a9')
 else:
  ox=220; ow=654; sy=y
  f.icon('owner',71,sy+97,64,'#53657a')
  f.label(103,sy+175,d['owner'],160,23,'bold','middle')
 first_offset=59+f.measure(d['owned'],ow-40,20)+22 if mobile else 179
 row_gap=14
 title_width=ow-112
 detail_width=ow-134
 row_title_size=22 if mobile else 20
 row_detail_size=20 if mobile else 18
 row_heights=[max(94,30+f.measure(title,title_width,row_title_size)+f.measure(detail,detail_width,row_detail_size)) for title,detail in d['links']]
 grid_height=sum(row_heights)+(len(row_heights)-1)*row_gap
 judgment_height=f.measure(d['judgment'],ow-32,21)
 oh=first_offset+grid_height+24+judgment_height+20
 f.rect(ox,sy,ow,oh,'#f0f6f9','#b6cad9',18)
 f.label(ox+20,sy+20,'Personal AgentOS',ow-40,26,'bold')
 f.label(ox+20,sy+59,d['owned'],ow-40,20,'muted')
 if not mobile:
  f.rect(ox+20,sy+102,ow-40,54,'#e3f0e9','#bad3c8',12)
  f.icon('pa',ox+38,sy+115,28,'#257a69')
  f.label(ox+ow/2+10,sy+113,d['pa'],ow-120,22,'bold','middle')
  f.path(f'M153 {sy+129}H{ox+20}','#8296a9')
  f.path(f'M160 {sy+123}L153 {sy+129}L160 {sy+135}M{ox+13} {sy+123}L{ox+20} {sy+129}L{ox+13} {sy+135}','#8296a9')
 first=sy+first_offset
 st=first
 kinds=['memory','context','work','authority']
 for index,((title,detail),row_height) in enumerate(zip(d['links'],row_heights)):
  sx=ox+20
  f.rect(sx,st,ow-40,row_height,'#fff','#d8e1e7',10)
  f.icon(kinds[index],sx+15,st+21,38,'#427665' if index<2 else '#496d92')
  title_height=f.label(sx+72,st+10,title,title_width,row_title_size,'bold')
  f.label(sx+72,st+18+title_height,detail,detail_width,row_detail_size,'muted')
  if index<len(row_heights)-1:
   f.arrow(ox+ow/2,st+row_height+1,ox+ow/2,st+row_height+row_gap-2)
  st+=row_height+row_gap
 f.label(ox+ow/2,first+grid_height+24,d['judgment'],ow-32,21,'blue bold','middle')
 f.arrow(ox+ow/2,sy+oh+4,ox+ow/2,sy+oh+27)
 ey=sy+oh+34
 if mobile:
  f.rect(ox,ey,ow,106,'#fafbfd','#d4dce5',12)
  f.icon('model',ox+20,ey+25,48,'#526b91')
  f.label(ox+88,ey+15,d['replaceable_ai'],ow-108,22,'bold')
  f.label(ox+88,ey+54,'AI A  →  AI B',ow-108,22,'blue')
  f.icon('tools',ox+24,ey+128,30,'#526b91')
  f.label(ox+68,ey+130,d['tools'],115,20)
  f.icon('services',ox+208,ey+128,30,'#526b91')
  f.label(ox+250,ey+130,d['services'],ow-265,20)
  cy=ey+186
  cy+=f.label(w/2,cy,d['same_pa']+' '+d['different_ai'],usable,25,'blue bold','middle')+8
  cy+=f.label(w/2,cy,d['context_stays'],usable,22,'muted','middle')
  y=cy+36
 else:
  ew=(ow-24)/3
  for index,(label,kind) in enumerate([(d['replaceable_ai'],'model'),(d['tools'],'tools'),(d['services'],'services')]):
   ex=ox+index*(ew+12)
   f.rect(ex,ey,ew,109,'#fafbfd','#d4dce5',12)
   f.icon(kind,ex+ew/2-19,ey+12,38,'#526b91')
   f.label(ex+ew/2,ey+61,label,ew-20,20,'muted','middle')
  rx=908; rw=184; cy=sy+102
  f.icon('pa',rx,cy-56,38,'#257a69')
  cy+=f.label(rx,cy,d['same_pa'],rw,27,'blue bold')+8
  cy+=f.label(rx,cy,d['different_ai'],rw,27,'blue bold')+20
  cy+=f.label(rx,cy,d['context_stays'],rw,22,'muted')+28
  f.label(rx,cy,'AI A → AI B',rw,22,'blue bold')
  y=ey+145
 f.path(f'M{margin} {y}H{w-margin}','#d4dce5')
 y+=16
 y+=f.label(margin,y,d['footer'],usable,20,'muted')+24
 return f.finish(int(y))

SCENES = {'en': {'title': 'Everyday conversation, continuing context',
        'label': 'Illustrative reconstruction · product direction',
        'pa_header': 'PA',
        'owner_label': 'You',
        'footer': 'Separate representative scenes. Not product screenshots, observed runs or claims of shipped '
                  'integrations.',
        'scenes': [{'id': 'way-home',
                    'title': 'On the way home',
                    'visual_title': 'Current location shared',
                    'visual_meta': 'Shared when needed',
                    'owner': 'Somewhere to eat on my way home?',
                    'reply': 'Where are you now? Share your location.',
                    'followup': '',
                    'response': 'Here are two places on your way home.',
                    'cards': [{'title': 'Restaurant A', 'detail': 'A quick meal'},
                              {'title': 'Restaurant B', 'detail': 'A relaxed meal'}],
                    'action': '',
                    'takeaway': 'Ask for context when it becomes useful.'},
                   {'id': 'product-choice',
                    'title': 'From a choice to the next step',
                    'visual_title': 'Headphone photo',
                    'visual_meta': 'A product to compare',
                    'owner': 'Something like this, within my budget.',
                    'reply': 'Two options within that budget.',
                    'followup': 'The first one. Add it to my cart.',
                    'response': 'Connect your shopping account to continue with Model A.',
                    'cards': [{'title': 'Model A', 'detail': 'Lighter to carry'},
                              {'title': 'Model B', 'detail': 'Longer battery life'}],
                    'action': 'Connect shopping account',
                    'takeaway': 'Keep the choice; ask for access when needed.'},
                   {'id': 'place-continuation',
                    'title': 'A photo, then the next thought',
                    'visual_title': 'Restaurant photo · current place shared',
                    'visual_meta': 'The starting point stays in context',
                    'owner': 'Here now. A walk afterwards?',
                    'reply': 'Two walks from the place you shared.',
                    'followup': 'The riverside one. How do I get there?',
                    'response': 'Starting from this restaurant, then.',
                    'cards': [{'title': 'Riverside walk', 'detail': 'Along the water'},
                              {'title': 'Neighborhood loop', 'detail': 'Around the local streets'}],
                    'action': 'Route from here',
                    'takeaway': 'The photo, place and next question stay connected.'}],
        'screen_badge': 'Reconstruction',
        'composer': 'Message PA'},
 'ko': {'title': '짧게 말해도, 앞뒤는 이어지도록',
        'label': '설명을 위해 재구성한 대화 · 제품 방향',
        'pa_header': 'PA',
        'owner_label': '나',
        'footer': '서로 독립된 대표 장면입니다. 실제 제품 캡처나 관측 실행이 아니며, 배포된 연동 기능을 뜻하지 않습니다.',
        'scenes': [{'id': 'way-home',
                    'title': '집에 가는 길에',
                    'visual_title': '현재 위치 공유',
                    'visual_meta': '필요해진 순간에 공유',
                    'owner': '집에 가는 길에 밥 먹을 만한 데 있을까?',
                    'reply': '지금 어디 계세요? 현재 위치를 알려주세요.',
                    'followup': '',
                    'response': '집에 가는 길에 들를 만한 곳 두 곳이에요.',
                    'cards': [{'title': '식당 A', 'detail': '간단한 한 끼'}, {'title': '식당 B', 'detail': '여유 있게 식사'}],
                    'action': '',
                    'takeaway': '맥락이 필요해진 순간에 묻습니다.'},
                   {'id': 'product-choice',
                    'title': '고른 뒤에 이어지는 일',
                    'visual_title': '헤드폰 사진',
                    'visual_meta': '비교할 상품의 모습',
                    'owner': '이런 걸로, 내 예산 안에서 찾아봐줘.',
                    'reply': '그 예산이면 이 두 가지를 비교해볼 만해요.',
                    'followup': '첫 번째 걸로. 장바구니에 넣어줘.',
                    'response': '모델 A로 이어갈게요. 쇼핑 계정을 연결해주세요.',
                    'cards': [{'title': '모델 A', 'detail': '가볍게 들고 다니기'},
                              {'title': '모델 B', 'detail': '더 긴 배터리 사용 시간'}],
                    'action': '쇼핑 계정 연결',
                    'takeaway': '선택은 이어받고, 필요한 접근만 요청합니다.'},
                   {'id': 'place-continuation',
                    'title': '사진에서 다음 이야기로',
                    'visual_title': '식당 사진 · 현재 장소 공유',
                    'visual_meta': '출발할 장소도 맥락에 남습니다',
                    'owner': '지금 여기야. 먹고 나서 산책할까?',
                    'reply': '알려주신 곳에서 가볼 만한 산책 코스 두 곳이에요.',
                    'followup': '강변 쪽으로. 어떻게 가면 돼?',
                    'response': '지금 계신 식당에서 출발하는 길로요.',
                    'cards': [{'title': '강변 산책', 'detail': '물가를 따라 걷기'},
                              {'title': '동네 한 바퀴', 'detail': '주변 골목을 걷기'}],
                    'action': '여기서 가는 길',
                    'takeaway': '사진과 장소, 다음 질문을 연결합니다.'}],
        'screen_badge': '재구성',
        'composer': 'PA에게 이야기하기'},
 'ja': {'title': '短い言葉でも、話はつながる',
        'title_narrow': ['短い言葉でも、', '話はつながる'],
        'label': '説明用に再構成した対話 · 製品の方向性',
        'pa_header': 'PA',
        'owner_label': 'あなた',
        'footer': 'それぞれ独立した代表例です。実際の製品画面や観測済みの動作ではなく、提供済みの連携機能を示すものでもありません。',
        'scenes': [{'id': 'way-home',
                    'title': '家に帰る途中で',
                    'visual_title': '現在地を共有',
                    'visual_meta': '必要になった時に共有',
                    'owner': '家に帰る途中で、ご飯を食べられるところある？',
                    'reply': '今どの辺りですか？現在地を教えてください。',
                    'followup': '',
                    'response': '帰り道に立ち寄れる候補が二つあります。',
                    'cards': [{'title': 'お店 A', 'detail': '手軽に食事'}, {'title': 'お店 B', 'detail': 'ゆっくり食事'}],
                    'action': '',
                    'takeaway': '必要になった時に、状況を尋ねる。'},
                   {'id': 'product-choice',
                    'title': '選んだ後も、続けられる',
                    'visual_title': 'ヘッドホンの写真',
                    'visual_meta': '比べたい商品のイメージ',
                    'owner': 'こんな感じで、予算内のものを探して。',
                    'reply': 'その予算なら、この二つが候補です。',
                    'followup': '最初のほうをカートに入れて。',
                    'response': 'モデル A ですね。続けるには購入用アカウントを接続してください。',
                    'cards': [{'title': 'モデル A', 'detail': '軽くて持ち運びやすい'},
                              {'title': 'モデル B', 'detail': 'バッテリーが長持ち'}],
                    'action': '購入用アカウントを接続',
                    'takeaway': '選択を引き継ぎ、必要な時に権限を確認。'},
                   {'id': 'place-continuation',
                    'title': '写真から、次の話へ',
                    'visual_title': 'お店の写真 · 現在地を共有',
                    'visual_meta': '出発する場所も文脈に残る',
                    'owner': '今ここ。食べた後に散歩しようかな？',
                    'reply': '教えてもらった場所から歩ける候補が二つあります。',
                    'followup': '川沿いのほう。どう行けばいい？',
                    'response': '今いるお店を出発点にしますね。',
                    'cards': [{'title': '川沿いの散歩', 'detail': '水辺を歩く'},
                              {'title': '近所をひと回り', 'detail': '周りの通りを歩く'}],
                    'action': 'ここからの道順',
                    'takeaway': '写真、場所、次の質問をつなぐ。'}],
        'screen_badge': '再構成',
        'composer': 'PA に話しかける'},
 'zh-CN': {'title': '话可以很短，前后仍能接上',
           'label': '为说明而重构的对话 · 产品方向',
           'pa_header': 'PA',
           'owner_label': '你',
           'footer': '三个独立的代表性场景，并非实际产品截图或观测运行，也不代表已发布的集成功能。',
           'scenes': [{'id': 'way-home',
                       'title': '回家的路上',
                       'visual_title': '已分享当前位置',
                       'visual_meta': '需要时再分享',
                       'owner': '回家路上有什么地方可以吃点东西？',
                       'reply': '你现在在哪里？分享一下当前位置吧。',
                       'followup': '',
                       'response': '这两家可以顺路去。',
                       'cards': [{'title': '餐馆 A', 'detail': '简单吃一顿'}, {'title': '餐馆 B', 'detail': '坐下来慢慢吃'}],
                       'action': '',
                       'takeaway': '需要上下文时，再向你询问。'},
                      {'id': 'product-choice',
                       'title': '选好以后，接着往下做',
                       'visual_title': '耳机照片',
                       'visual_meta': '想比较的商品类型',
                       'owner': '找个类似的，在我的预算内。',
                       'reply': '这个预算内，可以比较这两款。',
                       'followup': '第一款。帮我放进购物车。',
                       'response': '选型号 A。连接购物账户后，就能继续。',
                       'cards': [{'title': '型号 A', 'detail': '更轻便'}, {'title': '型号 B', 'detail': '电池续航更长'}],
                       'action': '连接购物账户',
                       'takeaway': '接住你的选择，需要时再请求权限。'},
                      {'id': 'place-continuation',
                       'title': '从照片，聊到下一件事',
                       'visual_title': '餐馆照片 · 已分享所在地点',
                       'visual_meta': '出发地点也留在上下文中',
                       'owner': '现在在这里。吃完去散散步？',
                       'reply': '从你分享的位置出发，可以考虑这两条路线。',
                       'followup': '河边那条。怎么过去？',
                       'response': '就从你现在这家餐馆出发。',
                       'cards': [{'title': '河边散步', 'detail': '沿着水边走'}, {'title': '街区小环线', 'detail': '逛逛周围的街道'}],
                       'action': '从这里出发',
                       'takeaway': '照片、地点和接下来的问题连在一起。'}],
           'screen_badge': '重构',
           'composer': '与 PA 交谈'}}

class SceneFigure(OverviewFigure):
 def message_height(self,text,width):
  return self.measure(text,width-44,20)+24
 def message(self,x,y,width,text,owner=False):
  bubble_width=width-16
  height=self.message_height(text,width)
  bx=x+16 if owner else x
  self.rect(bx,y,bubble_width,height,'#deecfa' if owner else '#ffffff','#deecfa' if owner else '#dbe3e9',12)
  self.label(bx+14,y+12,text,bubble_width-28,20)
  return height
 def photo(self,x,y,width,height,name,identity):
  # Keep input assets independent of ROOT: tests redirect ROOT for outputs.
  import base64
  source=Path(__file__).resolve().parent/name
  data=base64.b64encode(source.read_bytes()).decode('ascii')
  self.out.append(f'<defs><clipPath id="{identity}"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10"/></clipPath></defs>')
  self.out.append(f'<image x="{x}" y="{y}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{identity})" href="data:image/jpeg;base64,{data}"/>')
 def map(self,x,y,width,height,identity):
  self.out.append(f'<defs><clipPath id="{identity}"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10"/></clipPath></defs><g clip-path="url(#{identity})">')
  self.rect(x,y,width,height,'#f1efe8','none',0)
  self.out.append(f'<path d="M{x+width*.76} {y-10}Q{x+width*.57} {y+height/2} {x+width*.82} {y+height+20}" stroke="#c7dfeb" stroke-width="35" fill="none"/>')
  self.rect(x+20,y+14,width*.31,40,'#dce9d6','none',6)
  self.rect(x+width*.77,y+height*.6,width*.3,height*.5,'#dce9d6','none',6)
  for dy in (height*.33,height*.7):
   self.out.append(f'<path d="M{x} {y+dy}H{x+width}" stroke="#fff" stroke-width="14"/>')
  for dx in (width*.2,width*.5,width*.88):
   self.out.append(f'<path d="M{x+dx} {y}V{y+height}" stroke="#fff" stroke-width="12"/>')
  self.out.append(f'<path d="M{x+width*.2} {y+height*.82}V{y+height*.7}H{x+width*.5}V{y+height*.33}H{x+width*.68}" stroke="#4c83bc" stroke-width="5" stroke-linejoin="round" stroke-linecap="round" fill="none"/>')
  self.circle(x+width*.2,y+height*.82,11,'#5088c0','#fff')
  for label,px,py in [('A',x+width*.5,y+height*.37),('B',x+width*.68,y+height*.26)]:
   self.circle(px,py,14,'#fff','#43846c')
   self.text(px,py+7,label,20,'blue bold','middle')
  self.out.append('</g>')
 def results_height(self,scene,width):
  total=self.measure(scene['reply'],width-28,20)+26
  for card in scene['cards']:
   total+=max(58,self.measure(card['title'],width-82,20)+self.measure(card['detail'],width-82,20)+8)+12
  return total+4
 def results(self,x,y,width,scene):
  height=self.results_height(scene,width)
  self.rect(x,y,width,height,'#fff','#dbe3e9',12)
  cy=y+13
  cy+=self.label(x+14,cy,scene['reply'],width-28,20)+16
  for index,card in enumerate(scene['cards']):
   row_h=max(58,self.measure(card['title'],width-82,20)+self.measure(card['detail'],width-82,20)+8)
   self.circle(x+34,cy+24,17,'#e7f1ec')
   self.text(x+34,cy+31,chr(65+index),20,'blue bold','middle')
   tx=x+64
   th=self.label(tx,cy,card['title'],width-82,20,'bold')
   self.label(tx,cy+th+4,card['detail'],width-82,20,'muted')
   cy+=row_h+12
  return height
 def handoff_height(self,scene,width):
  return self.measure(scene['response'],width-32,20)+self.measure(scene['action'],width-48,20)+54
 def handoff(self,x,y,width,scene):
  height=self.handoff_height(scene,width)
  self.rect(x,y,width,height,'#edf5f0','#bfd6c8',12)
  cy=y+14
  cy+=self.label(x+16,cy,scene['response'],width-32,20)+16
  button_h=self.measure(scene['action'],width-48,20)+18
  self.rect(x+12,cy,width-24,button_h,'#fff','#8bad9b',8)
  self.label(x+width/2,cy+9,scene['action'],width-48,20,'blue bold','middle')
  return height


def scenes(d,mobile):
 w=420 if mobile else 1120
 f=SceneFigure(w,6000,d['title'],d['footer'])
 margin=20 if mobile else 28; usable=w-2*margin
 cw=usable if mobile else (usable-40)/3
 y=24
 for line in d.get('title_narrow',[d['title']]) if mobile else [d['title']]:
  y+=f.label(margin,y,line,usable,30,'bold')
 y+=10
 label_lines=d['label'].split(' · ') if mobile else [d['label']]
 for line in label_lines:
  y+=f.label(margin,y,line,usable,21,'blue bold')
 y+=30
 badge=d['screen_badge']
 headings=[f.measure(scene['title'],cw-44,24) for scene in d['scenes']]
 screen_heights=[]
 content_width=cw-32
 for index,scene in enumerate(d['scenes']):
  height=80
  if index:
   height+=172+10+f.measure(scene['visual_title'],content_width-28,20)+18
  height+=f.message_height(scene['owner'],content_width)+12
  if not index:
   height+=f.message_height(scene['reply'],content_width)+14
   height+=172+12+f.measure(scene['visual_title'],content_width-28,20)+18
   result_scene=dict(scene,reply=scene['response'])
  else:result_scene=scene
  height+=f.results_height(result_scene,content_width)+14
  if scene['followup']:
   height+=f.message_height(scene['followup'],content_width)+12
  if scene['action']:height+=f.handoff_height(scene,content_width)+14
  height+=68
  screen_heights.append(height)
 max_height=max(screen_heights)
 max_heading=max(headings)
 for index,scene in enumerate(d['scenes']):
  x=margin if mobile else margin+index*(cw+20)
  f.out.append(f'<g id="scene-{scene["id"]}">')
  heading_height=headings[index] if mobile else max_heading
  f.circle(x+13,y+17,12,'#e5edf4')
  f.text(x+13,y+23,str(index+1),18,'blue bold','middle')
  f.label(x+38,y,scene['title'],cw-44,24,'bold')
  top=y+heading_height+18
  sh=screen_heights[index] if mobile else max_height
  f.rect(x,top,cw,sh,'#f2f6f7','#aebdc8',26)
  f.rect(x+1,top+1,cw-2,62,'#fff','none',25)
  f.path(f'M{x+1} {top+62}H{x+cw-1}','#dbe3e9')
  f.icon('pa',x+17,top+18,27,'#3b7c69')
  f.label(x+54,top+17,d['pa_header'],60,22,'bold')
  f.label(x+cw-17,top+19,badge,cw-110,20,'muted','end')
  bx=x+16; bw=content_width; cy=top+80
  if index:
   photo='illustrative-headphones.jpg' if index==1 else 'illustrative-restaurant.jpg'
   f.photo(bx+16,cy,bw-16,172,photo,f'photo-{index}')
   cy+=184
   cy+=f.label(bx+22,cy,scene['visual_title'],bw-28,20,'muted')+16
  cy+=f.message(bx,cy,bw,scene['owner'],True)+12
  if not index:
   cy+=f.message(bx,cy,bw,scene['reply'])+14
   f.map(bx+16,cy,bw-16,172,'location-map')
   cy+=184
   cy+=f.label(bx+22,cy,scene['visual_title'],bw-28,20,'blue bold')+16
   result_scene=dict(scene,reply=scene['response'])
  else:result_scene=scene
  cy+=f.results(bx,cy,bw,result_scene)+14
  if scene['followup']:cy+=f.message(bx,cy,bw,scene['followup'],True)+12
  if scene['action']:cy+=f.handoff(bx,cy,bw,scene)+14
  composer_y=top+sh-54
  f.rect(bx,composer_y,bw,40,'#fff','#d0dce3',20)
  f.text(bx+21,composer_y+28,'+',25,'muted','middle')
  f.label(bx+42,composer_y+8,d['composer'],bw-56,20,'muted')
  takeaway_y=top+sh+15
  takeaway_h=f.label(x,takeaway_y,scene['takeaway'],cw,21,'blue')
  f.out.append('</g>')
  if mobile:y=takeaway_y+takeaway_h+34
 if not mobile:
  y=top+max_height+15+max(f.measure(scene['takeaway'],cw,21) for scene in d['scenes'])+30
 f.path(f'M{margin} {y}H{w-margin}','#d4dce5')
 y+=18
 y+=f.label(margin,y,d['footer'],usable,20,'muted')+22
 return f.finish(int(y))

if __name__=='__main__':
 for locale,d in DATA.items():
  for kind,builder in [('interaction-model',comparison),('presence',presence),('continuing-conversation',usage)]:
   for mobile in [False,True]:
    builder(d,mobile).write(f'{kind}.{locale}{".narrow" if mobile else ""}.svg')

 for locale,d in OVERVIEW.items():
  for mobile in [False,True]:
   overview(d,mobile).write(f'presence-overview.{locale}{".narrow" if mobile else ""}.svg')

 for locale,d in SCENES.items():
  for mobile in [False,True]:
   scenes(d,mobile).write(f'presence-scenes.{locale}{".narrow" if mobile else ""}.svg')
