"""Editable fitness goals with frozen revisions and source-specific projections."""
from collections import defaultdict
from datetime import date, timedelta
from math import isfinite, ceil
from statistics import median
import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from app import db
from app.models import Goal, NetWorthSnapshot
from app.body_composition import rows, CompositionRow
from app.gymday import GymExercise, GymSession, GymSessionExercise, GymSet

pages = Blueprint("goals_pages", __name__)
LIFTS = {
    "hack_squat": ("Hack Squat", "Machine Hack Squat"),
    "bench_press": ("Bench Press", "Barbell Bench Press"),
    "v_squat": ("V-Squat", "V Squat Machine"),
    "rdl": ("Romanian Deadlift", "Barbell Romanian Deadlift"),
    "hip_thrust": ("Hip Thrust Machine", "Machine Hip Thrust"),
    "incline_db": ("Incline Dumbbell Press", "Incline Dumbbell Bench Press"),
    "jm_press": ("JM Press", "Barbell JM Press"),
    "db_shoulder": ("DB Shoulder Press", "Dumbbell Shoulder Press"),
    "bb_row": ("Bent Over BB Row", "Bent Over Barbell Row"),
    "pull_ups": ("Pull Ups", "Pull Up", "Pull-Ups"),
    "hyperextensions": ("Hyperextensions", "Hyperextension", "Back Extension"),
}
SHAPES = ("Chest", "Bicep", "Bicep (flexed)", "Forearms", "Thigh", "Calf",
          "Butt", "Wrist", "Waist", "Neck", "Hips", "Shoulders")
BODY = {"weight": ("Body weight", "kg"), "fat": ("Body fat", "%"),
        "lean": ("Lean mass", "kg"), "ffmi": ("FFMI", "kg/m²")}


FINANCE = {"net_worth": ("Net Worth goal", "AUD"),
           "offset": ("Savings/Offset goal", "AUD"),
           "investing": ("Investing goal", "AUD")}
RATIOS = {
    "Shoulder to Waist": ("Shoulders", "Waist"),
    "Waist to Height": ("Waist", None),
    "Waist to Hip": ("Waist", "Hips"),
    "Forearm to Bicep": ("Forearms", "Bicep"),
    "Chest to Waist": ("Chest", "Waist"),
    "Chest to Hips": ("Chest", "Hips"),
    "Flexed Bicep to Calf": ("Bicep (flexed)", "Calf"),
    "Thigh to Waist": ("Thigh", "Waist"),
    "Calf to Thigh": ("Calf", "Thigh"),
    "Flexed Bicep to Chest": ("Bicep (flexed)", "Chest"),
    "Shoulder to Hips": ("Shoulders", "Hips"),
}


class GoalVersion(db.Model):
    __tablename__ = "goal_versions"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("goals.id"), nullable=False, unique=True)
    created_on = db.Column(db.Date, nullable=False)
    baseline = db.Column(db.Float)
    baseline_date = db.Column(db.Date)
    settings = db.Column(db.JSON, nullable=False)
    initial_forecast = db.Column(db.JSON)
    closed_on = db.Column(db.Date)
    outcome = db.Column(db.JSON)


def norm(v):
    return re.sub(r"[^a-z0-9]+", "", str(v or "").casefold())


def num(v):
    try:
        x = float(v)
        return x if not isinstance(v, bool) and isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def catalog():
    out = {k: (v[0],v[1],"composition") for k,v in BODY.items()}
    out.update({k:(v[0],"kg","strength") for k,v in LIFTS.items()})
    out.update({"shape_"+norm(n):(n,"cm","shape") for n in SHAPES})
    out.update({k:(v[0],v[1],"finance") for k,v in FINANCE.items()})
    out.update({"ratio_"+norm(n):(n,"ratio","shape") for n in RATIOS})
    return out


