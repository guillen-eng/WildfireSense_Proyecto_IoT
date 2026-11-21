import json, math, random, os, sys, zlib
PITCH=126.0; NC=32
BASE_MS=1784073600000  # 2026-07-15 00:00:00 UTC
OUT = 'out'
SEED = 42
if __name__ == '__main__':
    OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
    SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    os.makedirs(OUT, exist_ok=True)

def nid(col,row): return row*NC+col+1
def pos(i): return ((i-1)%NC, (i-1)//NC)
def dist(a,b):
    ca,ra=pos(a); cb,rb=pos(b); return math.hypot((cb-ca)*PITCH,(rb-ra)*PITCH)
def fac(dx,dy):
    d=math.hypot(dx,dy)
    if d==0: return 1.0
    return max(0.1,0.5+0.5*dx/d)
def box(center,half):
    c,r=pos(center); return [nid(c+i,r+j) for j in range(-half,half+1) for i in range(-half,half+1)]
def hh(t): return t/3600.0   # seconds -> hours
def Tdiurnal(t): return 18+8*math.sin(2*math.pi*(hh(t)-9)/24)
def RHdiurnal(t): return 70-25*math.sin(2*math.pi*(hh(t)-9)/24)
def S(h,m=0): return h*3600+m*60

class Node:
    def __init__(s,i,rng):
        s.id=i; s.rng=rng; s.seq=0
        s.off_pm=rng.gauss(0,1.5); s.off_t=rng.gauss(0,0.3); s.off_rh=rng.gauss(0,1.5)
        s.boot='%08x'%rng.getrandbits(32); s.phase=rng.random()

def meas_pm(rng,true,sd_scale=1.0):
    sd=(4.0 if true<100 else 0.04*true)*sd_scale
    return min(1000.0,max(0.0,true+rng.gauss(0,sd)))

def run(name,nodes_ids,t_start,t_end,period,truth_fun,desc,expect,extra=None,hooks=None):
    rng=random.Random(SEED+zlib.crc32(name.encode())%1000)
    nodes={i:Node(i,random.Random(SEED*1000+i)) for i in nodes_ids}
    lines=[]
    for i,nd in nodes.items():
        t=t_start+nd.phase*period
        frozen=None
        while t<t_end:
            send=True; kind='periodic'; sdm=1.0
            tv=truth_fun(nd.id,t)       # dict: pm25_exc,pm10_exc,dT,dRH,dead
            if tv.get('dead'): break
            bg=8+2*math.sin(2*math.pi*hh(t)/7)
            pm25=bg+nd.off_pm+tv.get('pm25_exc',0)
            pm10=(bg+nd.off_pm)/0.5+tv.get('pm10_exc',0)
            T=Tdiurnal(t)+nd.off_t+tv.get('dT',0)
            RH=min(100,max(5,RHdiurnal(t)+nd.off_rh+tv.get('dRH',0)))
            if hooks and 'node' in hooks: 
                r=hooks['node'](nd,t,rng)
                if r=='silent': send=False
                elif r=='frozen_on':
                    pass
            noisy=hooks.get('noisy',lambda n,t:1.0)(nd,t) if hooks else 1.0
            pm25m=meas_pm(rng,pm25,noisy)
            pm10m=max(pm25m,meas_pm(rng,pm10,noisy))
            Tm=T+rng.gauss(0,0.25*noisy)
            RHm=min(100,max(0,RH+rng.gauss(0,1.0*noisy)))
            fr=hooks.get('frozen',lambda n,t:False)(nd,t) if hooks else False
            if fr:
                if frozen is None: frozen=(pm25m,pm10m,Tm,RHm)
                pm25m,pm10m,Tm,RHm=frozen
            else: frozen=None
            if hooks and 'kind' in hooks:
                k=hooks['kind'](nd,t)
                if k: kind=k
            if send:
                nd.seq+=1
                ts=BASE_MS+int(t*1000)
                lines.append((ts,json.dumps({'id':nd.id,'ts':ts,'tx':ts,'seq':nd.seq,'kind':kind,'v':1,'boot_id':nd.boot,
                  'values':{'PM2.5':round(pm25m,1),'PM10':round(pm10m,1),'temperature':round(Tm,2),'humidity':round(RHm,1)}},separators=(',',':'))))
            per=period
            if hooks and 'period' in hooks: per=hooks['period'](nd,t,period)
            t+=per
    lines.sort()
    with open(os.path.join(OUT,name+'.jsonl'),'w') as f:
        for _,l in lines: f.write(l+'\n')
    tr={'escenario':name,'descripcion':desc,'seed':SEED,'periodo_s':period,'inicio_ventana':t_start,'fin_ventana':t_end,
        'nota_tiempo':'segundos desde las 00:00 del dia simulado; ts = %d + segundos*1000 (ms)'%BASE_MS,'mensajes':len(lines),'nodos':nodes_ids}
    tr.update(expect)
    if extra: tr.update(extra)
    json.dump(tr,open(os.path.join(OUT,name+'_verdad.json'),'w'),indent=1,ensure_ascii=False)
    return len(lines)

# ------------------------------------------------ fire
N3=nid(15,15); N4=nid(16,15); N5=nid(15,16); N6=nid(16,16)
FIRE_NODES=box(N3,3)
def fire_model(R0,wind,P0,tau,ratio,t0,kind):
    c0,r0=pos(N3)
    info={}
    for i in FIRE_NODES:
        c,r=pos(i); dx=(c-c0)*PITCH; dy=(r-r0)*PITCH; d=math.hypot(dx,dy)
        f=fac(dx,dy); cth=dx/d if d>0 else 1
        tf=t0+d/(R0*f)*60          # R0 en m/min
        ts_=t0+(d/(wind*max(0.3,cth)) if d>0 else 0)
        peak=P0*math.exp(-d/150)*(1 if d==0 else (1 if (dx>0 and dy==0) else f))
        info[i]=dict(d=d,tf=tf,ts=ts_,peak=peak,f=f)
    def tv(i,t):
        n=info[i]; out={}
        e=0.0
        if t>n['ts']:
            x=(t-n['ts'])/(tau*60)
            e=n['peak']*((1-math.exp(-x*x)) if kind=='fast' else (1-math.exp(-x)))
        if t>n['tf']:
            tau2=60 if kind=='fast' else 600
            e+=(P0-n['peak'])*(1-math.exp(-(t-n['tf'])/tau2))
        out['pm25_exc']=e; out['pm10_exc']=e/ratio-e*0 if False else e/ratio
        if kind=='slow':
            if t>n['tf']: out['dT']=0.8*(1-math.exp(-(t-n['tf'])/1800))
        else:
            tfT=n['tf']+(60 if i==N3 else 0)
            if t>=tfT:
                m=(t-tfT)/60
                if m>3: out['dead']=True
                else: out['dT']=8*m
        return out
    return info,tv

def fire_expect(info,thr_t):
    return None

def gen_fire(name,kind):
    t0=S(14)
    if kind=='slow':
        R0,wind,P0=1.0,1.0,150.0; tau=98.5; ratio=0.6; w=(S(12),S(19)); per=30
        desc='Fuego lento con origen en el nodo %d (alias N3). Viento 1 m/s hacia el este. Avance 1 m/min. PM2.5 pico 150, PM2.5/PM10 del humo 0,6.'%N3
    else:
        R0,wind,P0=20.0,3.0,500.0; tau=8.4; ratio=0.8; w=(S(13,30),S(15)); per=5
        desc='Fuego rapido con origen en el nodo %d (alias N3). Viento 3 m/s hacia el este. Avance 20 m/min. PM2.5 pico 500, PM2.5/PM10 del humo 0,8. El humo crece con forma 1-exp(-(t/8,4 min)^2). El frente destruye los nodos que alcanza (dejan de enviar 3 min despues).'%N3
    info,tv=fire_model(R0,wind,P0,tau,ratio,t0,kind)
    # momentos teoricos (sin ruido) en que PM2.5 total supera 35.5
    ex={}
    for i,n in info.items():
        cross=None
        t=w[0]
        while t<w[1]:
            o=tv(i,t)
            if o.get('dead'): break
            if 8+o.get('pm25_exc',0)>=35.5: cross=t; break
            t+=10
        ex[str(i)]={'distancia_m':round(n['d'],1),'llega_fuego_s':round(n['tf'],0) if n['tf']<w[1] else None,'humo_empieza_s':round(n['ts'],0),'pico_humo_ug_m3':round(n['peak'],1),'PM2.5_supera_35_5_s':cross}
    expect={'t0_s':t0,'alias':{'N3':N3,'N4':N4,'N5':N5,'N6':N6},'nodos_detalle':ex,
      'alarma_esperada':True,'nodo_primera_alarma':N3,
      'criterio':'Debe haber alarma de fuego en N3 y confirmacion de vecinos. Retardo = primera alarma - t0_s. Ningun nodo debe alarmar antes de t0_s.'}
    return run(name,FIRE_NODES,w[0],w[1],per,tv,desc,expect)

# ------------------------------------------------ non-fire
def gen_dust():
    c=nid(27,21); ids=box(c,2); t0=S(12,15)
    def tv(i,t):
        d=dist(i,c); a=math.exp(-d/100); tt=t-t0-d/3.0
        if tt<0 or tt>300: return {}
        sh=min(1,tt/30)*(1 if tt<210 else max(0,1-(tt-210)/90))
        pm10=400*a*sh; pm25=100*a*sh
        return {'pm25_exc':pm25,'pm10_exc':pm10}
    return run('polvo_tractor',ids,S(11,45),S(12,45),10,tv,
      'Tractor en el nodo %d a las 12:15: pico de 4-5 min, PM10 +400 y PM2.5 +100 (razon total ~0,25), sin cambio de temperatura. Los vecinos reciben menos (exp(-d/100)).'%c,
      {'t0_s':t0,'nodo_evento':c,'alarma_esperada':False,'criterio':'No debe haber alarma de fuego. Razon PM2.5/PM10 en el pico ~0,25 (<0,3). Duracion < 30 s por encima del suelo no se cumple de forma sostenida: debe suprimirse por razon baja.'})

def gen_fog():
    ids=box(nid(27,21),2)
    def sm(x): x=min(1,max(0,x)); return x*x*(3-2*x)
    def tv(i,t):
        h=hh(t); up=sm((h-5.5)/0.5)-sm((h-9)/0.5)       # 05:30-06:00 sube, 09:00-09:30 baja
        return {'pm25_exc':12*up,'pm10_exc':17*up,'dRH':(95-RHdiurnal(t))*up if up>0 else 0,'dT':-2.0*up}
    return run('niebla',ids,S(5),S(10),60,tv,
      'Niebla de 05:30 a 09:30 en toda la malla: HR sube hasta 95 %, PM2.5 aparente +12 y PM10 +17 (razon ~0,6), temperatura 2 °C por debajo de la normal.',
      {'t0_s':S(5,30),'alarma_esperada':False,'criterio':'No debe haber alarma: PM2.5 sube pero la HR es alta y la temperatura no sube. PM2.5 no supera 35,5 salvo posibles picos de ruido; si algun valor lo supera la HR alta debe suprimir.'})

def gen_sun():
    ids=box(nid(27,21),2)
    exp={i:(random.Random(i).uniform(0.3,1.0)*2.8 if random.Random(i*7).random()<0.4 else 0.0) for i in ids}
    def sm(x): x=min(1,max(0,x)); return x*x*(3-2*x)
    def tv(i,t):
        up=sm((t-S(10,30))/1800.0)
        return {'dT':4.0*up+exp[i]*up}
    return run('sol_directo',ids,S(10),S(12,30),60,tv,
      'Paso de nublado a soleado entre 10:30 y 11:00: temperatura del aire +4 °C en 30 min y error de radiacion de hasta 2,8 °C en el 40 % de los nodos. PM sin cambio.',
      {'t0_s':S(10,30),'alarma_esperada':False,'error_sol_por_nodo':{str(k):round(v,2) for k,v in exp.items()},'criterio':'No debe haber alarma. La subida maxima es ~0,3 °C/min, muy por debajo de 6,7 °C/min.'})

def gen_sos():
    c=nid(3,28); ids=box(c,1); t0=S(20)
    def tv(i,t): return {}
    def kind(nd,t): return 'emergency' if (nd.id==c and t0<=t<t0+60) else None
    def period(nd,t,p): return 5 if (nd.id==c and t0-5<=t<t0+60) else p
    return run('sos_boton',ids,S(19,30),S(20,30),60,tv,
      'Boton SOS pulsado en el nodo %d a las 20:00: kind=emergency cada 5 s durante 60 s. Valores ambientales normales.'%c,
      {'t0_s':t0,'nodo_evento':c,'alarma_esperada':True,'tipo_alarma':'sos_alert','criterio':'Alarma sos_alert inmediata (menos de 5 s) y sin esperar confirmacion de vecinos.'},hooks={'kind':kind,'period':period})

def gen_frozen():
    c=100; ids=box(c,1)
    return run('fallo_congelado',ids,S(2,30),S(3,30),10,lambda i,t:{},
      'Sensor congelado en el nodo 100 de 03:00 a 03:05: repite exactamente los mismos valores.',
      {'t0_s':S(3),'nodo_evento':c,'alarma_esperada':False,'estado_esperado_nodo':'SOSPECHOSO','criterio':'El nodo 100 pasa a SOSPECHOSO tras N lecturas iguales (propuesta N=10). No es alarma de fuego.'},
      hooks={'frozen':lambda nd,t: nd.id==c and S(3)<=t<S(3,5)})

def gen_noise():
    c=300; ids=box(c,1)
    return run('fallo_ruido',ids,S(16),S(17,30),10,lambda i,t:{},
      'Ruido excesivo en el nodo 300 de 16:30 a 17:00: desviacion tipica 4 veces mayor en PM y temperatura, sin cambio de nivel (los valores negativos se recortan a 0).',
      {'t0_s':S(16,30),'nodo_evento':c,'alarma_esperada':False,'estado_esperado_nodo':'SOSPECHOSO','criterio':'El nodo 300 pasa a SOSPECHOSO por varianza anomala. No es alarma de fuego. Nota: los valores negativos se recortan a 0.'},
      hooks={'noisy':lambda nd,t: 4.0 if (nd.id==c and S(16,30)<=t<S(17)) else 1.0})

def gen_silence():
    c=500; ids=box(c,1)
    return run('fallo_silencio',ids,S(21,30),S(22,30),10,lambda i,t:{},
      'El nodo 500 deja de enviar de 22:00 a 22:03 y vuelve a enviar (el contador seq no avanza durante el silencio).',
      {'t0_s':S(22),'nodo_evento':c,'alarma_esperada':False,'estado_esperado_nodo':'FALLO','criterio':'El nodo 500 pasa a FALLO por silencio (propuesta: 45 s con keep-alive de 30 s). No es alarma de fuego.'},
      hooks={'node':lambda nd,t,rng: 'silent' if (nd.id==c and S(22)<=t<S(22,3)) else None})

if __name__=='__main__':
    tot={}
    for nm,fn in [('fuego_lento',lambda: gen_fire('fuego_lento','slow')),('fuego_rapido',lambda: gen_fire('fuego_rapido','fast')),
                  ('polvo_tractor',gen_dust),('niebla',gen_fog),('sol_directo',gen_sun),('sos_boton',gen_sos),
                  ('fallo_congelado',gen_frozen),('fallo_ruido',gen_noise),('fallo_silencio',gen_silence)]:
        tot[nm]=fn(); print(nm,tot[nm])
