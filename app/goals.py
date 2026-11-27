"""Editable fitness goals with frozen revisions and source-specific projections."""
from collections import defaultdict
from datetime import date, timedelta
from math import isfinite, ceil
from statistics import median
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from app import db
from app.models import Goal
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
    return out


def parse_ideals(wb):
    name = next((n for n in wb.sheetnames if n.rstrip("!").casefold()=="dashboard"),None)
    if not name:
        return [], []
    ws = wb[name]
    grid = list(ws.iter_rows(max_row=min(ws.max_row or 200,200),
                            max_col=min(ws.max_column or 40,40),values_only=True))
    labels = {norm(n):n for n in SHAPES}
    labels.update(biceps="Bicep", thighs="Thigh", calves="Calf", bicepsflexed="Bicep (flexed)")
    found = defaultdict(set)
    for i,row in enumerate(grid):
        hdr = [norm(v) for v in row]
        for j,h in enumerate(hdr):
            if h not in ("ideal","idealcm","idealmeasurement","idealmeasurements","idealbodyshape"):
                continue
            cols = [k for k,v in enumerate(hdr) if v in ("measurement","measurements","bodypart","metric")]
            if not cols and j:
                cols = [j-1]
            for k in cols:
                for r in grid[i+1:i+30]:
                    label, value = labels.get(norm(r[k])),num(r[j])
                    if label and value is not None and 0<value<=250:
                        found[label].add(value)
    result = [(date.today(),"shape_"+norm(n),{"name":n,"target":next(iter(v))})
              for n,v in found.items() if len(v)==1]
    notes = [] if result else ["Dashboard ideal layout not recognised; configure targets manually."]
    if any(len(v)>1 for v in found.values()):
        notes.append("Conflicting Dashboard ideal targets omitted.")
    return result,notes


def exercises(key):
    names = {norm(n) for n in LIFTS[key]}
    return [e for e in GymExercise.query.order_by(GymExercise.name,GymExercise.id)
            if norm(e.name) in names]


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
    progress = [completion(baseline,v,t,g.direction) for d,v in points if d>=m.created_on]
    valid = [v for v in progress+[pct] if v is not None]
    sign = 1 if g.direction=="increase" else -1
    reached = [d for d,v in points if d>=m.created_on and sign*(v-t)>=0]
    return dict(id=g.id,key=g.metric_key,target=t,current=current,baseline=baseline,
                baseline_date=baseline_date.isoformat() if baseline_date else None,
                created=m.created_on.isoformat(),current_date=points[-1][0].isoformat() if points else None,
                direction=g.direction,unit=g.unit,completion=pct,
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
    if target is None or not 0<target<=1000 or (key=="fat" and target>=100):
        raise ValueError("Invalid positive target.")
    if direction not in ("increase","decrease"):
        raise ValueError("Invalid direction.")
    settings = {}
    unit = catalog()[key][1]
    if key in LIFTS:
        eid = form.get("exercise_id")
        if eid not in {e.id for e in exercises(key)}:
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
    groups={"composition":[],"strength":[],"shape":[]}
    ideals={r.row_key:r.payload.get("target") for r in CompositionRow.query.filter_by(source="ideals")}
    for key,(name,unit,group) in catalog().items():
        g=active(key)
        item=dict(key=key,name=name,unit=unit,ideal=ideals.get(key),active=snapshot(g,version(g)) if g else None)
        if key in LIFTS:
            item["exercises"]=[dict(id=e.id,name=e.name,equipment=e.equipment) for e in exercises(key)]
        groups[group].append(item)
    scores={}
    count=measured=achieved=0
    for k,items in groups.items():
        values=[i["active"]["completion"] for i in items if i["active"] and i["active"]["completion"] is not None]
        count+=sum(bool(i["active"]) for i in items)
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