def parse_ideals(wb):
    """Parse Dashboard columns B/D/E by section headings; also support generic headers."""
    from app.body_composition import as_date
    name = next((n for n in wb.sheetnames if n.rstrip("!").casefold()=="dashboard"),None)
    if not name:
        return [], ["Dashboard worksheet not found."]
    ws=wb[name]
    grid=list(ws.iter_rows(max_row=min(ws.max_row or 200,200),
                           max_col=min(ws.max_column or 40,40),values_only=True))
    shape_labels={norm(n):n for n in SHAPES}
    shape_labels.update(biceps="Bicep",thighs="Thigh",calves="Calf",bicepsflexed="Bicep (flexed)")
    ratio_labels={norm(n):n for n in RATIOS}
    results={}
    conflicts=set()
    day=date.today()
    for row in grid:
        if len(row)>3 and norm(row[1])=="lastupdated":
            day=as_date(row[3]) or day
            break

    def record(key,label,target,current=None,operator="increase"):
        raw=str(target or "").strip()
        if raw.startswith(("<",">","≤","≥")):
            operator="decrease" if raw[0] in "<≤" else "increase"
            target=raw.lstrip("<>≤≥= ")
        value=num(target)
        observed=num(current)
        if value is None or not 0<value<=250:
            return
        payload=dict(name=label,target=value,current=observed,direction=operator,
                     source="Dashboard")
        if key in results and results[key][2]["target"]!=value:
            conflicts.add(key)
        else:
            results[key]=(day,key,payload)

    section=None
    for row in grid:
        if len(row)<5:
            continue
        label=norm(row[1])
        if label=="idealbodyshape":
            section="ratio"
            continue
        if label=="musclegoals":
            section="muscle"
            continue
        if label in ("keyindicators","weekstosixpack"):
            section=None
            continue
        if section=="ratio" and label in ratio_labels:
            n=ratio_labels[label]
            record("ratio_"+norm(n),n,row[3],row[4],"exact")
        elif section=="muscle" and label in shape_labels:
            n=shape_labels[label]
            record("shape_"+norm(n),n,row[3],row[4],"decrease" if n=="Waist" else "increase")
    if not results:
        for i,row in enumerate(grid):
            hdr=[norm(v) for v in row]
            for j,h in enumerate(hdr):
                if h not in ("ideal","idealcm","idealmeasurement","idealmeasurements","idealbodyshape"):
                    continue
                cols=[k for k,v in enumerate(hdr) if v in ("measurement","measurements","bodypart","metric")]
                if not cols and j:
                    cols=[j-1]
                current_col=next((k for k,v in enumerate(hdr) if v=="current"),None)
                for k in cols:
                    for r in grid[i+1:i+30]:
                        n=shape_labels.get(norm(r[k]))
                        if n:
                            record("shape_"+norm(n),n,r[j],r[current_col] if current_col is not None else None,
                                   "decrease" if n=="Waist" else "increase")
    notes=[]
    if conflicts:
        notes.append("Conflicting Dashboard targets omitted.")
    values=[v for k,v in results.items() if k not in conflicts]
    if not values:
        notes.append("Dashboard ideal layout not recognised; check cached formula values.")
    return values,notes


def exercises(key):
    names = {norm(n) for n in LIFTS[key]}
    return [e for e in GymExercise.query.order_by(GymExercise.name,GymExercise.id)
            if norm(e.name) in names]


def exercise_catalog(key):
    preferred={e.id for e in exercises(key)}
    return sorted(GymExercise.query.all(),key=lambda e:(e.id not in preferred,
                  (e.name or "").casefold(),e.id))


def proximity(current,target,direction):
    if current is None or target is None:
        return None
    if direction=="exact":
        return round(100*min(current/target,target/current),1) if current>0 and target>0 else None
    if direction=="decrease":
        if current<=target:
            return 100.0
        return round(max(0,min(100,100*target/current)),1) if target>0 and current>0 else None
    if current>=target:
        return 100.0
    if target>0:
        return round(max(0,100*current/target),1)
    return None


def financial_series(key,today):
    from app.offset_projection import offset_history
    from app.goal_finance import investment_history
    if key=="net_worth":
        return [(r.as_of_date,float(r.source_net_worth)) for r in
                NetWorthSnapshot.query.filter(NetWorthSnapshot.as_of_date<=today,
                    NetWorthSnapshot.source_net_worth.isnot(None)).order_by(NetWorthSnapshot.as_of_date)]
    if key=="offset":
        return [(date.fromisoformat(r["as_of"]),float(r["balance_aud"])) for r in
                offset_history().get("history",[]) if date.fromisoformat(r["as_of"])<=today]
    return investment_history(today)



