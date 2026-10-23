'use strict';
const CS={data:null,board:null,gallery:null,loading:false,tab:'mine',draft:null,caption:'',preview:null,previewKey:null,previewLoading:null,again:null};
try{CS.again=JSON.parse(sessionStorage.getItem('phm-again')||'null');}catch{}
function socialNav(){return `<nav class="social-nav" aria-label="拼餐记录与社区"><a href="#social" data-social-nav="mine">我的拼餐</a><a href="#social" data-social-nav="board">站内排行榜</a><a href="#social" data-social-nav="gallery">合照墙</a></nav>`;}
function statsText(s){return `双方确认完成 ${s?.completedCount||0} 次`;}
function socialRoom(r){
 const mine=r.role!=='visitor',done=r.status==='completed',ph=r.social?.photo;
 if(!mine)return '';
 const complete=['confirmed','completed'].includes(r.status)?`<section class="panel"><h3>04 · 完成这一次拼餐</h3><p>先完成实际分餐或交接，再分别确认。双方都确认后，各计入一次成功记录。</p><div class="completion-pair"><span>${E(r.hostName)}：${r.hostCompleted?'✓ 已确认完成':'等待确认完成'}</span><span>${E(r.guestName)}：${r.guestCompleted?'✓ 已确认完成':'等待确认完成'}</span></div>${done?'<div class="success-banner">双方已确认完成，这次拼餐已经记入你们的记录。</div>':`<button class="primary" data-social-complete ${S.busy||r[r.role+'Completed']?'disabled':''}>${r[r.role+'Completed']?'我已确认，等对方完成':'我已完成分餐／交接'}</button>`}<p class="source-note">${E(r.social?.completionBasis)}。同一对搭子每天最多1次计入榜单，成功记录仍逐单保留。</p></section>`:'';
 const consent=ph?`<div class="photo-consent"><img id="pair-photo" class="pair-photo" alt="这次拼餐的合照预览" ${CS.previewKey===ph.version&&CS.preview?`src="${E(CS.preview)}"`:''}><p>${E(ph.caption)}</p><p>发起人${ph.hostAgreed?'已同意':'未同意'} · 搭子${ph.guestAgreed?'已同意':'未同意'} · <strong>${ph.public?'已公开在合照墙':'仅双方可见'}</strong></p>${!ph[r.role+'Agreed']?'<label class="consent-check"><input id="photo-agree-check" type="checkbox">我同意将这张照片、双方昵称和门店名称公开到合照墙</label><button class="primary" data-photo-agree>同意公开这张照片</button>':'<button class="secondary" data-photo-revoke>撤回我的同意并下架</button>'}<p class="source-note">任一方撤回，公开墙与图片接口立即停止展示；已经被其他人保存的副本无法收回。更换照片需双方重新同意。</p></div>`:'';
 const photo=done?`<section class="panel"><h3>05 · 自愿留一张合照</h3><p>不强制拍照或露脸。只有双方同意同一版本，才会公开。</p>${consent}<label class="field"><span>${ph?'换一张照片（双方重新同意）':'选择照片'}</span><input id="pair-file" type="file" accept="image/jpeg,image/png,image/webp"></label>${CS.draft?`<img class="pair-photo" alt="待上传照片" src="${CS.draft}"><label class="field"><span>照片说明（选填）</span><input id="photo-caption" maxlength="80" value="${E(CS.caption)}" placeholder="记录这次刚好的相遇"></label><label class="consent-check"><input type="checkbox" id="photo-upload-check">我有权分享这张照片，同意公开照片、双方昵称和门店名称；等待对方同意后展示</label><button class="primary" data-photo-upload>上传并等待对方同意</button>`:''}<p class="source-note">上传前在浏览器缩小为PNG，服务器重新编码并移除附带元数据。不要上传不愿公开的内容。</p></section>`:'';
 const again=done?`<section class="panel"><h3>06 · 下次还一起拼吗？</h3><p>邀请这次的搭子在同一家门店再拼一次。对方接受后，由你重新选餐核价，旧价格不会沿用。</p><label class="field"><span>未来7天的约拼时间</span><input type="datetime-local" id="again-time" value="${nextPickup()}" aria-label="下次约拼时间"></label><label class="field"><span>给搭子留句话</span><input id="again-note" maxlength="100" placeholder="例如：下次午休还一起吃？"></label><button class="secondary" data-reinvite>向这位搭子发出邀请</button><a class="text-link" href="#social">查看收到的邀请与回复 →</a></section>`:'';
 return `<div class="social-detail"><div class="section-head"><h3>拼完这一餐，再留下点什么</h3><a href="#social">我的拼餐与社区 →</a></div><div class="social-columns">${complete}${photo}${again}</div></div>`;
}
function againBanner(){return CS.again?`<div class="notice">正在为原搭子准备定向拼单：沿用约定门店和时间，重新核价后仅原搭子可领取。<button class="quiet" data-again-clear>退出定向模式</button></div>`:'';}
function socialPage(){
 const data=CS.data,me=data?.me;
 const requests=(data?.reinvites||[]).map(r=>`<article class="panel"><div class="card-meta"><strong>${E(r.partnerName)}</strong><span>${E(({pending:'等待回复',accepted:'已接受，等待发起人选餐',declined:'已婉拒',cancelled:'已取消',expired:'已过期',linked:'已生成新的定向拼单'})[r.status])}</span></div><p>${r.direction==='incoming'?'邀请你再次约拼':'你发出的再次约拼'} · ${when(r.pickup)}</p><p>${E(r.store.name)} · ${E(r.note)}</p>${r.status==='pending'&&r.direction==='incoming'?`<button class="primary" data-reply="accept" data-rid="${E(r.id)}">愿意，再拼一次</button> <button class="secondary" data-reply="decline" data-rid="${E(r.id)}">这次先不了</button>`:''}${['pending','accepted'].includes(r.status)&&r.direction==='outgoing'?`<button class="quiet" data-reply="cancel" data-rid="${E(r.id)}">取消这次约拼</button>`:''}${r.status==='accepted'&&r.direction==='outgoing'?`<button class="primary" data-again-start="${E(r.id)}">按约定重新选餐</button>`:''}${r.newInvitation?`<button class="primary" data-room="${E(r.newInvitation)}">查看新的定向拼单</button>`:''}</article>`).join('');
 const mine=`<section class="panel"><h3>我的拼餐记录</h3><div class="my-stats"><strong>${me?.completedCount||0}<small>次双方确认完成</small></strong><strong>${me?.rankedCount||0}<small>次有效榜单记录</small></strong></div><p class="source-note">当前身份保存在本浏览器；换浏览器或清除存储会产生新身份。测试昵称与自报完成记录不构成官方交易认证。</p><form id="rank-form"><label class="field"><span>榜单昵称</span><input id="rank-name" maxlength="16" value="${E(me?.name||S.name)}" placeholder="怎么称呼你"></label><label class="consent-check"><input id="rank-opt-in" type="checkbox" ${me?.rankOptIn?'checked':''}>自愿公开昵称和有效完成次数，参加站内榜（可随时退出）</label><button class="secondary" ${S.busy?'disabled':''}>保存榜单设置</button></form></section><h3>再次约拼</h3><div class="social-columns">${requests||'<div class="empty">还没有再次约拼邀请。完成一次拼餐后，可以向原搭子发出邀请。</div>'}</div><h3>你参与的拼餐</h3><div class="room-grid">${data?.invitations.length?data.invitations.map(r=>card(r,true)).join(''):'<div class="empty">还没有参与记录，发起或领取一份拼单吧。</div>'}</div>`;
 const board=`<section class="panel"><h3>站内排行榜</h3><p>${E(CS.board?.basis||'自愿参加的双方确认完成榜')}</p><ol class="leaderboard">${CS.board?.entries.length?CS.board.entries.map(p=>`<li><span class="rank-number">${p.rank}</span><strong>${E(p.name)}</strong><span>${p.completedCount} 次有效完成</span></li>`).join(''):'<li>暂时还没有完成拼餐并自愿参加榜单的用户。这里不填充虚假记录。</li>'}</ol><p class="source-note">仅覆盖拼好麦站内记录，不是全网排名。当前无实名或付款核验，无法彻底防止多身份刷榜。</p></section>`;
 const wall=`<section class="panel"><h3>刚好两个人 · 合照墙</h3><p>每一张都关联一份双方确认完成的拼单，并由双方同意公开。</p></section><div class="photo-wall">${CS.gallery?.entries.length?CS.gallery.entries.map(p=>`<article class="panel"><img class="pair-photo" src="${E(new URL('api/market/social/photos/'+p.id+'?v='+encodeURIComponent(p.version),base).href)}" alt="${E(p.caption||'双方同意公开的拼餐照片')}" loading="lazy"><h3>${E(p.hostName)} × ${E(p.guestName)}</h3><p>${E(p.caption)}</p><small>${E(p.storeName)} · 双方同意公开</small></article>`).join(''):'<div class="empty">还没有双方同意公开的合照。拍不拍、露不露脸，都由你们决定。</div>'}</div>`;
 return `<button class="back" data-go="">← 返回首页</button><div class="page-title"><div><div class="eyebrow">ONE MEAL · ANOTHER CONNECTION</div><h2>这次拼好，下次再约</h2><p>从一次刚好的拼餐，留下自愿的连接。</p></div><button class="secondary" data-social-refresh>刷新记录</button></div><div class="community-tabs" role="group" aria-label="社区页面"><button class="${CS.tab==='mine'?'active':''}" data-social-tab="mine">我的拼餐</button><button class="${CS.tab==='board'?'active':''}" data-social-tab="board">站内排行榜</button><button class="${CS.tab==='gallery'?'active':''}" data-social-tab="gallery">合照墙</button></div>${CS.loading&&!data?'<p role="status">正在加载站内记录…</p>':CS.tab==='board'?board:CS.tab==='gallery'?wall:mine}${statusBar()}`;
}
async function loadSocial(){
 if(CS.loading)return;CS.loading=true;render();
 try{[CS.data,CS.board,CS.gallery]=await Promise.all([api('social/overview'),api('social/leaderboard'),api('social/gallery')]);}
 catch(e){S.error=e.message;}finally{CS.loading=false;if(route()==='social')render();}
}
function socialBind(){
 if(route()==='social'&&!CS.data&&!CS.loading)queueMicrotask(loadSocial);
 if($('#rank-form'))$('#rank-form').onsubmit=e=>{e.preventDefault();const data={name:$('#rank-name').value,rankOptIn:$('#rank-opt-in').checked};work(async()=>{CS.data=await api('social/profile',data);CS.board=await api('social/leaderboard');toast('榜单设置已保存');});};
 const ph=route()==='room'?S.room?.social?.photo:null;
 if(ph&&CS.previewKey!==ph.version&&CS.previewLoading!==ph.version){
  CS.previewLoading=ph.version;const key=ph.version;
  fetch(new URL('api/market/social/photos/'+ph.id+'?v='+encodeURIComponent(key),base),{headers:{'X-Actor':actor},cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.blob();}).then(blob=>{if(CS.preview)URL.revokeObjectURL(CS.preview);CS.preview=URL.createObjectURL(blob);CS.previewKey=key;const img=$('#pair-photo');if(img&&S.room?.social?.photo?.version===key)img.src=CS.preview;}).catch(()=>{}).finally(()=>{if(CS.previewLoading===key)CS.previewLoading=null;});
 }
 if(CS.again&&route()==='create'&&$('#pickup'))$('#pickup').disabled=true;
}
async function normalizedPhoto(file){
 if(!file||!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>16000000)throw Error('请选择16MB以内的JPG、PNG或WebP照片。');
 const bitmap=await createImageBitmap(file);
 try{let scale=Math.min(1,960/bitmap.width,960/bitmap.height);const canvas=document.createElement('canvas');for(let i=0;i<6;i++){canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/png');if(data.length<=900000)return data;scale*=.75;}throw Error('照片压缩后仍较大，请选更小的照片。');}finally{bitmap.close();}
}
async function startAgain(id){
 const data=await api('social/overview'),request=data.reinvites.find(r=>r.id===id&&r.status==='accepted'&&r.direction==='outgoing');
 if(!request)throw Error('这次约拼尚未被接受或已过期。');
 const city=request.store.cityName||S.city||'西安市';const area=await api('stores?'+new URLSearchParams({city,keyword:request.store.name,radiusKm:20}));
 if(!area.stores.some(s=>s.id===request.store.id))throw Error('当前未查询到原门店，请稍后重试。');
 clearQuote();S.suggestions=[];S.suggestionInfo='';S.area=area;S.stores=area.stores;S.codes=[request.store.id];S.publishCodes=[];S.pickup=request.pickup;S.city=city;S.keyword=request.store.name;S.km=20;
 CS.again={id:request.id,storeId:request.store.id,pickup:request.pickup};sessionStorage.setItem('phm-again',JSON.stringify(CS.again));go('create');await loadTasteOptions();
}
document.addEventListener('click',e=>{
 const nav=e.target.closest('[data-social-nav]');if(nav){CS.tab=nav.dataset.socialNav;if(route()==='social')loadSocial();}
 const b=e.target.closest('button');if(!b||S.busy)return;
 if(b.dataset.socialTab){CS.tab=b.dataset.socialTab;loadSocial();}
 else if(b.hasAttribute('data-social-refresh'))loadSocial();
 else if(b.hasAttribute('data-again-clear')){CS.again=null;sessionStorage.removeItem('phm-again');render();}
 else if(b.hasAttribute('data-social-complete'))work(async()=>{S.room=await api('social/invitations/'+S.room.id+'/complete',{});CS.data=null;toast(S.room.status==='completed'?'双方已完成，记录已保存':'你已确认完成，等待对方');});
 else if(b.hasAttribute('data-photo-upload')){
  const agree=$('#photo-upload-check')?.checked,caption=$('#photo-caption')?.value||'';
  if(!agree){toast('请先阅读并勾选照片公开同意项');return;}
  work(async()=>{S.room=await api('social/invitations/'+S.room.id+'/photo/upload',{image:CS.draft,caption,agreePublic:true});CS.draft=null;CS.caption='';toast('已上传，目前仅双方可见，等待对方同意');});
 }
 else if(b.hasAttribute('data-photo-agree')||b.hasAttribute('data-photo-revoke')){
  const agree=b.hasAttribute('data-photo-agree');if(agree&&!$('#photo-agree-check')?.checked){toast('请先查看照片并勾选公开同意项');return;}
  const version=S.room.social.photo.version;work(async()=>{S.room=await api('social/invitations/'+S.room.id+'/photo/'+(agree?'agree':'revoke'),{version});toast(agree?'你的同意已保存':'已撤回同意，合照墙已下架');});
 }
 else if(b.hasAttribute('data-reinvite')){
  const pickup=$('#again-time').value,note=$('#again-note').value;
  work(async()=>{await api('social/invitations/'+S.room.id+'/reinvite',{pickup,note});CS.data=null;CS.tab='mine';go('social');toast('约拼邀请已保存，对方可在“我的拼餐”回复');});
 }
 else if(b.dataset.reply)work(async()=>{await api('social/reinvites/'+b.dataset.rid,{action:b.dataset.reply});await loadSocial();toast('约拼回复已保存');});
 else if(b.dataset.againStart)work(()=>startAgain(b.dataset.againStart));
});
document.addEventListener('change',e=>{if(e.target.id==='pair-file'){const file=e.target.files[0];work(async()=>{CS.draft=await normalizedPhoto(file);CS.caption='';});}});
window.addEventListener('hashchange',()=>{if(route()==='social')loadSocial();else{CS.draft=null;CS.caption='';}});
setInterval(()=>{if(route()==='social'&&!S.busy&&!CS.loading&&document.visibilityState==='visible'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName))loadSocial();},10000);
