from flask import current_app as app, render_template, request, redirect, url_for, flash, jsonify
from . import db
from .models import Team, Player, Match, MatchAssignment, Invite
from .utils import shuffle_players_list, balance_teams, make_token
from datetime import datetime

# Home
@app.route("/")
def index():
    teams = Team.query.order_by(Team.name).all()
    matches = Match.query.order_by(Match.created_at.desc()).all()
    open_matches = [m for m in matches if (not m.team1_id) or (not m.team2_id)]
    return render_template("index.html", teams=teams, matches=matches, open_matches=open_matches)

# -------------------------
# Team creation & detail
# -------------------------
@app.route("/teams/create", methods=["GET", "POST"])
def create_team():
    if request.method == "POST":
        name = request.form.get("name")
        color = request.form.get("color")
        skill = int(request.form.get("skill") or 1200)
        captain_name = request.form.get("captain_name") or None

        team = Team(name=name, color=color, skill_rating=skill)
        db.session.add(team)
        db.session.commit()

        if captain_name:
            captain = Player(name=captain_name, role="Captain", skill_rating=skill, team_id=team.id)
            db.session.add(captain)
            db.session.commit()
            team.captain_id = captain.id
            db.session.commit()

        flash("Team created", "success")
        return redirect(url_for("index"))
    return render_template("create_team.html")

@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    team = Team.query.get_or_404(team_id)
    return render_template("team_detail.html", team=team)

# manual add player to team
@app.route("/teams/<int:team_id>/add_player", methods=["POST"])
def team_add_player(team_id):
    team = Team.query.get_or_404(team_id)
    name = request.form.get("name")
    email = request.form.get("email") or None
    role = request.form.get("role") or None
    skill = int(request.form.get("skill") or 1200)
    if not name:
        flash("Player name required", "danger")
        return redirect(url_for("team_detail", team_id=team_id))
    p = Player(name=name, email=email, role=role, skill_rating=skill, team_id=team.id, invited=False)
    db.session.add(p); db.session.commit()
    flash("Player added", "success")
    return redirect(url_for("team_detail", team_id=team_id))

# invite player to a team (creates Invite row and shows a token / page)
@app.route("/teams/<int:team_id>/invite", methods=["GET","POST"])
def team_invite(team_id):
    team = Team.query.get_or_404(team_id)
    if request.method == "POST":
        invited_name = request.form.get("name") or None
        email = request.form.get("email") or None
        token = make_token(12)
        inv = Invite(token=token, context_type="team", context_id=team.id, email=email, invited_name=invited_name)
        db.session.add(inv); db.session.commit()
        # In production you'd email the token link; for MVP we just display a page with the link
        accept_url = url_for("accept_invite", token=token, _external=True)
        return render_template("invite_sent.html", invite=inv, accept_url=accept_url, team=team)
    return render_template("invite_sent.html", team=team, invite=None)

# -------------------------
# Matches: create, detail, join
# -------------------------
@app.route("/matches/create", methods=["GET","POST"])
def create_match():
    teams = Team.query.order_by(Team.name).all()
    if request.method == "POST":
        sport = request.form.get("sport") or "soccer"
        location = request.form.get("location")
        date_raw = request.form.get("date") or None
        team1_id = request.form.get("team1_id") or None
        team2_id = request.form.get("team2_id") or None
        stakes = float(request.form.get("stakes") or 0.0)

        m = Match(sport=sport, location=location, stakes=stakes)
        if team1_id:
            m.team1_id = int(team1_id)
        if team2_id:
            m.team2_id = int(team2_id)
        if date_raw:
            try:
                m.date = datetime.fromisoformat(date_raw)
            except Exception:
                m.date = None
        db.session.add(m); db.session.commit()
        flash("Match created", "success")
        return redirect(url_for("index"))
    return render_template("create_match.html", teams=teams)

@app.route("/matches/<int:match_id>")
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)
    # pool: players from team1 and team2 (if present), plus any standalone players
    pool = []
    if match.team1_id:
        pool += Player.query.filter_by(team_id=match.team1_id).all()
    if match.team2_id:
        pool += Player.query.filter_by(team_id=match.team2_id).all()
    # assigned players:
    assignments = MatchAssignment.query.filter_by(match_id=match.id).all()
    assigned_a = [a.player for a in assignments if a.team_side == 'A']
    assigned_b = [a.player for a in assignments if a.team_side == 'B']
    locked = (match.status == "locked")
    return render_template("match_detail.html", match=match, pool=pool, assigned_a=assigned_a, assigned_b=assigned_b, locked=locked)

# invite team to match (creates Invite linking to match)
@app.route("/matches/<int:match_id>/invite_team", methods=["POST"])
def invite_team_to_match(match_id):
    match = Match.query.get_or_404(match_id)
    team_id = request.form.get("team_id")
    token = make_token(12)
    inv = Invite(token=token, context_type="match", context_id=match.id, email=None, invited_name=None)
    db.session.add(inv); db.session.commit()
    accept_url = url_for("accept_invite", token=token, _external=True)
    flash(f"Invite created. Share this link to accept: {accept_url}", "info")
    return redirect(url_for("match_detail", match_id=match.id))