def body_value(key,source,r,settings):
    w = num(r.get("Total Mass" if source=="dexa" else "Weight"))
    f = num(r.get({"manual":"Body Fat %","evolt":"Total Body Fat Percentage","dexa":"Tissue % Fat"}[source]))
    if key=="weight":
        return w
    if key=="fat":
        return f if f is not None and 0<f<100 else None
    if source=="dexa":
        fm = num(r.get("Fat Mass"))
        ffm = w-fm if w is not None and fm is not None else None
        lean = num(r.get("Lean Mass"))
    else:
        ffm = w*(1-f/100) if w and f is not None and 0<f<100 else None
        lean = ffm
    if key=="lean":
        return lean
    h = num(settings.get("height_cm"))
    return ffm/(h/100)**2 if ffm and h and 100<=h<=250 else None


def series(key,settings,today=None):
    today = today or date.today()
    if key in FINANCE:
        return financial_series(key,today)
    data = defaultdict(list)
    if key in LIFTS:
        q = db.session.query(GymSession.local_date,GymSet.weight_kg,GymSet.reps).join(
            GymSessionExercise,GymSessionExercise.id==GymSet.session_exercise_id).join(
            GymSession,GymSession.id==GymSessionExercise.session_id).filter(
            GymSessionExercise.exercise_id==settings.get("exercise_id"),
            GymSession.active.is_(True),GymSet.complete.is_(True),GymSet.warmup.is_(False),
            GymSet.drop_set.is_(False),GymSession.local_date<=today)
        for d,w,r in q.all():
            w,r = num(w),num(r)
            if r is None or r<=0:
                continue
            if settings.get("mode")=="reps":
                if w==0:
                    data[d].append(r)
            elif w is not None and w>=0 and r>=settings.get("reps",6):
                data[d].append(w)
    else:
        source = settings.get("source","manual")
        for r in rows(source,end=today):
            if key.startswith("ratio_"):
                label=catalog()[key][0]
                a,b=RATIOS[label]
                numerator=num(r.get(a))
                denominator=num(r.get(b)) if b else num(settings.get("height_cm"))
                v=numerator/denominator if numerator is not None and denominator and denominator>0 else None
            else:
                v = body_value(key,source,r,settings) if key in BODY else num(r.get(catalog()[key][0]))
            if v is not None and 0<v<1000:
                data[date.fromisoformat(r["date"])].append(v)
    return [(d,max(v) if key in LIFTS else median(v)) for d,v in sorted(data.items())]


def completion(b,c,t,direction):
    if b is None or c is None:
        return None
    sign = 1 if direction=="increase" else -1
    if sign*(c-t)>=0:
        return 100.0
    return round(max(0,min(100,100*(c-b)/(t-b))),1) if sign*(t-b)>0 else 0.0


def forecast(points,target,direction,key,today=None):
    today = today or date.today()
    if not points:
        return {"status":"insufficient_data"}
    last,current = points[-1]
    sign = 1 if direction=="increase" else -1
    fast = key=="weight" or key in LIFTS
    if (today-last).days>(21 if fast else 90):
        return {"status":"stale"}
    if sign*(target-current)<=0:
        return {"status":"achieved","date":last.isoformat()}
    window = 56 if key=="weight" else 84 if key in LIFTS else 180
    pts = [(d,v) for d,v in points if (last-d).days<=window]
    if len(pts)<4 or (pts[-1][0]-pts[0][0]).days<(21 if fast else 60):
        return {"status":"insufficient_data"}
    slopes = [sign*(b-a)/(e-d).days for i,(d,a) in enumerate(pts)
              for e,b in pts[i+1:] if (e-d).days>=7]
    pace = median(slopes) if slopes else 0
    if pace<=0:
        return {"status":"not_progressing"}
    if key=="weight":
        pace = min(pace,current*.01/7)
    days = ceil(sign*(target-current)/pace)
    if days>365 or last+timedelta(days=days)<=today:
        return {"status":"no_reliable_eta"}
    return {"status":"estimated","date":(last+timedelta(days=days)).isoformat(),
            "early":max(today,last+timedelta(days=ceil(days*.75))).isoformat(),
            "late":(last+timedelta(days=ceil(days*1.5))).isoformat(),
            "pace_week":round(pace*7,3),"samples":len(pts)}


def active(key):
    return Goal.query.filter_by(module="fitness_goals",metric_key=key,status="active").order_by(Goal.id.desc()).first()


def version(g):
    return GoalVersion.query.filter_by(goal_id=g.id).one()


