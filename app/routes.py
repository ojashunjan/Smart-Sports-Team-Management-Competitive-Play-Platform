from flask import current_app as app, render_template, request, redirect, url_for, flash, jsonify
from . import db
from .models import Team, Player, Match, MatchAssignment, Invite, PlayerSkill
from .utils import shuffle_players_list, balance_teams, make_token
from datetime import datetime

# -------------------------
# Helper: sport -> skill fields
# -------------------------
def skill_fields_for_sport(sport):
    mapping = {
        "soccer": ["Shooting", "Passing", "Defending", "Speed", "Stamina"],
        "basketball": ["Shooting", "Dribbling", "Defense", "Passing", "Rebounding"],
        "volleyball": ["Serving", "Spiking", "Blocking", "Setting", "Passing"],
        "hockey": ["Shooting", "Skating", "Defense", "Checking", "Passing"],
        "football": ["Throwing", "Catching", "Tackling", "Speed", "Awareness"],
        "default": ["Skill A", "Skill B", "Skill C", "Skill D", "Skill E"]
    }
    if not sport:
        return mapping["default"]
    return mapping.get(sport.lower(), mapping["default"])

# -------------------------
# Helper: recalculate team skill rating
# -------------------------
def recalc_team_skill(team):
    """
    Recalculate team's average skill rating as:
    average of all PlayerSkill.value across all players in the team.
    If no PlayerSkill rows, fallback to average of player.skill_rating values
    or the default 1200.
    """
    players = Player.query.filter_by(team_id=team.id).all()
    total = 0
    count = 0
    for p in players:
        for s in p.skills:
            total += s.value
            count += 1
    if count > 0:
        team.skill_rating = int(round(total / count))
        db.session.add(team)
        db.session.commit()
        return team.skill_rating
    if players:
        team.skill_rating = int(round(sum((p.skill_rating or 1200) for p in players) / len(players)))
        db.session.add(team)
        db.session.commit()
        return team.skill_rating
    team.skill_rating = team.skill_rating or 1200
    db.session.add(team)
    db.session.commit()
    return team.skill_rating

# -------------------------
# Home
# -------------------------
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
        sport = request.form.get("sport") or "soccer"

        team = Team(name=name, color=color, skill_rating=skill, sport=sport)
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
    skill_names = skill_fields_for_sport(team.sport)
    players = team.players
    return render_template("team_detail.html", team=team, players=players, skill_names=skill_names)

# -------------------------
# Add player to team
# -------------------------
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

    # Create player
    p = Player(name=name, email=email, role=role, skill_rating=skill, team_id=team.id, invited=False)
    db.session.add(p)
    db.session.commit()

    # Save PlayerSkill values
    skill_names = skill_fields_for_sport(team.sport)
    any_skill_saved = False
    canonical_keys = {f"skill_{sn.replace(' ','_')}" for sn in skill_names}

    for sname in skill_names:
        key = f"skill_{sname.replace(' ','_')}"
        val = request.form.get(key)
        if val is None or val == "":
            continue
        try:
            v = int(val)
        except Exception:
            continue
        ps = PlayerSkill(player_id=p.id, sport=(team.sport.lower() if team.sport else "unknown"), name=sname, value=v)
        db.session.add(ps)
        any_skill_saved = True

    # Also save arbitrary skill_* fields
    for key in request.form:
        if key.startswith("skill_") and key not in canonical_keys:
            v_raw = request.form.get(key)
            if v_raw is None or v_raw == "":
                continue
            try:
                v = int(v_raw)
            except Exception:
                continue
            name_from_key = key[len("skill_"):].replace("_", " ")
            ps = PlayerSkill(player_id=p.id, sport=(team.sport.lower() if team.sport else "unknown"), name=name_from_key, value=v)
            db.session.add(ps)
            any_skill_saved = True

    db.session.commit()

    # --- NEW: Recalculate player skill_rating from PlayerSkill ---
    player_skills = PlayerSkill.query.filter_by(player_id=p.id).all()
    if player_skills:
        avg_skill = sum(s.value for s in player_skills) / len(player_skills)
        p.skill_rating = int(round(avg_skill))
        db.session.add(p)
        db.session.commit()

    # Recalculate team skill rating
    recalc_team_skill(team)

    flash("Player added", "success")
    return redirect(url_for("team_detail", team_id=team_id))

# -------------------------
# Edit player
# -------------------------
@app.route("/players/<int:player_id>/edit", methods=["GET", "POST"])
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    team = player.team
    sport = team.sport if team else None
    skill_names = skill_fields_for_sport(sport)

    if request.method == "POST":
        player.name = request.form.get("name") or player.name
        player.email = request.form.get("email") or player.email
        player.role = request.form.get("role") or player.role
        db.session.add(player)
        db.session.commit()

        # Delete old skills
        PlayerSkill.query.filter_by(player_id=player.id).delete()
        db.session.commit()

        canonical_keys = {f"skill_{sn.replace(' ','_')}" for sn in skill_names}
        for sname in skill_names:
            key = f"skill_{sname.replace(' ','_')}"
            val = request.form.get(key)
            if val is None or val == "":
                continue
            try:
                v = int(val)
            except Exception:
                continue
            ps = PlayerSkill(player_id=player.id, sport=(sport.lower() if sport else "unknown"), name=sname, value=v)
            db.session.add(ps)

        for key in request.form:
            if key.startswith("skill_") and key not in canonical_keys:
                v_raw = request.form.get(key)
                if v_raw is None or v_raw == "":
                    continue
                try:
                    v = int(v_raw)
                except Exception:
                    continue
                name_from_key = key[len("skill_"):].replace("_", " ")
                ps = PlayerSkill(player_id=player.id, sport=(sport.lower() if sport else "unknown"), name=name_from_key, value=v)
                db.session.add(ps)

        db.session.commit()

        # --- NEW: Recalculate player skill_rating from PlayerSkill ---
        player_skills = PlayerSkill.query.filter_by(player_id=player.id).all()
        if player_skills:
            avg_skill = sum(s.value for s in player_skills) / len(player_skills)
            player.skill_rating = int(round(avg_skill))
        else:
            player.skill_rating = 1200
        db.session.add(player)
        db.session.commit()

        # Recalculate team skill rating
        if team:
            recalc_team_skill(team)

        flash("Player updated", "success")
        if team:
            return redirect(url_for("team_detail", team_id=team.id))
        return redirect(url_for("index"))

    # GET
    existing_skills = {s.name: s.value for s in player.skills}
    return render_template("edit_player.html", player=player, team=team, skill_names=skill_names, existing_skills=existing_skills)

