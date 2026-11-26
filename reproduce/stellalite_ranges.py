import bisect,math

def stage_groups(rows):
    values=[r['difficulty'] for r in rows]
    # Fixed ability increments through the main distribution. Above its 90th
    # percentile, smoothly widen steps rather than making a long sparse ladder.
    tail=values[int(.9*(len(values)-1))]
    start=math.floor(values[0]/.155)*.155
    edges=[start]; nominal=start
    while nominal<=values[-1]:
        width=.155*(1+.6*max(0,nominal-tail))
        nominal+=width
        # Snap within 20% of a step to the largest adjacent-score gap. Only
        # adjust for a meaningful gap; never split identical score estimates.
        lo,hi=nominal-.2*width,nominal+.2*width
        gaps=[(b-a,(a+b)/2) for a,b in zip(values,values[1:]) if lo<=(a+b)/2<=hi and b-a>=.01]
        edge=max(gaps,key=lambda g:(g[0],-abs(g[1]-nominal)))[1] if gaps else nominal
        edges.append(round(edge,8))
    if edges[-1]<=values[-1]:edges.append(round(values[-1]+.155,8))
    groups=[]
    for lo,hi in zip(edges,edges[1:]):
        group=rows[bisect.bisect_left(values,lo):bisect.bisect_left(values,hi)]
        if group:groups.append((lo,hi,group))
    return groups,tail
