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

OVERVIEW = {
 'en': {
  'title':'One assistant. Your context stays with you.',
  'you':'You', 'pa':'Your PA', 'owned':'Personal AgentOS · in your control',
  'labels':['Your context','Your current work','What happened'],
  'terms':['Memory · Context','Work · Grant','Artifact · Event · Evidence'],
  'judgment':'Judgment: choose capabilities, check results',
  'replaceable':'Replaceable AI + tools / services', 'engines':'AI A  →  AI B',
  'desc':'You talk to one PA. AgentOS connects context, work, permissions and evidence. AI and tools can change beneath that continuing relationship.',
 },
 'ko': {
  'title':'하나의 비서, 내게 남는 맥락',
  'you':'나', 'pa':'내 PA', 'owned':'Personal AgentOS · 내가 통제하는 환경',
  'labels':['나에 대해 아는 것','지금 하고 있는 일','실제로 일어난 일'],
  'terms':['기억 · 맥락','작업 · 권한','결과 · 이벤트 · 근거'],
  'judgment':'판단: 필요한 기능 선택, 결과 확인',
  'replaceable':'교체 가능한 AI + 도구 / 서비스', 'engines':'AI A  →  AI B',
  'desc':'나는 하나의 PA와 이야기합니다. AgentOS는 맥락과 일, 권한과 근거를 연결합니다. 그 관계 아래의 AI와 도구는 교체할 수 있습니다.',
 },
 'ja': {
  'title':'一人のアシスタント。文脈は手元に。',
  'you':'あなた', 'pa':'あなたの PA', 'owned':'Personal AgentOS · 自分で管理する環境',
  'labels':['あなたについて知ること','今取り組んでいること','実際に起きたこと'],
  'terms':['記憶 · 文脈','作業 · 権限','成果 · イベント · 証拠'],
  'judgment':'判断：必要な機能を選び、結果を確認',
  'replaceable':'交換できる AI + ツール / サービス', 'engines':'AI A  →  AI B',
  'desc':'あなたは一人の PA と話します。AgentOS が文脈、作業、権限、証拠をつなぎ、その関係を保ちながら AI やツールを交換できます。',
 },
 'zh-CN': {
  'title':'同一个助手，上下文留在你手中',
  'you':'你', 'pa':'你的 PA', 'owned':'Personal AgentOS · 由你掌控的环境',
  'labels':['关于你的了解','正在处理的事','实际发生的事'],
  'terms':['记忆 · 上下文','工作 · 权限','成果 · 事件 · 证据'],
  'judgment':'判断：选择所需能力，检查结果',
  'replaceable':'可替换的 AI + 工具 / 服务', 'engines':'AI A  →  AI B',
  'desc':'你与同一个 PA 对话。AgentOS 连接上下文、工作、权限和证据；这段关系持续保留，底层 AI 和工具可以替换。',
 },
}

def overview(d,mobile):
 # A small reader-facing overview: conversation, connected owner state,
 # judgment, then replaceable execution. Detailed kernel vocabulary lives
 # in the linked architecture document rather than another README poster.
 w=420 if mobile else 840; h=656 if mobile else 434
 f=Figure(w,h,d['title'],d['desc'])
 f.lines(20,32,d['title'],w-40,23,'bold')
 offset=36 if mobile else 0
 f.rect(20,64+offset,w-40,54,'#fff')
 f.text(w/2-55,99+offset,d['you'],21,'bold','end')
 f.text(w/2-10,99+offset,'⇄',25,'blue','middle')
 f.text(w/2+25,99+offset,d['pa'],21,'bold')
 f.arrow(w/2,122+offset,w/2,140+offset)
 outer_h=364 if mobile else 194
 f.rect(20,148+offset,w-40,outer_h,'#f2f7fc','#96b6d6')
 f.lines(36,176+offset,d['owned'],w-72,18,'bold')
 for i in range(3):
  x=36 if mobile else 36+i*260
  y=(210+i*80 if mobile else 196)+offset
  cw=w-72 if mobile else 248
  f.rect(x,y,cw,66,'#fff','#ccd8e6',5)
  f.lines(x+cw/2,y+24,d['labels'][i],cw-24,18,'bold',anchor='middle',gap=23)
  f.text(x+cw/2,y+51,d['terms'][i],15,'muted','middle')
  if i<2:
   if mobile:f.path(f'M{w/2} {y+66}V{y+80}')
   else:f.path(f'M{x+cw} {y+33}H{x+260}')
 f.lines(w/2,(464 if mobile else 318)+offset,d['judgment'],w-72,17,'blue',anchor='middle',gap=22)
 bottom=148+offset+outer_h
 f.arrow(w/2,bottom+4,w/2,bottom+24)
 f.text(w/2,bottom+52,d['replaceable'],18,'muted','middle')
 f.text(w/2,bottom+81,d['engines'],22,'bold','middle')
 return f

if __name__=='__main__':
 for locale,d in DATA.items():
  for kind,builder in [('interaction-model',comparison),('presence',presence),('continuing-conversation',usage)]:
   for mobile in [False,True]:
    builder(d,mobile).write(f'{kind}.{locale}{".narrow" if mobile else ""}.svg')

 for locale,d in OVERVIEW.items():
  for mobile in [False,True]:
   overview(d,mobile).write(f'presence-overview.{locale}{".narrow" if mobile else ""}.svg')
