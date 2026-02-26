# Forbidden Bourbon Command Center v15b — Gallery + Photos + AI Bottle Ref Fix
import os
import json
import threading
import time as time_module
import random
from datetime import datetime, timedelta
from flask import (Flask, render_template, request, jsonify, redirect, 
                   url_for, flash, send_from_directory)
from werkzeug.utils import secure_filename

import database as db
import ga4
from publisher import publish_to_platform, PublishResult

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'forbidden-command-center-2025')

# Upload config
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max


# ============================================================
# GLOBAL ERROR HANDLERS — return JSON instead of HTML error pages
# Without these, any route crash returns HTML which breaks JS parsing
# ============================================================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    return e  # Let Flask handle non-API 404s normally

@app.errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Method not allowed'}), 405
    return e

@app.errorhandler(500)
def internal_error(e):
    print(f"[500 Error] {request.path}: {e}")
    return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP exceptions (404, 405, etc.) to their specific handlers
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': str(e)}), e.code
        return e
    # Catch-all for unhandled exceptions
    print(f"[Unhandled Error] {request.path}: {type(e).__name__}: {e}")
    return jsonify({'success': False, 'error': f'{type(e).__name__}: {str(e)}'}), 500

# API key helper - checks env vars first, then database
def get_api_key(provider):
    """Get API key from env var first, then database. Set once in Render, works everywhere."""
    env_map = {'openai': 'OPENAI_API_KEY', 'runway': 'RUNWAY_API_KEY', 'elevenlabs': 'ELEVENLABS_API_KEY'}
    env_key = os.environ.get(env_map.get(provider, ''), '')
    if env_key:
        return env_key
    platform = db.get_platform(provider)
    return platform.get('api_key', '') if platform else ''

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database and seed content
db.init_db()

