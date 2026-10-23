"""Two-party completion and opt-in social features. No official order/payment tools."""
import base64, binascii, datetime as dt, hashlib, json, secrets, struct, zlib


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS social_profiles (actor TEXT PRIMARY KEY,public_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,rank_opt_in INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS social_completions (invitation_id TEXT PRIMARY KEY,host TEXT NOT NULL,guest TEXT NOT NULL,completed_at TEXT NOT NULL,pair_day TEXT NOT NULL,ranked INTEGER NOT NULL)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS social_pair_day ON social_completions(pair_day) WHERE ranked=1')
    db.execute('CREATE TABLE IF NOT EXISTS social_photos (invitation_id TEXT PRIMARY KEY,version TEXT NOT NULL,image BLOB NOT NULL,caption TEXT NOT NULL,host_agree INTEGER NOT NULL,guest_agree INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS social_reinvites (id TEXT PRIMARY KEY,source_id TEXT NOT NULL,sender TEXT NOT NULL,recipient TEXT NOT NULL,status TEXT NOT NULL,pickup TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL,new_invitation TEXT)')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS social_pending_pair ON social_reinvites(source_id) WHERE status IN ('pending','accepted')")


def profile(db,actor,name='麦麦搭子'):
    db.execute('INSERT OR IGNORE INTO social_profiles(actor,public_id,name) VALUES (?,?,?)',(actor,secrets.token_urlsafe(12),name))
    return db.execute('SELECT public_id,name,rank_opt_in FROM social_profiles WHERE actor=?',(actor,)).fetchone()


def count(db,actor):
    row=db.execute('SELECT count(*),coalesce(sum(ranked),0) FROM social_completions WHERE host=? OR guest=?',(actor,actor)).fetchone()
    return {'completedCount':row[0],'rankedCount':row[1]}


def participant(row,actor):
    if actor and actor==row[2]:return 'host'
    if actor and actor==row[3]:return 'guest'
    raise ValueError('只有这份拼单的双方可以操作。')


def photo_view(db,id,role):
    p=db.execute('SELECT version,caption,host_agree,guest_agree FROM social_photos WHERE invitation_id=?',(id,)).fetchone()
    if not p:return None
    public=bool(p[2] and p[3])
    if role=='visitor' and not public:return None
    return {'id':id,'version':p[0],'caption':p[1],'hostAgreed':bool(p[2]),'guestAgreed':bool(p[3]),'public':public}


def room_data(core,row,r,actor):
    role='host' if row[2]==actor else 'guest' if row[3]==actor else 'visitor'
    with core.connect() as db:
        return {'hostStats':count(db,row[2]),'guestStats':count(db,row[3]) if row[3] else None,'photo':photo_view(db,r['id'],role),'completionBasis':'双方在本站确认完成分餐/交接，非官方订单或付款认证'}


def assert_access(db,row,r,actor):
    if r.get('reinviteId') and actor!=row[2]:
        p=db.execute('SELECT recipient FROM social_reinvites WHERE id=?',(r['reinviteId'],)).fetchone()
        if not p or p[0]!=actor:raise ValueError('这是一份给原搭子的定向邀请。')


def complete(core,id,actor):
    import market
    with core.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE');row,r=market.read(db,id);role=participant(row,actor)
        if row[1] not in ('confirmed','completed'):raise ValueError('先由双方确认餐品与金额，完成分餐后再确认完成。')
        r[role+'Completed']=True
        if r.get('hostCompleted') and r.get('guestCompleted'):
            date=core.now().date().isoformat()
            # Opaque pair key, never exposed. Same pair/day can only earn one ranking credit.
            key=hashlib.sha256(('\0'.join(sorted([row[2],row[3]]))+'\0'+date).encode()).hexdigest()
            ranked=not db.execute('SELECT 1 FROM social_completions WHERE pair_day=? AND ranked=1',(key,)).fetchone()
            inserted=db.execute('INSERT OR IGNORE INTO social_completions VALUES (?,?,?,?,?,?)',(id,row[2],row[3],core.timestamp(),key,int(ranked))).rowcount
            profile(db,row[2],r['hostName']);profile(db,row[3],r['guestName'])
            if inserted:r['completedAt']=core.timestamp()
            db.execute("UPDATE invitations SET status='completed',data=? WHERE id=?",(json.dumps(r,ensure_ascii=False),id))
        else:db.execute('UPDATE invitations SET data=? WHERE id=?',(json.dumps(r,ensure_ascii=False),id))
    return market.get(core,id,actor)


def png_bytes(encoded):
    """Accept bounded, non-interlaced RGB(A) PNG; re-encode pixels, discard all metadata."""
    if not isinstance(encoded,str) or not encoded.startswith('data:image/png;base64,') or len(encoded)>2100000:raise ValueError('请选择小于1.5MB的PNG预览图。')
    try:raw=base64.b64decode(encoded.split(',',1)[1],validate=True)
    except (ValueError,binascii.Error):raise ValueError('照片格式不正确。')
    signature=b'\x89PNG\r\n\x1a\n'
    if not raw.startswith(signature):raise ValueError('照片必须是PNG图片。')
    offset=8;header=None;chunks=[];ended=False;seen_idat=False;closed_idat=False
    while offset<len(raw):
        if offset+12>len(raw):raise ValueError('PNG文件不完整。')
        size=struct.unpack('>I',raw[offset:offset+4])[0];kind=raw[offset+4:offset+8]
        if size>1500000 or offset+12+size>len(raw):raise ValueError('PNG文件过大或损坏。')
        data=raw[offset+8:offset+8+size];crc=struct.unpack('>I',raw[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+data)&0xffffffff!=crc:raise ValueError('PNG校验失败。')
        if header is None and kind!=b'IHDR':raise ValueError('PNG头不正确。')
        if kind==b'IHDR':
            if header is not None or size!=13:raise ValueError('PNG头不正确。')
            header=data;w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if not 1<=w<=1280 or not 1<=h<=1280 or depth!=8 or color not in (2,6) or compression or filtering or interlace:raise ValueError('请使用浏览器生成的1280像素以内PNG预览图。')
        elif kind==b'IDAT':
            if closed_idat:raise ValueError('PNG数据顺序不正确。')
            seen_idat=True;chunks.append(data)
        elif kind==b'IEND':
            if size:raise ValueError('PNG结束标记不正确。')
            ended=True;offset+=12;break
        elif kind==b'acTL' or not (kind[0]&32):raise ValueError('不支持动画或此种PNG格式。')
        elif seen_idat:closed_idat=True
        offset+=size+12
    if not ended or offset!=len(raw) or not chunks:raise ValueError('PNG文件不完整。')
    stride=w*(4 if color==6 else 3)+1;expected=stride*h
    try:
        dec=zlib.decompressobj();pixels=dec.decompress(b''.join(chunks),expected+1)
        if len(pixels)!=expected or not dec.eof or dec.unused_data or dec.unconsumed_tail or any(pixels[y*stride]>4 for y in range(h)):raise ValueError('PNG像素数据不正确。')
    except zlib.error:raise ValueError('PNG像素数据损坏。')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return signature+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')


def photo_action(core,id,body,actor,action):
    import market
    image=png_bytes(body.get('image')) if action=='upload' else None
    if action=='upload' and body.get('agreePublic') is not True:raise ValueError('上传前请明确同意公开照片、双方昵称和门店名称。')
    caption=core.short_text(body.get('caption',''),'照片说明',80)
    with core.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE');row,r=market.read(db,id);role=participant(row,actor)
        if row[1]!='completed':raise ValueError('双方确认完成后才能上传或公开合照。')
        if action=='upload':
            db.execute('INSERT OR REPLACE INTO social_photos VALUES (?,?,?,?,?,?)',(id,secrets.token_urlsafe(12),image,caption,int(role=='host'),int(role=='guest')))
        else:
            p=db.execute('SELECT version FROM social_photos WHERE invitation_id=?',(id,)).fetchone()
            if not p or p[0]!=body.get('version'):raise market.Conflict('照片已变更，请重新查看后决定。')
            if action not in ('agree','revoke'):raise ValueError('照片操作不存在。')
            db.execute('UPDATE social_photos SET '+role+'_agree=? WHERE invitation_id=?',(int(action=='agree'),id))
    return market.get(core,id,actor)


def image(core,id,version,actor):
    import market
    with core.connect() as db:
        init(db);row,r=market.read(db,id)
        p=db.execute('SELECT version,image,host_agree,guest_agree FROM social_photos WHERE invitation_id=?',(id,)).fetchone()
        if not p or p[0]!=version:raise ValueError('照片不存在或已更新。')
        if not (p[2] and p[3]):participant(row,actor)
        return bytes(p[1])


def expire_reinvites(db,core):
    db.execute("UPDATE social_reinvites SET status='expired' WHERE status IN ('pending','accepted') AND pickup<=?",(core.now().isoformat(timespec='minutes'),))


def reinvite_view(core,p,actor):
    import market
    with core.connect() as db:row,r=market.read(db,p[1])
    option=next(o for o in r['options'] if o['store']['id']==r['selectedStore'])
    return {'id':p[0],'sourceId':p[1],'status':p[4],'pickup':p[5],'note':p[6],'createdAt':p[7],'newInvitation':p[8],'direction':'outgoing' if p[2]==actor else 'incoming','partnerName':r['guestName'] if row[2]==actor else r['hostName'],'store':option['store']}


def reinvite(core,id,body,actor):
    import market
    if not actor:raise ValueError('请重新打开页面。')
    with core.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE');expire_reinvites(db,core);row,r=market.read(db,id);participant(row,actor)
        if row[1]!='completed':raise ValueError('双方完成这次拼单后才能再次约拼。')
        existing=db.execute("SELECT * FROM social_reinvites WHERE source_id=? AND status IN ('pending','accepted')",(id,)).fetchone()
        if existing:p=existing
        else:
            try:pickup=dt.datetime.fromisoformat(body.get('pickup',''))
            except (ValueError,TypeError):raise ValueError('请选择下次约拼时间。')
            if pickup.tzinfo is not None or not core.now()<pickup<=core.now()+dt.timedelta(days=7):raise ValueError('请选择未来7天内的本地约拼时间。')
            note=core.short_text(body.get('note',''),'约拼留言',100)
            recipient=row[3] if row[2]==actor else row[2]
            rid=secrets.token_urlsafe(12)
            db.execute('INSERT INTO social_reinvites VALUES (?,?,?,?,?,?,?,?,?)',(rid,id,actor,recipient,'pending',pickup.isoformat(timespec='minutes'),note,core.timestamp(),None))
            p=db.execute('SELECT * FROM social_reinvites WHERE id=?',(rid,)).fetchone()
    return reinvite_view(core,p,actor)


def respond(core,id,body,actor):
    with core.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE');expire_reinvites(db,core)
        p=db.execute('SELECT * FROM social_reinvites WHERE id=?',(id,)).fetchone()
        if not p or actor not in (p[2],p[3]):raise ValueError('约拼邀请不存在。')
        action=body.get('action')
        if action=='cancel' and p[2]==actor and p[4] in ('pending','accepted'):status='cancelled'
        elif action in ('accept','decline') and p[3]==actor and p[4]=='pending':status='accepted' if action=='accept' else 'declined'
        else:raise ValueError('当前不能执行这项约拼操作。')
        db.execute('UPDATE social_reinvites SET status=? WHERE id=?',(status,id));p=db.execute('SELECT * FROM social_reinvites WHERE id=?',(id,)).fetchone()
    return reinvite_view(core,p,actor)


def prepare_reinvite(db,core,rid,actor,r):
    if not rid:return
    if not isinstance(rid,str) or len(rid)>80:raise ValueError('约拼标识不正确。')
    expire_reinvites(db,core)
    p=db.execute('SELECT * FROM social_reinvites WHERE id=?',(rid,)).fetchone()
    if not p or p[2]!=actor or p[4]!='accepted':raise ValueError('约拼尚未被接受、已过期或已使用。')
    if r['pickup']!=p[5]:raise ValueError('请按双方约定的时间重新核价。')
    from market import read
    _,original=read(db,p[1])
    if len(r['options'])!=1 or r['options'][0]['store']['id']!=original['selectedStore']:raise ValueError('再次约拼需使用原门店，选择其他门店请重新发起普通拼单。')
    r['reinviteId']=rid;r['privatePair']=True
    db.execute("UPDATE social_reinvites SET status='linked',new_invitation=? WHERE id=?",(r['id'],rid))


def overview(core,actor):
    import market
    with core.connect() as db:
        init(db);expire_reinvites(db,core)
        p=db.execute('SELECT public_id,name,rank_opt_in FROM social_profiles WHERE actor=?',(actor,)).fetchone()
        me={'name':p[1] if p else '', 'rankOptIn':bool(p and p[2]),**count(db,actor)}
        requests=list(db.execute('SELECT * FROM social_reinvites WHERE sender=? OR recipient=? ORDER BY rowid DESC LIMIT 50',(actor,actor))) if actor else []
        rows=list(db.execute("SELECT * FROM invitations WHERE owner=? OR guest=? ORDER BY rowid DESC LIMIT 100",(actor,actor))) if actor else []
    return {'me':me,'invitations':[market.output(core,row,json.loads(row[6]),actor) for row in rows],'reinvites':[reinvite_view(core,p,actor) for p in requests]}


def leaderboard(core):
    with core.connect() as db:
        init(db)
        rows=db.execute('''SELECT p.public_id,p.name,count(c.invitation_id),max(c.completed_at)
          FROM social_profiles p JOIN social_completions c ON (c.host=p.actor OR c.guest=p.actor)
          WHERE p.rank_opt_in=1 AND c.ranked=1 GROUP BY p.actor
          ORDER BY count(c.invitation_id) DESC,max(c.completed_at) ASC,p.public_id ASC LIMIT 50''').fetchall()
    return {'entries':[{'rank':i+1,'id':r[0],'name':r[1],'completedCount':r[2]} for i,r in enumerate(rows)],'basis':'站内自愿参与榜；同一对搭子每天最多1次计分。双方自报完成，非官方成交认证。'}


def gallery(core):
    with core.connect() as db:
        init(db)
        rows=db.execute("SELECT p.invitation_id,p.version,p.caption,i.data FROM social_photos p JOIN invitations i ON i.id=p.invitation_id WHERE p.host_agree=1 AND p.guest_agree=1 AND i.status='completed' ORDER BY p.rowid DESC LIMIT 50").fetchall()
    entries=[]
    for id,version,caption,data in rows:
        r=json.loads(data);o=next(x for x in r['options'] if x['store']['id']==r['selectedStore'])
        entries.append({'id':id,'version':version,'caption':caption,'hostName':r['hostName'],'guestName':r['guestName'],'storeName':o['store']['name']})
    return {'entries':entries}


def get_api(core,path,args,actor):
    if path=='overview':return overview(core,actor)
    if path=='leaderboard':return leaderboard(core)
    if path=='gallery':return gallery(core)
    raise ValueError('社交接口不存在。')


def post_api(core,path,body,actor):
    if path=='profile':
        name=core.short_text(body.get('name',''),'榜单昵称',16,'麦麦搭子')
        if type(body.get('rankOptIn'))!=bool:raise ValueError('请明确选择是否参加站内榜。')
        with core.connect() as db:
            init(db);profile(db,actor,name);db.execute('UPDATE social_profiles SET name=?,rank_opt_in=? WHERE actor=?',(name,int(body['rankOptIn']),actor))
        return overview(core,actor)
    parts=path.split('/')
    if len(parts)==3 and parts[0]=='invitations':
        id,action=parts[1:]
        if action=='complete':return complete(core,id,actor)
        if action=='reinvite':return reinvite(core,id,body,actor)
    if len(parts)==4 and parts[0]=='invitations' and parts[2]=='photo':return photo_action(core,parts[1],body,actor,parts[3])
    if len(parts)==2 and parts[0]=='reinvites':return respond(core,parts[1],body,actor)
    raise ValueError('社交接口不存在。')
