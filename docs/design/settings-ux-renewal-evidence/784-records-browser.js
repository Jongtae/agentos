async page=>{
 const check=(v,m)=>{if(!v)throw new Error(m)};
 await page.unroute('**/api/status');await page.route('**/api/status',r=>r.fulfill({json:{claimed:true,authenticated:true,local_access:false}}));await page.reload();await page.request.post('http://127.0.0.1:18789/control/rich-tasks',{data:{}});
 await page.locator('[data-view="tasks"]').click();await page.reload();await page.locator('.turn-pair').first().waitFor();await page.screenshot({path:'output/playwright/ux784-work.png'});
 const work=await page.locator('#task-list').innerText();check(work.includes('서울')&&work.includes('398,000'),'substantive result visible');
 await page.goto('http://127.0.0.1:18789/#item/memory/memory-exact');await page.locator('#item-detail').waitFor();await page.screenshot({path:'output/playwright/ux784-item.png'});
 const item=await page.locator('#item-detail').innerText();check(item.includes('exact durable memory'),'exact retained memory opens');
 await page.unroute('**/api/status');await page.route('**/api/status',r=>r.fulfill({json:{claimed:true,authenticated:false,local_access:false}}));await page.reload();check(await page.locator('#welcome-language').isVisible(),'welcome language reachable');check(await page.locator('#welcome-language option').count()===4,'welcome four languages');await page.screenshot({path:'output/playwright/ux784-welcome.png'});
 await page.unroute('**/api/status');await page.route('**/api/status',r=>r.fulfill({json:{claimed:true,authenticated:true,local_access:false}}));await page.goto('http://127.0.0.1:18789/#settings/ai');await page.reload();
 await page.locator('.settings-row-title').first().waitFor();const styles=await page.evaluate(()=>{const selectors=['body','.settings-row-title','.settings-row-value','#settings-tab-ai','button'];return selectors.map(selector=>{const n=document.querySelector(selector),s=n?getComputedStyle(n):null;if(!s)return {selector,missing:true};return {selector,color:s.color,background:s.backgroundColor,font:s.fontSize}})});
 return {workResult:true,exactItem:true,welcome:true,logout:await page.locator('#logout').isVisible(),styles};
}
