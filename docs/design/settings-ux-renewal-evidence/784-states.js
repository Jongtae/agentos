async (page) => {
 let variant="ready";
 await page.unroute("**/api/state");
 await page.route('**/api/folder-requests', route=>route.fulfill({json:{requests:[]}}));
 await page.route('**/api/state', async route=>{
  const response=await route.fetch(), data=await response.json();
  const routes=['codex','claude-code','openai','anthropic','openrouter'].map(id=>({id,name:{codex:'Codex','claude-code':'Claude Code',openai:'OpenAI',anthropic:'Anthropic',openrouter:'OpenRouter'}[id],kind:['codex','claude-code'].includes(id)?'subscription':'api',installed:true,login:{state:id==='codex'?'signed-in':'token-saved'},credential:id==='claude-code',destination:id==='codex'?'OpenAI':id==='claude-code'?'Anthropic':'api.'+id+'.com',model:id==='codex'?'':'fixture-model',key:{saved:id==='openai',pending:false},agency:{search:{available:true},browser:{available:true}}}));
  data.settings.main_ai={current:'codex',routes,order:routes.map(r=>r.id),last_check:{state:'signed-in',checked_at:1700000000}};
  data.settings.subscription_engines.selected='codex';
  data.settings.subscription_execution={trust:'trusted-local',selectable:['strict-isolated','trusted-local'],limitation:'Synthetic diagnostic details for layout review.',qualified:{}};
  data.settings.decision_route.mode='explicit';
  if(variant==='empty'){data.settings.main_ai.current='';data.settings.subscription_engines.selected='';}
  if(variant==='unknown-login')routes[0].login.state='unknown';
  if(['strict','stale'].includes(variant)){data.settings.subscription_execution.trust='strict-isolated';data.settings.subscription_execution.requalify_needed=variant==='stale';}
  if(variant==='unknown-access')data.settings.subscription_execution.trust='unexpected';
  await route.fulfill({json:data});
 });
 const checks=[];
 await page.setViewportSize({width:1280,height:800});
 for(const [value,label] of [['empty','선택된 AI 없음'],['unknown-login','로그인 상태 확인 필요'],['strict','작업 폴더로 제한'],['stale','격리 다시 확인 필요'],['unknown-access','접근 범위 확인 필요']]){
  variant=value;await page.reload();await page.locator('#active-ai').getByText(label,{exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/ux784-'+value+'.png'});checks.push(value);
 }
 variant='ready';await page.reload();await page.locator('#active-ai').getByText('로그인 확인됨',{exact:true}).waitFor();
 await page.setViewportSize({width:320,height:740});
 const mobile=await page.evaluate(()=>({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth}));
 await page.screenshot({path:'output/playwright/ux784-320.png'});await page.setViewportSize({width:1280,height:800});
 return {checks,mobile};
}