def snapshot(g,m,points=None):
    points = series(g.metric_key,m.settings) if points is None else points
    # If configured before first import, anchor to first observation on/after creation.
    baseline = m.baseline
    baseline_date = m.baseline_date
    if baseline is None:
        first = next(((d,v) for d,v in points if d>=m.created_on),None)
        if first:
            baseline_date,baseline = first
    current = points[-1][1] if points else None
    t = float(g.target)
    pct = completion(baseline,current,t,g.direction)
    near = proximity(current,t,g.direction)
    progress = [completion(baseline,v,t,g.direction) for d,v in points if d>=m.created_on]
    valid = [v for v in progress+[pct] if v is not None]
    sign = 1 if g.direction=="increase" else -1
    reached = [d for d,v in points if d>=m.created_on and sign*(v-t)>=0]
    return dict(id=g.id,key=g.metric_key,target=t,current=current,baseline=baseline,
                baseline_date=baseline_date.isoformat() if baseline_date else None,
                created=m.created_on.isoformat(),current_date=points[-1][0].isoformat() if points else None,
                direction=g.direction,unit=g.unit,completion=pct,proximity=near,
                best_completion=max(valid) if valid else None,
                first_achieved=reached[0].isoformat() if reached else None,
                due=g.due_date.isoformat() if g.due_date else None,settings=m.settings,
                initial_forecast=m.initial_forecast,forecast=forecast(points,t,g.direction,g.metric_key),
                points=[dict(date=d.isoformat(),value=round(v,3)) for d,v in points[-120:]])


def close(g,reason,note):
    m = version(g)
    s = snapshot(g,m)
    if reason=="achieved" and s["completion"]!=100:
        raise ValueError("Current evidence does not meet target.")
    m.closed_on = date.today()
    s.update(outcome=reason,note=note,closed=m.closed_on.isoformat(),duration=(m.closed_on-m.created_on).days)
    m.outcome = s
    g.status = reason


def save(form):
    key = form.get("key")
    if key not in catalog():
        raise ValueError("Unsupported goal.")
    old = active(key)
    if form.get("version_id","")!=str(old.id if old else ""):
        raise ValueError("Goal changed; reload before editing.")
    action = form.get("action","save")
    note = str(form.get("note",""))[:500]
    if action in ("achieved","paused","abandoned"):
        if not old:
            raise ValueError("No active goal.")
        close(old,action,note)
        db.session.commit()
        return
    if action!="save":
        raise ValueError("Invalid action.")
    target = num(form.get("target"))
    direction = form.get("direction","increase")
    if target is None or (key not in FINANCE and not 0<target<=1000) or (key in FINANCE and (abs(target)>1e10 or (key!="net_worth" and target<=0))) or (key=="fat" and target>=100):
        raise ValueError("Invalid positive target.")
    if direction not in ("increase","decrease"):
        raise ValueError("Invalid direction.")
    settings = {}
    unit = catalog()[key][1]
    if key.startswith("ratio_") or key.startswith("shape_"):
        raise ValueError("Edit workbook-managed ideals in Body Composition.xlsx and refresh.")
    if key in FINANCE:
        settings["source"]="financial_workbook"
    elif key in LIFTS:
        eid = form.get("exercise_id")
        if not eid or db.session.get(GymExercise,eid) is None:
            raise ValueError("Select the matching GymDay exercise.")
        mode = form.get("mode","weight") if key=="pull_ups" else "weight"
        reps = num(form.get("reps",6))
        if mode not in ("weight","reps") or reps is None or not 1<=reps<=30 or reps!=int(reps):
            raise ValueError("Invalid lift mode or repetitions.")
        if mode=="reps":
            if target!=int(target):
                raise ValueError("Rep target must be an integer.")
            unit="reps"
        settings.update(exercise_id=eid,mode=mode,reps=int(reps))
    else:
        source = form.get("source","manual") if key in BODY else "manual"
        if source not in ("manual","evolt","dexa"):
            raise ValueError("Invalid source.")
        settings["source"]=source
        if key=="ffmi":
            h=num(form.get("height_cm"))
            if h is None or not 100<=h<=250:
                raise ValueError("Enter height in cm.")
            settings["height_cm"]=h
    due = date.fromisoformat(form["due"]) if form.get("due") else None
    points = series(key,settings)
    if old:
        close(old,"revised",note)
    g=Goal(module="fitness_goals",metric_key=key,target=target,unit=unit,
           due_date=due,direction=direction,status="active")
    db.session.add(g)
    db.session.flush()
    db.session.add(GoalVersion(goal_id=g.id,created_on=date.today(),
        baseline=points[-1][1] if points else None,baseline_date=points[-1][0] if points else None,
        settings=settings,initial_forecast=forecast(points,target,direction,key)))
    db.session.commit()


