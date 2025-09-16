# Copyright (C) 2025 ZHEEZL
# All rights reserved.
# This software is proprietary and may not be used, copied, modified,
# or distributed without prior written permission from the author.



import os
import random
import subprocess
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from flask_limiter import Limiter

from forms import LoginForm, RegistrationForm
from models import db, User, Video, Like

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = ''
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['UPLOAD_AVATAR_FOLDER'] = 'static/avatars'
app.config['THUMBNAIL_FOLDER'] = 'static/thumbnails'
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'mov', 'avi', 'mkv'}
app.config['VIDEO_QUALITIES'] = ['1080p', '720p', '480p', '360p']
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
migrate = Migrate(app, db)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

BLOCKED_IPS = {'192.168.1.100', '192.168.1.101'}

# Create directories if they do not exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def block_method():
    if request.remote_addr in BLOCKED_IPS:
        return "Your IP has been blocked.", 403


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def generate_thumbnail(video_path, thumbnail_path):
    ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
    command = [
        ffmpeg_path,
        '-i', video_path,
        '-ss', '00:00:01.000',
        '-vframes', '1',
        '-vf', 'scale=320:-1',
        thumbnail_path
    ]
    subprocess.run(command, capture_output=True)


def get_video_resolution(video_path):
    ffprobe_path = r"C:\ffmpeg\bin\ffprobe.exe"
    command = [
        ffprobe_path,
        '-v', 'error',
        '-select_streams', 'v:0',
        '-count_packets', '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0',
        video_path
    ]
    output = subprocess.check_output(command).decode('utf-8').strip().split(',')
    return int(output[0]), int(output[1])


def generate_video_variants(video_path, base_filename):
    ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
    variants = {}
    qualities = {
        '4K': '3840x2160',
        'QHD': '2560x1440',
        '1080p': '1920x1080',
        '720p': '1280x720',
        '480p': '854x480',
        '360p': '640x360'
    }

    original_width, original_height = get_video_resolution(video_path)
    aspect_ratio = original_width / original_height

    for quality, resolution in qualities.items():
        target_width, target_height = map(int, resolution.split('x'))

        if original_width >= target_width or original_height >= target_height:
            variant_filename = f"{base_filename}_{quality}.mp4"
            variant_path = os.path.join(app.config['UPLOAD_FOLDER'], variant_filename)

            if abs(aspect_ratio - 1) < 0.01:  # Square video
                # Find the closest larger resolution
                if original_width <= target_width and original_height <= target_height:
                    new_size = max(original_width, original_height)
                    filter_complex = f'scale={new_size}:{new_size},pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2'
            elif abs(aspect_ratio - (target_width / target_height)) < 0.01:
                # Standard aspect ratio, just scale
                filter_complex = f'scale={target_width}:{target_height}'
            else:
                # Non-standard aspect ratio, scale and pad
                if aspect_ratio > 1:  # Landscape
                    new_height = int(target_width / aspect_ratio)
                    filter_complex = f'scale={target_width}:{new_height},pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2'
                else:  # Portrait
                    new_width = int(target_height * aspect_ratio)
                    filter_complex = f'scale={new_width}:{target_height},pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2'

            command = [
                ffmpeg_path,
                '-i', video_path,
                '-vf', filter_complex,
                '-c:v', 'libx264',
                '-crf', '23',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '128k',
                variant_path
            ]

            subprocess.run(command, capture_output=True)
            variants[quality] = variant_filename

    return variants


