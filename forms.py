from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Email
from flask_wtf.file import FileField, FileAllowed


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    avatar = FileField('Upload Avatar', validators=[FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')])
    submit = SubmitField('Register')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class UploadForm(FlaskForm):
    title = StringField('Video Title', validators=[DataRequired()])
    video = FileField('Upload Video', validators=[DataRequired(), FileAllowed(['mp4', 'mov', 'avi'])])
    submit = SubmitField('Upload')


class SearchForm(FlaskForm):
    search = StringField('Search Videos', validators=[DataRequired()])
    submit = SubmitField('Search')
