import csv, sys, time, resource
S=sys.argv[1]; t=time.perf_counter()
span={}; prev=None; switches=0; seen=set(); regroup=0; over24=0; rows=0
with open(f"{S}/stop_times.txt",newline="",encoding="utf-8-sig") as f:
    r=csv.reader(f); h=next(r); ti=h.index("trip_id"); ai=h.index("arrival_time"); di=h.index("departure_time")
    for row in r:
        rows+=1; tid=row[ti]
        if tid!=prev:
            if tid in seen: regroup+=1
            seen.add(tid); prev=tid
        a=row[ai] or row[di]; d=row[di] or row[ai]
        ha=int(a[:-6])*3600+int(a[-5:-3])*60+int(a[-2:]); hd=int(d[:-6])*3600+int(d[-5:-3])*60+int(d[-2:])
        if hd>=86400: over24+=1
        s=span.get(tid)
        if s is None: span[tid]=[ha,hd,1]
        else:
            if ha<s[0]: s[0]=ha
            if hd>s[1]: s[1]=hd
            s[2]+=1
print(f"rows={rows} trips={len(span)} time={time.perf_counter()-t:.1f}s maxRSS={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.0f}MB contiguous_by_trip={'yes' if regroup==0 else 'no ('+str(regroup)+' regroupings)'} stop_times>=24:00:00 rows={over24}")
late=sum(1 for s in span.values() if s[1]>=86400); print("trips ending after 24:00:",late, " max end h:",max(s[1] for s in span.values())/3600)