# Force-seed blog platforms (may not exist in older databases)
def ensure_blog_platforms():
    try:
        conn = db.get_db()
        
        # Ensure blog tables exist
        if db.USE_POSTGRES:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS blog_articles (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                excerpt TEXT DEFAULT '', topic TEXT DEFAULT '', keywords TEXT DEFAULT '',
                status TEXT DEFAULT 'draft', platform TEXT DEFAULT '', platform_url TEXT DEFAULT '',
                platform_post_id TEXT DEFAULT '', word_count INTEGER DEFAULT 0,
                ai_generated INTEGER DEFAULT 1, published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS blog_topics (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, category TEXT DEFAULT 'general',
                keywords TEXT DEFAULT '', last_used TIMESTAMP, times_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        else:
            conn.execute('''CREATE TABLE IF NOT EXISTS blog_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL,
                excerpt TEXT DEFAULT '', topic TEXT DEFAULT '', keywords TEXT DEFAULT '',
                status TEXT DEFAULT 'draft', platform TEXT DEFAULT '', platform_url TEXT DEFAULT '',
                platform_post_id TEXT DEFAULT '', word_count INTEGER DEFAULT 0,
                ai_generated INTEGER DEFAULT 1, published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS blog_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT DEFAULT 'general',
                keywords TEXT DEFAULT '', last_used TIMESTAMP, times_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Ensure blog platforms in platforms table
        blog_platforms = [
            ('medium', 'Medium', '📝'),
            ('wordpress', 'WordPress', '📰'),
            ('blogger', 'Blogger', '📢'),
            ('reddit', 'Reddit', '🤖'),
            ('pinterest', 'Pinterest', '📌'),
            ('quora', 'Quora (Manual)', '❓'),
        ]
        for name, display_name, icon in blog_platforms:
            existing = db._fetchone(conn, 'SELECT id FROM platforms WHERE name = ?', (name,))
            if not existing:
                if db.USE_POSTGRES:
                    conn.cursor().execute(
                        'INSERT INTO platforms (name, display_name, icon) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING',
                        (name, display_name, icon))
                else:
                    conn.execute('INSERT OR IGNORE INTO platforms (name, display_name, icon) VALUES (?, ?, ?)',
                                (name, display_name, icon))
        
        conn.commit()
        conn.close()
        print("[Startup] Blog platforms and tables verified")
    except Exception as e:
        print(f"Blog platforms seed: {e}")

ensure_blog_platforms()

# Ensure brand_mentions table exists
try:
    conn = db.get_db()
    if db.USE_POSTGRES:
        conn.cursor().execute('''CREATE TABLE IF NOT EXISTS brand_mentions (
            id SERIAL PRIMARY KEY, title TEXT NOT NULL, url TEXT DEFAULT '', source TEXT DEFAULT '',
            source_type TEXT DEFAULT 'article', snippet TEXT DEFAULT '', full_content TEXT DEFAULT '',
            author TEXT DEFAULT '', sentiment TEXT DEFAULT 'neutral', date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_published TEXT DEFAULT '', starred INTEGER DEFAULT 0, notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    else:
        conn.execute('''CREATE TABLE IF NOT EXISTS brand_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, url TEXT DEFAULT '', source TEXT DEFAULT '',
            source_type TEXT DEFAULT 'article', snippet TEXT DEFAULT '', full_content TEXT DEFAULT '',
            author TEXT DEFAULT '', sentiment TEXT DEFAULT 'neutral', date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_published TEXT DEFAULT '', starred INTEGER DEFAULT 0, notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    print("[Startup] Brand mentions table verified")
except Exception as e:
    print(f"Brand mentions table: {e}")

# Ensure ai_gallery table exists (with image_data for ephemeral-safe storage)
try:
    conn = db.get_db()
    if db.USE_POSTGRES:
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS ai_gallery (
            id SERIAL PRIMARY KEY,
            media_type TEXT NOT NULL,
            url TEXT NOT NULL,
            prompt TEXT DEFAULT '',
            revised_prompt TEXT DEFAULT '',
            saved BOOLEAN DEFAULT FALSE,
            bottle_type TEXT DEFAULT '',
            image_data TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # Migration: add image_data column if table already existed without it
        try:
            cur.execute("ALTER TABLE ai_gallery ADD COLUMN IF NOT EXISTS image_data TEXT DEFAULT ''")
        except Exception:
            pass
    else:
        conn.execute('''CREATE TABLE IF NOT EXISTS ai_gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_type TEXT NOT NULL,
            url TEXT NOT NULL,
            prompt TEXT DEFAULT '',
            revised_prompt TEXT DEFAULT '',
            saved BOOLEAN DEFAULT 0,
            bottle_type TEXT DEFAULT '',
            image_data TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # Migration: add image_data column if table already existed without it
        try:
            conn.execute("ALTER TABLE ai_gallery ADD COLUMN image_data TEXT DEFAULT ''")
        except Exception:
            pass
    conn.commit()
    conn.close()
    print("[Startup] AI gallery table verified")
except Exception as e:
    print(f"AI gallery table: {e}")

# Auto-seed content library on first run
try:
    from seed_content import seed
    seed()
except Exception as e:
    print(f"Seed note: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================================
# TEMPLATE FILTERS
# ============================================================

@app.template_filter('timeago')
def timeago_filter(dt_string):
    if not dt_string:
        return ''
    try:
        dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
        now = datetime.utcnow()
        diff = now - dt
        
        if diff.days > 30:
            return dt.strftime('%b %d, %Y')
        elif diff.days > 0:
            return f'{diff.days}d ago'
        elif diff.seconds > 3600:
            return f'{diff.seconds // 3600}h ago'
        elif diff.seconds > 60:
            return f'{diff.seconds // 60}m ago'
        else:
            return 'just now'
    except:
        return dt_string

@app.template_filter('shortdate')
def shortdate_filter(dt_string):
    if not dt_string:
        return ''
    try:
        dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%b %d, %I:%M %p')
    except:
        return dt_string

@app.template_filter('caldate')
def caldate_filter(dt_string):
    if not dt_string:
        return ''
    try:
        dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%dT%H:%M')
    except:
        return dt_string

# ============================================================
# PAGE ROUTES
# ============================================================

@app.route('/')
def dashboard():
    stats = db.get_dashboard_stats()
    recent_posts = db.get_posts(limit=5)
    scheduled = db.get_scheduled_posts()[:5]
    activity = db.get_activity(limit=10)
    platforms = db.get_platforms()
    
    # Update platform status based on env vars
    env_platform_map = {
        'openai': 'OPENAI_API_KEY',
        'runway': 'RUNWAY_API_KEY',
        'medium': 'MEDIUM_TOKEN',
        'wordpress': 'WORDPRESS_TOKEN',
        'reddit': 'REDDIT_CLIENT_ID',
        'pinterest': 'PINTEREST_TOKEN',
    }
    connected_count = 0
    for p in platforms:
        env_var = env_platform_map.get(p['name'])
        if env_var and os.environ.get(env_var, ''):
            p['connected'] = True
        # Blogger uses OAuth, check for stored token
        if p['name'] == 'blogger':
            blogger_token = db.get_oauth_token('blogger')
            if blogger_token and blogger_token.get('refresh_token'):
                p['connected'] = True
            elif os.environ.get('GOOGLE_CLIENT_ID', ''):
                p['connected'] = False  # Has config but not authorized yet
        if p.get('connected'):
            connected_count += 1
    
    # Override the DB connected_platforms with actual count
    stats['connected_platforms'] = connected_count
    
    # Get blog stats for dashboard
    blog_stats = db.get_blog_stats()
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         recent_posts=recent_posts, 
                         scheduled=scheduled,
                         activity=activity,
                         platforms=platforms,
                         blog_stats=blog_stats,
                         page='dashboard')

@app.route('/compose', methods=['GET'])
def compose():
    templates = db.get_templates()
    hashtag_groups = db.get_hashtag_groups()
    platforms = db.get_platforms()
    
    # Check if editing an existing post
    edit_id = request.args.get('edit')
    post = None
    if edit_id:
        post = db.get_post(int(edit_id))
    
    # Check if using a template
    template_id = request.args.get('template')
    template = None
    if template_id:
        t = [t for t in templates if t['id'] == int(template_id)]
        template = t[0] if t else None
        if template:
            db.increment_template_use(int(template_id))
    
    return render_template('compose.html',
                         templates=templates,
                         hashtag_groups=hashtag_groups,
                         platforms=platforms,
                         post=post,
                         template=template,
                         page='compose')

@app.route('/queue')
def queue():
    status_filter = request.args.get('status', 'all')
    if status_filter == 'all':
        posts = db.get_posts(limit=100)
    else:
        posts = db.get_posts(status=status_filter, limit=100)
    
    platforms = db.get_platforms()
    return render_template('queue.html', 
                         posts=posts, 
                         platforms=platforms,
                         status_filter=status_filter,
                         page='queue')

@app.route('/calendar')
def calendar():
    scheduled = db.get_scheduled_posts()
    published = db.get_posts(status='published', limit=50)
    return render_template('calendar.html',
                         scheduled=scheduled,
                         published=published,
                         page='calendar')

@app.route('/templates')
def templates_page():
    templates = db.get_templates()
    hashtag_groups = db.get_hashtag_groups()
    return render_template('templates.html',
                         templates=templates,
                         hashtag_groups=hashtag_groups,
                         page='templates')

@app.route('/platforms')
def platforms_page():
    platforms = db.get_platforms()
    # Get AI platform status
    openai_p = db.get_platform('openai')
    runway_p = db.get_platform('runway')
    return render_template('platforms.html',
                         platforms=[p for p in platforms if p['name'] not in ('openai', 'runway')],
                         openai_connected=openai_p['connected'] if openai_p else False,
                         openai_key=openai_p['api_key'] if openai_p else '',
                         runway_connected=runway_p['connected'] if runway_p else False,
                         runway_key=runway_p['api_key'] if runway_p else '',
                         config={
                             'OPENAI_API_KEY': get_api_key('openai'),
                             'RUNWAY_API_KEY': get_api_key('runway'),
                             'ANTHROPIC_API_KEY': os.environ.get('ANTHROPIC_API_KEY', ''),
                         },
                         page='platforms')

@app.route('/analytics')
def analytics_page():
    stats = db.get_dashboard_stats()
    summary = db.get_analytics_summary(30)
    published = db.get_posts(status='published', limit=50)
    ga4_configured = ga4.is_configured()
    return render_template('analytics.html',
                         stats=stats,
                         summary=summary,
                         published=published,
                         ga4_configured=ga4_configured,
                         page='analytics')

@app.route('/photos')
def photos_page():
    return render_template('photos.html', page='photos')

@app.route('/api/photos/gallery')
def api_photos_gallery():
    """Return all photos from the gallery folder with metadata"""
    gallery_dir = os.path.join(app.static_folder, 'photos', 'gallery')
    photos_dir = os.path.join(app.static_folder, 'photos')
    photos = []
    
    # Category mapping based on filename patterns
    def categorize(fname):
        fl = fname.lower()
        if 'lightbg' in fl:
            return 'Product (Light BG)'
        elif 'singlebarrel' in fl:
            if 'dark' in fl:
                return 'Single Barrel (Dark)'
            return 'Single Barrel'
        elif 'smallbatch' in fl:
            if 'dark' in fl:
                return 'Small Batch (Dark)'
            return 'Small Batch'
        elif 'golden_front' in fl:
            return 'Product (Light BG)'
        elif 'black_front' in fl:
            return 'Product (Light BG)'
        elif '-edit' in fl or 'edit.' in fl:
            return 'Lifestyle / Detail'
        else:
            return 'Photo Shoot'
    
    # Scan gallery folder
    if os.path.exists(gallery_dir):
        for fname in sorted(os.listdir(gallery_dir)):
            if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                fpath = os.path.join(gallery_dir, fname)
                photos.append({
                    'filename': fname,
                    'url': f'/static/photos/gallery/{fname}',
                    'category': categorize(fname),
                    'size': os.path.getsize(fpath),
                    'is_png': fname.lower().endswith('.png'),
                    'is_hero': 'lightbg' in fname.lower() or 'black_front' in fname.lower()
                })
    
    # Also include root-level photos
    for fname in sorted(os.listdir(photos_dir)):
        fpath = os.path.join(photos_dir, fname)
        if os.path.isfile(fpath) and fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            photos.append({
                'filename': fname,
                'url': f'/static/photos/{fname}',
                'category': 'Brand Assets',
                'size': os.path.getsize(fpath),
                'is_png': fname.lower().endswith('.png'),
                'is_hero': False
            })
    
    categories = sorted(set(p['category'] for p in photos))
    return jsonify({'success': True, 'photos': photos, 'categories': categories, 'total': len(photos)})

@app.route('/guide')
def guide_page():
    return render_template('guide.html', page='guide')

@app.route('/blog-hub')
def blog_hub_page():
    articles = db.get_blog_articles(limit=50)
    topics = db.get_blog_topics()
    stats = db.get_blog_stats()
    return render_template('blog_hub.html', 
                         articles=articles,
                         topics=topics,
                         stats=stats,
                         page='blog-hub')

@app.route('/brand-intel')
def brand_intel_page():
    mentions = db.get_brand_mentions(limit=500)
    stats = db.get_brand_mention_stats()
    return render_template('brand_intel.html',
                         mentions=mentions,
                         stats=stats,
                         page='brand-intel')

@app.route('/mash-analytics')
def mash_analytics_page():
    customer_email_count = db.get_customer_email_count()
    return render_template('mash_analytics.html',
                         customer_email_count=customer_email_count,
                         page='mash-analytics')

@app.route('/outreach')
def outreach_page():
    contacts = db.get_outreach_contacts(limit=500)
    stats = db.get_outreach_stats()
    customer_email_count = db.get_customer_email_count()
    return render_template('outreach.html',
                         contacts=contacts,
                         stats=stats,
                         customer_email_count=customer_email_count,
                         page='outreach')

@app.route('/ai-studio')
def ai_studio_page():
    openai_p = db.get_platform('openai')
    runway_p = db.get_platform('runway')
    return render_template('ai_studio.html',
                         page='ai-studio',
                         openai_connected=openai_p['connected'] if openai_p else False,
                         runway_connected=runway_p['connected'] if runway_p else False)

@app.route('/creative')
def creative_page():
    return redirect('/ai-studio')

# ============================================================
# API ROUTES - POSTS
# ============================================================

@app.route('/api/posts', methods=['POST'])
def api_create_post():
    try:
        content = request.form.get('content', '').strip()
        if not content:
            return jsonify({'success': False, 'error': 'Content is required'}), 400
        
        hashtags = request.form.get('hashtags', '').strip()
        link_url = request.form.get('link_url', '').strip()
        status = request.form.get('status', 'draft')
        scheduled_at = request.form.get('scheduled_at', '').strip()
        platforms = request.form.getlist('platforms')
        notes = request.form.get('notes', '').strip()
        ai_generated = int(request.form.get('ai_generated', 0))
        
        # Append hashtags to content if separate
        full_content = content
        if hashtags:
            full_content = f"{content}\n\n{hashtags}"
        
        # Handle image upload
        image_path = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{int(time_module.time())}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_path = f'/static/uploads/{filename}'
        
        # Handle scheduled time
        if status == 'scheduled' and scheduled_at:
            try:
                # Convert from datetime-local format
                scheduled_at = datetime.strptime(scheduled_at, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        elif status == 'scheduled' and not scheduled_at:
            status = 'draft'  # Can't schedule without a time
        
        post_id = db.create_post(
            content=full_content,
            image_path=image_path,
            status=status,
            hashtags=hashtags,
            link_url=link_url,
            scheduled_at=scheduled_at if status == 'scheduled' else None,
            platforms=platforms,
            ai_generated=ai_generated,
            notes=notes
        )
        
        return jsonify({'success': True, 'post_id': post_id, 'status': status})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def api_update_post(post_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        db.update_post(post_id, **data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def api_delete_post(post_id):
    try:
        db.delete_post(post_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>/publish', methods=['POST'])
def api_publish_post(post_id):
    """Publish a post to its selected platforms"""
    try:
        post = db.get_post(post_id)
        if not post:
            return jsonify({'success': False, 'error': 'Post not found'}), 404
        
        results = []
        all_platforms = db.get_platforms()
        platform_lookup = {p['name']: p for p in all_platforms}
        
        target_platforms = post.get('platforms', [])
        if not target_platforms:
            return jsonify({'success': False, 'error': 'No platforms selected for this post'}), 400
        
        image_full_path = ''
        if post.get('image_path'):
            image_full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                           post['image_path'].lstrip('/'))
        
        for pp in target_platforms:
            platform_name = pp['platform_name']
            platform_config = platform_lookup.get(platform_name, {})
            
            if not platform_config.get('connected'):
                results.append({
                    'platform': platform_name,
                    'success': False,
                    'error': f'{platform_name} is not connected'
                })
                continue
            
            # Build config dict for the publisher
            config = {
                'api_key': platform_config.get('api_key', ''),
                'api_secret': platform_config.get('api_secret', ''),
                'access_token': platform_config.get('access_token', ''),
                'refresh_token': platform_config.get('refresh_token', ''),
                'username': platform_config.get('username', ''),
            }
            
            # Add any additional config
            try:
                additional = json.loads(platform_config.get('additional_config', '{}'))
                config.update(additional)
            except:
                pass
            
            result = publish_to_platform(platform_name, post['content'], image_full_path, config)
            results.append(result.to_dict())
            
            if result.success:
                db.mark_post_published(post_id, platform_name, result.post_id)
            else:
                db.mark_post_failed(post_id, platform_name, result.error)
        
        # Update post status
        any_success = any(r['success'] for r in results)
        all_failed = all(not r['success'] for r in results)
        
        if all_failed:
            db.update_post(post_id, status='failed')
        elif any_success:
            db.update_post(post_id, status='published', 
                          published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
        
        return jsonify({'success': any_success, 'results': results})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>/duplicate', methods=['POST'])
def api_duplicate_post(post_id):
    """Duplicate a post as a new draft"""
    try:
        post = db.get_post(post_id)
        if not post:
            return jsonify({'success': False, 'error': 'Post not found'}), 404
        
        platform_names = [p['platform_name'] for p in post.get('platforms', [])]
        new_id = db.create_post(
            content=post['content'],
            image_path=post.get('image_path', ''),
            status='draft',
            hashtags=post.get('hashtags', ''),
            link_url=post.get('link_url', ''),
            platforms=platform_names,
            notes=f"Duplicated from post #{post_id}"
        )
        
        return jsonify({'success': True, 'post_id': new_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ROUTES - PLATFORMS
# ============================================================

@app.route('/api/platforms/<name>', methods=['PUT'])
def api_update_platform(n):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        db.update_platform(n, **data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/platforms/<name>/test', methods=['POST'])
def api_test_platform(n):
    """Test a platform connection"""
    try:
        platform = db.get_platform(n)
        if not platform:
            return jsonify({'success': False, 'error': 'Platform not found'}), 404
        
        if n == 'bluesky':
            from publisher import BlueskyPublisher
            result = BlueskyPublisher.authenticate(
                platform.get('username', ''),
                platform.get('api_key', '')
            )
            if result['success']:
                db.update_platform(n, connected=1, username=result['handle'])
                return jsonify({'success': True, 'message': f"Connected as @{result['handle']}"})
            else:
                db.update_platform(n, connected=0)
                return jsonify({'success': False, 'error': result['error']})
        
        elif n == 'twitter':
            # Simple validation - check credentials are provided
            if platform.get('api_key') and platform.get('access_token'):
                db.update_platform(n, connected=1)
                return jsonify({'success': True, 'message': 'Credentials saved. Will verify on first post.'})
            else:
                return jsonify({'success': False, 'error': 'API Key and Access Token required'})
        
        elif n == 'facebook':
            if platform.get('access_token') and platform.get('username'):
                db.update_platform(n, connected=1)
                return jsonify({'success': True, 'message': 'Credentials saved. Will verify on first post.'})
            else:
                return jsonify({'success': False, 'error': 'Page Access Token and Page ID required'})
        
        elif n == 'linkedin':
            if platform.get('access_token') and platform.get('username'):
                db.update_platform(n, connected=1)
                return jsonify({'success': True, 'message': 'Credentials saved. Will verify on first post.'})
            else:
                return jsonify({'success': False, 'error': 'Access Token and Author URN required'})
        
        return jsonify({'success': False, 'error': 'Unknown platform'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/platforms/<name>/disconnect', methods=['POST'])
def api_disconnect_platform(n):
    try:
        db.update_platform(n, connected=0, api_key='', api_secret='', 
                          access_token='', refresh_token='', username='')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ROUTES - TEMPLATES
# ============================================================

@app.route('/api/templates', methods=['POST'])
def api_create_template():
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        category = data.get('category', 'general')
        hashtags = data.get('hashtags', '')
        
        if not title or not content:
            return jsonify({'success': False, 'error': 'Title and content required'}), 400
        
        template_id = db.create_template(title, content, category, hashtags)
        return jsonify({'success': True, 'template_id': template_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def api_delete_template(template_id):
    try:
        db.delete_template(template_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ROUTES - HASHTAGS
# ============================================================

@app.route('/api/hashtags', methods=['POST'])
def api_create_hashtag_group():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        hashtags = data.get('hashtags', '').strip()
        
        if not name or not hashtags:
            return jsonify({'success': False, 'error': 'Name and hashtags required'}), 400
        
        group_id = db.create_hashtag_group(name, hashtags)
        return jsonify({'success': True, 'group_id': group_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hashtags/<int:group_id>', methods=['DELETE'])
def api_delete_hashtag_group(group_id):
    try:
        db.delete_hashtag_group(group_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ROUTES - AI CONTENT GENERATION
# ============================================================

@app.route('/api/generate', methods=['POST'])
def api_generate_content():
    """Generate content using Claude API (better writing quality)"""
    try:
        data = request.get_json()
        prompt_type = data.get('type', 'social_post')
        topic = data.get('topic', '')
        tone = data.get('tone', 'professional')
        platform = data.get('platform', 'general')
        custom_prompt = data.get('custom_prompt', '')
        
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not anthropic_key:
            # Fall back to OpenAI if no Anthropic key
            api_key = get_api_key('openai')
            if not api_key:
                return jsonify({
                    'success': False, 
                    'error': 'No API key configured. Add ANTHROPIC_API_KEY or OPENAI_API_KEY in Render environment variables.'
                }), 400
            use_openai = True
        else:
            use_openai = False
        
        system_prompt = """You are a social media content creator for Forbidden Bourbon, 
a premium wheated bourbon whiskey brand. The bourbon is crafted by Master Distiller Marianne Eaves 
in Kentucky, using white corn, white wheat, and a high percentage of barley. 
The brand has two products: Small Batch Select and Single Barrel Bourbon.
Website: drinkforbidden.com | Shop: shop.drinkforbidden.com

Key brand values: Innovation within tradition, craftsmanship, bold flavors, 
Southern inspiration, premium quality. The tagline is "A Twist on Tradition."

Write engaging, authentic social media content. Never be generic or salesy. 
Be specific about the bourbon's qualities. Match the specified tone and platform constraints."""

        char_limits = {
            'twitter': 'Keep under 280 characters (including hashtags).',
            'bluesky': 'Keep under 300 characters. Bluesky audience is tech-savvy and authentic.',
            'facebook': 'Can be longer, 1-3 paragraphs. Engaging and shareable.',
            'linkedin': 'Professional tone. 1-2 paragraphs. Industry-relevant.',
            'instagram': 'Visual-first caption. Engaging, use line breaks. Can be longer.',
            'general': 'Versatile post that works across platforms. Keep under 280 characters for maximum compatibility.'
        }
        
        tone_instructions = {
            'professional': 'Tone: Sophisticated, refined, authoritative.',
            'casual': 'Tone: Friendly, approachable, conversational. Like talking to a friend at a bar.',
            'playful': 'Tone: Fun, witty, unexpected. Surprise the reader.',
            'educational': 'Tone: Informative, interesting facts, teach something about bourbon.',
            'luxury': 'Tone: Premium, exclusive, aspirational. Make the reader feel special.',
        }
        
        if custom_prompt:
            user_message = custom_prompt
        else:
            platform_note = char_limits.get(platform, char_limits['general'])
            tone_note = tone_instructions.get(tone, tone_instructions['professional'])
            
            prompts = {
                'social_post': f"Write a social media post about: {topic or 'Forbidden Bourbon'}. {platform_note} {tone_note} Include 3-5 relevant hashtags at the end.",
                'thread': f"Write a 3-5 post thread about: {topic or 'Forbidden Bourbon'}. Separate each post with ---. {tone_note}",
                'caption': f"Write an Instagram caption for a photo of: {topic or 'Forbidden Bourbon bottle'}. {tone_note} Include relevant hashtags.",
                'blog_intro': f"Write a blog post introduction (2-3 paragraphs) about: {topic or 'bourbon tasting'}. {tone_note}",
                'engagement': f"Write an engagement-focused question or poll about: {topic or 'bourbon preferences'}. {tone_note} Make people want to comment.",
            }
            
            user_message = prompts.get(prompt_type, prompts['social_post'])
        
        import requests as req
        
        if use_openai:
            resp = req.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'gpt-4o-mini',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_message}
                    ],
                    'max_tokens': 1024,
                    'temperature': 0.8
                },
                timeout=30
            )
            if resp.status_code == 200:
                generated_text = resp.json()['choices'][0]['message']['content']
                return jsonify({'success': True, 'content': generated_text.strip()})
        else:
            resp = req.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': anthropic_key,
                    'anthropic-version': '2023-06-01',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 1024,
                    'system': system_prompt,
                    'messages': [{'role': 'user', 'content': user_message}]
                },
                timeout=30
            )
            if resp.status_code == 200:
                response_data = resp.json()
                generated_text = ''
                for block in response_data.get('content', []):
                    if block.get('type') == 'text':
                        generated_text += block['text']
                return jsonify({'success': True, 'content': generated_text.strip()})
        
        return jsonify({'success': False, 'error': f'API Error: {resp.status_code} - {resp.text}'}), 500
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# API ROUTES - AI IMAGE & VIDEO GENERATION
# ============================================================

@app.route('/api/ai/status', methods=['GET'])
def api_ai_status():
    """Check if AI API keys are configured"""
    return jsonify({
        'openai': bool(get_api_key('openai')),
        'runway': bool(get_api_key('runway'))
    })

@app.route('/api/ai/save-key', methods=['POST'])
def api_ai_save_key():
    """Save an AI API key"""
    try:
        data = request.get_json()
        provider = data.get('provider', '')
        key = data.get('key', '').strip()
        
        if provider not in ('openai', 'runway'):
            return jsonify({'success': False, 'error': 'Invalid provider'}), 400
        if not key:
            return jsonify({'success': False, 'error': 'Key is required'}), 400
        
        # Check if platform exists
        existing = db.get_platform(provider)
        if existing:
            db.update_platform(provider, api_key=key, connected=True)
        else:
            db.add_platform(provider, api_key=key, connected=True)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def _get_bottle_cutout(source_path, api_key=None):
    """
    Return a clean RGBA PIL Image of the bottle with background removed.

    Method 1 — remove.bg API (pixel-perfect segmentation, zero hallucination).
      Pure computer vision: classifies every pixel as foreground/background.
      Your exact bottle pixels come through untouched — label, badge, glass,
      liquid color, all identical to the source photo. Cached after first call.
      Requires REMOVEBG_API_KEY env var on Render.

    Method 2 — PIL color-range fallback.
      Used only if remove.bg key is absent or call fails. Less precise but
      never hallucinates — still your real pixels, just rougher edges.
    """
    from PIL import Image as PILImage
    import io as _io
    import requests as _req

    cache_dir = os.path.join(app.static_folder, 'uploads', 'cutout_cache')
    os.makedirs(cache_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(source_path))[0]
    cache_path = os.path.join(cache_dir, f"cutout_{base_name}.png")

    if os.path.exists(cache_path):
        print(f"[Cutout] Using cached cutout: {cache_path}")
        return PILImage.open(cache_path).convert('RGBA')

    print(f"[Cutout] Removing background from: {source_path}")

    # ---- PRE-PROCESS: Ensure source is at least 1024px on shortest side ----
    # Input image resolution directly determines output quality.
    # If source is too small, upscale it before sending to remove.bg.
    _MIN_DIM = 1024
    try:
        _src = PILImage.open(source_path).convert('RGBA')
        _w, _h = _src.size
        if min(_w, _h) < _MIN_DIM:
            _scale_up = _MIN_DIM / min(_w, _h)
            _new_w = int(_w * _scale_up)
            _new_h = int(_h * _scale_up)
            _src = _src.resize((_new_w, _new_h), PILImage.LANCZOS)
            _upscale_buf = _io.BytesIO()
            _src.save(_upscale_buf, format='PNG')
            img_bytes = _upscale_buf.getvalue()
            print(f"[Cutout] Upscaled source from {_w}x{_h} → {_new_w}x{_new_h} before remove.bg")
        else:
            with open(source_path, 'rb') as f:
                img_bytes = f.read()
            print(f"[Cutout] Source size OK: {_w}x{_h}")
    except Exception as _e:
        print(f"[Cutout] Pre-process failed, using raw file: {_e}")
        with open(source_path, 'rb') as f:
            img_bytes = f.read()

    # ---- METHOD 1: remove.bg API ----
    removebg_key = os.environ.get('REMOVEBG_API_KEY', '')
    if removebg_key:
        try:
            resp = _req.post(
                'https://api.remove.bg/v1.0/removebg',
                headers={'X-Api-Key': removebg_key},
                files={'image_file': ('bottle.png', img_bytes, 'image/png')},
                data={'size': 'auto'},
                timeout=60
            )

            if resp.status_code == 200:
                cutout = PILImage.open(_io.BytesIO(resp.content)).convert('RGBA')
                cutout.save(cache_path)
                print(f"[Cutout] remove.bg success — {cutout.size}, saved to {cache_path}")
                return cutout
            else:
                err = resp.json().get('errors', [{}])[0].get('title', resp.text[:200])
                print(f"[Cutout] remove.bg failed ({resp.status_code}): {err}")
        except Exception as e:
            print(f"[Cutout] remove.bg exception: {e}")
    else:
        print("[Cutout] REMOVEBG_API_KEY not set — falling back to PIL removal")

    # ---- METHOD 2: PIL color-range fallback ----
    try:
        print("[Cutout] Using PIL color-range removal (rough edges, real pixels)")
        img = PILImage.open(source_path).convert('RGBA')
        data = img.load()
        w, h = img.size
        corners = [data[0,0], data[w-1,0], data[0,h-1], data[w-1,h-1]]
        bg_samples = [(r,g,b) for (r,g,b,a) in corners if a > 200]
        if not bg_samples:
            bg_r, bg_g, bg_b = 255, 255, 255
        else:
            bg_r = sum(c[0] for c in bg_samples) // len(bg_samples)
            bg_g = sum(c[1] for c in bg_samples) // len(bg_samples)
            bg_b = sum(c[2] for c in bg_samples) // len(bg_samples)
        threshold = 35
        for y in range(h):
            for x in range(w):
                r, g, b, a = data[x, y]
                dist = ((r-bg_r)**2 + (g-bg_g)**2 + (b-bg_b)**2) ** 0.5
                if dist < threshold:
                    data[x, y] = (r, g, b, 0)
        img.save(cache_path)
        print(f"[Cutout] PIL color-range done, saved to {cache_path}")
        return img
    except Exception as e:
        print(f"[Cutout] PIL fallback failed: {e}")
        return PILImage.open(source_path).convert('RGBA')


def _composite_bottle_on_bg(bottle_cutout, background_img, position='center', scale=0.72):
    """
    Composite a transparent-background bottle cutout onto an AI background.
    Adds realistic Gaussian drop shadow for integration.
    Returns final PIL Image (RGB).
    """
    from PIL import Image as PILImage, ImageFilter
    import numpy as np_local
    
    bg = background_img.convert('RGBA')
    bg_w, bg_h = bg.size
    
    # Scale bottle to target height
    scale = max(0.4, min(0.88, float(scale)))
    target_h = int(bg_h * scale)
    aspect = bottle_cutout.width / bottle_cutout.height
    target_w = int(target_h * aspect)
    bottle = bottle_cutout.resize((target_w, target_h), PILImage.LANCZOS)
    
    # Position
    if position == 'left':
        x = int(bg_w * 0.12)
    elif position == 'right':
        x = bg_w - target_w - int(bg_w * 0.12)
    else:
        x = (bg_w - target_w) // 2
    y = bg_h - target_h - int(bg_h * 0.04)  # 4% margin from bottom
    
    # --- SHADOW ---
    # 1. Extract bottle alpha silhouette
    shadow_layer = PILImage.new('RGBA', (bg_w, bg_h), (0,0,0,0))
    # Solid dark fill using bottle alpha as mask
    shadow_color = PILImage.new('RGBA', bottle.size, (20, 10, 5, 180))  # warm dark shadow
    shadow_layer.paste(shadow_color, (x, y), bottle.split()[3])
    
    # 2. Gaussian blur the shadow for realism
    from PIL import ImageFilter
    shadow_blur_radius = max(12, int(target_w * 0.04))  # proportional to bottle width
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur_radius))
    
    # 3. Offset shadow slightly down-right (light source is upper-left)
    shadow_offset_x = int(target_w * 0.025)
    shadow_offset_y = int(target_h * 0.015)
    shadow_final = PILImage.new('RGBA', (bg_w, bg_h), (0,0,0,0))
    shadow_final.paste(shadow_layer, (shadow_offset_x, shadow_offset_y))
    
    # --- COMPOSITE: bg → shadow → bottle ---
    result = bg.copy()
    result = PILImage.alpha_composite(result, shadow_final)
    bottle_layer = PILImage.new('RGBA', (bg_w, bg_h), (0,0,0,0))
    bottle_layer.paste(bottle, (x, y), bottle.split()[3])
    result = PILImage.alpha_composite(result, bottle_layer)
    
    return result.convert('RGB')


def _ai_composite_bottle_on_bg(bottle_cutout, background_img, api_key, size='1024x1536', quality='high', position='center', scale=0.65):
    """
    AI-powered composite: passes both bottle cutout + background to gpt-image-1.5 Edit API.
    Uses input_fidelity=high so the bottle label/shape is preserved exactly.
    The model handles lighting match, contact shadows, rim lighting, and surface reflections natively.
    Returns final PIL Image (RGB), or None if the API call fails.
    """
    from PIL import Image as PILImage
    import io as _io
    import requests as _req
    import base64 as _b64

    try:
        # Convert bottle cutout (RGBA) to PNG bytes — Image 1 (highest fidelity slot)
        buf1 = _io.BytesIO()
        bottle_cutout.save(buf1, format='PNG')
        buf1.seek(0)

        # Convert background (RGBA/RGB) to PNG bytes — Image 2
        buf2 = _io.BytesIO()
        background_img.convert('RGBA').save(buf2, format='PNG')
        buf2.seek(0)

        # Build position instruction — Rule of Thirds for left/right, centered for center
        if position == 'left':
            placement = (
                "Position the bottle in the LEFT THIRD of the frame, "
                "leaving generous negative space on the right side for advertising copy. "
                "The bottle base should sit on the surface at the left third vertical line."
            )
        elif position == 'right':
            placement = (
                "Position the bottle in the RIGHT THIRD of the frame, "
                "leaving generous negative space on the left side for advertising copy. "
                "The bottle base should sit on the surface at the right third vertical line."
            )
        else:
            placement = (
                "Position the bottle centered horizontally in the frame. "
                "The bottle base should sit centered on the surface."
            )

        # Scale instruction
        scale = max(0.5, min(0.80, float(scale)))
        scale_pct = int(scale * 100)
        scale_instruction = f"The bottle should occupy approximately {scale_pct}% of the frame height."

        composite_prompt = (
            "Image 1 is a bourbon whiskey bottle with a transparent background — "
            "exact label, shape, colors, and brand markings must be preserved perfectly. "
            "Image 2 is a dramatic luxury product photography background scene. "
            "\n\n"
            f"{placement} {scale_instruction} "
            "The bottle base must rest naturally on the surface — do not float it. "
            "\n\n"
            "LIGHTING: Match the bottle's lighting to the scene from Image 2. "
            "Add bright rim lighting — thin bright highlights running vertically down both "
            "left and right edges of the bottle glass, characteristic of professional spirits "
            "studio photography with a vertical softbox. "
            "The bottle glass should pick up warm ambient color tones from the environment. "
            "Add a soft natural contact shadow directly beneath the bottle base. "
            "Add a faint realistic reflection of the bottle on the surface below it. "
            "\n\n"
            "PRESERVE: The bottle label text, logo, badge, shape, proportions, and liquid color "
            "must remain 100% identical to Image 1 — do not alter, hallucinate, or regenerate them. "
            "Do NOT add any extra text, objects, or watermarks. "
            "Commercial spirits advertisement. Professional product photography. Photorealistic."
        )

        print(f"[AI Composite] Sending 2-image Edit API call with input_fidelity=high, quality={quality}")

        resp = _req.post(
            'https://api.openai.com/v1/images/edits',
            headers={'Authorization': f'Bearer {api_key}'},
            files=[
                ('image[]', ('bottle.png', buf1, 'image/png')),
                ('image[]', ('background.png', buf2, 'image/png')),
            ],
            data={
                'model': 'gpt-image-1.5',
                'prompt': composite_prompt,
                'size': size,
                'quality': quality,
                'input_fidelity': 'high',
                'n': '1',
                'output_format': 'png',
            },
            timeout=180
        )

        if resp.status_code == 200:
            result = resp.json()
            img_b64 = result.get('data', [{}])[0].get('b64_json')
            if img_b64:
                final = PILImage.open(_io.BytesIO(_b64.b64decode(img_b64))).convert('RGB')
                print(f"[AI Composite] Success — {final.size}")
                return final
            else:
                print(f"[AI Composite] No image data in response")
                return None
        else:
            try:
                err = resp.json().get('error', {}).get('message', resp.text[:300])
            except Exception:
                err = resp.text[:300]
            print(f"[AI Composite] Edit API failed ({resp.status_code}): {err}")
            return None

    except Exception as e:
        import traceback
        print(f"[AI Composite] Exception: {traceback.format_exc()}")
        return None


@app.route('/api/ai/generate-image', methods=['POST'])
def api_generate_image():
    """
    TRUE COMPOSITE: 3-step pipeline for pixel-perfect brand accuracy.
    Step 1: remove.bg removes background from hi-res studio photo → exact bottle cutout
    Step 2: gpt-image-1.5 generates ONLY the background scene (no bottle at all)
    Step 3: gpt-image-1.5 Edit API composites bottle into scene with AI lighting/shadows
    Step 3b: PIL composite fallback if Edit API fails
    Result: 100% accurate bottle/label + beautiful AI backgrounds, social-media ready
    """
    try:
        data = request.get_json()
        prompt = data.get('prompt', '')
        size = data.get('size', '1024x1536')
        quality = data.get('quality', 'high')
        use_reference = data.get('use_reference', True)
        bottle_position = data.get('bottle_position', 'center')
        bottle_scale = data.get('bottle_scale', 0.72)
        bottle_type = data.get('bottle_type', 'small_batch')
        
        if not prompt:
            return jsonify({'success': False, 'error': 'Prompt required'}), 400
        
        api_key = get_api_key('openai')
        if not api_key:
            return jsonify({'success': False, 'error': 'OpenAI API key not configured. Set OPENAI_API_KEY in Render env vars.'}), 400
        
        import base64 as b64
        import requests as req
        from PIL import Image as PILImage, ImageFilter
        import io
        
        gpt_size = size if size in ('1024x1024', '1024x1536', '1536x1024') else '1024x1536'
        image_url = None
        model_used = None
        errors = []
        
        # =====================================================
        # STEP 1: GET BOTTLE CUTOUT (real photo, exact pixels)
        # =====================================================
        bottle_cutout = None
        if use_reference:
            if bottle_type == 'single_barrel':
                source_candidates = [
                    os.path.join(app.static_folder, 'photos', 'gallery', 'Golden_Front_57_LightBG_V1.png'),
                    os.path.join(app.static_folder, 'photos', 'gallery', 'Golden_Front_58_LightBG_V1.png'),
                    os.path.join(app.static_folder, 'photos', 'gallery', 'SingleBarrel1.jpg'),
                    os.path.join(app.static_folder, 'photos', 'SingleBarrel1.jpg'),
                ]
            else:
                source_candidates = [
                    os.path.join(app.static_folder, 'photos', 'gallery', 'Black_Front_LightBG_V1.png'),
                    os.path.join(app.static_folder, 'photos', 'gallery', 'SmallBatch1.jpg'),
                    os.path.join(app.static_folder, 'photos', 'SmallBatch1.jpg'),
                    os.path.join(app.static_folder, 'photos', 'bottle-ref.jpg'),
                ]
            
            # Log all candidates so we can debug path issues in Render logs
            for c in source_candidates:
                print(f"[AI Studio] Checking photo: {os.path.basename(c)} — exists: {os.path.exists(c)}")
            
            source_path = next((c for c in source_candidates if os.path.exists(c)), None)
            
            if source_path:
                try:
                    bottle_cutout = _get_bottle_cutout(source_path, api_key=api_key)
                    print(f"[AI Studio] Got bottle cutout: {bottle_cutout.size}")
                except Exception as e:
                    errors.append(f"Cutout: {str(e)[:200]}")
                    print(f"[AI Studio] Cutout failed: {e}")
            else:
                all_paths = [os.path.basename(c) for c in source_candidates]
                errors.append(f"No studio photo found. Tried: {all_paths}")
                print(f"[AI Studio] No bottle photo found. Candidates: {source_candidates}")
        
        # =====================================================
        # STEP 2: GENERATE BACKGROUND SCENE (AI, no bottle)
        # =====================================================
        background_img = None
        
        # Background prompt: describe the scene WITHOUT any bottle/product
        # The bottle is composited in Step 3 — AI only draws the environment
        # Add composition hint so negative space aligns with bottle placement
        if bottle_position == 'left':
            comp_hint = "Richer background detail on the right side, open negative space on the left third for a product. "
        elif bottle_position == 'right':
            comp_hint = "Richer background detail on the left side, open negative space on the right third for a product. "
        else:
            comp_hint = "Balanced composition with open negative space in the center foreground for a product. "

        bg_scene_prompt = (
            f"{prompt}. "
            "Environment only — no bottles, no products, no objects. "
            "Just the surface, background, and lighting. "
            "Flat polished surface in the foreground for a luxury product to rest on. "
            f"{comp_hint}"
            "High-end spirits advertisement environment. "
            "Cinematic lighting, rich atmospheric depth. "
            "Shot with 35mm lens, shallow depth of field, moody and dramatic. "
            "Photorealistic, commercial photography quality."
        )
        
        print(f"[AI Studio] Generating background with gpt-image-1.5...")
        try:
            resp = req.post(
                'https://api.openai.com/v1/images/generations',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': 'gpt-image-1.5',
                    'prompt': bg_scene_prompt,
                    'n': 1,
                    'size': gpt_size,
                    'quality': quality if quality in ('low', 'medium', 'high') else 'high',
                    'output_format': 'png',
                },
                timeout=120
            )
            
            if resp.status_code == 200:
                result = resp.json()
                img_b64 = result.get('data', [{}])[0].get('b64_json')
                if img_b64:
                    bg_bytes = b64.b64decode(img_b64)
                    background_img = PILImage.open(io.BytesIO(bg_bytes)).convert('RGBA')
                    print(f"[AI Studio] Background generated: {background_img.size}")
                else:
                    errors.append("Background generation: no image data")
            else:
                err_msg = 'Unknown error'
                try:
                    err_msg = resp.json().get('error', {}).get('message', resp.text[:500])
                except:
                    err_msg = resp.text[:500]
                errors.append(f"Background generation: {err_msg}")
                print(f"[AI Studio] Background generation failed ({resp.status_code}): {err_msg}")
        except Exception as e:
            errors.append(f"Background generation: {str(e)[:200]}")
            print(f"[AI Studio] Background generation exception: {e}")
        
        # =====================================================
        # STEP 3: AI COMPOSITE — gpt-image-1.5 Edit with both images
        # Handles lighting match, contact shadows, surface reflections.
        # Falls back to PIL composite if Edit API fails.
        # =====================================================
        if bottle_cutout and background_img:
            final = None
            composite_method = None

            # --- PRIMARY: AI composite via Edit API ---
            try:
                final = _ai_composite_bottle_on_bg(
                    bottle_cutout, background_img,
                    api_key=api_key,
                    size=gpt_size,
                    quality=quality if quality in ('low', 'medium', 'high') else 'high',
                    position=bottle_position,
                    scale=float(bottle_scale or 0.65)
                )
                if final:
                    composite_method = f'ai-composite-edit+rembg ({bottle_type})'
            except Exception as e:
                import traceback
                errors.append(f"AI Composite: {str(e)[:200]}")
                print(f"[AI Studio] AI composite exception: {traceback.format_exc()}")

            # --- FALLBACK: PIL composite ---
            if final is None:
                print(f"[AI Studio] AI composite failed — falling back to PIL composite")
                try:
                    final = _composite_bottle_on_bg(
                        bottle_cutout, background_img,
                        position=bottle_position,
                        scale=float(bottle_scale or 0.72)
                    )
                    composite_method = f'pil-composite-fallback+rembg ({bottle_type})'
                except Exception as e:
                    import traceback
                    errors.append(f"PIL Composite fallback: {str(e)[:200]}")
                    print(f"[AI Studio] PIL fallback exception: {traceback.format_exc()}")

            if final:
                filename = f"ai-composite-{int(time_module.time())}.png"
                filepath = os.path.join(app.static_folder, 'uploads', filename)
                final.save(filepath, quality=95, optimize=False)
                image_url = f"/static/uploads/{filename}"
                model_used = composite_method
                print(f"[AI Studio] Composite saved ({composite_method}): {filepath}")
        
        # If reference failed but we have a background, save that at minimum
        elif background_img and not bottle_cutout:
            filename = f"ai-bg-{int(time_module.time())}.png"
            filepath = os.path.join(app.static_folder, 'uploads', filename)
            background_img.convert('RGB').save(filepath, quality=95)
            image_url = f"/static/uploads/{filename}"
            model_used = 'gpt-image-1.5-background-only'
        
        # =====================================================
        # FALLBACK: Text-only with bottle description
        # =====================================================
        if not image_url:
            print(f"[AI Studio] Falling back to text-only generation...")
            try:
                if bottle_type == 'single_barrel':
                    bottle_desc = (
                        "Forbidden Bourbon Single Barrel bottle — hexagonal faceted crystal glass, "
                        "gold/copper label reading 'FORBIDDEN' in ornate serif letters, "
                        "'SINGLE BARREL STRAIGHT BOURBON WHISKEY', barrel badge emblem, "
                        "dark wooden stopper cap, rich amber liquid."
                    )
                else:
                    bottle_desc = (
                        "Forbidden Bourbon bottle — hexagonal faceted crystal glass, "
                        "black label reading 'FORBIDDEN' in ornate silver serif letters, "
                        "'STRAIGHT BOURBON WHISKEY', barrel badge emblem, "
                        "dark wooden stopper cap, rich deep amber liquid."
                    )
                
                text_prompt = (
                    f"Ultra-premium spirits product photography: {prompt}. "
                    f"{bottle_desc} "
                    "Cinematic luxury advertisement. Photorealistic, commercial photography, "
                    "shot with 35mm lens, dramatic lighting."
                )
                
                resp = req.post(
                    'https://api.openai.com/v1/images/generations',
                    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    json={
                        'model': 'gpt-image-1.5',
                        'prompt': text_prompt,
                        'n': 1,
                        'size': gpt_size,
                        'quality': quality if quality in ('low', 'medium', 'high') else 'high',
                    },
                    timeout=120
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    img_data_resp = result['data'][0]
                    if img_data_resp.get('b64_json'):
                        img_bytes = b64.b64decode(img_data_resp['b64_json'])
                        filename = f"ai-gen-{int(time_module.time())}.png"
                        filepath = os.path.join(app.static_folder, 'uploads', filename)
                        with open(filepath, 'wb') as f:
                            f.write(img_bytes)
                        image_url = f"/static/uploads/{filename}"
                    model_used = 'gpt-image-1.5 (text-only fallback)'
                else:
                    err_msg = resp.json().get('error', {}).get('message', resp.text[:300])
                    errors.append(f"Text-only fallback: {err_msg}")
            except Exception as e:
                errors.append(f"Text-only fallback: {str(e)[:200]}")
        
        if not image_url:
            error_detail = ' | '.join(errors) if errors else 'No image data returned'
            return jsonify({'success': False, 'error': f'Image generation failed: {error_detail}'}), 500
        
        # Read image bytes into base64 — stored in DB so gallery survives Render restarts
        _image_b64 = ''
        try:
            _img_path = app.static_folder + image_url[len('/static'):]
            with open(_img_path, 'rb') as _f:
                _image_b64 = b64.b64encode(_f.read()).decode('utf-8')
        except Exception as _e:
            print(f"[Gallery] Could not read image for b64 storage: {_e}")
        
        _save_gallery_id = _save_to_gallery('image', image_url, prompt, bg_scene_prompt if use_reference else prompt, bottle_type if use_reference else '', image_data=_image_b64)
        
        return jsonify({
            'success': True,
            'image_url': image_url,
            'revised_prompt': bg_scene_prompt if use_reference else prompt,
            'model': model_used,
            'used_reference': bool(bottle_cutout and background_img),
            'gallery_id': _save_gallery_id,
            'debug_errors': errors  # visible in browser devtools network tab
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


def _maybe_resize_for_runway(abs_path, rel_url, portrait=True, max_px=1280):
    """
    Crop to target aspect ratio (9:16 portrait or 16:9 landscape) then scale to max_px.
    Runway requires both dimensions < 8000px and aspect ratio 0.5–2.0.
    We normalise every source image to exactly 720×1280 (portrait) or 1280×720 (landscape)
    so Runway always gets a pixel-perfect match for the requested ratio.
    """
    try:
        from PIL import Image as _PILImage
        import hashlib
        img = _PILImage.open(abs_path).convert('RGB')
        w, h = img.size

        # Target dimensions
        if portrait:
            tgt_w, tgt_h = 720, 1280
        else:
            tgt_w, tgt_h = 1280, 720
        tgt_ratio = tgt_w / tgt_h  # 0.5625 for portrait

        # Crop to target aspect ratio
        # For tall bottle images (portrait source → portrait target) bias crop to TOP
        # so the bottle cap is always included and base gets trimmed, not the label/cap
        src_ratio = w / h
        if abs(src_ratio - tgt_ratio) > 0.01:
            if src_ratio > tgt_ratio:
                # Source is wider than target — crop width (centre)
                new_w = int(h * tgt_ratio)
                x0 = (w - new_w) // 2
                img = img.crop((x0, 0, x0 + new_w, h))
            else:
                # Source is taller than target — crop height
                new_h = int(w / tgt_ratio)
                # Bias: start from top (y0=0) so bottle cap is never cut off
                # Only trim from the bottom
                y0 = 0
                img = img.crop((0, y0, w, y0 + new_h))
            print(f"[Runway] Cropped {w}x{h} → {img.size[0]}x{img.size[1]} (ratio {tgt_ratio:.3f})")

        # Scale to exact target size
        img = img.resize((tgt_w, tgt_h), _PILImage.LANCZOS)

        # Save thumb
        thumb_name = 'runway_thumb_' + hashlib.md5(abs_path.encode()).hexdigest()[:8] + '.jpg'
        thumb_abs = os.path.join(os.path.dirname(abs_path), thumb_name)
        img.save(thumb_abs, 'JPEG', quality=88, optimize=True)

        thumb_rel = '/static/' + thumb_abs[thumb_abs.index('static/') + 7:]
        print(f"[Runway] Ready for Runway: {tgt_w}x{tgt_h} → {thumb_rel}")
        return thumb_rel
    except Exception as e:
        print(f"[Runway] Resize failed ({e}), using original")
        return rel_url


@app.route('/api/ai/generate-video', methods=['POST'])
def api_generate_video():
    """
    Generate a video using Runway ML (primary) or Luma Dream Machine (fallback).
    Runway gen4_turbo: image→video, cinematic product shots, $0.25/5s
    Luma Ray2: fast, cinematic, product explainers, ~$0.17-0.54/5s
    """
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        duration = data.get('duration', 5)
        source_image = data.get('source_image', None)
        provider = data.get('provider', 'runway')   # 'runway' or 'luma'
        model = data.get('model', 'gen4_turbo')     # gen4_turbo, gen4.5, veo3.1_fast
        # Default to portrait (9:16) for Instagram Reels / TikTok / Shorts
        portrait = data.get('portrait', True)
        bottle_type = data.get('bottle_type', 'small_batch')  # 'small_batch' or 'single_barrel'

        # ── SOURCE IMAGE: prefer clean isolated bottle shots, avoid pre-composed lifestyle images ──
        # Small Batch (copper): SmallBatch1.jpg > Black_Front_LightBG_V1.png > bottle-ref.jpg
        # Single Barrel (gold): Golden_Front_57 > Golden_Front_58 > SingleBarrel1.jpg
        if bottle_type == 'single_barrel':
            _clean_bottle_candidates = [
                '/static/photos/gallery/Golden_Front_57_LightBG_V1.png',
                '/static/photos/gallery/Golden_Front_58_LightBG_V1.png',
                '/static/photos/gallery/SingleBarrel1.jpg',
                '/static/photos/SingleBarrel1.jpg',
                '/static/photos/bottle-ref.jpg',
            ]
        else:
            _clean_bottle_candidates = [
                '/static/photos/SmallBatch1.jpg',
                '/static/photos/gallery/SmallBatch1.jpg',
                '/static/photos/gallery/Black_Front_LightBG_V1.png',
                '/static/photos/bottle-ref.jpg',
            ]
        _base_url = 'https://forbidden-command-center.onrender.com'

        # Validate any frontend-supplied source_image — strip domain, check file exists
        if source_image:
            _rel = source_image
            if _rel.startswith(_base_url):
                _rel = _rel[len(_base_url):]
            if _rel.startswith('/static/'):
                _abs = os.path.join(app.static_folder, _rel[len('/static/'):])
                if not os.path.exists(_abs):
                    print(f"[Video] source_image {source_image} not found on disk — will select best bottle photo")
                    source_image = None  # fall through to auto-select below

        # Auto-select best available clean bottle photo
        if not source_image:
            for _candidate in _clean_bottle_candidates:
                _abs = os.path.join(app.static_folder, _candidate[len('/static/'):])
                if os.path.exists(_abs):
                    source_image = _candidate
                    print(f"[Video] Auto-selected source image: {source_image}")
                    break

        # ── PROMPT: inject brand-specific camera-motion prompt if frontend sends generic/empty ──
        _DEFAULT_VIDEO_PROMPT = (
            "Slow 180-degree orbit around the Forbidden Bourbon whiskey bottle, "
            "jet black background with single warm overhead spotlight casting deep dramatic shadows, "
            "rim lighting catching the faceted glass edges, amber liquid glowing from within, "
            "luxury spirits commercial, no glass, no pour, no liquid, no people, "
            "bottle stays fully in frame at all times, smooth cinematic camera movement"
        )
        if not prompt or len(prompt) < 20:
            prompt = _DEFAULT_VIDEO_PROMPT
            print(f"[Video] Using default brand prompt")
        else:
            # Enforce no-pour and no-glass constraints on all prompts
            constraints = []
            if 'pour' not in prompt.lower():
                constraints.append("no liquid pouring")
            if 'glass' not in prompt.lower():
                constraints.append("no glass")
            constraints.append("bottle stays fully in frame")
            if constraints:
                prompt = prompt + ", " + ", ".join(constraints)
            print(f"[Video] Using user prompt (enhanced)")

        import requests as req

        # ── RUNWAY ML ──────────────────────────────────────────────────────────
        if provider == 'runway':
            api_key = get_api_key('runway')
            if not api_key:
                return jsonify({'success': False, 'error': 'Runway API key not configured. Set RUNWAY_API_KEY in Render env vars.'}), 400

            # Clamp duration to Runway-supported values (5 or 10 seconds)
            duration = 10 if int(duration) >= 8 else 5

            payload = {
                'promptText': prompt,
                'model': model,
                'duration': duration,
                'ratio': '720:1280' if portrait else '1280:720'  # portrait=True by default for social
            }
            if source_image:
                # Normalise to relative path (/static/...) regardless of whether frontend
                # sent a full URL or a relative path — then crop+resize for Runway
                _base = 'https://forbidden-command-center.onrender.com'
                _rel = source_image
                if _rel.startswith(_base):
                    _rel = _rel[len(_base):]
                if _rel.startswith('/static/'):
                    _img_abs = os.path.join(app.static_folder, _rel[len('/static/'):])
                    if os.path.exists(_img_abs):
                        _resized_rel = _maybe_resize_for_runway(_img_abs, _rel, portrait=portrait)
                        source_image = f"{_base}{_resized_rel}"
                    else:
                        print(f"[Runway] Source image not found on disk: {_img_abs}")
                        source_image = None
                else:
                    # External URL — can't resize, send as-is
                    print(f"[Runway] External source image URL, sending as-is: {source_image[:80]}")
                if source_image:
                    payload['promptImage'] = source_image

            print(f"[Video] Runway {model} — duration={duration}s, image={'yes' if source_image else 'no'}, url={source_image or 'none'}")

            resp = req.post(
                'https://api.dev.runwayml.com/v1/image_to_video',   # underscore — confirmed in Runway docs
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'X-Runway-Version': '2024-11-06'
                },
                json=payload,
                timeout=30
            )

            if resp.status_code in (200, 201):
                result = resp.json()
                task_id = result.get('id', '')
                print(f"[Video] Runway task created: {task_id}")
                return jsonify({'success': True, 'task_id': task_id, 'provider': 'runway'})
            else:
                try:
                    _err_body = resp.json()
                    error_msg = _err_body.get('error', resp.text[:300])
                    # Include 'issues' array for detailed validation errors
                    _issues = _err_body.get('issues', [])
                    if _issues:
                        _detail = ' | '.join(i.get('message', '') for i in _issues)
                        error_msg = f"{error_msg}: {_detail}"
                except Exception:
                    error_msg = resp.text[:300]
                print(f"[Video] Runway failed ({resp.status_code}): {error_msg}")
                return jsonify({'success': False, 'error': f'Runway API Error ({resp.status_code}): {error_msg}'}), 500

        # ── LUMA DREAM MACHINE ─────────────────────────────────────────────────
        elif provider == 'luma':
            luma_key = os.environ.get('LUMA_API_KEY', '')
            if not luma_key:
                return jsonify({'success': False, 'error': 'Luma API key not configured. Set LUMA_API_KEY in Render env vars.'}), 400

            luma_model = data.get('luma_model', 'ray-2')   # ray-2 or ray-2-flash

            payload = {
                'prompt': prompt,
                'model': luma_model,
                'aspect_ratio': '9:16' if portrait else '16:9',
                'duration': '5s'
            }
            if source_image:
                payload['keyframes'] = {
                    'frame0': {'type': 'image', 'url': source_image}
                }

            print(f"[Video] Luma {luma_model} — image={'yes' if source_image else 'no'}")

            resp = req.post(
                'https://api.lumalabs.ai/dream-machine/v1/generations',
                headers={
                    'Authorization': f'Bearer {luma_key}',
                    'Content-Type': 'application/json'
                },
                json=payload,
                timeout=30
            )

            if resp.status_code in (200, 201):
                result = resp.json()
                task_id = result.get('id', '')
                print(f"[Video] Luma generation created: {task_id}")
                return jsonify({'success': True, 'task_id': task_id, 'provider': 'luma'})
            else:
                try:
                    error_msg = resp.json().get('detail', resp.text[:300])
                except Exception:
                    error_msg = resp.text[:300]
                print(f"[Video] Luma failed ({resp.status_code}): {error_msg}")
                return jsonify({'success': False, 'error': f'Luma API Error ({resp.status_code}): {error_msg}'}), 500

        else:
            return jsonify({'success': False, 'error': f'Unknown provider: {provider}'}), 400

    except Exception as e:
        import traceback
        print(f"[Video] Exception: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/templates', methods=['GET'])
def api_ai_templates():
    """Return all video and image prompt templates for the AI Studio."""
    video_templates = [
        # ── ORIGINAL 6 (kept for reference) ─────────────────────────────
        {'id': 'v_product_hero', 'label': 'Product Hero', 'category': 'product',
         'prompt': 'Slow cinematic dolly push-in toward the Forbidden Bourbon bottle, warm amber bokeh background, dramatic side lighting catching the faceted glass, luxury spirits commercial, no pouring, bottle stays fully in frame'},
        {'id': 'v_orbit', 'label': 'Bottle Orbit', 'category': 'product',
         'prompt': 'Slow 180-degree orbit around Forbidden Bourbon bottle, camera level with label, dark moody background with rim lighting, luxury product reveal, smooth motion, no camera shake'},
        {'id': 'v_lifestyle', 'label': 'Speakeasy Mood', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle in foreground on a dark mahogany bar, blurred warm speakeasy bar background with candles and bokeh, cinematic shallow depth of field, camera gently drifts left to right, no pour, no glass, bottle stays fully in frame'},
        {'id': 'v_barrel', 'label': 'Barrel Room', 'category': 'heritage',
         'prompt': 'Camera slowly pulls back from close-up of Forbidden Bourbon label to reveal a dark Kentucky rickhouse full of aging barrels, warm amber shafts of light through wood slats, dramatic and cinematic'},
        {'id': 'v_fire', 'label': 'Fireplace Glow', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle resting on a stone hearth, firelight flickering warm reflections across the faceted glass, intimate luxury scene, slow gentle camera drift, no pouring'},
        {'id': 'v_smoke', 'label': 'Smokehouse', 'category': 'product',
         'prompt': 'Forbidden Bourbon bottle surrounded by thin wisps of oak smoke drifting past in slow motion, jet black background, single dramatic spotlight from above, cinematic and moody'},
        # ── NEW 10 ────────────────────────────────────────────────────────
        {'id': 'v_gold_hero', 'label': 'Gold Edition Hero', 'category': 'product',
         'prompt': 'Gold Forbidden Bourbon Single Barrel bottle, slow dramatic push-in, jet black background with warm single overhead spotlight casting deep shadows on the faceted gold glass, luxury whiskey commercial'},
        {'id': 'v_whiskey_neat', 'label': 'Whiskey Neat', 'category': 'lifestyle',
         'prompt': 'Extreme close-up of a filled crystal rocks glass with golden bourbon, slow ripple across the amber liquid surface, Forbidden Bourbon bottle in soft bokeh behind, warm intimate lighting'},
        {'id': 'v_kentucky_sunrise', 'label': 'Kentucky Sunrise', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle silhouetted against a hazy golden sunrise over rolling Kentucky hills, slow cinematic push-in, warm orange sky, mist in the valleys below, epic and emotional'},
        {'id': 'v_copper_ice', 'label': 'Copper & Ice', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon copper bottle beside a crystal glass with a single large perfectly clear ice cube, slow fog drift across the marble table surface, cool blue-and-amber contrast lighting'},
        {'id': 'v_vault', 'label': 'Vault Door Reveal', 'category': 'brand',
         'prompt': 'Dramatic reveal: heavy antique vault door swings slowly open from the left, revealing Forbidden Bourbon bottle bathed in warm golden light from behind, theatrical and cinematic'},
        {'id': 'v_label_macro', 'label': 'Label Macro Study', 'category': 'product',
         'prompt': 'Ultra-tight macro lens slowly racking focus across the FORBIDDEN label — first the engraved text, then the wax seal, then the bourbon color in the glass — cinematic depth of field pull'},
        {'id': 'v_award_shelf', 'label': 'Award Shelf', 'category': 'brand',
         'prompt': 'Forbidden Bourbon bottle displayed on a dark velvet shelf with Double Gold and Gold medal badges visible, camera slowly orbits the bottle, warm museum-quality spotlighting, prestigious and confident'},
        {'id': 'v_social_reel', 'label': 'Social Reel (Portrait)', 'category': 'social',
         'prompt': 'Vertical portrait format — Forbidden Bourbon bottle centered in frame, dramatic neon-and-candlelight bar background, slow zoom out revealing the full bottle, bold cinematic color grade for Instagram Reels'},
        {'id': 'v_two_bottle', 'label': 'Two Bottles Side by Side', 'category': 'brand',
         'prompt': 'Forbidden Bourbon Small Batch (copper) and Single Barrel (gold) bottles standing side by side, slow zoom out symmetrically revealing both, dark background with matching spotlight on each bottle'},
        {'id': 'v_old_fashioned', 'label': 'Old Fashioned Moment', 'category': 'lifestyle',
         'prompt': 'A perfect Old Fashioned cocktail in a crystal glass with orange peel garnish and cherry, Forbidden Bourbon bottle slightly behind and to the right in bokeh, warm amber bar lighting, slow drift right'},
        # ── NEW 10 ────────────────────────────────────────────────────────
        {'id': 'v_fog_reveal', 'label': 'Fog Reveal', 'category': 'product',
         'prompt': 'Forbidden Bourbon bottle emerges slowly from thin low-lying fog on a dark stone surface, single dramatic overhead spotlight, jet black background, cinematic luxury reveal, no pour, no glass, bottle stays fully in frame'},
        {'id': 'v_candlelight', 'label': 'Candlelight Glow', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle illuminated solely by a cluster of tall pillar candles on a dark oak table, warm flickering candlelight dancing across the faceted glass, intimate moody atmosphere, slow gentle push-in, no pour, no glass'},
        {'id': 'v_rain_window', 'label': 'Rainy Window', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle in sharp focus on a windowsill, rainy night cityscape blurred in background, neon reflections in wet glass, moody noir atmosphere, slow rack focus pull, no pour, bottle stays fully in frame'},
        {'id': 'v_copper_spotlight', 'label': 'Copper Spotlight', 'category': 'product',
         'prompt': 'Forbidden Bourbon Small Batch copper bottle under a single warm copper-toned spotlight on pure black background, camera slowly circles the bottle revealing every facet of the glass, luxury product reveal, no pour, no glass'},
        {'id': 'v_ice_melt', 'label': 'Ice & Condensation', 'category': 'product',
         'prompt': 'Forbidden Bourbon bottle with slow condensation droplets forming on the cold glass surface, macro close-up tracking shot, deep black background, cinematic product detail video, no pour, bottle stays fully in frame'},
        {'id': 'v_rickhouse', 'label': 'Rickhouse Shadows', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle sitting on a weathered barrel in a dark Kentucky rickhouse, shafts of golden light filtering through the wood slat walls, camera slowly pushes in from a low angle, cinematic heritage storytelling, no pour'},
        {'id': 'v_awards_reveal', 'label': 'Awards Reveal', 'category': 'brand',
         'prompt': 'Forbidden Bourbon bottle with Double Gold and Gold medal medallions slowly swinging into frame in front of it, dark velvet background with a single overhead spotlight, slow dramatic push-in, prestigious luxury brand reveal, no pour'},
        {'id': 'v_bokeh_drift', 'label': 'Bokeh Drift', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle in sharp focus with dreamy out-of-focus warm amber and gold bokeh lights slowly drifting behind it, camera gently drifts right revealing a full bottle hero shot, cinematic luxury feel, no pour, no glass'},
        {'id': 'v_wax_seal', 'label': 'Wax Seal Close-Up', 'category': 'product',
         'prompt': 'Extreme close-up slow push-in on the wax seal and neck of the Forbidden Bourbon bottle, warm single-source lighting catching the texture of the wax and the embossed details, luxury craft distillery detail shot, cinematic, no pour'},
        {'id': 'v_sunset_silhouette', 'label': 'Sunset Silhouette', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle silhouetted against a blazing orange and red Kentucky sunset, slow cinematic tilt up from the base of the bottle to the cap revealing the sky behind, epic and emotional heritage brand moment, no pour, no glass'},
    ]

    image_templates = [
        # ── ORIGINAL 6 ────────────────────────────────────────────────────
        {'id': 'i_product', 'label': 'Product Hero', 'category': 'product',
         'prompt': 'Professional product photography of Forbidden Bourbon bottle, dramatic studio lighting, black background, rim lighting highlighting the faceted glass, luxury whiskey brand aesthetic'},
        {'id': 'i_lifestyle', 'label': 'Lifestyle Scene', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle in an upscale bar setting, warm amber lighting, crystal glassware, bokeh background, editorial luxury spirits photography'},
        {'id': 'i_artdeco', 'label': 'Art Deco Poster', 'category': 'brand',
         'prompt': 'Art Deco prohibition era poster featuring Forbidden Bourbon, gold and navy geometric design, 1920s speakeasy aesthetic, vintage letterpress typography'},
        {'id': 'i_cocktail', 'label': 'Cocktail Hero', 'category': 'lifestyle',
         'prompt': 'Old fashioned cocktail with Forbidden Bourbon, garnished with orange twist and cherry, crystal rocks glass, warm candlelight, lifestyle spirits photography'},
        {'id': 'i_social', 'label': 'Social Ad', 'category': 'social',
         'prompt': 'Bold Instagram-ready graphic with Forbidden Bourbon bottle, dramatic lighting, text space for overlay, vibrant yet sophisticated color palette, social media advertising aesthetic'},
        {'id': 'i_editorial', 'label': 'Editorial', 'category': 'editorial',
         'prompt': 'Editorial whiskey photography — Forbidden Bourbon bottle with dramatic chiaroscuro lighting, artistic composition, magazine-quality depth and texture'},
        # ── NEW 20 ────────────────────────────────────────────────────────
        {'id': 'i_gold_hero', 'label': 'Gold Edition Hero', 'category': 'product',
         'prompt': 'Forbidden Bourbon Single Barrel gold bottle, jet black background, single dramatic overhead spotlight, deep dramatic shadows, ultra-sharp product photography, luxury spirits'},
        {'id': 'i_two_bottle', 'label': 'Two Bottles Comparison', 'category': 'brand',
         'prompt': 'Forbidden Bourbon Small Batch (copper) and Single Barrel (gold) bottles side by side, perfectly matched studio lighting, symmetrical composition, luxury brand photography'},
        {'id': 'i_limestone', 'label': 'Kentucky Limestone', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle resting on rough Kentucky limestone rock, spring bluegrass and wildflowers out of focus behind, golden hour light, rustic luxury outdoor photography'},
        {'id': 'i_nightcap', 'label': 'Night Cap', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle and crystal rocks glass on a dark leather-top mahogany desk, single warm desk lamp illuminating the scene, masculine editorial lifestyle photography'},
        {'id': 'i_gift', 'label': 'Gift Box Flat Lay', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle overhead flat lay on dark velvet surface with elegant gift wrap, gold ribbon, and a handwritten note card, holiday gifting photography'},
        {'id': 'i_bardstown', 'label': 'Bardstown Heritage', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle with a faded vintage map of Bardstown Kentucky as a background texture, aged editorial treatment, bourbon capital of the world heritage aesthetic'},
        {'id': 'i_story_bold', 'label': 'Bold Story Graphic', 'category': 'social',
         'prompt': 'Vertical 9:16 bold typography social graphic — "Double Gold. Single Barrel. Zero Compromise." text with Forbidden Bourbon bottle, dark dramatic background, Instagram story format'},
        {'id': 'i_fall', 'label': 'Fall Season', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle surrounded by autumn maple and oak leaves on a weathered wood surface, warm golden-hour side light, fall harvest season lifestyle photography'},
        {'id': 'i_smoke_studio', 'label': 'Smoke Studio', 'category': 'product',
         'prompt': 'Forbidden Bourbon bottle in a professional studio with wisps of real oak smoke drifting across the scene, single overhead dramatic spotlight, black background, cinematic product photography'},
        {'id': 'i_speakeasy', 'label': 'Speakeasy Scene', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle on a vintage brass bar rail in a dimly lit 1920s speakeasy, low candles, pressed tin ceiling, dark wood, moody prohibition era atmosphere'},
        {'id': 'i_cheers', 'label': 'Cheers Moment', 'category': 'lifestyle',
         'prompt': 'Two crystal rocks glasses clinking with Forbidden Bourbon, warm bokeh bar background, celebratory lifestyle photography, friendship and luxury'},
        {'id': 'i_macro_label', 'label': 'Label Macro', 'category': 'product',
         'prompt': 'Extreme macro close-up of the FORBIDDEN label — sharp focus on the engraved letterpress text and wax seal, shallow depth of field blurring the bottle edges, fine detail product photography'},
        {'id': 'i_winter', 'label': 'Winter Warmth', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle beside a fireplace with a fur throw and a filled crystal glass, snow visible through a frosted window behind, cozy luxury winter scene'},
        {'id': 'i_dark_editorial', 'label': 'Dark Editorial', 'category': 'editorial',
         'prompt': 'High contrast black and white editorial photography of Forbidden Bourbon bottle, dramatic chiaroscuro lighting, artistic magazine-quality composition, noir aesthetic'},
        {'id': 'i_kentucky_field', 'label': 'Kentucky Field', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle standing in a Kentucky bluegrass field at golden hour, rolling hills and a white fence in the soft background, authentic bourbon country heritage photography'},
        {'id': 'i_awards', 'label': 'Awards Showcase', 'category': 'brand',
         'prompt': 'Forbidden Bourbon bottle prominently displayed with Double Gold (NYISC) and Gold (SFWSC) medal badges arranged artistically, museum lighting, prestigious and confident brand photography'},
        {'id': 'i_cocktail_making', 'label': 'Bartender Craft', 'category': 'lifestyle',
         'prompt': 'Bartender hands muddling an Old Fashioned with Forbidden Bourbon bottle visible on the back bar, warm bar lighting, craft cocktail making in action, editorial lifestyle photography'},
        {'id': 'i_gifting_duo', 'label': 'Gifting Duo', 'category': 'lifestyle',
         'prompt': 'Both Forbidden Bourbon bottles (copper Small Batch and gold Single Barrel) as a gift set in a dark luxury box with tissue paper, premium gift photography for holiday campaigns'},
        # ── NEW 10 ────────────────────────────────────────────────────────
        {'id': 'i_neon_noir', 'label': 'Neon Noir', 'category': 'editorial',
         'prompt': 'Forbidden Bourbon bottle bathed in deep red and gold neon light, dark wet bar surface reflecting the neon, dramatic noir editorial photography, cinematic shadows, luxury and mystery'},
        {'id': 'i_overhead_pour', 'label': 'Overhead Flat Lay', 'category': 'lifestyle',
         'prompt': 'Overhead flat lay of Forbidden Bourbon bottle with a filled crystal rocks glass, single large ice sphere, orange peel garnish, and dark slate surface, editorial cocktail photography, warm side light'},
        {'id': 'i_copper_texture', 'label': 'Copper & Glass Texture', 'category': 'product',
         'prompt': 'Ultra-close-up macro of Forbidden Bourbon bottle faceted glass surface, copper label reflection visible in the glass, extreme depth of field, fine material detail product photography, black background'},
        {'id': 'i_heritage_map', 'label': 'Heritage Map Poster', 'category': 'brand',
         'prompt': 'Vintage illustrated map poster of Kentucky bourbon country featuring Forbidden Bourbon branding, aged paper texture, hand-drawn distillery illustrations, warm sepia tones, antique cartography aesthetic'},
        {'id': 'i_spring_garden', 'label': 'Spring Garden', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle on a white limestone garden table surrounded by fresh Kentucky wildflowers, soft afternoon sunlight, shallow depth of field, light and elegant seasonal lifestyle photography'},
        {'id': 'i_summer_ice', 'label': 'Summer Ice Bucket', 'category': 'lifestyle',
         'prompt': 'Forbidden Bourbon bottle in a polished silver ice bucket on a poolside table, summer light, clean bright editorial photography, luxury outdoor entertaining lifestyle'},
        {'id': 'i_prohibition', 'label': 'Prohibition Poster', 'category': 'brand',
         'prompt': 'Bold vintage prohibition era poster art — FORBIDDEN bourbon in heavy distressed typography, dark red and black color scheme, 1920s illegal speakeasy underground aesthetic, limited edition brand artwork'},
        {'id': 'i_barrel_char', 'label': 'Charred Barrel Detail', 'category': 'heritage',
         'prompt': 'Forbidden Bourbon bottle resting against the inside of a freshly charred new oak barrel, dramatic warm light through the barrel opening, extreme texture and depth, craft distillery heritage photography'},
        {'id': 'i_gold_foil', 'label': 'Gold Foil Luxury', 'category': 'brand',
         'prompt': 'Forbidden Bourbon Single Barrel gold bottle on a polished obsidian surface with subtle gold foil reflections, ultra-clean luxury brand photography, high-end spirits packaging aesthetic, black and gold palette'},
        {'id': 'i_tasting_notes', 'label': 'Tasting Notes Scene', 'category': 'editorial',
         'prompt': 'Forbidden Bourbon bottle with a filled Glencairn nosing glass and handwritten tasting notes card on a dark oak table, soft warm editorial photography, whiskey enthusiast lifestyle, refined and intellectual mood'},
    ]

    return jsonify({'success': True, 'video': video_templates, 'image': image_templates})


@app.route('/api/ai/finalize-video', methods=['POST'])
def api_finalize_video():
    """
    Download a generated video from CDN and optionally layer audio (SFX, music, voiceover)
    using ElevenLabs + ffmpeg, then return a locally-stored file URL.

    Request body:
    {
      "video_url": "https://runway-cdn.../video.mp4",
      "duration": 10,
      "sfx":       { "enabled": true, "prompt": "..." },
      "music":     { "enabled": true, "prompt": "..." },
      "voiceover": { "enabled": true, "text": "...", "voice_id": "..." }
    }
    """
    import requests as req
    import subprocess
    import uuid
    import tempfile

    try:
        data = request.get_json()
        video_url = data.get('video_url', '').strip()
        duration  = int(data.get('duration', 10))
        sfx_opts  = data.get('sfx', {})
        music_opts= data.get('music', {})
        vo_opts   = data.get('voiceover', {})

        if not video_url:
            return jsonify({'success': False, 'error': 'video_url required'}), 400

        el_key = get_api_key('elevenlabs')
        audio_requested = (
            sfx_opts.get('enabled') or
            music_opts.get('enabled') or
            vo_opts.get('enabled')
        )
        if audio_requested and not el_key:
            return jsonify({'success': False, 'error': 'ELEVENLABS_API_KEY not set in Render env vars'}), 400

        uid = uuid.uuid4().hex[:10]
        uploads_dir = os.path.join(app.static_folder, 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        # ── Step 1: Download the video from Runway/Luma CDN ────────────────
        print(f"[Finalize] Downloading video: {video_url[:80]}...")
        vid_path = os.path.join(uploads_dir, f'vid_raw_{uid}.mp4')
        with req.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(vid_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        print(f"[Finalize] Video downloaded: {os.path.getsize(vid_path)//1024}KB")

        # ── Step 2: Generate audio layers via ElevenLabs ────────────────────
        el_headers = {'xi-api-key': el_key, 'Content-Type': 'application/json'}
        audio_paths = []

        def _generate_sfx(prompt, dur):
            """Call ElevenLabs sound-generation endpoint, return path to mp3."""
            resp = req.post(
                'https://api.elevenlabs.io/v1/sound-generation',
                headers=el_headers,
                json={
                    'text': prompt,
                    'duration_seconds': min(float(dur), 30),
                    'prompt_influence': 0.5,
                    'model_id': 'eleven_text_to_sound_v2'
                },
                timeout=60
            )
            resp.raise_for_status()
            path = os.path.join(uploads_dir, f'audio_{uuid.uuid4().hex[:8]}.mp3')
            with open(path, 'wb') as f:
                f.write(resp.content)
            print(f"[Finalize] Audio generated: {os.path.getsize(path)//1024}KB — {prompt[:50]}")
            return path

        def _generate_tts(text, voice_id):
            """Call ElevenLabs TTS endpoint, return path to mp3."""
            vid = voice_id or '2EiwWnXFnvU5JabPnv8n'  # default: Clyde (warm male, suits bourbon brand)
            resp = req.post(
                f'https://api.elevenlabs.io/v1/text-to-speech/{vid}',
                headers=el_headers,
                json={
                    'text': text,
                    'model_id': 'eleven_turbo_v2_5',
                    'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}
                },
                timeout=60
            )
            resp.raise_for_status()
            path = os.path.join(uploads_dir, f'vo_{uuid.uuid4().hex[:8]}.mp3')
            with open(path, 'wb') as f:
                f.write(resp.content)
            print(f"[Finalize] Voiceover generated: {os.path.getsize(path)//1024}KB")
            return path

        if sfx_opts.get('enabled') and sfx_opts.get('prompt', '').strip():
            audio_paths.append(('sfx', _generate_sfx(sfx_opts['prompt'], duration)))

        if music_opts.get('enabled') and music_opts.get('prompt', '').strip():
            # Music uses the same SFX endpoint — describe ambient music in the prompt
            audio_paths.append(('music', _generate_sfx(music_opts['prompt'], duration)))

        if vo_opts.get('enabled') and vo_opts.get('text', '').strip():
            audio_paths.append(('voiceover', _generate_tts(vo_opts['text'], vo_opts.get('voice_id', ''))))

        # ── Step 3: Mux video + audio with ffmpeg ───────────────────────────
        out_path = os.path.join(uploads_dir, f'video_final_{uid}.mp4')

        if not audio_paths:
            # No audio — just copy the downloaded file as-is
            import shutil
            shutil.copy(vid_path, out_path)
            print(f"[Finalize] No audio — copied video directly")
        else:
            # Build ffmpeg command dynamically for 1–3 audio inputs
            cmd = ['ffmpeg', '-y', '-i', vid_path]
            for _, ap in audio_paths:
                cmd += ['-stream_loop', '-1', '-i', ap]

            n = len(audio_paths)
            if n == 1:
                # Single audio track — simplest case
                cmd += ['-c:v', 'copy', '-c:a', 'aac',
                        '-map', '0:v:0', '-map', '1:a:0',
                        '-shortest', out_path]
            else:
                # Mix multiple audio tracks together
                mix_inputs = ''.join(f'[{i+1}:a]' for i in range(n))
                filter_str = f'{mix_inputs}amix=inputs={n}:duration=longest:normalize=0[aout]'
                cmd += [
                    '-filter_complex', filter_str,
                    '-map', '0:v:0', '-map', '[aout]',
                    '-c:v', 'copy', '-c:a', 'aac',
                    '-shortest', out_path
                ]

            print(f"[Finalize] ffmpeg muxing {n} audio track(s)...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"[Finalize] ffmpeg error: {result.stderr[-500:]}")
                return jsonify({'success': False, 'error': f'ffmpeg mux failed: {result.stderr[-300:]}'}), 500
            print(f"[Finalize] Mux complete: {os.path.getsize(out_path)//1024}KB")

        # ── Step 4: Clean up temp audio files ──────────────────────────────
        for _, ap in audio_paths:
            try: os.remove(ap)
            except: pass
        try: os.remove(vid_path)
        except: pass

        # Save to gallery
        final_url = f'/static/uploads/video_final_{uid}.mp4'
        _save_to_gallery('video', final_url, '', '')

        return jsonify({'success': True, 'video_url': final_url})

    except req.exceptions.HTTPError as e:
        print(f"[Finalize] ElevenLabs HTTP error: {e.response.status_code} {e.response.text[:300]}")
        return jsonify({'success': False, 'error': f'ElevenLabs error ({e.response.status_code}): {e.response.text[:200]}'}), 500
    except Exception as e:
        import traceback
        print(f"[Finalize] Exception: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _auto_add_audio(raw_video_url, duration=10):
    """
    Download a Runway/Luma CDN video, generate a branded ambient SFX track via
    ElevenLabs, mux them with ffmpeg, and return a local /static/uploads/ URL.
    Falls back to the original CDN URL if ElevenLabs key missing or any step fails.
    """
    import requests as req
    import subprocess
    import uuid

    el_key = get_api_key('elevenlabs')
    uploads_dir = os.path.join(app.static_folder, 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    uid = uuid.uuid4().hex[:10]

    try:
        # Step 1: Download video from CDN
        vid_path = os.path.join(uploads_dir, f'vid_raw_{uid}.mp4')
        with req.get(raw_video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(vid_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        print(f"[Audio] Downloaded video: {os.path.getsize(vid_path)//1024}KB")

        out_path = os.path.join(uploads_dir, f'video_final_{uid}.mp4')

        if not el_key:
            # No ElevenLabs key — still save locally for persistent storage
            import shutil
            shutil.copy(vid_path, out_path)
            os.remove(vid_path)
            print("[Audio] No ElevenLabs key — saved video without audio")
            return f'/static/uploads/video_final_{uid}.mp4'

        # Step 2: Generate branded ambient SFX via ElevenLabs
        sfx_prompt = (
            "Deep cinematic bourbon ambience — low resonant barrel hum, faint crackling fireplace, "
            "subtle ambient whiskey atmosphere, moody luxury spirits commercial background, no music"
        )
        sfx_resp = req.post(
            'https://api.elevenlabs.io/v1/sound-generation',
            headers={'xi-api-key': el_key, 'Content-Type': 'application/json'},
            json={
                'text': sfx_prompt,
                'duration_seconds': min(float(duration), 30),
                'prompt_influence': 0.4,
                'model_id': 'eleven_text_to_sound_v2'
            },
            timeout=60
        )
        sfx_resp.raise_for_status()
        sfx_path = os.path.join(uploads_dir, f'sfx_{uid}.mp3')
        with open(sfx_path, 'wb') as f:
            f.write(sfx_resp.content)
        print(f"[Audio] SFX generated: {os.path.getsize(sfx_path)//1024}KB")

        # Step 3: Mux video + audio with ffmpeg (-shortest trims audio to video length)
        result = subprocess.run([
            'ffmpeg', '-y',
            '-i', vid_path,
            '-stream_loop', '-1', '-i', sfx_path,
            '-c:v', 'copy', '-c:a', 'aac',
            '-map', '0:v:0', '-map', '1:a:0',
            '-shortest', out_path
        ], capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            print(f"[Audio] ffmpeg error: {result.stderr[-300:]}")
            import shutil
            shutil.copy(vid_path, out_path)  # fallback: save without audio

        print(f"[Audio] Final video: {os.path.getsize(out_path)//1024}KB")

        # Cleanup temps
        for p in [vid_path, sfx_path]:
            try: os.remove(p)
            except: pass

        return f'/static/uploads/video_final_{uid}.mp4'

    except Exception as e:
        import traceback
        print(f"[Audio] Auto-audio failed: {traceback.format_exc()}")
        # Best-effort: return CDN URL unchanged so video still works, just silent
        return raw_video_url


@app.route('/api/ai/video-status/<task_id>', methods=['GET'])
def api_video_status(task_id):
    """Check video generation status — supports Runway and Luma"""
    try:
        import requests as req
        provider = request.args.get('provider', 'runway')

        if provider == 'runway':
            api_key = get_api_key('runway')
            if not api_key:
                return jsonify({'status': 'ERROR', 'error': 'Runway not configured'}), 400
            resp = req.get(
                f'https://api.dev.runwayml.com/v1/tasks/{task_id}',
                headers={'Authorization': f'Bearer {api_key}', 'X-Runway-Version': '2024-11-06'},
                timeout=15
            )
            if resp.status_code == 200:
                result = resp.json()
                status = result.get('status', 'UNKNOWN')
                video_url = None
                if status == 'SUCCEEDED':
                    output = result.get('output', [])
                    if output:
                        video_url = output[0] if isinstance(output, list) else output
                        # Auto-add ElevenLabs ambient audio + save locally
                        video_url = _auto_add_audio(video_url, duration=10)
                    _save_to_gallery('video', video_url, '', '')
                return jsonify({'status': status, 'video_url': video_url, 'error': result.get('failure', None)})
            else:
                return jsonify({'status': 'ERROR', 'error': resp.text}), 500

        elif provider == 'luma':
            luma_key = os.environ.get('LUMA_API_KEY', '')
            if not luma_key:
                return jsonify({'status': 'ERROR', 'error': 'Luma not configured'}), 400
            resp = req.get(
                f'https://api.lumalabs.ai/dream-machine/v1/generations/{task_id}',
                headers={'Authorization': f'Bearer {luma_key}'},
                timeout=15
            )
            if resp.status_code == 200:
                result = resp.json()
                status_map = {'pending': 'PENDING', 'dreaming': 'RUNNING', 'completed': 'SUCCEEDED', 'failed': 'FAILED'}
                status = status_map.get(result.get('state', 'pending'), 'RUNNING')
                video_url = None
                if status == 'SUCCEEDED':
                    video_url = result.get('assets', {}).get('video')
                    if video_url:
                        # Auto-add ElevenLabs ambient audio + save locally
                        video_url = _auto_add_audio(video_url, duration=5)
                        _save_to_gallery('video', video_url, '', '')
                return jsonify({'status': status, 'video_url': video_url, 'error': result.get('failure_reason', None)})
            else:
                return jsonify({'status': 'ERROR', 'error': resp.text}), 500

        else:
            return jsonify({'status': 'ERROR', 'error': f'Unknown provider: {provider}'}), 400

    except Exception as e:
        return jsonify({'status': 'ERROR', 'error': str(e)}), 500

@app.route('/api/ai/clear-cutout-cache', methods=['POST'])
def api_clear_cutout_cache():
    """Delete all cached bottle cutouts so next generation re-extracts via OpenAI API."""
    try:
        cache_dir = os.path.join(app.static_folder, 'uploads', 'cutout_cache')
        deleted = []
        if os.path.exists(cache_dir):
            for f in os.listdir(cache_dir):
                if f.startswith('cutout_') and f.endswith('.png'):
                    os.remove(os.path.join(cache_dir, f))
                    deleted.append(f)
        print(f"[Cutout] Cache cleared: {deleted}")
        return jsonify({'success': True, 'deleted': deleted, 'count': len(deleted)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/gallery', methods=['GET'])
def api_ai_gallery():
    """Get AI-generated content gallery"""
    try:
        saved_only = request.args.get('saved', '') == 'true'
        conn = db.get_db()
        if saved_only:
            items = db._fetchall(conn, 'SELECT * FROM ai_gallery WHERE saved = TRUE ORDER BY created_at DESC LIMIT 100')
        else:
            items = db._fetchall(conn, 'SELECT * FROM ai_gallery ORDER BY created_at DESC LIMIT 50')
        conn.close()

        result = []
        for i in items:
            url = i['url']
            # If file is in ephemeral uploads and has been wiped on restart, serve from stored base64
            if url.startswith('/static/uploads/'):
                abs_path = app.static_folder + url[len('/static'):]
                if not os.path.exists(abs_path):
                    img_data = i.get('image_data', '') or ''
                    if img_data:
                        ext = 'png' if url.lower().endswith('.png') else 'jpeg'
                        url = f'data:image/{ext};base64,{img_data}'
                    else:
                        url = ''  # genuinely gone, no backup stored
            result.append({
                'id': i.get('id'),
                'type': i['media_type'],
                'url': url,
                'prompt': i['prompt'],
                'created': str(i['created_at']),
                'saved': bool(i.get('saved', False)),
                'bottle_type': i.get('bottle_type', '')
            })

        return jsonify({'items': result})
    except Exception as e:
        return jsonify({'items': []})


@app.route('/api/ai/save-image', methods=['POST'])
def api_save_image():
    """Toggle save status on a gallery image"""
    try:
        data = request.get_json()
        gallery_id = data.get('id')
        saved = data.get('saved', True)
        
        if not gallery_id:
            return jsonify({'success': False, 'error': 'No image ID provided'}), 400
        
        conn = db.get_db()
        if db.USE_POSTGRES:
            conn.cursor().execute('UPDATE ai_gallery SET saved = %s WHERE id = %s', (saved, gallery_id))
        else:
            conn.execute('UPDATE ai_gallery SET saved = ? WHERE id = ?', (1 if saved else 0, gallery_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'saved': saved})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/delete-image/<int:image_id>', methods=['DELETE'])
def api_delete_image(image_id):
    """Delete an image from the gallery"""
    try:
        conn = db.get_db()
        if db.USE_POSTGRES:
            conn.cursor().execute('DELETE FROM ai_gallery WHERE id = %s', (image_id,))
        else:
            conn.execute('DELETE FROM ai_gallery WHERE id = ?', (image_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_featured_bottle_image():
    """Return the URL of the best bottle photo for use in blog articles"""
    # Prefer clean product shots with light backgrounds
    candidates = [
        'gallery/Black_Front_LightBG_V1.png',
        'gallery/Golden_Front_57_LightBG_V1.png',
        'gallery/Golden_Front_58_LightBG_V1.png',
        'gallery/SingleBarrel1.jpg',
        'gallery/SmallBatch1.jpg',
        'bottle-ref.jpg',
    ]
    for fname in candidates:
        fpath = os.path.join(app.static_folder, 'photos', fname)
        if os.path.exists(fpath):
            return f'/static/photos/{fname}'
    return None


def _save_to_gallery(media_type, url, prompt, revised_prompt, bottle_type='', image_data=''):
    """Save generated media to gallery, returns the new row ID.
    image_data: base64 string of the image file — survives Render ephemeral filesystem resets.
    """
    try:
        conn = db.get_db()
        if db.USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO ai_gallery (media_type, url, prompt, revised_prompt, bottle_type, image_data) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id',
                (media_type, url or '', prompt or '', revised_prompt or '', bottle_type or '', image_data or '')
            )
            row = cur.fetchone()
            new_id = row[0] if row else None
        else:
            cur = conn.execute(
                'INSERT INTO ai_gallery (media_type, url, prompt, revised_prompt, bottle_type, image_data) VALUES (?, ?, ?, ?, ?, ?)',
                (media_type, url or '', prompt or '', revised_prompt or '', bottle_type or '', image_data or '')
            )
            new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        print(f"Gallery save error: {e}")
        return None

# ============================================================
# AI HELP ASSISTANT
# ============================================================

ASSISTANT_SYSTEM_PROMPT = """You are the Forbidden Bourbon Command Center assistant. You help team members use the app effectively. Be concise, friendly, and specific. Use short paragraphs — no bullet points or markdown formatting since this displays in a small chat widget.

ABOUT THE APP:
The Forbidden Bourbon Command Center is a social media management and brand intelligence tool built for the Forbidden Bourbon team. It runs at forbidden-command-center.onrender.com.

APP TABS & FEATURES:

DASHBOARD (home page): Shows key stats — total posts, drafts, scheduled, published, failed posts, connected platforms, and template count. Also shows a Forbidden bottle showcase and recent activity feed.

COMPOSE (/compose): Create new social media posts. Write content, add hashtags, attach images, select target platforms (Twitter/X, Bluesky, Facebook, LinkedIn, Instagram), set post type (standard, thread, story, reel), and either save as draft or schedule for later. You can also add notes and link URLs.

QUEUE (/queue): View and manage all posts organized by status — drafts, scheduled, published, failed, and archived. You can edit, delete, or change the status of any post. This is where you manage your content pipeline.

CALENDAR (/calendar): See scheduled posts on a calendar view. Helps plan content timing and avoid gaps.

TEMPLATES (/templates): 80+ pre-written content templates organized by category — product spotlights, cocktail recipes, Marianne Eaves features, brand stories, engagement posts, education, pairings, awards, events, seasonal campaigns, holiday cocktails, and more. Use a template to quickly start a new post. You can also create custom templates.

CREATIVE (/creative): Hashtag group management. Pre-built groups for Instagram (5 max per post), Twitter, and Bluesky. Copy hashtag sets with one tap.

PHOTOS (/photos): Brand photo gallery with 35 images organized by category — Bottles, Marianne Eaves, Lifestyle, Ingredients, Awards, Logos, Cocktails (Holiday Whiskey Sours), and Brand assets (bottle top detail, Mash Networks banner, QR code). Tap any photo to see it full-size and copy its URL for use in posts.

GUIDE (/guide): Complete app manual with instructions for every feature, quick start guide, team tips, brand info, and a QR code to share the app with teammates.

BRAND INTEL (/brand-intel): Content repository that scrapes the entire web for every article, review, video, blog post, podcast, and social mention of Forbidden Bourbon. Quick Scan runs 8 searches, Deep Scan runs 30+ queries across reviews, YouTube, Reddit, podcasts, news, awards, pricing, and comparisons. Auto-fetches full article text. Filter by type, star important mentions, copy content, or add mentions manually. Use it to track brand awareness, repurpose content, and see what people are saying about Forbidden.

OUTREACH HUB (/outreach): CRM for bourbon influencer outreach. Scan finds 35+ bourbon YouTubers, bloggers, Instagram creators, podcast hosts, bourbon bars, industry events, media outlets, and adjacent lifestyle influencers (BBQ, cigars, outdoors). Scrapes public contact emails from blog contact pages. Track status (new, researching, contacted, product sent, posted about us), copy email templates for influencers, bars, press, adjacent creators, and community leaders. Add contacts manually too.

BLOG HUB (/blog-hub): SEO content engine that generates long-form blog articles about bourbon topics using AI. 32 pre-loaded topics across categories (education, cocktails, culture, food pairing, people, seasonal). Generate articles with one tap, preview them, then publish directly to Medium, WordPress.com, or Blogger. Each article creates backlinks to drinkforbidden.com, boosting Google rankings and LLM visibility. Set up platform tokens in Render env vars (MEDIUM_TOKEN, WORDPRESS_SITE + WORDPRESS_TOKEN, BLOGGER_BLOG_ID + BLOGGER_TOKEN). Strategy: 2-3 articles per week across all three platforms for maximum SEO impact.

AI STUDIO (/ai-studio): Generate AI images using DALL-E 3 and AI videos using Runway ML. Includes style presets (Product, Lifestyle, Art Deco, Cocktail, Social Ad, Editorial) with pre-built prompt templates tuned to the Forbidden brand. Generated content saves to a gallery. Requires OpenAI and Runway ML API keys set as environment variables in Render (OPENAI_API_KEY, RUNWAY_API_KEY).

PLATFORMS (/platforms): Connect and manage social media platform API credentials (Twitter, Bluesky, Facebook, LinkedIn, Instagram). Each platform card shows connection status.

ANALYTICS (/analytics): Google Analytics 4 integration. Shows real-time active users, total users, sessions, pageviews, avg session duration, bounce rate, and engaged sessions. Includes a traffic-over-time chart (users/sessions/pageviews), top pages, traffic sources (channels), top referrers, device breakdown (desktop/mobile/tablet), country breakdown, and top cities. Switch between 7, 14, 30, or 90 day views. Requires GA4_PROPERTY_ID and GA4_CREDENTIALS_JSON env vars on Render. Setup: create a Google Cloud service account, enable Analytics Data API, add service account as Viewer in GA4, paste credentials JSON as env var.

AI ASSISTANT: The 🤖 button (bottom right) opens the AI Help assistant that can answer questions about any feature in the Command Center.

ABOUT FORBIDDEN BOURBON:
Forbidden is a premium Kentucky wheated bourbon made by Master Distiller Marianne Eaves at Bardstown Bourbon Company. The mash bill uses white corn, white wheat, and a high percentage of barley. Available as Small Batch Select (max 50 barrels per blend) and Single Barrel. Multiple award winner (SF, NY, LA, Denver, Ascot). Website: drinkforbidden.com, Shop: shop.drinkforbidden.com.

TIPS FOR THE TEAM:
- Use Templates to quickly draft posts — they're pre-written with optimized hashtags
- Instagram now limits to 5 hashtags per post (2026 rule) — use the IG-specific hashtag groups
- Save drafts first, review with the team in Queue, then schedule
- Photos tab has all brand assets — copy URLs to use in posts
- AI Studio can generate on-brand images for social posts
- The app syncs across all team members — everyone sees the same data

Keep answers SHORT and actionable. 2-3 sentences max unless they ask for detail."""

@app.route('/api/assistant/chat', methods=['POST'])
def api_assistant_chat():
    """AI help assistant powered by OpenAI"""
    try:
        data = request.get_json()
        user_messages = data.get('messages', [])
        
        if not user_messages:
            return jsonify({'error': 'No message provided'}), 400
        
        api_key = get_api_key('openai')
        if not api_key:
            return jsonify({'reply': "I'm not connected yet — the team needs to set the OPENAI_API_KEY in Render environment variables. Once that's done, I'll be able to help!"})
        
        import requests as req
        
        # Build messages with system prompt
        messages = [{'role': 'system', 'content': ASSISTANT_SYSTEM_PROMPT}]
        # Only send last 10 messages to keep context manageable
        for msg in user_messages[-10:]:
            messages.append({
                'role': msg.get('role', 'user'),
                'content': msg.get('content', '')
            })
        
        resp = req.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-4o-mini',
                'messages': messages,
                'max_tokens': 300,
                'temperature': 0.7
            },
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            reply = result['choices'][0]['message']['content']
            return jsonify({'reply': reply})
        else:
            return jsonify({'reply': 'Sorry, I had trouble connecting. Try again in a moment.'})
    
    except Exception as e:
        print(f"Assistant error: {e}")
        return jsonify({'reply': 'Something went wrong. Please try again.'})

# ============================================================
# API ROUTES - ANALYTICS & STATS
# ============================================================

@app.route('/api/stats')
def api_stats():
    stats = db.get_dashboard_stats()
    return jsonify(stats)

@app.route('/api/activity')
def api_activity():
    activity = db.get_activity(limit=20)
    return jsonify(activity)

# ============================================================
# IMAGE UPLOAD
# ============================================================

@app.route('/api/upload', methods=['POST'])
def api_upload_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{int(time_module.time())}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'success': True, 'path': f'/static/uploads/{filename}'})
    
    return jsonify({'success': False, 'error': 'File type not allowed'}), 400

# ============================================================
# SCHEDULER BACKGROUND THREAD
# ============================================================

def scheduler_loop():
    """Check for due posts every 60 seconds and publish them"""
    while True:
        try:
            due_posts = db.get_due_posts()
            for post in due_posts:
                all_platforms = db.get_platforms()
                platform_lookup = {p['name']: p for p in all_platforms}
                
                image_full_path = ''
                if post.get('image_path'):
                    image_full_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        post['image_path'].lstrip('/')
                    )
                
                for pp in post.get('platforms', []):
                    platform_name = pp['platform_name']
                    platform_config = platform_lookup.get(platform_name, {})
                    
                    if not platform_config.get('connected'):
                        db.mark_post_failed(post['id'], platform_name, 'Platform not connected')
                        continue
                    
                    config = {
                        'api_key': platform_config.get('api_key', ''),
                        'api_secret': platform_config.get('api_secret', ''),
                        'access_token': platform_config.get('access_token', ''),
                        'refresh_token': platform_config.get('refresh_token', ''),
                        'username': platform_config.get('username', ''),
                    }
                    
                    result = publish_to_platform(platform_name, post['content'], image_full_path, config)
                    
                    if result.success:
                        db.mark_post_published(post['id'], platform_name, result.post_id)
                    else:
                        db.mark_post_failed(post['id'], platform_name, result.error)
                
                # Update overall post status
                updated_post = db.get_post(post['id'])
                if updated_post:
                    statuses = [p['status'] for p in updated_post.get('platforms', [])]
                    if all(s == 'published' for s in statuses):
                        db.update_post(post['id'], status='published',
                                      published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                    elif all(s == 'failed' for s in statuses):
                        db.update_post(post['id'], status='failed')
        except Exception as e:
            print(f"Scheduler error: {e}")
        
        time_module.sleep(60)

# Start scheduler thread
scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()


# ============================================================
# BLOG AUTO-SCHEDULER
# ============================================================

# Schedule: which platforms to post to on which days (0=Mon, 6=Sun)
BLOG_SCHEDULE = {
    0: ['medium'],          # Monday: Medium article
    1: ['reddit'],          # Tuesday: Reddit post
    2: ['wordpress'],       # Wednesday: WordPress article
    3: ['reddit'],          # Thursday: Reddit post  
    4: ['blogger'],         # Friday: Blogger article
    5: [],                  # Saturday: off
    6: [],                  # Sunday: off
}

REDDIT_SUBREDDITS = ['bourbon', 'whiskey', 'cocktails', 'Kentucky', 'craftspirits']

def clean_article_title(title):
    """Strip 'Reddit r/xxx:' prefix from article titles for non-Reddit publishing"""
    import re
    return re.sub(r'^Reddit\s+r/\w+:\s*', '', title).strip()


def blog_auto_post(platform):
    """Generate and publish one blog article to a platform"""
    import requests as req
    import re
    
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    
    if not anthropic_key and not openai_key:
        print(f"[Blog Auto] No AI key — skipping")
        return False
    
    # Pick a least-used topic
    topics = db.get_blog_topics()
    if not topics:
        print(f"[Blog Auto] No topics available")
        return False
    
    topic = topics[0]  # Already sorted by least used
    db.use_blog_topic(topic['id'])
    
    try:
        if platform == 'reddit':
            # Generate Reddit-style post
            subreddit = random.choice(REDDIT_SUBREDDITS)
            user_message = f"Write a Reddit post for r/{subreddit} about: {topic['title']}"
            
            if anthropic_key:
                resp = req.post('https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': anthropic_key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                    json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 1024, 'system': REDDIT_SYSTEM_PROMPT,
                          'messages': [{'role': 'user', 'content': user_message}]}, timeout=60)
                text = ''.join(b['text'] for b in resp.json().get('content', []) if b.get('type') == 'text')
            else:
                resp = req.post('https://api.openai.com/v1/chat/completions',
                    headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                    json={'model': 'gpt-4o-mini', 'messages': [{'role': 'system', 'content': REDDIT_SYSTEM_PROMPT},
                          {'role': 'user', 'content': user_message}], 'max_tokens': 1024}, timeout=60)
                text = resp.json()['choices'][0]['message']['content']
            
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            post_data = json.loads(json_match.group()) if json_match else {'title': topic['title'], 'body': text, 'subreddit': subreddit}
            
            # Save article
            article_id = db.create_blog_article(
                title=f"Reddit r/{post_data.get('subreddit', subreddit)}: {post_data.get('title', topic['title'])}",
                content=post_data.get('body', ''),
                excerpt=post_data.get('body', '')[:200],
                topic=topic['title'], keywords=subreddit,
                status='draft', platform='reddit',
                word_count=len(post_data.get('body', '').split())
            )
            
            # Try to publish to Reddit
            client_id = os.environ.get('REDDIT_CLIENT_ID', '')
            client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '')
            reddit_user = os.environ.get('REDDIT_USERNAME', '')
            reddit_pass = os.environ.get('REDDIT_PASSWORD', '')
            
            if all([client_id, client_secret, reddit_user, reddit_pass]):
                auth_resp = req.post('https://www.reddit.com/api/v1/access_token',
                    auth=(client_id, client_secret),
                    data={'grant_type': 'password', 'username': reddit_user, 'password': reddit_pass},
                    headers={'User-Agent': 'ForbiddenCommandCenter/1.0'})
                
                if auth_resp.status_code == 200:
                    reddit_token = auth_resp.json().get('access_token')
                    pub_resp = req.post('https://oauth.reddit.com/api/submit',
                        headers={'Authorization': f'Bearer {reddit_token}', 'User-Agent': 'ForbiddenCommandCenter/1.0'},
                        data={'kind': 'self', 'sr': post_data.get('subreddit', subreddit),
                              'title': post_data.get('title', ''), 'text': post_data.get('body', ''), 'api_type': 'json'})
                    
                    if pub_resp.status_code == 200:
                        reddit_data = pub_resp.json().get('json', {}).get('data', {})
                        db.update_blog_article(article_id, status='published',
                            platform=f"reddit/r/{post_data.get('subreddit', subreddit)}",
                            platform_url=reddit_data.get('url', ''),
                            published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                        db.add_published_platform(article_id, 'reddit', reddit_data.get('url', ''))
                        print(f"[Blog Auto] ✓ Reddit r/{subreddit}: {post_data.get('title', '')}")
                        db.create_notification('blog', f"📝 Blog Published: Reddit r/{subreddit}",
                            f"{post_data.get('title', '')}", reddit_data.get('url', '/blog-hub'))
                        return True
            
            print(f"[Blog Auto] Reddit saved as draft (no API keys)")
            db.create_notification('blog', f"📝 Blog Draft: Reddit r/{subreddit}",
                f"{post_data.get('title', '')} — saved as draft (no Reddit API keys)", '/blog-hub')
            return True
        
        else:
            # Generate blog article for Medium/WordPress/Blogger
            user_message = f"Write a blog article about: {topic['title']}\n\nTarget SEO keywords: {topic.get('keywords', '')}"
            
            if anthropic_key:
                resp = req.post('https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': anthropic_key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                    json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 4096, 'system': BLOG_SYSTEM_PROMPT,
                          'messages': [{'role': 'user', 'content': user_message}]}, timeout=60)
                text = ''.join(b['text'] for b in resp.json().get('content', []) if b.get('type') == 'text')
            else:
                resp = req.post('https://api.openai.com/v1/chat/completions',
                    headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                    json={'model': 'gpt-4o-mini', 'messages': [{'role': 'system', 'content': BLOG_SYSTEM_PROMPT},
                          {'role': 'user', 'content': user_message}], 'max_tokens': 4096, 'temperature': 0.8}, timeout=60)
                text = resp.json()['choices'][0]['message']['content']
            
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            article_data = json.loads(json_match.group()) if json_match else {'title': topic['title'], 'content': text, 'excerpt': text[:200], 'keywords': topic.get('keywords', '')}
            
            word_count = len(article_data.get('content', '').split())
            
            article_id = db.create_blog_article(
                title=article_data.get('title', topic['title']),
                content=article_data.get('content', ''),
                excerpt=article_data.get('excerpt', ''),
                topic=topic['title'],
                keywords=article_data.get('keywords', ''),
                status='draft', platform=platform,
                word_count=word_count
            )
            
            # Try to publish
            published = False
            
            if platform == 'medium':
                token = os.environ.get('MEDIUM_TOKEN', '')
                if token:
                    user_resp = req.get('https://api.medium.com/v1/me', headers={'Authorization': f'Bearer {token}'})
                    if user_resp.status_code == 200:
                        user_id = user_resp.json()['data']['id']
                        pub_resp = req.post(f'https://api.medium.com/v1/users/{user_id}/posts',
                            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                            json={'title': clean_article_title(article_data.get('title', '')), 'contentFormat': 'html',
                                  'content': article_data.get('content', ''),
                                  'tags': [k.strip() for k in article_data.get('keywords', '').split(',')[:5]],
                                  'publishStatus': 'public'})
                        if pub_resp.status_code in (200, 201):
                            pub_data = pub_resp.json()['data']
                            db.update_blog_article(article_id, status='published', platform='medium',
                                platform_url=pub_data.get('url', ''),
                                published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                            db.add_published_platform(article_id, 'medium', pub_data.get('url', ''))
                            published = True
                else:
                    # NO TOKEN WORKAROUND: host article publicly for Medium import
                    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://forbidden-command-center.onrender.com')
                    public_url = f"{render_url}/blog/public/{article_id}"
                    import_url = f"https://medium.com/p/import?url={public_url}"
                    db.update_blog_article(article_id, status='ready_for_import', platform='medium',
                        platform_url=import_url,
                        published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                    db.create_notification('blog',
                        f"📝 Medium Article Ready: {article_data.get('title', '')[:50]}",
                        f"Tap to import to Medium with one click",
                        import_url)
                    published = True  # Mark as handled so it doesn't retry
            
            elif platform == 'wordpress':
                from urllib.parse import unquote
                wp_site = os.environ.get('WORDPRESS_SITE', '')
                wp_token = unquote(os.environ.get('WORDPRESS_TOKEN', ''))
                if wp_site and wp_token:
                    pub_resp = req.post(f'https://public-api.wordpress.com/rest/v1.1/sites/{wp_site}/posts/new',
                        headers={'Authorization': f'Bearer {wp_token}'},
                        json={'title': clean_article_title(article_data.get('title', '')), 'content': article_data.get('content', ''),
                              'excerpt': article_data.get('excerpt', ''), 'tags': article_data.get('keywords', ''), 'status': 'publish'})
                    if pub_resp.status_code in (200, 201):
                        pub_data = pub_resp.json()
                        db.update_blog_article(article_id, status='published', platform='wordpress',
                            platform_url=pub_data.get('URL', ''),
                            published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                        db.add_published_platform(article_id, 'wordpress', pub_data.get('URL', ''))
                        published = True
            
            elif platform == 'blogger':
                blog_id = os.environ.get('BLOGGER_BLOG_ID', '')
                blogger_token = get_blogger_access_token()
                if blog_id and blogger_token:
                    pub_resp = req.post(f'https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/',
                        headers={'Authorization': f'Bearer {blogger_token}'},
                        json={'kind': 'blogger#post', 'title': clean_article_title(article_data.get('title', '')),
                              'content': article_data.get('content', ''),
                              'labels': [k.strip() for k in article_data.get('keywords', '').split(',')[:5]]})
                    if pub_resp.status_code in (200, 201):
                        pub_data = pub_resp.json()
                        db.update_blog_article(article_id, status='published', platform='blogger',
                            platform_url=pub_data.get('url', ''),
                            published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                        db.add_published_platform(article_id, 'blogger', pub_data.get('url', ''))
                        published = True
                    else:
                        print(f"[Blog Auto] Blogger publish error: {pub_resp.text[:200]}")
                else:
                    print(f"[Blog Auto] Blogger not configured. blog_id={bool(blog_id)}, token={bool(blogger_token)}")
            
            status = "published" if published else "draft (no API token)"
            print(f"[Blog Auto] ✓ {platform}: {article_data.get('title', '')} — {status}")
            notif_icon = "✅" if published else "📝"
            db.create_notification('blog', f"{notif_icon} Blog {status.title()}: {platform.title()}",
                f"{article_data.get('title', '')}", '/blog-hub')
            return True
    
    except Exception as e:
        print(f"[Blog Auto] Error on {platform}: {e}")
        db.create_notification('error', f"❌ Blog Error: {platform}",
            f"Auto-post failed: {str(e)[:200]}", '/blog-hub')
        return False


def blog_scheduler_loop():
    """Auto-generate and post blog content on schedule"""
    # Wait 5 min after startup before first check
    time_module.sleep(300)
    
    while True:
        try:
            today = datetime.utcnow().weekday()  # 0=Mon
            hour = datetime.utcnow().hour
            
            # Only post between 9am-5pm UTC (roughly US business hours)
            if 9 <= hour <= 17:
                platforms_today = BLOG_SCHEDULE.get(today, [])
                
                if platforms_today:
                    # Check if we already posted today
                    today_str = datetime.utcnow().strftime('%Y-%m-%d')
                    recent = db.get_blog_articles(limit=5)
                    already_posted_today = any(
                        a.get('created_at', '').startswith(today_str) and a.get('status') != 'draft'
                        for a in recent
                    ) if recent else False
                    
                    # Also check drafts created today (auto-generated but not published)
                    drafts_today = any(
                        str(a.get('created_at', '')).startswith(today_str)
                        for a in recent
                    ) if recent else False
                    
                    if not drafts_today:
                        for platform in platforms_today:
                            print(f"[Blog Auto] Generating for {platform} (day={today}, hour={hour})")
                            blog_auto_post(platform)
                            time_module.sleep(30)  # Small delay between posts
        
        except Exception as e:
            print(f"[Blog Scheduler] Error: {e}")
        
        # Check every 2 hours
        time_module.sleep(7200)


# Start blog scheduler
blog_scheduler_thread = threading.Thread(target=blog_scheduler_loop, daemon=True)
blog_scheduler_thread.start()

# ============================================================
# BRAND INTEL AUTO-SCANNER (every 10 days)
# ============================================================

BRAND_INTEL_SCAN_INTERVAL = 10 * 24 * 60 * 60  # 10 days in seconds

def brand_intel_scanner_loop():
    """Auto-run deep scan for Forbidden Bourbon mentions every 10 days"""
    # Wait 2 min after startup before first scan
    time_module.sleep(120)
    
    while True:
        try:
            print(f"[Brand Intel Auto] Starting deep scan at {datetime.utcnow()}")
            results = scrape_mentions(deep=True)
            saved = 0
            fetched = 0
            
            for r in results:
                mention_id = db.add_brand_mention(
                    title=r['title'],
                    url=r['url'],
                    source=r['source'],
                    source_type=r['source_type'],
                    snippet=r['snippet']
                )
                if mention_id:
                    saved += 1
                    if r['source_type'] not in ('video', 'social', 'own_site') and r['url']:
                        try:
                            content = fetch_full_content(r['url'])
                            if content and len(content) > 100:
                                db.update_brand_mention(mention_id, full_content=content)
                                fetched += 1
                        except:
                            pass
            
            print(f"[Brand Intel Auto] ✓ Deep scan complete — {len(results)} found, {saved} new, {fetched} full text fetched")
        
        except Exception as e:
            print(f"[Brand Intel Auto] Error: {e}")
        
        # Sleep 10 days
        time_module.sleep(BRAND_INTEL_SCAN_INTERVAL)

brand_intel_thread = threading.Thread(target=brand_intel_scanner_loop, daemon=True)
brand_intel_thread.start()

# ============================================================
# BLOG HUB API
# ============================================================

BLOG_SYSTEM_PROMPT = """You are an expert bourbon industry writer creating SEO-optimized blog articles for Forbidden Bourbon (drinkforbidden.com). 

About Forbidden Bourbon:
- Premium Kentucky wheated bourbon
- Master Distiller: Marianne Eaves (one of Kentucky's most celebrated distillers)
- Distilled at Bardstown Bourbon Company, Bardstown, Kentucky
- Mash bill: white corn, white wheat, high percentage of barley (all food-grade)
- Products: Small Batch Select (max 50 barrels per blend), Single Barrel
- Tagline: "A Twist on Tradition"
- Shop: shop.drinkforbidden.com | Website: drinkforbidden.com

Writing guidelines:
- Write 600-1000 word articles that are educational, engaging, and naturally mention Forbidden Bourbon
- Include the target keywords naturally (not stuffed)
- Use a warm, knowledgeable tone — like a bourbon expert sharing with friends
- Include a brief call-to-action at the end mentioning drinkforbidden.com
- Structure with a compelling headline, introduction, 3-5 subheadings, and conclusion
- Make content genuinely useful — not just marketing. Readers should learn something.
- Write in HTML format with h2/h3 tags for subheadings, p tags for paragraphs

Return ONLY a JSON object with these fields:
{"title": "...", "content": "...(HTML)...", "excerpt": "...(2-3 sentence summary)...", "keywords": "keyword1, keyword2, keyword3"}"""


@app.route('/api/blog/generate', methods=['POST'])
def api_blog_generate():
    """Generate a blog article using AI"""
    try:
        data = request.get_json()
        topic = data.get('topic', '')
        keywords = data.get('keywords', '')
        custom_prompt = data.get('custom_prompt', '')
        
        # Try Anthropic first (better writing), fall back to OpenAI
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        openai_key = get_api_key('openai')
        
        if not anthropic_key and not openai_key:
            return jsonify({'success': False, 'error': 'No AI API key configured'}), 400
        
        if custom_prompt:
            user_message = custom_prompt
        else:
            user_message = f"Write a blog article about: {topic}"
            if keywords:
                user_message += f"\n\nTarget SEO keywords to include naturally: {keywords}"
        
        import requests as req
        
        if anthropic_key:
            resp = req.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': anthropic_key,
                    'anthropic-version': '2023-06-01',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 4096,
                    'system': BLOG_SYSTEM_PROMPT,
                    'messages': [{'role': 'user', 'content': user_message}]
                },
                timeout=60
            )
            if resp.status_code == 200:
                text = ''
                for block in resp.json().get('content', []):
                    if block.get('type') == 'text':
                        text += block['text']
            else:
                return jsonify({'success': False, 'error': f'Anthropic API error: {resp.status_code}'}), 500
        else:
            resp = req.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                json={
                    'model': 'gpt-4o-mini',
                    'messages': [
                        {'role': 'system', 'content': BLOG_SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_message}
                    ],
                    'max_tokens': 4096,
                    'temperature': 0.8
                },
                timeout=60
            )
            if resp.status_code == 200:
                text = resp.json()['choices'][0]['message']['content']
            else:
                return jsonify({'success': False, 'error': f'OpenAI API error: {resp.status_code}'}), 500
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            article_data = json.loads(json_match.group())
        else:
            # Fallback: treat as plain content
            article_data = {
                'title': topic,
                'content': text,
                'excerpt': text[:200] + '...',
                'keywords': keywords
            }
        
        word_count = len(article_data.get('content', '').split())
        
        # Auto-inject featured bottle image into article content
        featured_image = _get_featured_bottle_image()
        content = article_data.get('content', '')
        if featured_image and '<img' not in content[:500]:
            # Insert hero image after the first paragraph
            first_p_end = content.find('</p>')
            if first_p_end > 0:
                img_html = f'\n<figure style="text-align:center;margin:24px 0;"><img src="{featured_image}" alt="Forbidden Bourbon" style="max-width:100%;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.2);"><figcaption style="font-size:0.85em;color:#888;margin-top:8px;">Forbidden Bourbon — A Twist on Tradition</figcaption></figure>\n'
                content = content[:first_p_end + 4] + img_html + content[first_p_end + 4:]
                article_data['content'] = content
        
        # Save to database
        article_id = db.create_blog_article(
            title=article_data.get('title', topic),
            content=article_data.get('content', ''),
            excerpt=article_data.get('excerpt', ''),
            topic=topic,
            keywords=article_data.get('keywords', keywords),
            status='draft',
            word_count=word_count
        )
        
        return jsonify({
            'success': True,
            'article': {
                'id': article_id,
                'title': article_data.get('title', ''),
                'content': article_data.get('content', ''),
                'excerpt': article_data.get('excerpt', ''),
                'keywords': article_data.get('keywords', ''),
                'word_count': word_count
            }
        })
        
    except Exception as e:
        print(f"[Blog Generate] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blog/articles', methods=['GET'])
def api_blog_articles():
    status = request.args.get('status')
    articles = db.get_blog_articles(status=status)
    return jsonify({'success': True, 'articles': articles})


@app.route('/api/blog/articles/<int:article_id>', methods=['GET'])
def api_blog_article(article_id):
    article = db.get_blog_article(article_id)
    if not article:
        return jsonify({'success': False, 'error': 'Article not found'}), 404
    return jsonify({'success': True, 'article': article})


@app.route('/api/blog/articles/<int:article_id>', methods=['DELETE'])
def api_blog_delete(article_id):
    db.delete_blog_article(article_id)
    return jsonify({'success': True})


@app.route('/api/blog/articles/<int:article_id>', methods=['PUT'])
def api_blog_update(article_id):
    data = request.get_json()
    db.update_blog_article(article_id, **data)
    return jsonify({'success': True})


@app.route('/blog/public/<int:article_id>')
def blog_public_article(article_id):
    """Serve a blog article as a clean public HTML page (for Medium import)"""
    article = db.get_blog_article(article_id)
    if not article:
        return "Article not found", 404
    
    title = clean_article_title(article.get('title', 'Untitled'))
    content = article.get('content', '')
    keywords = article.get('keywords', '')
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{title} - Forbidden Bourbon">
    <meta name="keywords" content="{keywords}">
    <link rel="canonical" href="https://drinkforbidden.com">
    <style>
        body {{ font-family: Georgia, serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.7; }}
        h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
        h2 {{ font-size: 1.5rem; margin-top: 2rem; }}
        h3 {{ font-size: 1.2rem; margin-top: 1.5rem; }}
        img {{ max-width: 100%; border-radius: 8px; }}
        a {{ color: #b8860b; }}
        .byline {{ color: #666; font-size: 0.95rem; margin-bottom: 2rem; }}
    </style>
</head>
<body>
    <article>
        <h1>{title}</h1>
        <p class="byline">By Forbidden Bourbon &bull; <a href="https://drinkforbidden.com">drinkforbidden.com</a></p>
        {content}
        <hr>
        <p><em>Discover more at <a href="https://drinkforbidden.com">drinkforbidden.com</a> &bull; Follow <a href="https://instagram.com/forbiddenbourbon">@forbiddenbourbon</a></em></p>
    </article>
</body>
</html>'''
    return html, 200, {'Content-Type': 'text/html'}


@app.route('/api/blog/publish/<int:article_id>', methods=['POST'])
def api_blog_publish(article_id):
    """Publish article to a blog platform"""
    try:
        data = request.get_json()
        platform = data.get('platform', '')
        article = db.get_blog_article(article_id)
        
        if not article:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        import requests as req
        
        if platform == 'medium':
            token = data.get('token', os.environ.get('MEDIUM_TOKEN', ''))
            
            if not token:
                # NO TOKEN WORKAROUND: Generate public URL for Medium import
                render_url = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
                public_url = f"{render_url}/blog/public/{article_id}"
                import_url = f"https://medium.com/p/import?url={public_url}"
                
                db.update_blog_article(article_id, 
                    status='ready_for_import', platform='medium',
                    platform_url=import_url,
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                
                db.create_notification('blog', 
                    f"📝 Medium Article Ready: {article['title'][:50]}",
                    f"Click to import to Medium → one click publish",
                    import_url)
                
                return jsonify({
                    'success': True, 
                    'import_url': import_url,
                    'public_url': public_url,
                    'message': 'No Medium API token. Use the import link to publish to Medium with one click.'
                })
            
            # Get Medium user ID
            user_resp = req.get('https://api.medium.com/v1/me', 
                              headers={'Authorization': f'Bearer {token}'})
            if user_resp.status_code != 200:
                return jsonify({'success': False, 'error': 'Invalid Medium token'}), 400
            user_id = user_resp.json()['data']['id']
            
            # Publish
            pub_resp = req.post(
                f'https://api.medium.com/v1/users/{user_id}/posts',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    'title': clean_article_title(article['title']),
                    'contentFormat': 'html',
                    'content': article['content'],
                    'tags': [k.strip() for k in article.get('keywords', '').split(',')[:5]],
                    'publishStatus': 'public'
                }
            )
            
            if pub_resp.status_code in (200, 201):
                pub_data = pub_resp.json()['data']
                medium_url = pub_data.get('url', '')
                db.update_blog_article(article_id, 
                    status='published', platform='medium',
                    platform_url=medium_url,
                    platform_post_id=pub_data.get('id', ''),
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                db.add_published_platform(article_id, 'medium', medium_url)
                return jsonify({'success': True, 'url': medium_url})
            else:
                return jsonify({'success': False, 'error': f'Medium error: {pub_resp.text}'}), 500
        
        elif platform == 'wordpress':
            from urllib.parse import unquote
            wp_site = data.get('site', os.environ.get('WORDPRESS_SITE', ''))
            wp_token = unquote(data.get('token', os.environ.get('WORDPRESS_TOKEN', '')))
            if not wp_site or not wp_token:
                return jsonify({'success': False, 'error': 'WordPress site and token required. Set WORDPRESS_SITE and WORDPRESS_TOKEN in Render env vars.'}), 400
            
            pub_resp = req.post(
                f'https://public-api.wordpress.com/rest/v1.1/sites/{wp_site}/posts/new',
                headers={'Authorization': f'Bearer {wp_token}'},
                json={
                    'title': clean_article_title(article['title']),
                    'content': article['content'],
                    'excerpt': article.get('excerpt', ''),
                    'tags': article.get('keywords', ''),
                    'status': 'publish'
                }
            )
            
            if pub_resp.status_code in (200, 201):
                pub_data = pub_resp.json()
                wp_url = pub_data.get('URL', '')
                db.update_blog_article(article_id,
                    status='published', platform='wordpress',
                    platform_url=wp_url,
                    platform_post_id=str(pub_data.get('ID', '')),
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                db.add_published_platform(article_id, 'wordpress', wp_url)
                return jsonify({'success': True, 'url': wp_url})
            else:
                return jsonify({'success': False, 'error': f'WordPress error: {pub_resp.text}'}), 500
        
        elif platform == 'blogger':
            blog_id = data.get('blog_id', os.environ.get('BLOGGER_BLOG_ID', ''))
            blogger_token = get_blogger_access_token()
            if not blog_id:
                return jsonify({'success': False, 'error': 'Blogger blog ID required. Set BLOGGER_BLOG_ID in Render env vars.'}), 400
            if not blogger_token:
                return jsonify({'success': False, 'error': 'Blogger not authorized. Go to your app URL + /auth/blogger/start to connect your Google account.'}), 400
            
            pub_resp = req.post(
                f'https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/',
                headers={'Authorization': f'Bearer {blogger_token}'},
                json={
                    'kind': 'blogger#post',
                    'title': clean_article_title(article['title']),
                    'content': article['content'],
                    'labels': [k.strip() for k in article.get('keywords', '').split(',')[:5]]
                }
            )
            
            if pub_resp.status_code in (200, 201):
                pub_data = pub_resp.json()
                blogger_url = pub_data.get('url', '')
                db.update_blog_article(article_id,
                    status='published', platform='blogger',
                    platform_url=blogger_url,
                    platform_post_id=pub_data.get('id', ''),
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                db.add_published_platform(article_id, 'blogger', blogger_url)
                return jsonify({'success': True, 'url': blogger_url})
            else:
                return jsonify({'success': False, 'error': f'Blogger error: {pub_resp.text}'}), 500
        
        elif platform == 'reddit':
            client_id = os.environ.get('REDDIT_CLIENT_ID', '')
            client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '')
            reddit_user = os.environ.get('REDDIT_USERNAME', '')
            reddit_pass = os.environ.get('REDDIT_PASSWORD', '')
            subreddit = data.get('subreddit', 'bourbon')
            
            if not all([client_id, client_secret, reddit_user, reddit_pass]):
                return jsonify({'success': False, 'error': 'Reddit credentials required. Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD in Render env vars.'}), 400
            
            # Get Reddit access token
            auth_resp = req.post(
                'https://www.reddit.com/api/v1/access_token',
                auth=(client_id, client_secret),
                data={'grant_type': 'password', 'username': reddit_user, 'password': reddit_pass},
                headers={'User-Agent': 'ForbiddenCommandCenter/1.0'}
            )
            if auth_resp.status_code != 200:
                return jsonify({'success': False, 'error': 'Reddit auth failed'}), 400
            
            reddit_token = auth_resp.json().get('access_token')
            
            # Adapt content for Reddit (shorter, conversational)
            reddit_body = article.get('excerpt', '') + '\n\n'
            # Strip HTML from content for Reddit text post
            import re
            clean_content = re.sub(r'<[^>]+>', '', article.get('content', ''))
            # Take first ~500 words for Reddit
            words = clean_content.split()
            reddit_body += ' '.join(words[:500])
            if len(words) > 500:
                reddit_body += f'\n\n---\n\n*Full article and more at drinkforbidden.com*'
            
            pub_resp = req.post(
                'https://oauth.reddit.com/api/submit',
                headers={
                    'Authorization': f'Bearer {reddit_token}',
                    'User-Agent': 'ForbiddenCommandCenter/1.0'
                },
                data={
                    'kind': 'self',
                    'sr': subreddit,
                    'title': article['title'],
                    'text': reddit_body,
                    'api_type': 'json'
                }
            )
            
            if pub_resp.status_code == 200:
                reddit_data = pub_resp.json().get('json', {}).get('data', {})
                post_url = reddit_data.get('url', f'https://reddit.com/r/{subreddit}')
                db.update_blog_article(article_id,
                    status='published', platform=f'reddit/r/{subreddit}',
                    platform_url=post_url,
                    platform_post_id=reddit_data.get('id', ''),
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                db.add_published_platform(article_id, 'reddit', post_url)
                return jsonify({'success': True, 'url': post_url})
            else:
                return jsonify({'success': False, 'error': f'Reddit error: {pub_resp.text}'}), 500
        
        elif platform == 'pinterest':
            pinterest_token = os.environ.get('PINTEREST_TOKEN', '')
            board_id = data.get('board_id', os.environ.get('PINTEREST_BOARD_ID', ''))
            image_url = data.get('image_url', '')
            
            if not pinterest_token or not board_id:
                return jsonify({'success': False, 'error': 'Pinterest credentials required. Set PINTEREST_TOKEN and PINTEREST_BOARD_ID in Render env vars.'}), 400
            
            pin_data = {
                'board_id': board_id,
                'title': clean_article_title(article['title'])[:100],
                'description': article.get('excerpt', '')[:500] + '\n\ndrinkforbidden.com',
                'link': 'https://drinkforbidden.com',
            }
            if image_url:
                pin_data['media_source'] = {'source_type': 'image_url', 'url': image_url}
            
            pub_resp = req.post(
                'https://api.pinterest.com/v5/pins',
                headers={
                    'Authorization': f'Bearer {pinterest_token}',
                    'Content-Type': 'application/json'
                },
                json=pin_data
            )
            
            if pub_resp.status_code in (200, 201):
                pin_resp = pub_resp.json()
                pin_url = f"https://pinterest.com/pin/{pin_resp.get('id', '')}"
                db.update_blog_article(article_id,
                    status='published', platform='pinterest',
                    platform_url=pin_url,
                    platform_post_id=pin_resp.get('id', ''),
                    published_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                db.add_published_platform(article_id, 'pinterest', pin_url)
                return jsonify({'success': True, 'url': pin_url})
            else:
                return jsonify({'success': False, 'error': f'Pinterest error: {pub_resp.text}'}), 500
        
        else:
            return jsonify({'success': False, 'error': 'Unknown platform'}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


QUORA_SYSTEM_PROMPT = """You are a bourbon expert answering questions on Quora. Write helpful, genuine answers that naturally mention Forbidden Bourbon when relevant. 

Rules:
- Sound like a real person sharing knowledge, NOT a brand account
- Lead with value — answer the question thoroughly first
- Only mention Forbidden Bourbon where it genuinely fits (1-2 natural mentions max)
- Include specific details that show expertise
- Keep it 150-300 words
- End with something engaging, not a sales pitch
- Include "drinkforbidden.com" once naturally if appropriate

About Forbidden Bourbon (use naturally when relevant):
- Premium Kentucky wheated bourbon by Master Distiller Marianne Eaves
- Bardstown Bourbon Company, Kentucky
- Mash bill: white corn, white wheat, high barley (all food-grade)
- Small Batch Select (50-barrel max) and Single Barrel

Return ONLY a JSON object: {"question": "...", "answer": "...", "tags": "tag1, tag2, tag3"}"""

REDDIT_SYSTEM_PROMPT = """You are a bourbon enthusiast posting on Reddit. Write authentic, community-friendly posts about bourbon topics. You occasionally enjoy Forbidden Bourbon but you're NOT a brand account.

Rules:
- Sound like a real bourbon fan sharing knowledge
- Use casual Reddit tone — abbreviations, lowercase, authentic voice
- Mention Forbidden only if genuinely relevant (never forced)
- Include actual useful info, tips, or discussion prompts
- No marketing language. Be genuine.
- Keep posts 200-400 words for text posts
- End with a question or discussion prompt to encourage comments

Return ONLY a JSON object: {"title": "...", "body": "...", "subreddit": "bourbon"}"""


@app.route('/api/blog/generate-quora', methods=['POST'])
def api_blog_generate_quora():
    """Generate Quora-style answer for copy/paste"""
    try:
        data = request.get_json()
        topic = data.get('topic', '')
        
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        openai_key = get_api_key('openai')
        
        if not anthropic_key and not openai_key:
            return jsonify({'success': False, 'error': 'No AI API key configured'}), 400
        
        user_message = f"Write a Quora answer about: {topic}"
        
        import requests as req
        import re
        
        if anthropic_key:
            resp = req.post('https://api.anthropic.com/v1/messages',
                headers={'x-api-key': anthropic_key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 1024, 'system': QUORA_SYSTEM_PROMPT,
                      'messages': [{'role': 'user', 'content': user_message}]}, timeout=30)
            text = ''.join(b['text'] for b in resp.json().get('content', []) if b.get('type') == 'text')
        else:
            resp = req.post('https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                json={'model': 'gpt-4o-mini', 'messages': [{'role': 'system', 'content': QUORA_SYSTEM_PROMPT},
                      {'role': 'user', 'content': user_message}], 'max_tokens': 1024}, timeout=30)
            text = resp.json()['choices'][0]['message']['content']
        
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            answer_data = json.loads(json_match.group())
        else:
            answer_data = {'question': topic, 'answer': text, 'tags': ''}
        
        # Save as article
        article_id = db.create_blog_article(
            title=f"Quora: {answer_data.get('question', topic)}",
            content=answer_data.get('answer', ''),
            excerpt=answer_data.get('answer', '')[:200],
            topic=topic, keywords=answer_data.get('tags', ''),
            status='draft', platform='quora',
            word_count=len(answer_data.get('answer', '').split())
        )
        
        return jsonify({'success': True, 'article': {
            'id': article_id,
            'question': answer_data.get('question', ''),
            'answer': answer_data.get('answer', ''),
            'tags': answer_data.get('tags', '')
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blog/generate-reddit', methods=['POST'])
def api_blog_generate_reddit():
    """Generate Reddit-style post"""
    try:
        data = request.get_json()
        topic = data.get('topic', '')
        subreddit = data.get('subreddit', 'bourbon')
        
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        openai_key = get_api_key('openai')
        
        if not anthropic_key and not openai_key:
            return jsonify({'success': False, 'error': 'No AI API key configured'}), 400
        
        user_message = f"Write a Reddit post for r/{subreddit} about: {topic}"
        
        import requests as req
        import re
        
        if anthropic_key:
            resp = req.post('https://api.anthropic.com/v1/messages',
                headers={'x-api-key': anthropic_key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 1024, 'system': REDDIT_SYSTEM_PROMPT,
                      'messages': [{'role': 'user', 'content': user_message}]}, timeout=30)
            text = ''.join(b['text'] for b in resp.json().get('content', []) if b.get('type') == 'text')
        else:
            resp = req.post('https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'},
                json={'model': 'gpt-4o-mini', 'messages': [{'role': 'system', 'content': REDDIT_SYSTEM_PROMPT},
                      {'role': 'user', 'content': user_message}], 'max_tokens': 1024}, timeout=30)
            text = resp.json()['choices'][0]['message']['content']
        
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            post_data = json.loads(json_match.group())
        else:
            post_data = {'title': topic, 'body': text, 'subreddit': subreddit}
        
        article_id = db.create_blog_article(
            title=f"Reddit r/{post_data.get('subreddit', subreddit)}: {post_data.get('title', topic)}",
            content=post_data.get('body', ''),
            excerpt=post_data.get('body', '')[:200],
            topic=topic, keywords=subreddit,
            status='draft', platform='reddit',
            word_count=len(post_data.get('body', '').split())
        )
        
        return jsonify({'success': True, 'article': {
            'id': article_id,
            'title': post_data.get('title', ''),
            'body': post_data.get('body', ''),
            'subreddit': post_data.get('subreddit', subreddit)
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blog/topics', methods=['GET'])
def api_blog_topics():
    topics = db.get_blog_topics()
    return jsonify({'success': True, 'topics': topics})


@app.route('/api/blog/topics', methods=['POST'])
def api_blog_add_topic():
    data = request.get_json()
    db.add_blog_topic(data.get('title', ''), data.get('category', 'general'), data.get('keywords', ''))
    return jsonify({'success': True})


# ============================================================
# BRAND INTEL API
# ============================================================

def scrape_mentions(deep=False):
    """Search the web for Forbidden Bourbon mentions across multiple sources"""
    import requests as req
    
    results = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    errors = []
    
    # === METHOD 1: DDGS package ===
    ddgs_count = 0
    search_queries = [
        'Forbidden Bourbon review',
        'Forbidden Bourbon Marianne Eaves',
        '"Forbidden Bourbon" tasting notes',
    ]
    
    if deep:
        search_queries += [
            'Forbidden Bourbon podcast interview',
            'Forbidden Bourbon award 2024',
            'Forbidden Bourbon youtube video review',
            'Forbidden Bourbon feature article',
            'Marianne Eaves distiller interview',
            'Forbidden wheated bourbon press',
        ]
    
    for query in search_queries:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                ddgs_results = list(ddgs.text(query, max_results=8))
            if ddgs_results:
                for r in ddgs_results:
                    url = r.get('href', '')
                    title = r.get('title', '')
                    snippet = r.get('body', '')
                    if url and 'duckduckgo' not in url:
                        classified = _classify_result(url, title, snippet, query)
                        if _is_relevant_content(classified):
                            results.append(classified)
                            ddgs_count += 1
            import time as time_mod
            time_mod.sleep(1.5)  # Rate limit protection
        except ImportError:
            errors.append('duckduckgo-search package not installed')
            break
        except Exception as e:
            errors.append(f"DDGS '{query}': {str(e)[:80]}")
            import time as time_mod
            time_mod.sleep(2)
            continue  # Try next query, don't break
    
    print(f"[Brand Intel] DDGS found {ddgs_count} relevant results ({len(errors)} errors)")
    
    # === METHOD 2: Known Forbidden Bourbon seed URLs (always add) ===
    seed_urls = [
        {'title': 'Forbidden Bourbon — Official Site', 'url': 'https://drinkforbidden.com', 'source': 'drinkforbidden.com', 'source_type': 'own_site', 'snippet': 'Official website of Forbidden Bourbon. A Twist on Tradition. Premium Kentucky wheated bourbon by Master Distiller Marianne Eaves.', 'query': 'seed'},
    ]
    results.extend(seed_urls)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in results:
        url_key = r['url'].rstrip('/').lower().replace('www.', '')
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            unique_results.append(r)
    
    print(f"[Brand Intel] Total unique results: {len(unique_results)}")
    return unique_results


def _is_relevant_content(result):
    """Filter out sales listings, generic retail pages, and irrelevant content.
    Only allow genuine editorial content about Forbidden Bourbon."""
    url = result.get('url', '').lower()
    title = result.get('title', '').lower()
    snippet = result.get('snippet', '').lower()
    combined = title + ' ' + snippet
    
    # MUST mention Forbidden (not just generic bourbon)
    if 'forbidden' not in combined and 'forbidden' not in url:
        return False
    
    # REJECT: Pure retail / e-commerce / shopping pages (NO RETAIL EVER)
    retail_signals = [
        'add to cart', 'buy now', 'add to bag', 'in stock', 'out of stock',
        'free shipping', 'price:', 'msrp:', 'shop now', 'checkout',
        '/cart', '/checkout', '/collections/', '/products/',
        'delivery available', 'ships to', 'order now', 'add to wishlist',
        'quantity:', 'select quantity', 'bottle size', 'case of',
    ]
    retail_domains = [
        'totalwine.com', 'wine-searcher.com', 'drizly.com', 'reservebar.com',
        'caskers.com', 'thewhiskyexchange.com', 'masterofmalt.com', 'flaviar.com',
        'klwines.com', 'caskcartel.com', 'thebarreltap.com', 'seelbachs.com',
        'bourbonoutfitter.com', 'woodencork.com', 'sipwhiskey.com', 'mash-bills.com',
        'binnys.com', 'specsonline.com', 'finewineandgoodspirits.com',
        'abc.virginia.gov', 'mainstreetliquor.com', 'thirstie.com',
        'minibar.com', 'gopuff.com', 'instacart.com', 'craftshack.com',
        'liquor.com/buy', 'frootbat.com', 'thewhiskyworld.com', 'dekanta.com',
        'oldtowntequila.com', 'breakingbourbon.com/buy', 'spiritshunter.com',
        'shopmbs.com', 'liquorama.net', 'nestorliquor.com', 'uptown-spirits.com',
        'shop.drinkforbidden.com',
    ]
    
    # Check for retail domain
    for domain in retail_domains:
        if domain in url:
            return False
    
    # Check for retail signals in content
    retail_count = sum(1 for sig in retail_signals if sig in combined or sig in url)
    if retail_count >= 2:
        return False
    
    # REJECT: Generic search result pages
    if any(x in url for x in ['/search?', '/search/', '?q=', '?text=', '?term=']):
        return False
    
    # REJECT: Social media listing pages (not specific posts)
    if 'reddit.com/r/' in url and '/search' in url:
        return False
    
    # ACCEPT: Known quality patterns
    quality_signals = [
        'review', 'tasting', 'interview', 'podcast', 'feature', 'profile',
        'article', 'news', 'press', 'award', 'event', 'marianne eaves',
        'master distiller', 'wheated bourbon', 'white corn', 'batch',
    ]
    quality_count = sum(1 for sig in quality_signals if sig in combined)
    
    # Must have at least one quality signal
    if quality_count == 0:
        # Exception: YouTube/TikTok videos about Forbidden are OK
        if any(v in url for v in ['youtube.com/watch', 'youtu.be/', 'tiktok.com/']):
            return True
        return False
    
    return True


def _classify_result(url, title, snippet, query):
    """Classify a search result by type"""
    from urllib.parse import urlparse
    
    source_type = 'article'
    source = urlparse(url).netloc.replace('www.', '') if url.startswith('http') else ''
    
    url_lower = url.lower()
    combined = (snippet + title).lower()
    
    if any(v in url_lower for v in ['youtube.com', 'youtu.be']):
        source_type = 'video'
    elif any(v in url_lower for v in ['reddit.com']):
        source_type = 'social'
    elif any(v in url_lower for v in ['instagram.com', 'twitter.com', 'x.com', 'facebook.com', 'tiktok.com']):
        source_type = 'social'
    elif any(v in url_lower for v in ['podcast', 'spotify.com', 'apple.com/podcast', 'podbean', 'anchor.fm']):
        source_type = 'podcast'
    elif any(v in combined for v in ['review', 'rating', 'tasting', 'score', '/10', 'stars', 'points']):
        source_type = 'review'
    elif any(v in url_lower for v in ['blog', 'medium.com', 'wordpress', 'substack']):
        source_type = 'blog'
    
    if 'drinkforbidden.com' in url_lower or 'shop.drinkforbidden' in url_lower:
        source_type = 'own_site'
    
    return {
        'title': title[:300], 'url': url[:500], 'source': source[:100],
        'source_type': source_type, 'snippet': snippet[:500], 'query': query
    }


def fetch_full_content(url):
    """Fetch the full text content of a URL"""
    import requests as req
    from bs4 import BeautifulSoup
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = req.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Remove scripts/styles
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'iframe']):
                tag.decompose()
            # Get article or main content
            article = soup.find('article') or soup.find('main') or soup.find('body')
            if article:
                text = article.get_text(separator='\n', strip=True)
                # Clean up
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                return '\n'.join(lines)[:10000]
        return ''
    except:
        return ''


@app.route('/api/brand-intel/scan', methods=['POST'])
def api_brand_intel_scan():
    """Run a web scan for Forbidden Bourbon mentions"""
    try:
        data = request.get_json() or {}
        deep = data.get('deep', False)
        
        results = scrape_mentions(deep=deep)
        saved = 0
        skipped = 0
        fetched = 0
        fetch_errors = 0
        
        for r in results:
            mention_id = db.add_brand_mention(
                title=r['title'],
                url=r['url'],
                source=r['source'],
                source_type=r['source_type'],
                snippet=r['snippet']
            )
            if mention_id:
                saved += 1
                # Auto-fetch full content for new mentions (skip videos/social)
                if r['source_type'] not in ('video', 'social', 'own_site') and r['url']:
                    try:
                        content = fetch_full_content(r['url'])
                        if content and len(content) > 100:
                            db.update_brand_mention(mention_id, full_content=content)
                            fetched += 1
                    except Exception:
                        fetch_errors += 1
            else:
                skipped += 1
        
        return jsonify({
            'success': True,
            'found': len(results),
            'saved': saved,
            'fetched_content': fetched,
            'fetch_errors': fetch_errors,
            'skipped_duplicates': skipped,
            'mode': 'deep' if deep else 'quick',
            'message': f"Scan complete. Found {len(results)} results, saved {saved} new mentions, {skipped} already existed."
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/brand-intel/fetch-content/<int:mention_id>', methods=['POST'])
def api_brand_intel_fetch_content(mention_id):
    """Fetch the full content of a mention"""
    try:
        mention = db.get_brand_mention(mention_id)
        if not mention:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        content = fetch_full_content(mention['url'])
        if content:
            db.update_brand_mention(mention_id, full_content=content)
            return jsonify({'success': True, 'content': content[:5000]})
        else:
            return jsonify({'success': False, 'error': 'Could not fetch content'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/brand-intel/mentions', methods=['GET'])
def api_brand_intel_mentions():
    source_type = request.args.get('type')
    starred = request.args.get('starred')
    mentions = db.get_brand_mentions(
        source_type=source_type if source_type else None,
        starred=int(starred) if starred else None
    )
    return jsonify({'success': True, 'mentions': mentions})


@app.route('/api/brand-intel/mentions/<int:mention_id>', methods=['PUT'])
def api_brand_intel_update(mention_id):
    data = request.get_json()
    db.update_brand_mention(mention_id, **data)
    return jsonify({'success': True})


@app.route('/api/brand-intel/mentions/<int:mention_id>', methods=['DELETE'])
def api_brand_intel_delete(mention_id):
    db.delete_brand_mention(mention_id)
    return jsonify({'success': True})


@app.route('/api/brand-intel/star/<int:mention_id>', methods=['POST'])
def api_brand_intel_star(mention_id):
    mention = db.get_brand_mention(mention_id)
    if mention:
        new_starred = 0 if mention.get('starred', 0) else 1
        db.update_brand_mention(mention_id, starred=new_starred)
        return jsonify({'success': True, 'starred': new_starred})
    return jsonify({'success': False}), 404


@app.route('/api/brand-intel/add', methods=['POST'])
def api_brand_intel_add():
    """Manually add a mention"""
    data = request.get_json()
    mention_id = db.add_brand_mention(
        title=data.get('title', ''),
        url=data.get('url', ''),
        source=data.get('source', ''),
        source_type=data.get('source_type', 'article'),
        snippet=data.get('snippet', ''),
        author=data.get('author', ''),
        date_published=data.get('date_published', '')
    )
    return jsonify({'success': True, 'id': mention_id})


# ============================================================
# GOOGLE ANALYTICS 4 API
# ============================================================

@app.route('/api/ga4/status')
def api_ga4_status():
    """Check if GA4 is configured"""
    return jsonify({
        'configured': ga4.is_configured(),
        'property_id': bool(os.environ.get('GA4_PROPERTY_ID', '')),
        'credentials': bool(os.environ.get('GA4_CREDENTIALS_JSON', '')),
    })

@app.route('/api/ga4/data')
def api_ga4_data():
    """Get all GA4 data for the dashboard"""
    days = request.args.get('days', 30, type=int)
    if not ga4.is_configured():
        return jsonify({'configured': False, 'error': 'GA4 not configured'})
    
    try:
        data = ga4.get_all_data(days)
        return jsonify(data)
    except Exception as e:
        return jsonify({'configured': True, 'error': str(e)})

@app.route('/api/ga4/realtime')
def api_ga4_realtime():
    """Get real-time data"""
    if not ga4.is_configured():
        return jsonify({'configured': False})
    return jsonify(ga4.get_realtime())


# ============================================================
# OUTREACH HUB API
# ============================================================

def scan_bourbon_contacts():
    """Find bourbon influencers, reviewers, bartenders, and media contacts with public emails"""
    import requests as req
    from bs4 import BeautifulSoup
    
    contacts = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    # === SEED: Known bourbon influencers with public business emails ===
    # These are all publicly listed business/press contacts
    seed_contacts = [
        # Tier 1: Major bourbon YouTubers (emails from YouTube About pages)
        {'name': 'Whiskey Tribe', 'platform': 'YouTube', 'platform_handle': 'WhiskeyTribe', 'platform_url': 'https://youtube.com/@WhiskeyTribe', 'followers': 400000, 'category': 'influencer', 'tier': '1', 'notes': 'Top bourbon YouTube channel. Check About page for business email.'},
        {'name': 'Bourbon Junkies', 'platform': 'YouTube', 'platform_handle': 'BourbonJunkies', 'platform_url': 'https://youtube.com/@BourbonJunkies', 'followers': 180000, 'category': 'influencer', 'tier': '1', 'notes': 'Major bourbon review channel. Check About page for business email.'},
        {'name': 'Bourbon Real Talk', 'platform': 'YouTube', 'platform_handle': 'BourbonRealTalk', 'platform_url': 'https://youtube.com/@BourbonRealTalk', 'followers': 100000, 'category': 'influencer', 'tier': '1', 'notes': 'Popular bourbon discussion/review channel.'},
        {'name': 'Fred Minnick', 'platform': 'YouTube', 'platform_handle': 'FredMinnick', 'platform_url': 'https://youtube.com/@FredMinnick', 'followers': 90000, 'category': 'media', 'tier': '1', 'notes': 'Bourbon author, competition judge, major industry voice. Check fredminnick.com for press contact.'},
        {'name': 'Its Bourbon Night', 'platform': 'YouTube', 'platform_handle': 'ItsBourbonNight', 'platform_url': 'https://youtube.com/@ItsBourbonNight', 'followers': 75000, 'category': 'influencer', 'tier': '1', 'notes': 'Bourbon review and tasting channel.'},
        {'name': 'Bourbon Pursuit', 'platform': 'Podcast', 'platform_handle': 'BourbonPursuit', 'platform_url': 'https://bourbonpursuit.com', 'followers': 50000, 'category': 'influencer', 'tier': '1', 'notes': 'Top bourbon podcast. Check website for sponsor/contact info.'},
        {'name': 'The Mash & Drum', 'platform': 'YouTube', 'platform_handle': 'TheMashAndDrum', 'platform_url': 'https://youtube.com/@TheMashAndDrum', 'followers': 60000, 'category': 'influencer', 'tier': '1', 'notes': 'Detailed bourbon reviews and channel.'},
        {'name': 'Sipp\'n Corn', 'platform': 'YouTube', 'platform_handle': 'SippnCorn', 'platform_url': 'https://youtube.com/@SippnCorn', 'followers': 50000, 'category': 'influencer', 'tier': '1', 'notes': 'Popular bourbon review channel.'},
        
        # Tier 1: Major bourbon bloggers/review sites
        {'name': 'Breaking Bourbon', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.breakingbourbon.com', 'followers': 0, 'category': 'media', 'tier': '1', 'notes': 'Top bourbon review website. Check contact page for editorial email.'},
        {'name': 'Bourbon Culture', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.bourbonculture.com', 'followers': 0, 'category': 'media', 'tier': '1', 'notes': 'Detailed bourbon review blog. Check contact page.'},
        {'name': 'The Whiskey Shelf', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://thewhiskeyshelf.com', 'followers': 0, 'category': 'media', 'tier': '1', 'notes': 'Comprehensive whiskey review site. Check contact page.'},
        {'name': 'Whisky Advocate', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.whiskyadvocate.com', 'followers': 0, 'category': 'media', 'tier': '1', 'notes': 'Major spirits publication. Submit for review via website.'},
        {'name': 'The Bourbon Review', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.thebourbonreview.com', 'followers': 0, 'category': 'media', 'tier': '1', 'notes': 'Bourbon-focused publication. Check for editorial contact.'},
        
        # Tier 2: Instagram bourbon influencers
        {'name': 'Bourbon_Blogger', 'platform': 'Instagram', 'platform_handle': 'bourbon_blogger', 'platform_url': 'https://instagram.com/bourbon_blogger', 'followers': 50000, 'category': 'influencer', 'tier': '2', 'notes': 'Check Instagram bio for business email.'},
        {'name': 'BourbonandBanter', 'platform': 'Instagram', 'platform_handle': 'bourbonbanter', 'platform_url': 'https://instagram.com/bourbonbanter', 'followers': 40000, 'category': 'influencer', 'tier': '2', 'notes': 'Bourbon lifestyle content. Check bio for email.'},
        {'name': 'TheBourbonFinder', 'platform': 'Instagram', 'platform_handle': 'thebourbonfinder', 'platform_url': 'https://instagram.com/thebourbonfinder', 'followers': 30000, 'category': 'influencer', 'tier': '2', 'notes': 'Bourbon hunting and reviews. Check bio for email.'},
        
        # Tier 2: Reddit community leaders
        {'name': 'r/bourbon moderators', 'platform': 'Reddit', 'platform_handle': 'r/bourbon', 'platform_url': 'https://reddit.com/r/bourbon', 'followers': 500000, 'category': 'community', 'tier': '2', 'notes': '500k+ member bourbon subreddit. Message moderators for AMA or promotion guidelines.'},
        {'name': 'r/whiskey moderators', 'platform': 'Reddit', 'platform_handle': 'r/whiskey', 'platform_url': 'https://reddit.com/r/whiskey', 'followers': 400000, 'category': 'community', 'tier': '2', 'notes': '400k+ member whiskey community.'},
        
        # Tier 2: Adjacent lifestyle influencers (BBQ, cigars, outdoors)
        {'name': 'Meat Church BBQ', 'platform': 'YouTube', 'platform_handle': 'MeatChurchBBQ', 'platform_url': 'https://youtube.com/@MeatChurchBBQ', 'followers': 600000, 'category': 'adjacent', 'tier': '2', 'notes': 'Major BBQ channel. Bourbon + BBQ pairing collab potential. Check About for business email.'},
        {'name': 'How To BBQ Right', 'platform': 'YouTube', 'platform_handle': 'HowToBBQRight', 'platform_url': 'https://youtube.com/@HowToBBQRight', 'followers': 2000000, 'category': 'adjacent', 'tier': '1', 'notes': 'Huge BBQ channel. Bourbon is natural pairing content. Check About for business email.'},
        {'name': 'Cigar Obsession', 'platform': 'YouTube', 'platform_handle': 'CigarObsession', 'platform_url': 'https://youtube.com/@CigarObsession', 'followers': 250000, 'category': 'adjacent', 'tier': '2', 'notes': 'Cigar reviews often feature bourbon pairings. Check About for email.'},
        
        # Tier 2: Bourbon events & festivals
        {'name': 'Bourbon & Beyond Festival', 'platform': 'Event', 'platform_handle': '', 'platform_url': 'https://bourbonandbeyond.com', 'followers': 0, 'category': 'industry', 'tier': '2', 'notes': 'Major bourbon festival in Louisville. Check website for vendor/sponsor contact.'},
        {'name': 'Kentucky Bourbon Festival', 'platform': 'Event', 'platform_handle': '', 'platform_url': 'https://kybourbonfestival.com', 'followers': 0, 'category': 'industry', 'tier': '2', 'notes': 'Annual Bardstown bourbon festival. Check website for exhibitor contact.'},
        {'name': 'Tales of the Cocktail', 'platform': 'Event', 'platform_handle': '', 'platform_url': 'https://talesofthecocktail.org', 'followers': 0, 'category': 'industry', 'tier': '2', 'notes': 'Huge cocktail industry event. Sponsor and exhibitor opportunities.'},
        {'name': 'WhiskyFest', 'platform': 'Event', 'platform_handle': '', 'platform_url': 'https://whiskyadvocate.com/whiskyfest', 'followers': 0, 'category': 'industry', 'tier': '2', 'notes': 'Whisky Advocate tasting events. Submit for inclusion.'},
        
        # Tier 3: Bourbon bars and retailers
        {'name': 'Haymarket Whiskey Bar', 'platform': 'Bar', 'platform_handle': '', 'platform_url': 'https://www.haymarketwhiskeybar.com', 'followers': 0, 'category': 'industry', 'tier': '3', 'notes': 'Louisville bourbon bar. 400+ bourbon selection. Check website for buyer contact.'},
        {'name': 'Silver Dollar Louisville', 'platform': 'Bar', 'platform_handle': '', 'platform_url': 'https://www.whiskeybythedrink.com', 'followers': 0, 'category': 'industry', 'tier': '3', 'notes': 'Award-winning Louisville bourbon bar. Check website for manager contact.'},
        {'name': 'Jack Rose Dining Saloon', 'platform': 'Bar', 'platform_handle': '', 'platform_url': 'https://www.jackrosediningsaloon.com', 'followers': 0, 'category': 'industry', 'tier': '3', 'notes': 'DC bourbon bar with 2700+ whiskeys. Check website for buyer.'},
        {'name': 'Julep (Houston)', 'platform': 'Bar', 'platform_handle': '', 'platform_url': 'https://www.julephouston.com', 'followers': 0, 'category': 'industry', 'tier': '3', 'notes': 'Award-winning Houston whiskey bar. Check website for buyer contact.'},
        
        # Tier 3: Media/press
        {'name': 'VinePair', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://vinepair.com', 'followers': 0, 'category': 'media', 'tier': '2', 'notes': 'Major drinks publication. Check editorial contact for reviews/features.'},
        {'name': 'Punch Drink', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://punchdrink.com', 'followers': 0, 'category': 'media', 'tier': '2', 'notes': 'Cocktail and spirits journalism. Check contact page.'},
        {'name': 'Liquor.com', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.liquor.com', 'followers': 0, 'category': 'media', 'tier': '2', 'notes': 'Major spirits media site. Submit for review coverage.'},
        {'name': 'The Spirits Business', 'platform': 'Website', 'platform_handle': '', 'platform_url': 'https://www.thespiritsbusiness.com', 'followers': 0, 'category': 'media', 'tier': '2', 'notes': 'Industry trade publication. Check for press submission.'},
        {'name': 'Distiller.com', 'platform': 'App/Website', 'platform_handle': '', 'platform_url': 'https://distiller.com', 'followers': 0, 'category': 'media', 'tier': '2', 'notes': 'Bourbon rating/review platform. Submit brand for listing and reviews.'},
    ]
    
    contacts.extend(seed_contacts)
    
    # === SCRAPE: Try to find emails from YouTube About pages and blog contact pages ===
    email_scrape_targets = [
        'https://www.breakingbourbon.com/contact',
        'https://www.bourbonculture.com/contact',
        'https://thewhiskeyshelf.com/contact/',
        'https://www.fredminnick.com/contact/',
        'https://bourbonpursuit.com/contact/',
        'https://www.thebourbonreview.com/contact',
        'https://vinepair.com/contact/',
    ]
    
    import re
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    
    for url in email_scrape_targets:
        try:
            resp = req.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                emails_found = email_pattern.findall(resp.text)
                for email in emails_found:
                    # Skip common non-person emails
                    if any(skip in email.lower() for skip in ['noreply', 'privacy', 'support', 'admin', 'webmaster', 'example.com']):
                        continue
                    domain = url.split('/')[2].replace('www.', '')
                    # Find matching contact and add email
                    for c in contacts:
                        if domain in c.get('platform_url', ''):
                            c['email'] = email
                            break
                    else:
                        contacts.append({
                            'name': domain, 'email': email, 'platform': 'Website',
                            'platform_handle': '', 'platform_url': url.rsplit('/', 1)[0],
                            'followers': 0, 'category': 'media', 'tier': '2',
                            'notes': f'Email found on contact page: {url}'
                        })
            import time as time_mod
            time_mod.sleep(1)
        except Exception as e:
            print(f"[Outreach] Email scrape error for {url}: {e}")
    
    # === SCRAPE: Try DuckDuckGo for more bourbon influencers ===
    try:
        from duckduckgo_search import DDGS
        search_queries = [
            'bourbon youtube channel review',
            'bourbon blog review contact',
            'bourbon influencer Instagram',
            'bourbon podcast host',
            'bourbon bar best america',
            'BBQ bourbon pairing youtube',
        ]
        for q in search_queries:
            try:
                for r in DDGS().text(q, max_results=5):
                    url = r.get('href', '')
                    title = r.get('title', '')
                    snippet = r.get('body', '')
                    if url and 'forbidden' not in url.lower() and 'duckduckgo' not in url:
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc.replace('www.', '')
                        cat = 'influencer'
                        if 'youtube' in url: cat = 'influencer'
                        elif any(w in url for w in ['bar', 'restaurant', 'saloon']): cat = 'industry'
                        elif any(w in url for w in ['magazine', 'advocate', 'vine']): cat = 'media'
                        contacts.append({
                            'name': title[:100], 'email': '', 'platform': domain,
                            'platform_handle': '', 'platform_url': url[:500],
                            'followers': 0, 'category': cat, 'tier': '3',
                            'notes': snippet[:300]
                        })
                import time as time_mod
                time_mod.sleep(1)
            except:
                pass
    except:
        print("[Outreach] DDGS not available for expanded search")
    
    return contacts


@app.route('/api/outreach/scan', methods=['POST'])
def api_outreach_scan():
    try:
        contacts = scan_bourbon_contacts()
        saved = 0
        emails_found = 0
        for c in contacts:
            cid = db.add_outreach_contact(
                name=c['name'], email=c.get('email', ''), platform=c.get('platform', ''),
                platform_handle=c.get('platform_handle', ''), platform_url=c.get('platform_url', ''),
                followers=c.get('followers', 0), category=c.get('category', 'influencer'),
                tier=c.get('tier', '1'), notes=c.get('notes', '')
            )
            if cid:
                saved += 1
                if c.get('email'):
                    emails_found += 1
        return jsonify({'success': True, 'found': len(contacts), 'saved': saved, 'emails_found': emails_found})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/outreach/contacts', methods=['POST'])
def api_outreach_add():
    data = request.get_json()
    cid = db.add_outreach_contact(**{k: data[k] for k in data if k in ['name','email','platform','platform_handle','platform_url','followers','category','tier','notes']})
    return jsonify({'success': True, 'id': cid})


@app.route('/api/outreach/contacts/<int:contact_id>', methods=['PUT'])
def api_outreach_update(contact_id):
    data = request.get_json()
    db.update_outreach_contact(contact_id, **data)
    return jsonify({'success': True})


@app.route('/api/outreach/contacts/<int:contact_id>', methods=['DELETE'])
def api_outreach_delete(contact_id):
    db.delete_outreach_contact(contact_id)
    return jsonify({'success': True})


@app.route('/api/outreach/contacts/<int:contact_id>/toggle-sent', methods=['POST'])
def api_outreach_toggle_sent(contact_id):
    contact = db.get_outreach_contact(contact_id)
    if contact:
        new_val = 0 if contact.get('product_sent', 0) else 1
        db.update_outreach_contact(contact_id, product_sent=new_val)
        if new_val:
            db.update_outreach_contact(contact_id, status='product_sent')
        return jsonify({'success': True, 'product_sent': new_val})
    return jsonify({'success': False}), 404


@app.route('/api/outreach/customer-emails')
def api_customer_emails():
    """Get all customer emails for the email list"""
    emails = db.get_customer_emails()
    return jsonify({'success': True, 'emails': [dict(e) for e in emails], 'count': len(emails)})


@app.route('/api/outreach/customer-emails/export')
def api_customer_emails_export():
    """Export customer emails as CSV"""
    emails = db.get_customer_emails()
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Email', 'Orders', 'Total Spend', 'AOV', 'First Order', 'Last Order'])
    for e in emails:
        writer.writerow([e['email'], e.get('orders', 1), e.get('total_spend', 0), e.get('aov', 0), e.get('first_order', ''), e.get('last_order', '')])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=forbidden_customer_emails.csv'})


# ============================================================
# EMAIL CAMPAIGNS (SendGrid)
# ============================================================

@app.route('/api/email/campaigns', methods=['GET'])
def api_get_email_campaigns():
    """Get all email campaigns"""
    campaigns = db.get_email_campaigns()
    return jsonify({'campaigns': campaigns})


@app.route('/api/email/campaigns', methods=['POST'])
def api_create_email_campaign():
    """Create and optionally send an email campaign"""
    data = request.get_json()
    subject = data.get('subject', '')
    body = data.get('body', '')
    send_now = data.get('send_now', False)
    
    if not subject or not body:
        return jsonify({'error': 'Subject and body required'}), 400
    
    # Get all customer emails
    emails = db.get_customer_emails()
    recipient_count = len(emails)
    
    sendgrid_key = os.environ.get('SENDGRID_API_KEY', '')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', '')
    
    # Create campaign record
    campaign_id = db.create_email_campaign(
        subject=subject, body=body,
        from_email=from_email,
        recipient_count=recipient_count
    )
    
    if not campaign_id:
        return jsonify({'error': 'Failed to create campaign'}), 500
    
    if send_now:
        if not sendgrid_key or not from_email:
            return jsonify({
                'campaign_id': campaign_id,
                'status': 'draft',
                'message': 'Campaign saved as draft. Set SENDGRID_API_KEY and SENDGRID_FROM_EMAIL env vars on Render to enable sending.',
                'recipient_count': recipient_count
            })
        
        # Send via SendGrid
        import requests as req
        sent = 0
        failed = 0
        
        # Send in batches of 50 using personalizations
        batch_size = 50
        for i in range(0, len(emails), batch_size):
            batch = emails[i:i + batch_size]
            personalizations = []
            for e in batch:
                personalizations.append({
                    'to': [{'email': e['email']}]
                })
            
            try:
                resp = req.post('https://api.sendgrid.com/v3/mail/send',
                    headers={
                        'Authorization': f'Bearer {sendgrid_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'personalizations': personalizations,
                        'from': {'email': from_email, 'name': 'Forbidden Bourbon'},
                        'subject': subject,
                        'content': [
                            {'type': 'text/html', 'value': body}
                        ]
                    },
                    timeout=30
                )
                
                if resp.status_code in (200, 201, 202):
                    sent += len(batch)
                else:
                    failed += len(batch)
                    print(f"[Email] SendGrid error: {resp.status_code} - {resp.text}")
            except Exception as e:
                failed += len(batch)
                print(f"[Email] Send error: {e}")
        
        db.update_email_campaign(campaign_id,
            status='sent',
            sent_count=sent,
            failed_count=failed,
            sent_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
        
        return jsonify({
            'campaign_id': campaign_id,
            'status': 'sent',
            'sent': sent,
            'failed': failed,
            'recipient_count': recipient_count
        })
    
    return jsonify({
        'campaign_id': campaign_id,
        'status': 'draft',
        'recipient_count': recipient_count
    })


@app.route('/api/email/test', methods=['POST'])
def api_test_email():
    """Send a test email to verify setup"""
    data = request.get_json()
    test_email = data.get('email', '')
    subject = data.get('subject', 'Test Email from Forbidden Bourbon')
    body = data.get('body', '<h2>Test Email</h2><p>Your email sending is working!</p>')
    
    sendgrid_key = os.environ.get('SENDGRID_API_KEY', '')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', '')
    
    if not sendgrid_key or not from_email:
        return jsonify({'error': 'SENDGRID_API_KEY and SENDGRID_FROM_EMAIL not configured'}), 400
    if not test_email:
        return jsonify({'error': 'Test email address required'}), 400
    
    import requests as req
    try:
        resp = req.post('https://api.sendgrid.com/v3/mail/send',
            headers={'Authorization': f'Bearer {sendgrid_key}', 'Content-Type': 'application/json'},
            json={
                'personalizations': [{'to': [{'email': test_email}]}],
                'from': {'email': from_email, 'name': 'Forbidden Bourbon'},
                'subject': subject,
                'content': [{'type': 'text/html', 'value': body}]
            }, timeout=15)
        
        if resp.status_code in (200, 201, 202):
            return jsonify({'success': True, 'message': f'Test email sent to {test_email}'})
        else:
            return jsonify({'error': f'SendGrid error: {resp.status_code}', 'details': resp.text}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/email/status', methods=['GET'])
def api_email_status():
    """Check if email sending is configured"""
    sendgrid_key = os.environ.get('SENDGRID_API_KEY', '')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', '')
    return jsonify({
        'configured': bool(sendgrid_key and from_email),
        'from_email': from_email if from_email else 'Not set',
        'provider': 'SendGrid'
    })


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    """Get notifications"""
    try:
        notifs = db.get_notifications(limit=30)
        unread = db.get_unread_notification_count()
        print(f"[Notifications API] Returning {len(notifs)} notifications, {unread} unread")
        return jsonify({'notifications': notifs, 'unread_count': unread})
    except Exception as e:
        print(f"[Notifications API] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'notifications': [], 'unread_count': 0, 'error': str(e)})


@app.route('/api/notifications/read', methods=['POST'])
def api_mark_notifications_read():
    """Mark all notifications as read"""
    db.mark_notifications_read()
    return jsonify({'success': True})


@app.route('/api/notifications/count', methods=['GET'])
def api_notification_count():
    """Get unread notification count"""
    count = db.get_unread_notification_count()
    return jsonify({'count': count})


# ============================================================
# BLOGGER OAUTH2 AUTHENTICATION
# ============================================================

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
BLOGGER_REDIRECT_URI = os.environ.get('RENDER_EXTERNAL_URL', 'https://forbidden-command-center.onrender.com') + '/auth/blogger/callback'

def get_blogger_access_token():
    """Get a valid Blogger access token, refreshing if needed"""
    import requests as req
    
    token_data = db.get_oauth_token('blogger')
    if not token_data or not token_data.get('refresh_token'):
        print("[Blogger OAuth] No refresh token stored")
        return None
    
    # Try refreshing the token
    try:
        resp = req.post('https://oauth2.googleapis.com/token', data={
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': token_data['refresh_token'],
            'grant_type': 'refresh_token'
        })
        if resp.status_code == 200:
            data = resp.json()
            access_token = data['access_token']
            expires_in = data.get('expires_in', 3600)
            expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).strftime('%Y-%m-%d %H:%M:%S')
            db.save_oauth_token('blogger', access_token=access_token, expires_at=expires_at)
            print(f"[Blogger OAuth] Token refreshed, expires in {expires_in}s")
            return access_token
        else:
            print(f"[Blogger OAuth] Refresh failed: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"[Blogger OAuth] Error: {e}")
        return None


@app.route('/api/blog/token-status')
def blog_token_status():
    """Check OAuth token status for debugging"""
    token = db.get_oauth_token('blogger')
    has_refresh = bool(token and token.get('refresh_token'))
    has_access = bool(token and token.get('access_token'))
    blogger_token = get_blogger_access_token() if has_refresh else None
    return jsonify({
        'blogger': {
            'has_refresh_token': has_refresh,
            'has_access_token': has_access,
            'can_refresh': blogger_token is not None,
            'updated_at': token.get('updated_at', '') if token else '',
            'blog_id': os.environ.get('BLOGGER_BLOG_ID', '(not set)'),
            'google_client_id': 'set' if GOOGLE_CLIENT_ID else '(not set)',
        },
        'wordpress': {
            'site': os.environ.get('WORDPRESS_SITE', '(not set)'),
            'has_token': bool(os.environ.get('WORDPRESS_TOKEN', '')),
        }
    })


@app.route('/auth/blogger/start')
def auth_blogger_start():
    """Start Blogger OAuth2 flow"""
    if not GOOGLE_CLIENT_ID:
        return "GOOGLE_CLIENT_ID not configured", 400
    
    auth_url = (
        'https://accounts.google.com/o/oauth2/v2/auth?'
        f'client_id={GOOGLE_CLIENT_ID}'
        f'&redirect_uri={BLOGGER_REDIRECT_URI}'
        '&response_type=code'
        '&scope=https://www.googleapis.com/auth/blogger'
        '&access_type=offline'
        '&prompt=consent'
    )
    return redirect(auth_url)


@app.route('/auth/blogger/callback')
def auth_blogger_callback():
    """Handle Blogger OAuth2 callback"""
    import requests as req
    
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        return f"<h2>Auth Error: {error}</h2><p><a href='/blog-hub'>Back to Blog Hub</a></p>"
    
    if not code:
        return "<h2>No authorization code received</h2><p><a href='/blog-hub'>Back to Blog Hub</a></p>"
    
    # Exchange code for tokens
    try:
        resp = req.post('https://oauth2.googleapis.com/token', data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': BLOGGER_REDIRECT_URI,
            'grant_type': 'authorization_code'
        })
        
        if resp.status_code == 200:
            data = resp.json()
            access_token = data['access_token']
            refresh_token = data.get('refresh_token', '')
            expires_in = data.get('expires_in', 3600)
            expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).strftime('%Y-%m-%d %H:%M:%S')
            
            db.save_oauth_token('blogger', access_token=access_token, 
                              refresh_token=refresh_token, expires_at=expires_at)
            
            db.create_notification('success', '✅ Blogger Connected!',
                'Blogger OAuth2 authorized. Blog posts can now publish automatically.', '/blog-hub')
            
            print(f"[Blogger OAuth] ✓ Authorized! Refresh token: {'yes' if refresh_token else 'no'}")
            return redirect('/blog-hub')
        else:
            print(f"[Blogger OAuth] Token exchange failed: {resp.text}")
            return f"<h2>Auth Failed</h2><p>{resp.text}</p><p><a href='/blog-hub'>Back to Blog Hub</a></p>"
    except Exception as e:
        print(f"[Blogger OAuth] Callback error: {e}")
        return f"<h2>Auth Error</h2><p>{str(e)}</p><p><a href='/blog-hub'>Back to Blog Hub</a></p>"


# ============================================================
# MANUAL BLOG TRIGGER
# ============================================================

@app.route('/api/blog/trigger', methods=['POST'])
def api_blog_trigger():
    """Manually trigger a blog post"""
    data = request.get_json() or {}
    platform = data.get('platform', '')
    
    # Auto-detect platform from schedule if not specified
    if not platform:
        today = datetime.utcnow().weekday()
        platforms_today = BLOG_SCHEDULE.get(today, [])
        if platforms_today:
            platform = platforms_today[0]
        else:
            platform = 'medium'  # fallback
    
    db.create_notification('info', f"🔄 Blog generation started: {platform.title()}",
        f"Manually triggered blog post for {platform}", '/blog-hub')
    
    # Run in a thread so it doesn't block the response
    import threading
    def run_blog():
        try:
            print(f"[Blog Trigger] Starting blog_auto_post for {platform}")
            result = blog_auto_post(platform)
            print(f"[Blog Trigger] Result: {result}")
            if not result:
                db.create_notification('error', f"❌ Blog generation failed: {platform}",
                    "Check that ANTHROPIC_API_KEY or OPENAI_API_KEY is set on Render.", '/blog-hub')
        except Exception as e:
            print(f"[Blog Trigger] Exception: {e}")
            import traceback
            traceback.print_exc()
            db.create_notification('error', f"❌ Blog error: {platform}",
                f"Error: {str(e)[:200]}", '/blog-hub')
    
    t = threading.Thread(target=run_blog, daemon=True)
    t.start()
    
    return jsonify({
        'success': True,
        'message': f'Blog generation started for {platform}. Check notifications for results.',
        'platform': platform
    })


@app.route('/api/blog/scheduler-status', methods=['GET'])
def api_blog_scheduler_status():
    """Check blog auto-scheduler status"""
    today = datetime.utcnow().weekday()
    platforms_today = BLOG_SCHEDULE.get(today, [])
    
    # Check recent auto-posts
    recent = db.get_blog_articles(limit=10)
    
    return jsonify({
        'active': True,
        'today': datetime.utcnow().strftime('%A'),
        'platforms_today': platforms_today,
        'schedule': {
            'Monday': 'Medium article',
            'Tuesday': 'Reddit post',
            'Wednesday': 'WordPress article',
            'Thursday': 'Reddit post',
            'Friday': 'Blogger article',
            'Saturday': 'Off',
            'Sunday': 'Off'
        },
        'recent_count': len(recent),
        'total_published': db.get_blog_stats()['published']
    })


# ============================================================
# RUN
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