# -------------------------
# Delete player
# -------------------------
@app.route("/player/<int:player_id>/delete", methods=["POST", "GET"])
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)
    team = player.team

    PlayerSkill.query.filter_by(player_id=player.id).delete()
    db.session.delete(player)
    db.session.commit()

    if team:
        try:
            recalc_team_skill(team)
        except Exception:
            team.skill_rating = team.skill_rating or 1200
            db.session.add(team)
            db.session.commit()

    flash(f"{player.name} has been deleted{(' from ' + team.name) if team else ''}.", "warning")
    if team:
        return redirect(url_for("team_detail", team_id=team.id))
    return redirect(url_for("index"))

# -------------------------
# Invites, Matches, Shuffle, etc.
# -------------------------
# [All the rest of your existing routes stay the same]
# I didn’t modify them so every feature is preserved


# -------------------------
# Invite player/team
# -------------------------
@app.route("/teams/<int:team_id>/invite", methods=["GET","POST"])
def team_invite(team_id):
    team = Team.query.get_or_404(team_id)
    if request.method == "POST":
        invited_name = request.form.get("name") or None
        email = request.form.get("email") or None
        token = make_token(12)
        inv = Invite(token=token, context_type="team", context_id=team.id, email=email, invited_name=invited_name)
        db.session.add(inv); db.session.commit()
        accept_url = url_for("accept_invite", token=token, _external=True)
        return render_template("invite_sent.html", invite=inv, accept_url=accept_url, team=team)
    return render_template("invite_sent.html", team=team, invite=None)

# -------------------------
# Matches routes (create, detail, join)
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
            team1_id = int(team1_id)
        if team2_id:
            team2_id = int(team2_id)

        if team1_id and team2_id:
            team1 = Team.query.get(team1_id)
            team2 = Team.query.get(team2_id)
            t1_sport = team1.sport or sport
            t2_sport = team2.sport or sport
            if t1_sport != t2_sport:
                flash(f"Cannot create match: teams must have the same sport. {team1.name} plays {t1_sport}, while {team2.name} plays {t2_sport}.", "danger")
                return redirect(url_for("create_match"))
            m.sport = t1_sport

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
    pool = []
    if match.team1_id:
        pool += Player.query.filter_by(team_id=match.team1_id).all()
    if match.team2_id:
        pool += Player.query.filter_by(team_id=match.team2_id).all()
    assignments = MatchAssignment.query.filter_by(match_id=match.id).all()
    assigned_a = [a.player for a in assignments if a.team_side == 'A']
    assigned_b = [a.player for a in assignments if a.team_side == 'B']
    locked = (match.status == "locked")
    return render_template("match_detail.html", match=match, pool=pool, assigned_a=assigned_a, assigned_b=assigned_b, locked=locked)

# -------------------------
# Invite and accept
# -------------------------
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

@app.route("/invite/<token>", methods=["GET","POST"])
def accept_invite(token):
    inv = Invite.query.filter_by(token=token).first_or_404()
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email") or None
        if inv.context_type == "team":
            p = Player(name=name or inv.invited_name or "Guest", email=email, invited=False, team_id=inv.context_id)
            db.session.add(p); db.session.commit()
            inv.accepted = True; db.session.commit()
            try:
                team = Team.query.get(inv.context_id)
                recalc_team_skill(team)
            except Exception:
                pass
            flash("You joined the team!", "success")
            return redirect(url_for("team_detail", team_id=inv.context_id))
        else:
            p = Player(name=name or "Guest", email=email, invited=False, team_id=None)
            db.session.add(p); db.session.commit()
            ma = MatchAssignment(match_id=inv.context_id, player_id=p.id, team_side='A')
            db.session.add(ma)
            inv.accepted = True; db.session.commit()
            flash("You joined the match pool!", "success")
            return redirect(url_for("match_detail", match_id=inv.context_id))
    return render_template("invite_accept.html", invite=inv)

# -------------------------
# Open challenge join
# -------------------------
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
# Shuffle & auto-balance
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
    if match.status == "locked":
        match.status = "pending"
    else:
        if not MatchAssignment.query.filter_by(match_id=match.id).count():
            return jsonify({"error":"no assignments to lock"}), 400
        match.status = "locked"
    db.session.commit()
    return jsonify({"status":match.status})

@app.route("/matches/<int:match_id>/assign", methods=["POST"])
def match_assign_player(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status == "locked":
        return jsonify({"error":"match locked"}), 400
    player_id = request.form.get("player_id")
    team_side = request.form.get("team_side") or "A"
    if not player_id: return jsonify({"error":"player_id missing"}),400
    player = Player.query.get(int(player_id))
    if not player: return jsonify({"error":"player not found"}),404
    ma = MatchAssignment(match_id=match.id, player_id=player.id, team_side=team_side)
    db.session.add(ma)
    db.session.commit()
    return jsonify({"success":True})

