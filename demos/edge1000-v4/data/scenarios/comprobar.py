import json,sys,math,collections,os
D=sys.argv[1] if len(sys.argv)>1 else '.'
BASE=1784073600000
def load(n):
    r=collections.defaultdict(list)
    for l in open(os.path.join(D,n+'.jsonl')):
        m=json.loads(l); r[m['id']].append(m)
    return r
def tsec(m): return (m['ts']-BASE)/1000
def hm(s): return '%02d:%02d'%(s//3600,(s%3600)//60)
def first(r,cond):
    for k in range(len(r)-2):
        if cond(r[k]) and cond(r[k+1]) and cond(r[k+2]): return tsec(r[k])
ok=True
def chk(c,msg):
    global ok; ok&=bool(c); print(('OK   ' if c else 'FALLA'),msg)
N3,N4,N5,N6=496,497,528,529
for n,t0 in (('fuego_lento',14*3600),('fuego_rapido',14*3600)):
    d=load(n); print('--',n)
    for nm,i in (('N3',N3),('N4',N4),('N5',N5),('N6',N6)):
        c=first(d[i],lambda m:m['values']['PM2.5']>=35.5)
        pk=max(m['values']['PM2.5'] for m in d[i])
        T0=[m['values']['temperature'] for m in d[i]][:5]
        mx=0;
        for a,b in zip(d[i],d[i][1:]):
            dt=(b['ts']-a['ts'])/60000
            if dt>0: mx=max(mx,(b['values']['temperature']-a['values']['temperature'])/dt) if dt>0.5 else mx
        last=tsec(d[i][-1])
        print('  %s id%d: PM2.5>=35.5 sostenido (3 lecturas) en %s (t0+%s min); pico %.0f; ultimo msg %s'%(nm,i,hm(int(c)) if c else '-',round((c-t0)/60,1) if c else '-',pk,hm(int(last))))
    pre=[m for i in d for m in d[i] if tsec(m)<t0-600 and m['values']['PM2.5']>=35.5]
    chk(not pre,'ningun valor >=35,5 antes de t0 (falsos: %d)'%len(pre))
    nonerr=[tsec(m) for i in d for m in d[i] if m['values']['PM2.5']>=35.5]
    mx=max(m['values']['PM2.5'] for i in d for m in d[i]); chk(mx<=1000,'PM2.5 maximo %.0f <= 1000'%mx)
d=load('fuego_rapido')
c3=first(d[N3],lambda m:m['values']['PM2.5']>=35.5)
chk(c3 and 100<=c3-14*3600<=300,'rapido: N3 supera 35,5 entre 2 y 5 min tras t0 (%.1f min)'%((c3-14*3600)/60))
chk(tsec(d[N3][-1])<=14*3600+4*60+10,'rapido: N3 deja de enviar ~t0+4 min (%s)'%hm(int(tsec(d[N3][-1]))))
chk(tsec(d[N4][-1])<=14*3600+6.3*60+3*60+15,'rapido: N4 destruido ~t0+9,3 min')
ds=load('fuego_lento')
c3=first(ds[N3],lambda m:m['values']['PM2.5']>=35.5)
chk(c3 and 18*60<=c3-14*3600<=45*60,'lento: N3 supera 35,5 a ~20-40 min (%.1f)'%((c3-14*3600)/60))
for nm,i in (('N4',N4),('N6',N6),('N5',N5)):
    c=first(ds[i],lambda m:m['values']['PM2.5']>=35.5); print('  lento %s supera 35,5 en t0+%s min'%(nm,round((c-14*3600)/60,1) if c else 'nunca'))
# polvo
d=load('polvo_tractor'); c=27+21*32+1
pk=max(d[c],key=lambda m:m['values']['PM10']); r=pk['values']['PM2.5']/pk['values']['PM10']
chk(0.1<=r<=0.4,'polvo: razon PM2.5/PM10 en el pico = %.2f (esperado 0,10-0,40)'%r)
tt=[m['values']['temperature'] for m in d[c] if 12.25*3600<=tsec(m)<=12.25*3600+300]
chk(max(tt)-min(tt)<2.0,'polvo: temperatura sin cambio (rango %.2f °C en el pico)'%(max(tt)-min(tt)))
dur=[tsec(m) for m in d[c] if m['values']['PM10']>150]; print('  polvo: PM10>150 durante %.0f s (%s-%s)'%(max(dur)-min(dur),hm(int(min(dur))),hm(int(max(dur)))))
# niebla
d=load('niebla'); allm=[m for i in d for m in d[i]]
mx=max(m['values']['PM2.5'] for m in allm); hr=max(m['values']['humidity'] for m in allm)
chk(hr>=90 and mx<45,'niebla: HR max %.0f, PM2.5 max %.1f'%(hr,mx))
print('  niebla: PM2.5>=35.5 en %d lecturas'%sum(m['values']['PM2.5']>=35.5 for m in allm))
# sol
d=load('sol_directo'); mx=0
for i in d:
    for a,b in zip(d[i],d[i][1:]):
        mx=max(mx,(b['values']['temperature']-a['values']['temperature'])/((b['ts']-a['ts'])/60000))
chk(mx<2.0,'sol: subida maxima entre lecturas %.2f °C/min (ruido incluido; < 6,7)'%mx)
# sos
d=load('sos_boton'); em=[m for i in d for m in d[i] if m['kind']=='emergency']
chk(len(em)>=10 and all(m['id']==3*0+(3+28*32+1) for m in em),'sos: %d mensajes emergency, solo del nodo %d'%(len(em),3+28*32+1))
chk(min(tsec(m) for m in em)>=20*3600-5 and min(tsec(m) for m in em)<=20*3600+5,'sos: primer emergency a las 20:00')
# congelado
d=load('fallo_congelado'); c=100; fz=[m for m in d[c] if 3*3600<=tsec(m)<3*3600+300]
chk(len(set(json.dumps(m['values']) for m in fz))==1,'congelado: %d mensajes con valores identicos'%len(fz))
# ruido
d=load('fallo_ruido'); import statistics as st
a=[m['values']['PM2.5'] for m in d[300] if 16*3600+30*60<=tsec(m)<17*3600]; b=[m['values']['PM2.5'] for m in d[300] if tsec(m)<16*3600+30*60]
chk(st.pstdev(a)>3*st.pstdev(b),'ruido: desviacion %.1f vs %.1f antes'%(st.pstdev(a),st.pstdev(b)))
# silencio
d=load('fallo_silencio'); ts=[tsec(m) for m in d[500]]; gap=max(b-a for a,b in zip(ts,ts[1:]))
seqs=[m['seq'] for m in d[500]]
chk(170<=gap<=200,'silencio: hueco maximo %.0f s'%gap)
chk(all(b-a==1 for a,b in zip(seqs,seqs[1:])),'silencio: seq continuo (no avanza durante el silencio)')
print('RESULTADO','TODO OK' if ok else 'HAY FALLOS')
