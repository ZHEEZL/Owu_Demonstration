from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    channel_name = db.Column(db.String(150), nullable=False)
    channel_description = db.Column(db.String(150), nullable=True)
    avatar_filename = db.Column(db.String(150), nullable=True)

    videos = db.relationship('Video', backref='uploader', lazy=True)
    likes = db.relationship('Like', back_populates='user', lazy=True)  # Added back_populates

    def set_password(self, password):
        """Generate a password hash."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check the password against the hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        """Assume all users are active by default."""
        return True

    @property
    def is_authenticated(self):
        """Always true for authenticated users."""
        return True

    @property
    def is_anonymous(self):
        """Anonymous users aren't supported."""
        return False

    def get_id(self):
        """Use the primary key as the user ID."""
        return str(self.id)

    def __repr__(self):
        return f'<User {self.username}>'

    def subscribe(self, user):
        if not self.is_subscribed(user):
            subscription = Subscription(subscriber_id=self.id, subscribed_to_id=user.id)
            db.session.add(subscription)
            db.session.commit()

    def unsubscribe(self, user):
        subscription = Subscription.query.filter_by(subscriber_id=self.id, subscribed_to_id=user.id).first()
        if subscription:
            db.session.delete(subscription)
            db.session.commit()

    def is_subscribed(self, user):
        return Subscription.query.filter_by(subscriber_id=self.id, subscribed_to_id=user.id).count() > 0

    def get_subscriptions(self):
        return User.query.join(Subscription, Subscription.subscribed_to_id == User.id).filter(
            Subscription.subscriber_id == self.id).all()

    def get_subscribers(self):
        return User.query.join(Subscription, Subscription.subscriber_id == User.id).filter(
            Subscription.subscribed_to_id == self.id).all()

    def subscribers_count(self):
        return Subscription.query.filter_by(subscribed_to_id=self.id).count()


class Video(db.Model):
    __tablename__ = 'video'

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(32), unique=True, nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename_4k = db.Column(db.String(120), nullable=True)
    filename_2k = db.Column(db.String(120), nullable=True)
    filename_1080p = db.Column(db.String(120), nullable=True)
    filename_720p = db.Column(db.String(120), nullable=True)
    filename_480p = db.Column(db.String(120), nullable=True)
    filename_360p = db.Column(db.String(120), nullable=True)
    thumbnail_filename = db.Column(db.String(120), nullable=True)
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    liked_by = db.relationship('Like', back_populates='video', lazy='dynamic')  # Updated back_populates
    user = db.relationship('User', backref='user_videos', lazy=True)
    duration = db.Column(db.String(50), nullable=True)  # Added duration field

    def __repr__(self):
        return f'<Video {self.title}>'


class Like(db.Model):
    __tablename__ = 'like'

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    video_id = db.Column(db.String(32), db.ForeignKey('video.video_id'), primary_key=True)
    user = db.relationship('User', back_populates='likes')
    video = db.relationship('Video', back_populates='liked_by')  # Updated back_populates


class Subscription(db.Model):
    __tablename__ = 'subscription'

    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Определяем отношения
    subscriber = db.relationship('User', foreign_keys=[subscriber_id], backref='subscriptions')
    subscribed_to = db.relationship('User', foreign_keys=[subscribed_to_id], backref='subscribers')