# accept invite via token (either join team or accept match invite)
@app.route("/invite/<token>", methods=["GET","POST"])
def accept_invite(token):
    inv = Invite.query.filter_by(token=token).first_or_404()
    if request.method == "POST":
        # user provides a name (and optional email) to accept
        name = request.form.get("name")
        email = request.form.get("email") or None
        if inv.context_type == "team":
            # add player into the team
            p = Player(name=name or inv.invited_name or "Guest", email=email, invited=False, team_id=inv.context_id)
            db.session.add(p); db.session.commit()
            inv.accepted = True; db.session.commit()
            flash("You joined the team!", "success")
            return redirect(url_for("team_detail", team_id=inv.context_id))
        else:
            # match invite - join as a player assigned to match pool (we create a player w/o team)
            p = Player(name=name or "Guest", email=email, invited=False, team_id=None)
            db.session.add(p); db.session.commit()
            # create assignment on the match (unassigned side: 'A' or 'B' chosen later)
            # For simplicity, add assignment with team_side = 'A' by default (captain can reassign)
            ma = MatchAssignment(match_id=inv.context_id, player_id=p.id, team_side='A')
            db.session.add(ma)
            inv.accepted = True; db.session.commit()
            flash("You joined the match pool!", "success")
            return redirect(url_for("match_detail", match_id=inv.context_id))
    # GET: render accept form
    return render_template("invite_accept.html", invite=inv)

# open challenge join (team fills a blank slot)
@app.route("/matches/<int:match_id>/join/<int:team_id>", methods=["POST"])
def join_open_match(match_id, team_id):
    match = Match.query.get_or_404(match_id)
    if match.status == "locked":
        flash("Match is locked", "danger"); return redirect(url_for("match_detail", match_id=match_id))
    if not match.team1_id:
        match.team1_id = team_id
    elif not match.team2_id:
        match.team2_id = team_id
    else:
        flash("Both slots filled", "danger")
        return redirect(url_for("match_detail", match_id=match_id))
    db.session.commit()
    flash("Team joined the match", "success")
    return redirect(url_for("match_detail", match_id=match_id))

# -------------------------
# Balancing & shuffle endpoints (AJAX-friendly JSON)
# -------------------------
@app.route("/matches/<int:match_id>/auto_balance", methods=["POST"])
def match_auto_balance(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status == "locked":
        return jsonify({"error": "match locked"}), 400
    pool = []
    if match.team1_id:
        pool += Player.query.filter_by(team_id=match.team1_id).all()
    if match.team2_id:
        pool += Player.query.filter_by(team_id=match.team2_id).all()
    if not pool:
        pool = Player.query.all()
    team_a, team_b = balance_teams(pool)
    # remove old assignments for match
    MatchAssignment.query.filter_by(match_id=match.id).delete()
    db.session.commit()
    for p in team_a:
        db.session.add(MatchAssignment(match_id=match.id, player_id=p.id, team_side='A'))
    for p in team_b:
        db.session.add(MatchAssignment(match_id=match.id, player_id=p.id, team_side='B'))
    db.session.commit()
    return jsonify({"team_a":[p.name for p in team_a],"team_b":[p.name for p in team_b]})

@app.route("/matches/<int:match_id>/shuffle", methods=["POST"])
def match_shuffle(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status == "locked": return jsonify({"error":"match locked"}), 400
    pool = []
    if match.team1_id:
        pool += Player.query.filter_by(team_id=match.team1_id).all()
    if match.team2_id:
        pool += Player.query.filter_by(team_id=match.team2_id).all()
    if not pool:
        pool = Player.query.all()
    a, b = shuffle_players_list(pool)
    MatchAssignment.query.filter_by(match_id=match.id).delete()
    db.session.commit()
    for p in a:
        db.session.add(MatchAssignment(match_id=match.id, player_id=p.id, team_side='A'))
    for p in b:
        db.session.add(MatchAssignment(match_id=match.id, player_id=p.id, team_side='B'))
    db.session.commit()
    return jsonify({"team_a":[p.name for p in a],"team_b":[p.name for p in b]})

@app.route("/matches/<int:match_id>/toggle_lock", methods=["POST"])
def match_toggle_lock(match_id):
    match = Match.query.get_or_404(match_id)
    # require at least one assignment to lock
    if match.status == "locked":
        match.status = "pending"
    else:
        if not MatchAssignment.query.filter_by(match_id=match.id).count():
            return jsonify({"error":"no assignments to lock"}), 400
        match.status = "locked"
    db.session.commit()
    return jsonify({"status":match.status})

# manual assignment (AJAX POST) - assign/remove players to side
@app.route("/matches/<int:match_id>/assign", methods=["POST"])
def match_assign_player(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status == "locked":
        return jsonify({"error":"match locked"}), 400
    player_id = int(request.form.get("player_id"))
    side = request.form.get("team_side")  # 'A' or 'B', or 'remove'
    if request.form.get("remove") == "1" or side == "remove":
        MatchAssignment.query.filter_by(match_id=match.id, player_id=player_id).delete()
        db.session.commit()
        return jsonify({"ok":True})
    # remove existing then add
    MatchAssignment.query.filter_by(match_id=match.id, player_id=player_id).delete()
    db.session.commit()
    ma = MatchAssignment(match_id=match.id, player_id=player_id, team_side=side)
    db.session.add(ma); db.session.commit()
    return jsonify({"ok":True})