def get_video_duration(video_path):
    """Returns the duration of the video in 'MM:SS' format, or 'HH:MM:SS' if longer than an hour."""
    ffprobe_path = r"C:\ffmpeg\bin\ffprobe.exe"
    command = [
        ffprobe_path,
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    duration_seconds = float(result.stdout.strip())

    # Calculate hours, minutes, and seconds
    hours, remainder = divmod(int(duration_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    else:
        return f"{minutes}:{seconds:02}"


@app.route('/favicon.ico')
def favicon():
    return url_for('static', filename='favicon.ico')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        avatar_filename = None
        if form.avatar.data:
            avatar_file = form.avatar.data
            avatar_filename = secure_filename(f"{uuid.uuid4().hex}_{avatar_file.filename}")
            avatar_path = os.path.join(app.config['UPLOAD_AVATAR_FOLDER'], avatar_filename)
            avatar_file.save(avatar_path)

        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password,
            avatar_filename=avatar_filename,
            channel_name=form.username.data,
            channel_description=form.username.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Your account has been created!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('You have been logged in!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', form=form)


@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    if 'avatar' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.referrer or url_for('home'))

    avatar_file = request.files['avatar']
    if avatar_file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.referrer or url_for('home'))

    if avatar_file:
        filename = secure_filename(f"{uuid.uuid4().hex}_{avatar_file.filename}")
        avatar_path = os.path.join(app.config['UPLOAD_AVATAR_FOLDER'], filename)
        avatar_file.save(avatar_path)

        # Process the image to make it square
        with Image.open(avatar_path) as img:
            # Calculate the size of the square
            min_side = min(img.size)
            left = (img.width - min_side) / 2
            top = (img.height - min_side) / 2
            right = (img.width + min_side) / 2
            bottom = (img.height + min_side) / 2

            # Crop the image to a square
            img = img.crop((left, top, right, bottom))
            img = img.resize((256, 256), Image.LANCZOS)  # Resize to desired size

            # Save the processed image
            img.save(avatar_path)

        current_user.avatar_filename = filename
        db.session.commit()

        flash('Avatar updated successfully!', 'success')
        return redirect(url_for('view_channel', user_id=current_user.id, view_name=current_user.channel_name))
    else:
        print('biba')
        return redirect(request.referrer or url_for('home'))


def time_since(past_datetime):
    now = datetime.now()
    diff = now - past_datetime

    # Define time units and corresponding strings
    time_units = [
        (timedelta(days=365), 'год', 'года', 'лет'),
        (timedelta(days=30), 'месяц', 'месяца', 'месяцев'),
        (timedelta(days=1), 'день', 'дня', 'дней'),
        (timedelta(hours=1), 'час', 'часа', 'часов'),
        (timedelta(minutes=1), 'минуту', 'минуты', 'минут'),
        (timedelta(seconds=1), 'секунду', 'секунды', 'секунд'),
    ]

    # If the difference is less than 1 second
    if diff < timedelta(seconds=1):
        return 'Только что'

    for delta, singular, few, many in time_units:
        if diff >= delta:
            count = int(diff / delta)
            if count == 1:
                return f'{count} {singular} назад'
            elif int(str(count)[-1]) == 1 and int(str(count)[-2]) in [2, 3, 4, 5]:
                return f'{count} {singular} назад'
            elif 2 <= count <= 4:
                return f'{count} {few} назад'
            elif int(str(count)[-1]) in [2, 3, 4] and int(str(count)[-2]) in [2, 3, 4, 5]:
                return f'{count} {few} назад'
            else:
                return f'{count} {many} назад'

    return 'Время не определено'


@app.route('/')
def home():
    query = request.args.get('query')

    if query:
        videos = Video.query.join(User).filter(
            or_(
                Video.title.contains(query),
                User.username.contains(query)
            )
        ).all()
    else:
        videos = Video.query.all()

    for video in videos:
        video.formatted_upload_date = time_since(video.created_at)

    # Поиск каналов по запросу
    channels = User.query.filter(User.username.ilike(f'%{query}%')).all() if query else []

    return render_template('home.html', videos=videos, channels=channels, title="Owu")


@app.route('/video/<video_id>')
@limiter.limit("100 per minute")
def view_video(video_id):
    video = Video.query.filter_by(video_id=video_id).first_or_404()
    suggested_videos = Video.query.filter(Video.video_id != video_id).all()

    available_qualities = {
        '2160p': url_for('static', filename=f'uploads/{video.filename_4k}') if video.filename_4k else None,
        '1440p': url_for('static', filename=f'uploads/{video.filename_2k}') if video.filename_2k else None,
        '1080p': url_for('static', filename=f'uploads/{video.filename_1080p}') if video.filename_1080p else None,
        '720p': url_for('static', filename=f'uploads/{video.filename_720p}') if video.filename_720p else None,
        '480p': url_for('static', filename=f'uploads/{video.filename_480p}') if video.filename_480p else None,
        '360p': url_for('static', filename=f'uploads/{video.filename_360p}') if video.filename_360p else None,
    }
    available_qualities = {k: v for k, v in available_qualities.items() if v is not None}

    video.formatted_upload_date = time_since(video.created_at)
    for videos in suggested_videos:
        videos.formatted_upload_date = time_since(videos.created_at)

    random.shuffle(suggested_videos)

    return render_template('view_video.html', video=video, suggested_videos=suggested_videos,
                           available_qualities=available_qualities)


@app.route('/update_views', methods=['POST'])
def update_views():
    data = request.get_json()
    video_id = data.get('video_id')

    video = Video.query.filter_by(video_id=video_id).first_or_404()
    video.views += 1
    db.session.commit()

    return jsonify({'success': True})


@app.route('/like/<video_id>', methods=['POST'])
@login_required
def like_video(video_id):
    video = Video.query.filter_by(video_id=video_id).first_or_404()

    existing_like = Like.query.filter_by(user_id=current_user.id, video_id=video_id).first()
    if existing_like:
        db.session.delete(existing_like)
        video.likes -= 1
    else:
        new_like = Like(user_id=current_user.id, video_id=video_id)
        db.session.add(new_like)
        video.likes += 1

    db.session.commit()

    return jsonify({'success': True, 'new_likes_count': video.likes})


@app.route('/subscribe/<int:user_id>', methods=['POST'])
@login_required
def subscribe(user_id):
    if user_id == current_user.id:
        return jsonify(success=False, message="Вы не можете подписаться на самого себя.")

    user_to_subscribe = User.query.get_or_404(user_id)
    if not current_user.is_subscribed(user_to_subscribe):
        current_user.subscribe(user_to_subscribe)
        db.session.commit()

    return jsonify(success=True, new_subscribers_count=user_to_subscribe.subscribers_count())


@app.route('/unsubscribe/<int:user_id>', methods=['POST'])
@login_required
def unsubscribe(user_id):
    user_to_unsubscribe = User.query.get_or_404(user_id)
    if current_user.is_subscribed(user_to_unsubscribe):
        current_user.unsubscribe(user_to_unsubscribe)
        db.session.commit()

    return jsonify(success=True, new_subscribers_count=user_to_unsubscribe.subscribers_count())


@app.route('/channel/<int:user_id>')
def view_channel(user_id):
    # Получаем пользователя, чей канал просматривается
    viewed_user = User.query.get_or_404(user_id)

    # Получаем все видео, загруженные этим пользователем
    videos = Video.query.filter_by(user_id=user_id).all()

    for video in videos:
        video.formatted_upload_date = time_since(video.created_at)

    # Передаем данные в шаблон
    return render_template('view_channel.html', viewed_user=viewed_user, videos=videos)


@app.route('/liked_videos')
@limiter.limit("5 per minute")
@login_required
def liked_videos():
    user = User.query.get_or_404(current_user.id)
    liked_videos = [like.video for like in user.likes]
    for video in liked_videos:
        video.formatted_upload_date = time_since(video.created_at)
    return render_template('liked_videos.html', videos=liked_videos, title="Понравившиеся видео")


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        video_file = request.files.get('video')

        if not video_file:
            flash('No video file selected.')
            return redirect(request.url)

        if not allowed_file(video_file.filename):
            flash('File type not allowed.')
            return redirect(request.url)

        video_id = uuid.uuid4().hex
        base_filename = secure_filename(video_file.filename.rsplit('.', 1)[0])
        unique_base_filename = f"{video_id}_{base_filename}"
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{unique_base_filename}.mp4")

        try:
            with open(video_path, 'wb') as f:
                while chunk := video_file.stream.read(1024 * 1024):
                    f.write(chunk)

            # Get the video duration
            video_duration = get_video_duration(video_path)

            # Generate video variants
            variants = generate_video_variants(video_path, unique_base_filename)

            # Handle thumbnail creation
            thumbnail_file = request.files.get('thumbnail')
            if thumbnail_file and thumbnail_file.filename:
                thumbnail_filename = secure_filename(thumbnail_file.filename)
                thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
                thumbnail_file.save(thumbnail_path)
            else:
                thumbnail_filename = f"{unique_base_filename}.png"
                thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
                generate_thumbnail(video_path, thumbnail_path)

            # Create and save the video object in the database
            video = Video(
                video_id=video_id,
                title=title,
                description=description,
                filename_1080p=variants['1080p'],
                filename_720p=variants['720p'],
                filename_480p=variants['480p'],
                filename_360p=variants['360p'],
                thumbnail_filename=thumbnail_filename,
                user_id=current_user.id,
                duration=str(video_duration)  # Store the duration in a suitable format
            )
            db.session.add(video)
            db.session.commit()
            flash('Video and thumbnail uploaded successfully.')
            if os.path.exists(video_path):
                os.remove(video_path) # Remove the video file

            return redirect(url_for('home'))

        except Exception as e:
            flash(f'An error occurred during upload: {str(e)}', 'danger')
            print(e)
            db.session.rollback()

            # Удаление всех созданных файлов в случае ошибки
            if os.path.exists(video_path):
                os.remove(video_path)
            for variant in variants.values():
                variant_path = os.path.join(app.config['UPLOAD_FOLDER'], variant)
                if os.path.exists(variant_path):
                    os.remove(variant_path)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

            return redirect(request.url)

    return render_template('upload.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