def report():
    groups={"finance":[],"composition":[],"strength":[],"shape":[]}
    ideals={r.row_key:r for r in CompositionRow.query.filter_by(source="ideals")}
    for key,(name,unit,group) in catalog().items():
        g=active(key)
        ideal=ideals.get(key)
        item=dict(key=key,name=name,unit=unit,ideal=ideal.payload.get("target") if ideal else None,
                  active=snapshot(g,version(g)) if g else None)
        if group=="shape":
            # Workbook values are authoritative and update on each sync; no DB goal
            # mutation or automatic history revision on observation refresh.
            if ideal:
                payload=ideal.payload
                current=payload.get("current")
                settings={"source":"manual","height_cm":num(current_app.config.get("GOAL_HEIGHT_CM"))}
                pts=series(key,settings)
                if current is None and pts:
                    current=pts[-1][1]
                direction=payload.get("direction","increase")
                item.update(workbook=True,current=current,current_date=ideal.observed_on.isoformat(),
                            proximity=proximity(current,item["ideal"],direction),direction=direction)
            else:
                pts=series(key,{"source":"manual","height_cm":num(current_app.config.get("GOAL_HEIGHT_CM"))})
                item.update(workbook=True,current=pts[-1][1] if pts else None,
                            current_date=pts[-1][0].isoformat() if pts else None,proximity=None)
            groups[group].append(item)
            continue
        if key in LIFTS:
            candidates=exercises(key)
            item["exercises"]=[dict(id=e.id,name=e.name,equipment=e.equipment) for e in exercise_catalog(key)]
            if len(candidates)==1:
                item["suggested_exercise"]=candidates[0].id
            pts=series(key,{"exercise_id":item.get("suggested_exercise"),
                            "mode":"reps" if key=="pull_ups" else "weight","reps":6})
            if key=="pull_ups" and not g:
                item["unit"]="reps"
        elif key in FINANCE:
            pts=series(key,{})
        else:
            settings={"source":"manual","height_cm":num(current_app.config.get("GOAL_HEIGHT_CM"))}
            pts=series(key,settings)
        item.update(current=pts[-1][1] if pts else None,current_date=pts[-1][0].isoformat() if pts else None)
        if not g and key in ("weight","fat"):
            item["ideal"]=num(current_app.config.get("BODY_WEIGHT_GOAL_KG" if key=="weight" else "BODY_FAT_GOAL_PCT"))
        groups[group].append(item)
    scores={}
    count=measured=achieved=0
    for k,items in groups.items():
        values=[v for i in items if (v:=i.get("proximity") if k=="shape" else
                i["active"].get("proximity") if i["active"] else None) is not None]
        count+=sum(bool(i.get("ideal") is not None) if k=="shape" else bool(i["active"]) for i in items)
        measured+=len(values)
        achieved+=values.count(100)
        scores[k]=round(sum(values)/len(values),1) if values else None
    valid=[v for v in scores.values() if v is not None]
    hist=[m.outcome for m in GoalVersion.query.filter(GoalVersion.closed_on.isnot(None)).order_by(GoalVersion.id.desc()) if m.outcome]
    hv=[x["completion"] for x in hist if x["completion"] is not None]
    return dict(groups=groups,scores=scores,overall=round(sum(valid)/len(valid),1) if valid else None,
                configured=count,measured=measured,achieved=achieved,history=hist,
                history_average=round(sum(hv)/len(hv),1) if hv else None,
                history_achieved=hv.count(100),labels={k:v[0] for k,v in catalog().items()})


@pages.route("/goals",methods=["GET","POST"])
def goals_page():
    if request.method=="POST":
        try:
            save(request.form)
        except (ValueError,OverflowError) as exc:
            db.session.rollback()
            flash(str(exc),"error")
        else:
            flash("Goal saved. History retained.","success")
        return redirect(url_for("goals_pages.goals_page"))
    return render_template("goals.html",title="Goals",section="goals",report=report())
