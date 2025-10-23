from . import db
from datetime import datetime

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(30), nullable=True)
    skill_rating = db.Column(db.Integer, default=1200)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sport = db.Column(db.String(50), nullable=True, default="soccer")
    captain_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    players = db.relationship("Player", backref="team", lazy=True, foreign_keys="Player.team_id")


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    role = db.Column(db.String(80), nullable=True)
    skill_rating = db.Column(db.Integer, default=1200)
    invited = db.Column(db.Boolean, default=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    games_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    skills = db.relationship("PlayerSkill", backref="player", lazy=True, cascade="all, delete-orphan")


class PlayerSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    sport = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    value = db.Column(db.Integer, nullable=False, default=0)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sport = db.Column(db.String(80), nullable=False, default="soccer")
    location = db.Column(db.String(200), nullable=True)
    date = db.Column(db.DateTime, nullable=True)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    stakes = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team1 = db.relationship("Team", foreign_keys=[team1_id], lazy=True)
    team2 = db.relationship("Team", foreign_keys=[team2_id], lazy=True)


class MatchAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    team_side = db.Column(db.String(2), nullable=False)
    match = db.relationship("Match", backref=db.backref("assignments", cascade="all, delete-orphan"))
    player = db.relationship("Player", lazy=True)


class Invite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(120), unique=True, nullable=False)
    context_type = db.Column(db.String(20), nullable=False)
    context_id = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(200), nullable=True)
    invited_name = db.Column(db.String(120), nullable=True)
    accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
