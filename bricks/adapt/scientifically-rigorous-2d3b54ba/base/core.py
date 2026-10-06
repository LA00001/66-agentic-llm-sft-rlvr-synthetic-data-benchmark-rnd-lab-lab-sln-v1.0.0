from __future__ import annotations
from math import erf, sqrt
import pandas as pd

def _norm_cdf(z: float) -> float:
    return 0.5*(1.0+erf(z/sqrt(2.0)))

def analyze(df: pd.DataFrame, days: int=7, region: str|None=None, device: str|None=None) -> dict:
    latest=pd.to_datetime(df["date"]).max(); start=latest-pd.Timedelta(days=days-1)
    x=df.loc[pd.to_datetime(df["date"])>=start].copy()
    if region: x=x.loc[x["region"]==region]
    if device: x=x.loc[x["device"]==device]
    vals={}
    for variant in ["control","treatment"]:
        s=x.loc[x["experiment"]==variant]
        vals[variant]={"n":int(len(s)),"success":int(s["converted"].sum())}
        vals[variant]["rate"]=vals[variant]["success"]/max(vals[variant]["n"],1)
    c,t=vals["control"],vals["treatment"]
    p_pool=(c["success"]+t["success"])/max(c["n"]+t["n"],1)
    se=sqrt(max(p_pool*(1-p_pool)*(1/max(c["n"],1)+1/max(t["n"],1)),1e-16))
    diff=t["rate"]-c["rate"]; z=diff/se; p=2*(1-_norm_cdf(abs(z)))
    se_unpooled=sqrt(max(c["rate"]*(1-c["rate"])/max(c["n"],1)+t["rate"]*(1-t["rate"])/max(t["n"],1),1e-16))
    ci=(diff-1.96*se_unpooled,diff+1.96*se_unpooled)
    expected=(c["n"]+t["n"])/2
    srm=((c["n"]-expected)**2/max(expected,1))+((t["n"]-expected)**2/max(expected,1))
    srm_p=1-_norm_cdf(sqrt(max(srm,0)))  # conservative 1-df approximation for demo
    verdict="ROLLBACK" if p<0.05 and diff<0 else ("SHIP" if p<0.05 and diff>0 else "INCONCLUSIVE")
    return {"window_days":days,"region":region,"device":device,"control":{"n":c["n"],"conversion":round(c["rate"],5)},"treatment":{"n":t["n"],"conversion":round(t["rate"],5)},"absolute_uplift_pp":round(diff*100,3),"relative_uplift_pct":round(diff/max(c["rate"],1e-9)*100,2),"z":round(z,3),"p_value":round(p,6),"ci95_pp":[round(ci[0]*100,3),round(ci[1]*100,3)],"srm_p_value":round(srm_p,6),"significant":bool(p<0.05),"verdict":verdict}
