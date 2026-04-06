"""
TimerFreak Authentication Blueprint
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timezone, timedelta
import secrets
from functools import wraps

from models import db, User, OAuthAccount, UserActivityLog, Sequence, CounterLog

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# OAuth setup
oauth = OAuth()


def init_auth(app):
    """Initialize authentication with the Flask app"""
    login_manager.init_app(app)
    oauth.init_app(app)
    
    # Configure OAuth providers
    if app.config.get('GOOGLE_CLIENT_ID'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile',
            },
        )
    
    if app.config.get('GITHUB_CLIENT_ID'):
        oauth.register(
            name='github',
            client_id=app.config['GITHUB_CLIENT_ID'],
            client_secret=app.config['GITHUB_CLIENT_SECRET'],
            access_token_url='https://github.com/login/oauth/access_token',
            authorize_url='https://github.com/login/oauth/authorize',
            api_base_url='https://api.github.com/',
            client_kwargs={
                'scope': 'user:email',
            },
        )
    
    # Note: Apple Sign In requires Apple Developer Program ($99/year)
    # Uncomment below to enable when you have an Apple Developer account
    # if app.config.get('APPLE_CLIENT_ID'):
    #     oauth.register(
    #         name='apple',
    #         client_id=app.config['APPLE_CLIENT_ID'],
    #         client_secret=app.config['APPLE_CLIENT_SECRET'],
    #         server_metadata_url='https://appleid.apple.com/.well-known/openid-configuration',
    #         client_kwargs={
    #             'scope': 'name email',
    #             'response_type': 'code',
    #             'response_mode': 'form_post',
    #         },
    #     )
    
    # Register blueprint
    app.register_blueprint(auth_bp)
    
    # Setup user loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))


def log_user_activity(action, category, sequence_id=None, timer_order=None, metadata=None):
    """Log user activity for analytics and security"""
    if not current_user.is_authenticated:
        return
    
    import json
    metadata_str = json.dumps(metadata) if metadata else None
    
    log = UserActivityLog(
        user_id=current_user.id,
        action=action,
        category=category,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500],
        session_id=session.get('session_id', ''),
        sequence_id=sequence_id,
        timer_order=timer_order,
        extra_data=metadata_str,
    )
    db.session.add(log)
    db.session.commit()


def owner_required(f):
    """Decorator to check if user owns the resource"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this resource.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Get sequence_id from kwargs or request
        sequence_id = kwargs.get('sequence_id') or request.args.get('sequence_id')
        
        if sequence_id:
            sequence = Sequence.query.get(sequence_id)
            if sequence and sequence.owner_id and sequence.owner_id != current_user.id:
                flash('You do not have permission to access this resource.', 'error')
                return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('This account has been deactivated.', 'error')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember)
            session['session_id'] = secrets.token_urlsafe(32)
            
            # Update last login
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            # Log activity
            log_user_activity('login', 'auth')
            
            flash(f'Welcome back, {user.display_name or user.username}!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        errors = []
        if not email or '@' not in email:
            errors.append('Please enter a valid email address.')
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not password or len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        # Check existing
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Create user
        user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            display_name=username,
            verification_token=secrets.token_urlsafe(32),
        )
        db.session.add(user)
        db.session.commit()
        
        # Log activity
        log_user_activity('register', 'auth')
        
        flash('Account created successfully! Please check your email for verification.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')


@auth_bp.route('/logout', methods=['GET', 'POST'])
def user_logout():
    """User logout"""
    if current_user.is_authenticated:
        log_user_activity('logout', 'auth')
        logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@auth_bp.route('/verify/<token>')
def verify_email(token):
    """Email verification"""
    user = User.query.filter_by(verification_token=token).first()
    
    if user:
        user.is_verified = True
        user.verification_token = None
        db.session.commit()
        flash('Email verified successfully!', 'success')
        return redirect(url_for('auth.login'))
    else:
        flash('Invalid or expired verification link.', 'error')
        return redirect(url_for('auth.login'))


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    """Request password reset"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            user.reset_token = secrets.token_urlsafe(32)
            db.session.commit()
            
            # TODO: Send email with reset link
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        else:
            # Don't reveal if email exists
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password_request.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    user = User.query.filter_by(reset_token=token).first()
    
    if not user:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        user.password_hash = generate_password_hash(password)
        user.reset_token = None
        db.session.commit()
        
        flash('Password reset successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/oauth/<provider>')
def oauth_login(provider):
    """OAuth login redirect"""
    if provider not in ['google', 'github']:
        flash('Invalid OAuth provider.', 'error')
        return redirect(url_for('auth.login'))

    oauth_client = oauth.create_client(provider)
    if not oauth_client:
        flash(f'{provider.capitalize()} login is not configured.', 'error')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('auth.oauth_callback', provider=provider, _external=True)
    return oauth_client.authorize_redirect(redirect_uri)


@auth_bp.route('/oauth/<provider>/callback')
def oauth_callback(provider):
    """OAuth callback handler"""
    if provider not in ['google', 'github']:
        flash('Invalid OAuth provider.', 'error')
        return redirect(url_for('auth.login'))

    oauth_client = oauth.create_client(provider)
    if not oauth_client:
        flash(f'{provider.capitalize()} login is not configured.', 'error')
        return redirect(url_for('auth.login'))

    try:
        token = oauth_client.authorize_access_token()
    except Exception as e:
        current_app.logger.error(f"OAuth error for {provider}: {e}")
        flash(f'Authentication with {provider} failed.', 'error')
        return redirect(url_for('auth.login'))

    # Get user info from provider
    if provider == 'google':
        user_info = token.get('userinfo')
        provider_user_id = user_info.get('sub')
        email = user_info.get('email')
        username = email.split('@')[0] if email else f'user_{provider_user_id}'
        display_name = user_info.get('name', username)
    elif provider == 'github':
        resp = oauth_client.get('user')
        user_info = resp.json()
        provider_user_id = str(user_info.get('id'))
        email = user_info.get('email') or f'{provider_user_id}@users.noreply.github.com'
        username = user_info.get('login', f'user_{provider_user_id}')
        display_name = user_info.get('name', username)
    # Note: Apple OAuth removed - requires $99/year Apple Developer Program
    # Uncomment apple section in oauth_callback when Apple Developer account is available
    else:
        flash('Invalid OAuth provider.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check if OAuth account exists
    oauth_account = OAuthAccount.query.filter_by(
        provider=provider,
        provider_user_id=provider_user_id
    ).first()
    
    if oauth_account:
        # Existing user - log in with remember me
        user = oauth_account.user
        login_user(user, remember=True, duration=timedelta(days=30))
        session['session_id'] = secrets.token_urlsafe(32)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        log_user_activity('login_oauth', 'auth', metadata={'provider': provider})
        flash(f'Welcome back, {display_name}!', 'success')
    else:
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        
        if existing_user:
            # Link OAuth to existing account
            oauth_account = OAuthAccount(
                user_id=existing_user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                access_token=token.get('access_token'),
                refresh_token=token.get('refresh_token'),
                token_expires=datetime.now(timezone.utc) + timedelta(seconds=token.get('expires_in', 3600)),
                profile_data=str(user_info),
            )
            db.session.add(oauth_account)
            db.session.commit()

            login_user(existing_user, remember=True, duration=timedelta(days=30))
            session['session_id'] = secrets.token_urlsafe(32)
            existing_user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            flash(f'Linked {provider} account to {email}.', 'success')
        else:
            # Create new user
            user = User(
                email=email,
                username=username,
                display_name=display_name,
                is_verified=True,  # OAuth emails are pre-verified
            )
            db.session.add(user)
            db.session.flush()  # Get user ID
            
            oauth_account = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                access_token=token.get('access_token'),
                refresh_token=token.get('refresh_token'),
                token_expires=datetime.now(timezone.utc) + timedelta(seconds=token.get('expires_in', 3600)),
                profile_data=str(user_info),
            )
            db.session.add(oauth_account)
            db.session.commit()

            login_user(user, remember=True, duration=timedelta(days=30))
            session['session_id'] = secrets.token_urlsafe(32)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            log_user_activity('register_oauth', 'auth', metadata={'provider': provider})
            flash(f'Welcome, {display_name}! Your account has been created.', 'success')
    
    next_page = request.args.get('next')
    return redirect(next_page if next_page else url_for('index'))


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    # Get user's sequences count
    sequences_count = current_user.sequences.count()
    
    # Get recent activity
    recent_activity = UserActivityLog.query.filter_by(
        user_id=current_user.id
    ).order_by(UserActivityLog.timestamp.desc()).limit(10).all()
    
    return render_template('auth/profile.html', 
                         sequences_count=sequences_count,
                         recent_activity=recent_activity)


@auth_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings page"""
    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        username = request.form.get('username', '').strip()
        
        # Validation
        if not display_name:
            flash('Display name is required.', 'error')
            return render_template('auth/settings.html')
        
        # Check username availability
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != current_user.id:
            flash('Username already taken.', 'error')
            return render_template('auth/settings.html')
        
        current_user.display_name = display_name
        current_user.username = username
        db.session.commit()
        
        log_user_activity('update_profile', 'auth')
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/settings.html')


@auth_bp.route('/settings/password', methods=['POST'])
@login_required
def change_password():
    """Change password"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not check_password_hash(current_user.password_hash, current_password):
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('auth.settings'))
    
    if not new_password or len(new_password) < 8:
        flash('New password must be at least 8 characters.', 'error')
        return redirect(url_for('auth.settings'))
    
    if new_password != confirm_password:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('auth.settings'))
    
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    log_user_activity('change_password', 'auth')
    flash('Password changed successfully!', 'success')
    return redirect(url_for('auth.settings'))


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with stats"""
    # Get user's sequences
    user_sequences = current_user.sequences.order_by(Sequence.created_at.desc()).limit(10).all()
    
    # Get stats
    total_sequences = current_user.sequences.count()
    total_timers = db.session.query(Sequence).join(Timer).filter(Sequence.owner_id == current_user.id).count()
    
    # Get recent activity logs for owned sequences
    recent_logs = CounterLog.query.join(Sequence).filter(
        Sequence.owner_id == current_user.id
    ).order_by(CounterLog.timestamp.desc()).limit(20).all()
    
    return render_template('auth/dashboard.html',
                         user_sequences=user_sequences,
                         total_sequences=total_sequences,
                         total_timers=total_timers,
                         recent_logs=recent_logs)


# Import Timer for dashboard
from models import Timer
