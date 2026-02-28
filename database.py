# Forbidden Bourbon Command Center Database v12.1 — Blog tables + 6 platform seeds
import os
import json
from datetime import datetime, timedelta

# ============================================================
# DATABASE CONNECTION - PostgreSQL (Render) or SQLite (local)
# ============================================================

DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # Render gives postgres:// but psycopg2 needs postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
else:
    import sqlite3

DB_PATH = os.environ.get('DB_PATH', 'command_center.db')


def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _execute(conn, sql, params=None):
    """Execute SQL, converting ? placeholders to %s for PostgreSQL"""
    if USE_POSTGRES:
        sql = sql.replace('?', '%s')
        # Convert SQLite-specific syntax
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        # Convert SQLite's INSERT OR IGNORE to Postgres ON CONFLICT DO NOTHING
        if 'INSERT OR IGNORE' in sql:
            sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
            sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if USE_POSTGRES else conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur


def _fetchone(conn, sql, params=None):
    cur = _execute(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    for key in d:
        if hasattr(d[key], 'strftime'):
            d[key] = d[key].strftime('%Y-%m-%d %H:%M:%S')
    return d


def _fetchall(conn, sql, params=None):
    cur = _execute(conn, sql, params)
    rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Convert datetime objects to strings for JSON serialization (Postgres returns datetime, SQLite returns string)
        for key in d:
            if hasattr(d[key], 'strftime'):
                d[key] = d[key].strftime('%Y-%m-%d %H:%M:%S')
        result.append(d)
    return result


# ============================================================
# INIT DATABASE
# ============================================================

def init_db():
    conn = get_db()

    if USE_POSTGRES:
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS platforms (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                icon TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                api_secret TEXT DEFAULT '',
                access_token TEXT DEFAULT '',
                refresh_token TEXT DEFAULT '',
                additional_config TEXT DEFAULT '{}',
                connected INTEGER DEFAULT 0,
                username TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                image_path TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                post_type TEXT DEFAULT 'standard',
                hashtags TEXT DEFAULT '',
                link_url TEXT DEFAULT '',
                ai_generated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scheduled_at TIMESTAMP,
                published_at TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS post_platforms (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                platform_name TEXT NOT NULL,
                platform_post_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                published_at TIMESTAMP,
                error_message TEXT DEFAULT ''
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS content_templates (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                hashtags TEXT DEFAULT '',
                is_favorite INTEGER DEFAULT 0,
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS hashtag_groups (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                hashtags TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS analytics (
                id SERIAL PRIMARY KEY,
                post_id INTEGER REFERENCES posts(id) ON DELETE SET NULL,
                platform_name TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                retweets INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                post_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ai_gallery (
                id SERIAL PRIMARY KEY,
                media_type TEXT NOT NULL,
                url TEXT NOT NULL,
                prompt TEXT DEFAULT '',
                revised_prompt TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add new columns if they don't exist
        try:
            cur.execute("ALTER TABLE ai_gallery ADD COLUMN saved BOOLEAN DEFAULT FALSE")
        except Exception:
            if USE_POSTGRES:
                conn.rollback()
        try:
            cur.execute("ALTER TABLE ai_gallery ADD COLUMN bottle_type TEXT DEFAULT ''")
        except Exception:
            if USE_POSTGRES:
                conn.rollback()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS blog_articles (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT DEFAULT '',
                topic TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                platform TEXT DEFAULT '',
                platform_url TEXT DEFAULT '',
                platform_post_id TEXT DEFAULT '',
                published_platforms TEXT DEFAULT '{}',
                word_count INTEGER DEFAULT 0,
                ai_generated INTEGER DEFAULT 1,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add published_platforms column if missing (existing tables)
        try:
            cur.execute("ALTER TABLE blog_articles ADD COLUMN published_platforms TEXT DEFAULT '{}'")
            conn.commit()
        except:
            conn.rollback()
        
        # Backfill published_platforms from existing platform/platform_url for pre-migration articles
        try:
            cur.execute("SELECT id, platform, platform_url FROM blog_articles WHERE platform != '' AND (published_platforms IS NULL OR published_platforms = '{}')")
            rows = cur.fetchall()
            for row in rows:
                import json as _json
                pp = _json.dumps({row[1]: row[2] or ''})
                cur.execute("UPDATE blog_articles SET published_platforms = %s WHERE id = %s", (pp, row[0]))
            if rows:
                conn.commit()
        except:
            conn.rollback()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS blog_topics (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                keywords TEXT DEFAULT '',
                last_used TIMESTAMP,
                times_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS brand_mentions (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT DEFAULT '',
                source TEXT DEFAULT '',
                source_type TEXT DEFAULT 'article',
                snippet TEXT DEFAULT '',
                full_content TEXT DEFAULT '',
                author TEXT DEFAULT '',
                sentiment TEXT DEFAULT 'neutral',
                date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_published TEXT DEFAULT '',
                starred INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS outreach_contacts (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                platform TEXT DEFAULT '',
                platform_handle TEXT DEFAULT '',
                platform_url TEXT DEFAULT '',
                followers INTEGER DEFAULT 0,
                category TEXT DEFAULT 'influencer',
                tier TEXT DEFAULT '1',
                status TEXT DEFAULT 'new',
                notes TEXT DEFAULT '',
                last_contacted TEXT DEFAULT '',
                product_sent INTEGER DEFAULT 0,
                responded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS customer_emails (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                orders INTEGER DEFAULT 1,
                total_spend REAL DEFAULT 0,
                aov REAL DEFAULT 0,
                first_order TEXT DEFAULT '',
                last_order TEXT DEFAULT '',
                source TEXT DEFAULT 'mash_networks',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id SERIAL PRIMARY KEY,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                from_name TEXT DEFAULT 'Forbidden Bourbon',
                from_email TEXT DEFAULT '',
                recipient_count INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft',
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                link TEXT DEFAULT '',
                read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id SERIAL PRIMARY KEY,
                service TEXT NOT NULL UNIQUE,
                access_token TEXT DEFAULT '',
                refresh_token TEXT DEFAULT '',
                expires_at TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
    else:
        # SQLite schema
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS platforms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                icon TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                api_secret TEXT DEFAULT '',
                access_token TEXT DEFAULT '',
                refresh_token TEXT DEFAULT '',
                additional_config TEXT DEFAULT '{}',
                connected INTEGER DEFAULT 0,
                username TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                image_path TEXT DEFAULT '',
                status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'scheduled', 'published', 'failed', 'archived')),
                post_type TEXT DEFAULT 'standard' CHECK(post_type IN ('standard', 'thread', 'story', 'reel')),
                hashtags TEXT DEFAULT '',
                link_url TEXT DEFAULT '',
                ai_generated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scheduled_at TIMESTAMP,
                published_at TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_platforms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                platform_name TEXT NOT NULL,
                platform_post_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'published', 'failed', 'skipped')),
                published_at TIMESTAMP,
                error_message TEXT DEFAULT '',
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                hashtags TEXT DEFAULT '',
                is_favorite INTEGER DEFAULT 0,
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hashtag_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hashtags TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                platform_name TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                retweets INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE SET NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                post_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blog_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT DEFAULT '',
                topic TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                platform TEXT DEFAULT '',
                platform_url TEXT DEFAULT '',
                platform_post_id TEXT DEFAULT '',
                published_platforms TEXT DEFAULT '{}',
                word_count INTEGER DEFAULT 0,
                ai_generated INTEGER DEFAULT 1,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add published_platforms column if missing (existing tables)
        try:
            cursor.execute("ALTER TABLE blog_articles ADD COLUMN published_platforms TEXT DEFAULT '{}'")
            conn.commit()
        except:
            pass
        
        # Backfill published_platforms from existing platform/platform_url for pre-migration articles
        try:
            cursor.execute("SELECT id, platform, platform_url FROM blog_articles WHERE platform != '' AND (published_platforms IS NULL OR published_platforms = '{}')")
            rows = cursor.fetchall()
            for row in rows:
                import json as _json
                pp = _json.dumps({row[1]: row[2] or ''})
                cursor.execute("UPDATE blog_articles SET published_platforms = ? WHERE id = ?", (pp, row[0]))
            if rows:
                conn.commit()
        except:
            pass
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blog_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                keywords TEXT DEFAULT '',
                last_used TIMESTAMP,
                times_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS brand_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT DEFAULT '',
                source TEXT DEFAULT '',
                source_type TEXT DEFAULT 'article',
                snippet TEXT DEFAULT '',
                full_content TEXT DEFAULT '',
                author TEXT DEFAULT '',
                sentiment TEXT DEFAULT 'neutral',
                date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_published TEXT DEFAULT '',
                starred INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS outreach_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                platform TEXT DEFAULT '',
                platform_handle TEXT DEFAULT '',
                platform_url TEXT DEFAULT '',
                followers INTEGER DEFAULT 0,
                category TEXT DEFAULT 'influencer',
                tier TEXT DEFAULT '1',
                status TEXT DEFAULT 'new',
                notes TEXT DEFAULT '',
                last_contacted TEXT DEFAULT '',
                product_sent INTEGER DEFAULT 0,
                responded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customer_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                orders INTEGER DEFAULT 1,
                total_spend REAL DEFAULT 0,
                aov REAL DEFAULT 0,
                first_order TEXT DEFAULT '',
                last_order TEXT DEFAULT '',
                source TEXT DEFAULT 'mash_networks',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                from_name TEXT DEFAULT 'Forbidden Bourbon',
                from_email TEXT DEFAULT '',
                recipient_count INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft',
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                link TEXT DEFAULT '',
                read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL UNIQUE,
                access_token TEXT DEFAULT '',
                refresh_token TEXT DEFAULT '',
                expires_at TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # Seed default platforms
    default_platforms = [
        ('twitter', 'Twitter / X', '𝕏'),
        ('bluesky', 'Bluesky', '🦋'),
        ('facebook', 'Facebook', 'f'),
        ('linkedin', 'LinkedIn', 'in'),
        ('instagram', 'Instagram', '📷'),
        ('openai', 'OpenAI (DALL-E)', '🎨'),
        ('runway', 'Runway ML (Video)', '🎬'),
        ('medium', 'Medium', '📝'),
        ('wordpress', 'WordPress', '📰'),
        ('blogger', 'Blogger', '📢'),
        ('reddit', 'Reddit', '🤖'),
        ('pinterest', 'Pinterest', '📌'),
        ('quora', 'Quora (Manual)', '❓'),
    ]
    
    for name, display_name, icon in default_platforms:
        if USE_POSTGRES:
            conn.cursor().execute(
                'INSERT INTO platforms (name, display_name, icon) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING',
                (name, display_name, icon)
            )
        else:
            conn.execute(
                'INSERT OR IGNORE INTO platforms (name, display_name, icon) VALUES (?, ?, ?)',
                (name, display_name, icon)
            )
    
    # Seed default hashtag groups
    default_hashtag_groups = [
        ('Bourbon Core', '#bourbon #whiskey #bourbonwhiskey #wheatedbourbon #kentuckybourbon #forbiddenbourbon #drinkforbidden'),
        ('Cocktails', '#bourboncocktail #cocktails #mixology #craftcocktails #oldfashioned #whiskeysour #manhattancocktail'),
        ('Lifestyle', '#bourbonlife #bourbonculture #sipandsavor #cheers #bourboncommunity #whiskeylovers'),
        ('Product Launch', '#newrelease #limitededition #singlebarre #smallbatch #craftspirits #distillery'),
        ('Food Pairing', '#bourbonpairing #foodanddrink #whiskeyandfood #bourbonchocolate #bourbondinner'),
    ]
    
    for name, hashtags in default_hashtag_groups:
        existing = _fetchone(conn, 'SELECT id FROM hashtag_groups WHERE name = ?', (name,))
        if not existing:
            if USE_POSTGRES:
                conn.cursor().execute('INSERT INTO hashtag_groups (name, hashtags) VALUES (%s, %s)', (name, hashtags))
            else:
                conn.execute('INSERT INTO hashtag_groups (name, hashtags) VALUES (?, ?)', (name, hashtags))
    
    # Seed content templates
    default_templates = [
        ('Product Spotlight - Small Batch', 
         'Beautifully balanced, sweet and complex. Our Small Batch Select is hand-blended by Master Distiller Marianne Eaves using white corn, white wheat, and a high percentage of barley. A new twist on tradition.\n\nShop now: https://shop.drinkforbidden.com',
         'product', '#forbiddenbourbon #smallbatch #wheatedbourbon #bourbon #whiskey'),
        
        ('Product Spotlight - Single Barrel',
         'A bolder expression of Forbidden. Each Single Barrel is hand-selected by Master Distiller Marianne Eaves for its unique character. No two barrels are alike.\n\nShop now: https://shop.drinkforbidden.com',
         'product', '#forbiddenbourbon #singlebarrel #bourbon #whiskey #craftspirits'),
        
        ('Marianne Eaves Feature',
         'Master Distiller Marianne Eaves brings innovation while respecting heritage. As one of Kentucky\'s most celebrated distillers, she crafts each expression of Forbidden with intention and artistry.',
         'brand', '#marianneeaves #masterdistiller #forbiddenbourbon #womeninwhiskey #kentucky'),
        
        ('Weekend Sipping',
         'Weekend plans: pour something Forbidden. What\'s in your glass tonight?',
         'engagement', '#forbiddenbourbon #weekendvibes #bourbon #whiskey #fridaynight'),
        
        ('Old Fashioned Recipe',
         'The Forbidden Old Fashioned:\n\n2 oz Forbidden Small Batch\n1 sugar cube\n2-3 dashes Angostura bitters\nOrange peel\n\nMuddle sugar and bitters. Add bourbon and ice. Stir. Express orange peel over glass. Enjoy the twist on tradition.',
         'recipe', '#oldfashioned #bourboncocktail #forbiddenbourbon #cocktailrecipe #mixology'),
        
        ('Tasting Notes',
         'On the nose: vanilla, caramel, toasted oak. On the palate: honey, baking spices, a whisper of citrus. The finish: long, warm, and inviting. This is Forbidden.\n\nExperience it yourself: https://shop.drinkforbidden.com',
         'product', '#forbiddenbourbon #tastingnotes #bourbon #whiskey #wheatedbourbon'),
        
        ('Store Locator Push',
         'Looking for Forbidden near you? Use our store locator to find a bottle at a retailer close to home.\n\n🔍 drinkforbidden.com/store-locator',
         'sales', '#forbiddenbourbon #bourbon #findyourbottle #whiskey'),
        
        ('Bourbon & Chocolate Pairing',
         'Forbidden + dark chocolate = a match made in Kentucky. The rich, wheated profile of our Small Batch pairs perfectly with 70% cacao. Try it tonight.',
         'pairing', '#bourbonpairing #chocolate #forbiddenbourbon #bourbon #foodanddrink'),

        ('Whiskey Sour Recipe',
         'The Forbidden Whiskey Sour:\n\n2 oz Forbidden Small Batch\n1 oz fresh lemon juice\n3/4 oz simple syrup\n1 egg white (optional)\n\nDry shake with egg white. Add ice, shake again. Strain into rocks glass. Garnish with a cherry and lemon wheel.',
         'recipe', '#whiskeysour #forbiddenbourbon #cocktailrecipe #bourbon #mixology'),

        ('Mint Julep Recipe',
         'The Forbidden Mint Julep:\n\n2.5 oz Forbidden Small Batch\n1 oz simple syrup\n8-10 fresh mint leaves\nCrushed ice\n\nGently muddle mint with syrup. Pack glass with crushed ice. Pour bourbon. Stir until glass frosts. Crown with more ice. Garnish with mint sprig.',
         'recipe', '#mintjulep #forbiddenbourbon #derbycocktail #bourbon #kentucky'),

        ('Manhattan Recipe',
         'The Forbidden Manhattan:\n\n2 oz Forbidden Small Batch\n1 oz sweet vermouth\n2 dashes Angostura bitters\nLuxardo cherry\n\nStir ingredients with ice for 30 seconds. Strain into chilled coupe. Garnish with cherry. Pure sophistication.',
         'recipe', '#manhattan #forbiddenbourbon #classiccocktail #bourbon #cocktails'),

        ('Bourbon Smash Recipe',
         'The Forbidden Smash:\n\n2 oz Forbidden Small Batch\n1 oz fresh lemon juice\n3/4 oz simple syrup\n4-5 fresh mint leaves\n\nMuddle mint with syrup. Add bourbon and lemon. Shake with ice. Strain over fresh ice. Garnish with mint and lemon wheel. Refreshing and bold.',
         'recipe', '#bourbonsmash #forbiddenbourbon #summercocktail #bourbon #mixology'),

        ('Gold Rush Recipe',
         'The Forbidden Gold Rush:\n\n2 oz Forbidden Small Batch\n3/4 oz honey syrup (equal parts honey + hot water)\n3/4 oz fresh lemon juice\n\nShake all ingredients with ice. Strain into rocks glass over fresh ice. Simple. Elegant. Golden.',
         'recipe', '#goldrush #forbiddenbourbon #honeycocktail #bourbon #craftcocktails'),

        ('Boulevardier Recipe',
         'The Forbidden Boulevardier:\n\n1.5 oz Forbidden Small Batch\n1 oz Campari\n1 oz sweet vermouth\nOrange peel\n\nStir with ice. Strain into rocks glass over a large ice cube. Express orange peel. A bourbon lover\'s Negroni.',
         'recipe', '#boulevardier #forbiddenbourbon #bittercocktail #bourbon #aperitivo'),

        ('White Corn Difference',
         'Most bourbons use yellow dent corn. Forbidden uses white corn — the same variety prized in artisan cornbread and fine cooking. The result? A cleaner, sweeter foundation that lets our wheated mash bill shine.',
         'product', '#forbiddenbourbon #whitecorn #bourboneducation #mashbill #craftspirits'),

        ('Bardstown Bourbon Company',
         'Forbidden is distilled at Bardstown Bourbon Company — one of the most advanced and respected distilleries in Kentucky. State-of-the-art meets Southern tradition. The perfect home for a bourbon that breaks the mold.',
         'brand', '#bardstownbourboncompany #forbiddenbourbon #kentucky #distillery #bourboncountry'),

        ('Award Winner Announcement',
         '🏆 Forbidden Bourbon keeps racking up medals. Award-winning at San Francisco, New York, Los Angeles, Denver, and Ascot competitions. The judges agree — this bourbon is something special.\n\nTaste what the fuss is about: shop.drinkforbidden.com',
         'brand', '#awardwinning #forbiddenbourbon #bourbon #goldmedal #spiritsaward'),

        ('Wheated Bourbon Education',
         'What makes a wheated bourbon? Instead of rye as the secondary grain, we use wheat. The result is a smoother, softer, more approachable pour — without sacrificing complexity. Forbidden is wheated by design, not by accident.',
         'product', '#wheatedbourbon #bourboneducation #forbiddenbourbon #mashbill #whiskey'),

        ('Gift Idea Post',
         'Looking for the perfect gift for the bourbon lover in your life? Forbidden Small Batch Select or Single Barrel — both arrive in a stunning package worthy of any occasion.\n\n🎁 shop.drinkforbidden.com',
         'sales', '#bourbongift #forbiddenbourbon #giftideas #whiskeygift #bourbonlover'),

        ('Behind the Label',
         'Every detail of the Forbidden bottle was designed with intention. The dark glass protects the spirit. The gold accents speak to quality. The name — Forbidden — is an invitation to break from the ordinary.',
         'brand', '#forbiddenbourbon #bottledesign #brandstory #bourbon #premiumspirits'),

        ('Bourbon & Steak Pairing',
         'Forbidden Small Batch + a perfectly seared ribeye. The wheated sweetness complements the char, the caramel notes echo the Maillard crust. This is bourbon and beef at its finest.',
         'pairing', '#bourbonandsteak #forbiddenbourbon #foodpairing #bourbon #steaknight'),

        ('Bourbon & Cigar Pairing',
         'Forbidden Single Barrel and a medium-bodied cigar — cedar, leather, and toasted oak. The bold bourbon stands up to smoke while the wheat softness keeps things balanced. A gentleman\'s evening.',
         'pairing', '#bourbonandcigar #forbiddenbourbon #cigarlife #bourbon #gentlemanstyle'),

        ('Bourbon & Pecan Pie',
         'Pour a glass of Forbidden alongside a warm slice of pecan pie. The vanilla and caramel notes in our wheated bourbon mirror the buttery sweetness of the filling. Pure Southern comfort.',
         'pairing', '#bourbonpairing #pecanpie #forbiddenbourbon #southernfood #dessert'),

        ('Bourbon & Charcuterie',
         'Build the perfect bourbon board: aged cheddar, honeycomb, dark chocolate, candied pecans, and prosciutto. Pour Forbidden Small Batch and let the flavors mingle. Date night, elevated.',
         'pairing', '#charcuterie #bourbonboard #forbiddenbourbon #bourbon #datenight'),

        ('Monday Motivation',
         'Start the week with intention. End it with a pour of Forbidden. You\'ve earned it.',
         'engagement', '#mondaymotivation #forbiddenbourbon #bourbon #weekstart #whiskey'),

        ('This or That - Engagement',
         'Neat or on the rocks? Small Batch or Single Barrel? Let us know in the comments 👇\n\nEither way, you\'re drinking Forbidden. And that\'s always the right choice.',
         'engagement', '#thisorthat #forbiddenbourbon #bourbon #whiskeylover #poll'),

        ('Pour & Share',
         'Tag someone you\'d share a glass of Forbidden with. Good bourbon is even better with good company. 🥃',
         'engagement', '#tagafriend #forbiddenbourbon #bourbon #whiskey #cheers'),

        ('Sunset Pour',
         'Golden hour hits different with a glass of Forbidden in hand. The light catches the bourbon the same way — amber, warm, and full of promise.',
         'engagement', '#goldenhour #forbiddenbourbon #sunsetpour #bourbon #eveningvibes'),

        ('Shop Small Batch Select',
         '🛒 Forbidden Small Batch Select — max 50 barrels per blend. Limited by design. Crafted by Marianne Eaves. Ships nationwide.\n\nOrder now: shop.drinkforbidden.com\n\nFree shipping on orders over $100.',
         'sales', '#forbiddenbourbon #smallbatch #shopnow #bourbon #freeshiping'),

        ('Shop Single Barrel',
         '🛒 Forbidden Single Barrel — hand-picked by our Master Distiller. Every bottle is unique. Every sip tells a different story.\n\nOrder: shop.drinkforbidden.com',
         'sales', '#forbiddenbourbon #singlebarrel #shopnow #rarebourbon #whiskey'),

        ('Customer Testimonial',
         '"I\'ve tried a lot of bourbons, but Forbidden is something else. Smooth enough to sip neat, complex enough to keep you coming back. My new go-to." — A real Forbidden customer\n\nJoin them: shop.drinkforbidden.com',
         'sales', '#forbiddenbourbon #customerreview #bourbon #testimonial #whiskey'),

        ('Cocktail Hour Invite',
         'It\'s 5 o\'clock somewhere — and wherever you are, Forbidden makes it better. What are you mixing tonight?\n\nShare your Forbidden cocktail with us! 🍸',
         'engagement', '#cocktailhour #forbiddenbourbon #happyhour #bourbon #mixology'),

        ('Father\'s Day Gift',
         'Dad deserves better than a tie this year. Give him a bottle of Forbidden — Kentucky\'s finest wheated bourbon, crafted by Marianne Eaves.\n\n🎁 shop.drinkforbidden.com',
         'seasonal', '#fathersday #forbiddenbourbon #dadgift #bourbon #giftideas'),

        ('Holiday Whiskey Sour',
         'Holiday Forbidden Whiskey Sour:\n\n2 oz Forbidden Small Batch\n1 oz cranberry juice\n3/4 oz lemon juice\n1/2 oz maple syrup\nRosemary sprig\n\nShake, strain, garnish with rosemary and cranberries. Festive and Forbidden.',
         'seasonal', '#holidaycocktail #forbiddenbourbon #cranberry #festivedrinks #bourbon'),

        ('Valentine\'s Day Pour',
         'This Valentine\'s Day, skip the wine. Pour something bold, something smooth, something... Forbidden. \n\nTwo glasses. One bottle. All heart. ❤️\n\nshop.drinkforbidden.com',
         'seasonal', '#valentinesday #forbiddenbourbon #datenight #bourbon #love'),

        ('National Bourbon Day',
         'Happy National Bourbon Day! 🥃 Today we celebrate America\'s native spirit — and there\'s no better way than with a glass of Forbidden.\n\nHow are you celebrating? Drop your pour below 👇',
         'seasonal', '#nationalbourbonday #forbiddenbourbon #bourbon #june14 #whiskey'),
    ]
    
    for title, content, category, hashtags in default_templates:
        existing = _fetchone(conn, 'SELECT id FROM content_templates WHERE title = ?', (title,))
        if not existing:
            if USE_POSTGRES:
                conn.cursor().execute(
                    'INSERT INTO content_templates (title, content, category, hashtags) VALUES (%s, %s, %s, %s)',
                    (title, content, category, hashtags)
                )
            else:
                conn.execute(
                    'INSERT INTO content_templates (title, content, category, hashtags) VALUES (?, ?, ?, ?)',
                    (title, content, category, hashtags)
                )
    
    # Seed blog topics for SEO content generation
    blog_topics = [
        ('What Makes a Wheated Bourbon Different', 'education', 'wheated bourbon, bourbon mash bill, wheat vs rye'),
        ('The Art of Small Batch Blending', 'education', 'small batch bourbon, barrel selection, blending'),
        ('Understanding Bourbon Mash Bills', 'education', 'bourbon mash bill, corn wheat barley, bourbon grains'),
        ('How Bourbon is Aged: The Science of the Barrel', 'education', 'bourbon aging, oak barrel, char levels'),
        ('Kentucky Straight Bourbon: What the Label Means', 'education', 'Kentucky bourbon, straight bourbon, bourbon rules'),
        ('The Difference Between Single Barrel and Small Batch', 'education', 'single barrel bourbon, small batch, bourbon types'),
        ('Why Proof Matters in Bourbon', 'education', 'bourbon proof, barrel proof, cask strength'),
        ('Food-Grade Grains: Why Quality Ingredients Matter', 'education', 'food grade corn, white corn, bourbon ingredients'),
        ('Women Pioneers in American Whiskey', 'people', 'women in whiskey, master distiller, Marianne Eaves'),
        ('The Role of a Master Distiller', 'people', 'master distiller, bourbon distiller, distilling craft'),
        ('Innovation Meets Tradition in Modern Bourbon', 'people', 'craft bourbon, bourbon innovation, modern distilling'),
        ('Bardstown: The Bourbon Capital of the World', 'culture', 'Bardstown Kentucky, bourbon trail, bourbon capital'),
        ('5 Classic Bourbon Cocktails Everyone Should Know', 'cocktails', 'bourbon cocktails, old fashioned, whiskey sour'),
        ('The Perfect Old Fashioned: A Step-by-Step Guide', 'cocktails', 'old fashioned recipe, bourbon cocktail, classic cocktail'),
        ('Bourbon Cocktails for Every Season', 'cocktails', 'seasonal cocktails, bourbon drinks, summer winter cocktails'),
        ('The History of the Whiskey Sour', 'cocktails', 'whiskey sour history, bourbon cocktail, cocktail history'),
        ('How to Build a Home Bourbon Bar', 'cocktails', 'home bar, bourbon bar setup, cocktail tools'),
        ('Bourbon Hot Toddy for Cold Nights', 'cocktails', 'hot toddy, bourbon hot toddy, winter cocktails'),
        ('The Ultimate Bourbon and Chocolate Pairing Guide', 'pairing', 'bourbon chocolate, bourbon pairing, food pairing'),
        ('Bourbon and BBQ: A Match Made in the South', 'pairing', 'bourbon bbq, bourbon food pairing, southern food'),
        ('Bourbon and Cheese: An Unexpected Pairing', 'pairing', 'bourbon cheese pairing, bourbon food, artisan cheese'),
        ('Cooking with Bourbon: Recipes That Impress', 'pairing', 'cooking with bourbon, bourbon recipes, bourbon glaze'),
        ('The Rise of Craft Bourbon in America', 'culture', 'craft bourbon, bourbon industry, American whiskey'),
        ('Kentucky Bourbon Trail: Planning Your Visit', 'culture', 'bourbon trail, Kentucky distillery tour, bourbon tourism'),
        ('Bourbon Collecting: What to Know Before You Start', 'culture', 'bourbon collecting, rare bourbon, bourbon investment'),
        ('Bourbon vs Whiskey: What You Need to Know', 'culture', 'bourbon vs whiskey, American whiskey, whiskey types'),
        ('The Story Behind Bourbon Bottle Design', 'culture', 'bourbon bottle design, bourbon packaging, craft design'),
        ('Direct-to-Consumer Bourbon: The Future of Buying Spirits', 'culture', 'DTC spirits, buy bourbon online, bourbon delivery'),
        ('Holiday Gift Guide: Bourbon Edition', 'seasonal', 'bourbon gifts, holiday bourbon, whiskey gifts'),
        ('Summer Bourbon Cocktails That Beat the Heat', 'seasonal', 'summer bourbon, refreshing bourbon cocktails, bourbon lemonade'),
        ('New Year Bourbon Traditions Worth Starting', 'seasonal', 'new year bourbon, bourbon toast, bourbon traditions'),
        ('Fall Flavors and Bourbon: A Perfect Match', 'seasonal', 'fall bourbon, autumn cocktails, bourbon and apple'),
        ('The Perfect Bourbon Gift for Every Budget', 'seasonal', 'bourbon gift guide, affordable bourbon, premium bourbon gifts'),
        ('White Corn vs Yellow Corn in Bourbon: Why It Matters', 'education', 'white corn bourbon, yellow dent corn, bourbon grain quality'),
        ('How to Read a Bourbon Label Like a Pro', 'education', 'bourbon label, straight bourbon, bottled in bond, age statement'),
        ('What Does Wheated Mean in Bourbon?', 'education', 'wheated bourbon, wheat mash bill, smooth bourbon, Pappy Van Winkle'),
        ('Barrel Char Levels Explained: How They Shape Bourbon', 'education', 'barrel char, alligator char, bourbon barrel, oak aging'),
        ('The Science of Bourbon Color', 'education', 'bourbon color, amber whiskey, barrel aging color, caramel notes'),
        ('Bourbon vs Scotch: A Complete Comparison', 'education', 'bourbon vs scotch, American whiskey, single malt, comparison'),
        ('How Temperature Affects Bourbon Aging in Kentucky', 'education', 'Kentucky climate, bourbon aging, rickhouse temperature, angels share'),
        ('Marianne Eaves: Breaking Barriers in Bourbon', 'people', 'Marianne Eaves, women master distiller, Kentucky bourbon, glass ceiling'),
        ('How Bardstown Became the Bourbon Capital', 'culture', 'Bardstown Kentucky, bourbon capital, distillery row, bourbon heritage'),
        ('The Resurgence of Wheated Bourbons', 'culture', 'wheated bourbon trend, bourbon market, craft distilling renaissance'),
        ('Direct-to-Consumer Spirits: How Online Sales Are Changing Bourbon', 'culture', 'DTC bourbon, online spirits, e-commerce whiskey, shipping laws'),
        ('Building a Bourbon Collection: Tips from Enthusiasts', 'culture', 'bourbon collection, whiskey shelf, rare bourbon, bourbon hunting'),
        ('Bourbon and Music: Pairing Playlists with Your Pour', 'culture', 'bourbon playlist, whiskey music, jazz bourbon, country bourbon'),
        ('The Forbidden Whiskey Sour: Our Signature Cocktail', 'cocktails', 'whiskey sour recipe, forbidden cocktail, bourbon sour, egg white cocktail'),
        ('Bourbon Highball: The Underrated Classic', 'cocktails', 'bourbon highball, highball recipe, Japanese highball, simple cocktail'),
        ('Smoked Bourbon Cocktails at Home', 'cocktails', 'smoked cocktail, bourbon smoke, cocktail smoking, mixology'),
        ('Batch Cocktails for Your Next Party', 'cocktails', 'batch cocktails, bourbon punch, party drinks, large format cocktails'),
        ('Bourbon and Apple Cider: A Fall Essential', 'cocktails', 'bourbon apple cider, fall cocktail, hot cider bourbon, autumn drink'),
        ('Bourbon and Coffee: Morning Meets Evening', 'pairing', 'bourbon coffee, Irish coffee bourbon, coffee cocktail, espresso bourbon'),
        ('Grilling with Bourbon: Marinades and Glazes', 'pairing', 'bourbon glaze, bourbon marinade, bourbon BBQ sauce, grilling'),
        ('Bourbon and Ice Cream: Yes Really', 'pairing', 'bourbon ice cream, bourbon float, dessert cocktail, bourbon vanilla'),
        ('Bourbon and Thanksgiving: The Complete Guide', 'seasonal', 'Thanksgiving bourbon, holiday dinner bourbon, bourbon cranberry'),
        ('Derby Day: Mint Juleps and Forbidden Bourbon', 'seasonal', 'Kentucky Derby, mint julep, Derby Day bourbon, Churchill Downs'),
        ('Bourbon Advent Calendar: 25 Days of Discovery', 'seasonal', 'bourbon advent, whiskey calendar, holiday bourbon tasting'),
    ]
    
    for title, category, keywords in blog_topics:
        existing = _fetchone(conn, 'SELECT id FROM blog_topics WHERE title = ?', (title,))
        if not existing:
            if USE_POSTGRES:
                conn.cursor().execute(
                    'INSERT INTO blog_topics (title, category, keywords) VALUES (%s, %s, %s)',
                    (title, category, keywords)
                )
            else:
                conn.execute(
                    'INSERT INTO blog_topics (title, category, keywords) VALUES (?, ?, ?)',
                    (title, category, keywords)
                )
    
    conn.commit()
    conn.close()
    
    # Seed brand mentions
    seed_brand_mentions()
    # Seed outreach contacts
    seed_outreach_contacts()
    # Seed customer emails from Mash Networks
    seed_customer_emails()


def seed_outreach_contacts():
    """Pre-populate outreach contacts — ONLY contacts with verified email addresses"""
    conn = get_db()
    
    # Clear old data and re-seed fresh
    _execute(conn, "DELETE FROM outreach_contacts")
    
    contacts = [
        # (name, email, platform, handle, url, followers, category, tier, notes)
        
        # === BOURBON REVIEWERS WITH EMAIL ===
        ('Christopher Null (Drinkhacker)', 'editor@drinkhacker.com', 'website', '@drinkhacker', 'https://www.drinkhacker.com', 50000, 'media', '1',
         'Publisher & Editor-in-Chief, Drinkhacker. Already reviewed Forbidden (A-). Send new batches + single barrels.'),
        ('Frank Dobbins (Drinkhacker)', 'frank@drinkhacker.com', 'website', '@drinkhacker', 'https://www.drinkhacker.com/contact-information/', 50000, 'media', '1',
         'Drinkhacker reviewer. Wrote the Forbidden Bourbon A- review. DC-based. Whiskey, rum, tequila, cocktails.'),
        ('Maggie Kimberl (Drinkhacker)', 'maggie@drinkhacker.com', 'website', '@maggiekimberl', 'https://www.drinkhacker.com/contact-information/staff', 50000, 'media', '2',
         'Drinkhacker staff. 2020 World Icon of Whiskey Award. ADI top influencer 2024.'),
        ('Patrick Garrett (Bourbon & Banter)', 'pops@bourbonbanter.com', 'website', '@bourbonbanter', 'https://www.bourbonbanter.com', 55000, 'media', '1',
         'Founder Bourbon & Banter. 3M annual users. 37K Twitter, 20K IG. Hosts Drink Curious tastings. Podcast too.'),
        ('Tom Fischer (BourbonBlog)', 'bourbon@bourbonblog.com', 'website', '@bourbonblog', 'https://bourbonblog.com', 95000, 'media', '1',
         'Founder BourbonBlog.com. 95K Twitter. Netflix Heist expert. Phone: 310-598-1550. Hosts tastings. Also: tasting@bourbonblog.com.'),
        ('Drink Spirits', 'editor@drinkspirits.com', 'website', '@drinkspirits', 'https://www.drinkspirits.com', 20000, 'media', '2',
         'DrinkSpirits.com. Independent reviews. Phone: 617-249-4947. Prior authorization for samples.'),
        
        # === MAJOR PUBLICATIONS WITH SUBMISSION EMAILS ===
        ('VinePair — Sample Submissions', 'tastings@vinepair.com', 'website', '@vinepair', 'https://vinepair.com', 500000, 'media', '1',
         'Already awarded Marianne Master Distiller of Year 2024. Ship to: 244 5th Ave 11th Fl NY 10001. Submit new batches.'),
        ('Whisky Advocate — Buying Guide', 'watasting@mshanken.com', 'website', '@whiskyadvocate', 'https://whiskyadvocate.com/contact', 200000, 'media', '1',
         'Submit for Buying Guide review. Ship to: 825 8th Ave 33rd Fl NY 10019. 100-point scale. Top 20 Whiskies list.'),
        ('David Fleming (Whisky Advocate)', 'dfleming@mshanken.com', 'website', '@whiskyadvocate', 'https://whiskyadvocate.com/contact', 200000, 'media', '1',
         'Executive Editor, Whisky Advocate. Key decision maker for reviews and features. Also: info@whiskyadvocate.com.'),
        ('Julia Higgins (Whisky Advocate)', 'jhiggins@mshanken.com', 'website', '@whiskyadvocate', 'https://whiskyadvocate.com/contact', 200000, 'media', '2',
         'Senior Editor, Whisky Advocate. Buying Guide reviewer.'),
        ('Stephen Senatore (Whisky Advocate Ads)', 'ssenatore@mshanken.com', 'website', '@whiskyadvocate', 'https://whiskyadvocate.com/contact', 200000, 'media', '2',
         'Advertising contact at Whisky Advocate. Media kit, rates, deadlines, ad opportunities.'),
        
        # === EVENTS & COMPETITIONS WITH EMAIL ===
        ('WhiskyFest', 'whiskyfest@whiskyadvocate.com', 'website', '@whiskyfest', 'https://whiskyadvocate.com', 200000, 'industry', '1',
         'Multi-city events: NY, Chicago, SF. Exhibit booth opportunity. Direct consumer tasting.'),
        ('SF World Spirits Competition', 'info@sfspiritscomp.com', 'website', '@sfwspiritscomp', 'https://thetastingalliance.com/events/san-francisco-world-spirits-competition', 31000, 'industry', '1',
         '2026 open for entries. Deadline Apr 24, ship by May 1. $600/entry. Ship to Pier 50 Shed A, San Francisco CA 94158. Phone: 415-345-9000.'),
        ('SF World Spirits (Europe Satellite)', 'maddee@thetastingalliance.com', 'website', '@sfwspiritscomp', 'https://thetastingalliance.com', 31000, 'industry', '2',
         'European satellite competition contact. Also handles general competition inquiries.'),
        
        # === PODCASTS WITH EMAIL ===
        ('Bourbon Pursuit Podcast', 'podcast@pursuitspirits.com', 'podcast', '@bourbonpursuit', 'https://bourbonpursuit.com', 78500, 'influencer', '1',
         'Top bourbon podcast. Kenny Coleman, Ryan Cecil, Fred Minnick. Already had Marianne on Ep 425. Send new batches.'),
    ]
    
    for c in contacts:
        name, email, platform, handle, url, followers, category, tier, notes = c
        existing = _fetchone(conn, 'SELECT id FROM outreach_contacts WHERE email = ?', (email,))
        if not existing:
            _execute(conn, '''INSERT INTO outreach_contacts (name, email, platform, platform_handle, platform_url, followers, category, tier, notes)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (name, email, platform, handle, url, followers, category, tier, notes))
    
    conn.commit()
    conn.close()
    print(f"Outreach contacts seeded: {len(contacts)} contacts (all with verified emails)")


def seed_brand_mentions():
    """Pre-populate Brand Intel with verified Forbidden Bourbon mentions only"""
    conn = get_db()
    
    # Clear old seeded data and re-seed fresh (prevents duplicates across versions)
    _execute(conn, "DELETE FROM brand_mentions")
    
    mentions = [
        # === REVIEWS (6) - All specifically review Forbidden Bourbon ===
        ('Forbidden Bourbon Review', 'https://thebourbonculture.com/whiskey-reviews/forbidden-bourbon-review/', 'thebourbonculture.com', 'review',
         'In-depth review of Forbidden Bourbon. Covers low-temp fermentation, white corn mash bill, $129 price point. Wheated profile with vanilla, brown butter, orange citrus.', 'Bourbon Culture'),
        ('Forbidden Batch 3 Bourbon Review & Rating', 'https://vinepair.com/review/forbidden-batch-3-bourbon/', 'vinepair.com', 'review',
         'VinePair review of Forbidden Batch 3. Bright, borderline-refreshing wheated bourbon blended with a deft touch. Lavender, honey syrup, bright oak on the nose.', 'VinePair'),
        ('Forbidden Bourbon Review: Tasting Notes & Complete Analysis', 'https://thewhiskeywash.com/reviews/whiskey-review-forbidden-bourbon/', 'thewhiskeywash.com', 'review',
         'Whiskey Wash review of Forbidden Bourbon. Notes vanilla, creme brulee, clove, coffee. Calls it subtly ingenious — familiar flavors arranged in unexpected ways.', 'The Whiskey Wash'),
        ('Review: Forbidden Bourbon (Rated A-)', 'https://www.drinkhacker.com/2023/07/26/review-forbidden-bourbon/', 'drinkhacker.com', 'review',
         'Drinkhacker rates Forbidden Bourbon A-. Wheat toast, tayberries, chocolate almonds, cinnamon bark, creamy custard. Emblematic of Eaves deft blending touch.', 'Drinkhacker'),
        ('Forbidden Kentucky Straight Bourbon Review (8.3/10)', 'https://www.pastemagazine.com/drink/whiskey/fordbidden-bourbon-review-marianne-eaves', 'pastemagazine.com', 'review',
         'Paste Magazine scores Forbidden Bourbon 8.3/10. Creamy texture, orange citrus, toffee, cream soda. Mouthfeel is one of the most memorable under 100 proof.', 'Paste Magazine'),
        ('Forbidden Batch 2 Review', 'https://www.josephbourbon.com/post/forbidden-batch-2', 'josephbourbon.com', 'review',
         'Review of Forbidden Bourbon Batch 2. Star-shaped bottle. 75% white corn, 12% white wheat, 13% malted barley. 95.2 proof.', 'Joseph Bourbon'),
        ('Bourbon Lens: Forbidden Bourbon Tasted & Reviewed', 'https://bourbonlens.com/forbidden-bourbon-reviewed/', 'bourbonlens.com', 'review',
         'Bourbon Lens review. Habanero honey, pepper, cinnamon on palate. Long milk chocolate finish. Can get behind this bourbon despite higher price tag.', 'Bourbon Lens'),
        ('The Bourbon Flight: Forbidden Bourbon Review (5/5 Barrels)', 'https://www.thebourbonflight.com/featured-bourbon-review-forbidden-bourbon-by-marianne-eaves/', 'thebourbonflight.com', 'review',
         'Featured review. 5/5 Barrels rating. Vanilla, deep-roasted corn, hazelnut aromas. Caramel creme brulee, toffee, cherry. Minimal burn at 95.2 proof. Worth the extra money at $129.', 'The Bourbon Flight'),
        ('Distiller.com: Forbidden Bourbon User Reviews (4.0/5)', 'https://distiller.com/spirits/forbidden-bourbon/tastes', 'distiller.com', 'review',
         'Distiller.com community reviews. 4.0 out of 5 stars. Batch #3 notes: grain, wood, fruits, flowers, vanilla bean, orange zest, glazed doughnuts, spiced caramel latte.', 'Distiller.com'),
        ('American Whiskey Magazine: Forbidden Bourbon Batch 1 Tasting', 'https://americanwhiskeymag.com/reviews/tasting-forbidden-bourbon-batch-1/', 'americanwhiskeymag.com', 'review',
         'American Whiskey Magazine official tasting of Forbidden Bourbon Batch 1. 47.6% ABV, 95.2 proof. Wheat style from Kentucky.', 'American Whiskey Magazine'),

        # === MAJOR MAGAZINE FEATURES (8) - All specifically about Forbidden Bourbon ===
        ('Forbes: Whiskey Of The Week — Forbidden Bourbon Batch #2', 'https://www.forbes.com/sites/joemicallef/2023/11/16/whiskey-of-the-week-forbidden-bourbon-batch-2/', 'forbes.com', 'feature',
         'Forbes Whiskey Of The Week feature on Forbidden Bourbon Batch #2. $130, rich profile with mellow corn, soft wheat, notable barley. Low-temperature fermentation.', 'Forbes'),
        ('Maxim: Spirit of the Week — Forbidden Small Batch Bourbon', 'https://www.maxim.com/food-drink/spirit-of-the-week-forbidden-small-batch-bourbon/', 'maxim.com', 'feature',
         'Maxim Spirit of the Week feature (Aug 2023). Forbidden Small Batch Bourbon highlighted as a standout new release with innovative mash bill.', 'Maxim'),
        ('Garden & Gun: Marianne Eaves Whiskey Dreams (Forbidden Profile)', 'https://gardenandgun.com/articles/marianne-eavess-whiskey-dreams/', 'gardenandgun.com', 'feature',
         'Garden & Gun feature profile on Forbidden Bourbon. Eaves discusses making it from scratch with white corn and white winter wheat. Name nods to KY law forbidding women as master distillers.', 'Garden & Gun'),
        ('Garden & Gun: 2023 Holiday Gift Guide feat. Forbidden Bourbon', 'https://gardenandgun.com/feature/gift-guide-2023/', 'gardenandgun.com', 'feature',
         'Garden & Gun holiday gift guide featuring Forbidden Bourbon as a top gift pick for bourbon lovers in 2023.', 'Garden & Gun'),
        ('Garden & Gun: A Forbidden Evening (Brand Event)', 'https://gardenandgun.com/slideshow/a-forbidden-evening/', 'gardenandgun.com', 'event',
         'Garden & Gun hosted A Forbidden Evening in Charleston, SC — a dedicated Forbidden Bourbon event with tastings and live music. May 2023.', 'Garden & Gun'),
        ('Garden & Gun: Craig Melvin Says Forbidden Is His Favorite Bourbon', 'https://gardenandgun.com/articles/get-to-know-craig-melvin-the-today-shows-new-co-lead-anchor/', 'gardenandgun.com', 'feature',
         'TODAY Show co-anchor Craig Melvin tells Garden & Gun that Forbidden by Marianne Eaves is his favorite bourbon. Calls it perfectly balanced.', 'Garden & Gun'),
        ('Gear Patrol: Best New Bourbon Releases of 2023 (feat. Forbidden)', 'https://www.gearpatrol.com/food-drink/a44215959/best-new-bourbon-releases-2023/', 'gearpatrol.com', 'feature',
         'Gear Patrol names Forbidden Bourbon one of the best new bourbon releases of 2023. Highlights innovative mash bill and Marianne Eaves pedigree.', 'Gear Patrol'),
        ('American Whiskey Magazine: Marianne Eaves Talks Forbidden Bourbon', 'https://americanwhiskeymag.com/articles/marianne-eaves-forbidden-bourbon/', 'americanwhiskeymag.com', 'feature',
         'American Whiskey Magazine interview about Forbidden Bourbon. Eaves explains the name, low-temp fermentation from a 1910 Seagrams manual, KY law against women in production until 1974.', 'American Whiskey Magazine'),

        # === TV / BROADCAST (1) - Specifically about Forbidden Bourbon ===
        ('NBC TODAY Show: Craig Melvin Features Forbidden Bourbon', 'https://www.today.com/video/kentucky-s-first-female-master-distiller-set-to-launch-her-own-brand-186833477881', 'today.com', 'video',
         'NBC TODAY Show segment. Craig Melvin visits Bardstown Bourbon Company to taste Forbidden Bourbon from the barrel with Marianne Eaves. National broadcast feature. July 2023.', 'NBC TODAY Show'),

        # === PRESS / NEWS (9) - All specifically about Forbidden Bourbon launch/coverage ===
        ('Breaking Bourbon: Rebellion and Innovation Collide to Birth Forbidden', 'https://www.breakingbourbon.com/bourbon-whiskey-press-releases/rebellion-and-innovation-collide-to-birth-forbidden-bourbon', 'breakingbourbon.com', 'press',
         'Breaking Bourbon press release. Forbidden Bourbon — first white corn and white winter wheat bourbon. Distilled at Bardstown Bourbon Co. KY, TN, GA, SC at $129.', 'Breaking Bourbon'),
        ('GoBourbon: Marianne Eaves Debuts Forbidden Bourbon', 'https://www.gobourbon.com/new-release-marianne-eaves-debuts-forbidden-bourbon/', 'gobourbon.com', 'press',
         'The Bourbon Review coverage of Forbidden Bourbon launch. Mash bill details, low-temperature fermentation, SC-based partnership.', 'The Bourbon Review'),
        ('Distillery Trail: Marianne Eaves Releases Forbidden Bourbon', 'https://www.distillerytrail.com/blog/master-distiller-marianne-eaves-releases-forbidden-her-5-year-old-grain-to-glass-kentucky-bourbon/', 'distillerytrail.com', 'press',
         'Distillery Trail deep dive into Forbidden Bourbon launch. Direct quotes from Eaves on low-temp fermentation. Craig Melvin TODAY Show visit also documented.', 'Distillery Trail'),
        ('Cola Daily: Columbia Mayor Partners to Debut Forbidden Bourbon', 'https://www.coladaily.com/business/master-distiller-marianne-eaves-partners-with-columbia-mayor-to-debut-new-bourbon-forbidden/article_840f19be-202a-11ee-82ea-5bbcc61d6ada.html', 'coladaily.com', 'press',
         'Columbia SC news on Forbidden Bourbon debut tasting at Smoked restaurant. Details partnership with Mayor Daniel Rickenmann and SC-based founders.', 'Cola Daily'),
        ('Tasting Table: Eaves Reinvents Kentucky Bourbon With Forbidden', 'https://www.tastingtable.com/1308476/marianne-eaves-reinvents-kentucky-bourbon-forbidden-debut/', 'tastingtable.com', 'press',
         'Tasting Table coverage of Forbidden Bourbon launch. White corn, white wheat, low-temperature fermentation. May 16, 2023.', 'Tasting Table'),
        ('Atlanta Journal-Constitution: Female Master Distiller Tackles the Forbidden', 'https://www.ajc.com/things-to-do/female-master-distiller-likes-to-tackle-the-forbidden/', 'ajc.com', 'press',
         'AJC feature on Forbidden Bourbon launch. Coverage of the brand debut for the Georgia market. May 2023.', 'Atlanta Journal-Constitution'),
        ('Post and Courier: Forbidden Bourbon Debuts in South Carolina', 'https://www.postandcourier.com/free-times/food/kentuckys-1st-female-master-distiller-debuts-new-bourbon-in-sc/', 'postandcourier.com', 'press',
         'Charleston Post and Courier covers Forbidden Bourbon debut in South Carolina, backed by Columbia mayor Daniel Rickenmann.', 'The Post and Courier'),
        ('The Daily Pour: Forbidden Bourbon Breaks All the Rules', 'https://thedailypour.com/whiskey/bourbon/marianne-eaves-forbidden-bourbon/', 'thedailypour.com', 'press',
         'The Daily Pour coverage of Forbidden Bourbon launch. First white corn and white winter wheat bourbon. Cold fermentation, cuisine-quality ingredients. $129.', 'The Daily Pour'),
        ('TOWN Carolina: Forbidden Bourbon Leaves Innovative Mark', 'https://towncarolina.com/marianne-eaves-forbidden-bourbon-leaves-innovative-mark', 'towncarolina.com', 'press',
         'TOWN Carolina feature on Forbidden Bourbon and its impact on the South Carolina spirits scene.', 'TOWN Carolina'),
        ('Fred Minnick: Marianne Eaves Forbidden Brand Debuts', 'https://www.fredminnick.com/2023/05/19/marianne-eaves-forbidden-brand-debuts/', 'fredminnick.com', 'press',
         'Fred Minnick covers Forbidden Bourbon debut. First white corn and white winter wheat bourbon. Available in KY, TN, GA, SC at $129. Single barrel cask strength expressions.', 'Fred Minnick'),

        # === AWARDS (11) - Specifically credits Forbidden Bourbon ===
        ('VinePair Next Wave: Master Distiller of the Year (for Forbidden)', 'https://vinepair.com/articles/2024-next-wave-marianne-eaves/', 'vinepair.com', 'award',
         'VinePair 2024 Next Wave Award — Master Distiller of the Year. Profiles Eaves career culminating in Forbidden Bourbon. All three batches sold out quickly and well reviewed.', 'VinePair'),
        ('New Orleans Spirits Competition 2024: Silver Medal — Forbidden Single Barrel', 'https://www.nolaspiritscomp.com/awards-24/silver-medal-spirits-24', 'nolaspiritscomp.com', 'award',
         'Forbidden Bourbon Single Barrel won Silver Medal at the 2024 New Orleans Spirits Competition. Entered by Small Batch Medicinal Spirits Company.', 'New Orleans Spirits Competition'),
        ('New Orleans Spirits Competition 2024: Silver Medal — Forbidden Small Batch', 'https://www.nolaspiritscomp.com/awards-24/silver-medal-spirits-24', 'nolaspiritscomp.com', 'award',
         'Forbidden Bourbon Small Batch won Silver Medal at the 2024 New Orleans Spirits Competition. Entered by Small Batch Medicinal Spirits Company.', 'New Orleans Spirits Competition'),
        ('Denver International Spirits Competition 2025: Double Gold (96 pts) — Forbidden Single Barrel', 'https://denverspiritscomp.com/wp-content/uploads/2025/04/2025_DISC_Win.xls.pdf', 'denverspiritscomp.com', 'award',
         'Forbidden Single Barrel Bourbon won Double Gold with 96 points at the 2025 Denver International Spirits Competition. Highest-scoring Forbidden entry.', 'Denver International Spirits Competition'),
        ('Denver International Spirits Competition 2025: Silver (88 pts) — Forbidden Small Batch 3', 'https://denverspiritscomp.com/wp-content/uploads/2025/04/2025_DISC_Win.xls.pdf', 'denverspiritscomp.com', 'award',
         'Forbidden Bourbon Small Batch 3 won Silver Medal with 88 points at the 2025 Denver International Spirits Competition.', 'Denver International Spirits Competition'),
        ('New York International Spirits Competition 2024: 96 Points — Forbidden Single Barrel', 'https://nyispiritscompetition.com/2024-whisky-awards/', 'nyispiritscompetition.com', 'award',
         'Forbidden Bourbon Single Barrel scored 96 points at the 2024 New York International Spirits Competition, placing among the Best Whiskies of the Year.', 'New York International Spirits Competition'),
        ('L.A. Spirits Awards 2025: Best Bourbons — Forbidden Single Barrel', 'https://www.thebestdrinkever.com/home/2025/8/13/the-best-bourbons-of-2025-according-to-the-prestigious-la-spirits-awards', 'thebestdrinkever.com', 'award',
         'Forbidden Single Barrel Wheated Bourbon recognized among the Best Bourbons of 2025 at the L.A. Spirits Awards. Praised for 114 proof, creamy butterscotch, and warm finish.', 'L.A. Spirits Awards'),
        ('Fred Minnick Top 100 American Whiskeys 2024 — Forbidden Batch 3', 'https://www.fredminnick.com/2024/12/24/2024-top-100-american-whiskeys-unranked/', 'fredminnick.com', 'award',
         'Forbidden Batch 3 named to Fred Minnick Top 100 American Whiskeys of 2024. Minnick called it "one of the best whiskeys Marianne Eaves has created."', 'Fred Minnick'),
        ('Fred Minnick Top 100 American Whiskeys 2025: #82 — Forbidden Batch 3', 'https://brewpublic.com/distilling/fred-minnick-delivers-his-top-100-whiskeys-of-2025/', 'brewpublic.com', 'award',
         'Forbidden Batch 3 ranked #82 on Fred Minnick Top 100 American Whiskeys of 2025. Second consecutive year on the list. 95.2 proof, $100.', 'Fred Minnick'),
        ('San Francisco World Spirits Competition — Forbidden Bourbon', 'https://thetastingalliance.com/events/san-francisco-world-spirits-competition', 'thetastingalliance.com', 'award',
         'Forbidden Bourbon recognized at the San Francisco World Spirits Competition, the most prestigious spirits competition in the world. Award laurel displayed on drinkforbidden.com.', 'San Francisco World Spirits Competition'),
        ('ASCOT Awards — Forbidden Bourbon', 'https://www.fredminnick.com/2023/05/17/2023-ascot-awards-winners-announced/', 'fredminnick.com', 'award',
         'Forbidden Bourbon recognized at the ASCOT Awards, Fred Minnick international spirits competition. Award laurel displayed on drinkforbidden.com.', 'ASCOT Awards'),

        # === INTERVIEWS (1) - Specifically discusses Forbidden Bourbon ===
        ('Drinkhacker: Eaves on Forbidden, Innovation & Bourbon Gluts', 'https://www.drinkhacker.com/2023/10/30/marianne-eaves-speaks-on-forbidden-whiskey-innovation-and-bourbon-gluts/', 'drinkhacker.com', 'interview',
         'Drinkhacker interview focused on Forbidden Bourbon. Eaves discusses Bardstown Bourbon Company partnership, pricing, and industry overproduction.', 'Drinkhacker'),

        # === PODCASTS (4) - All specifically discuss Forbidden Bourbon ===
        ('Bourbon Pursuit #425: Marianne Eaves on Forbidden Bourbon', 'https://bourbonpursuit.com/2023/08/31/425-marianne-eaves-gets-real-about-her-new-bourbon/', 'bourbonpursuit.com', 'podcast',
         'Marianne Eaves discusses Forbidden Bourbon in detail. Clears up press release confusion about distilling timeline. Discusses pricing, process, and mash bill.', 'Bourbon Pursuit'),
        ('The Mash Up E322: Marianne Eaves of Forbidden Bourbon', 'https://open.spotify.com/episode/1EPo0g8qPhirFHtHjKvdr7', 'spotify.com', 'podcast',
         'Deep conversation about Forbidden Bourbon origins, craft distilling approach, and future plans for the brand.', 'The Mash Up'),
        ('Barrel Room Chronicles: Marianne Eaves on Forbidden Bourbon', 'https://www.barrelroomchronicles.com/exploring-louisvilles-whiskey-row-and-the-trailblazing-women-in-whiskey-at-the-wow-awards-s3-e15/', 'barrelroomchronicles.com', 'podcast',
         'Eaves discusses Forbidden Bourbon at WOW Awards. Reveals plans for Montana distillery and Louisville tasting room on 5th and Market Street.', 'Barrel Room Chronicles'),
        ('Distilling Greatness Ep 13: Marianne Eaves on Forbidden', 'https://companydistilling.com/2024/06/podcast-marianne-eaves/', 'companydistilling.com', 'podcast',
         'Company Distilling podcast. Eaves discusses her journey to creating Forbidden Bourbon, white corn sourcing, and the Eaves Foundation.', 'Company Distilling'),

        # === EVENTS (5) - Forbidden Bourbon tasting events ===
        ('Virgin Hotels NYC: Meet the Maker — Forbidden Bourbon Tasting', 'https://virginhotels.com/new-york/entertainment/meet-the-maker/', 'virginhotels.com', 'event',
         'Virgin Hotels NYC event. Forbidden Bourbon tasting and lite bites presented by Marianne Eaves at The Shag Room at Everdene.', 'Virgin Hotels'),
        ('Garden & Gun Distilled Week: Forbidden Bourbon Pairing', 'https://thewhiskeywash.com/whiskey-news/garden-gun-partners-with-kentucky-distilleries-to-offer-a-week-of-bourbon-experiences/', 'thewhiskeywash.com', 'event',
         'Forbidden Bourbon featured at G&G Distilled week in Kentucky. Eaves provided Forbidden bourbon pairings at Yew Dell Botanical Gardens.', 'The Whiskey Wash'),
        ('New Orleans Bourbon Festival 2025: Forbidden Booth & Women\'s Panel', 'https://www.thebourbonandryeclub.com/splash-page/new-orleans-bourbon-festival-2025-live-updates', 'thebourbonandryeclub.com', 'event',
         'Forbidden had booth at NOLA Bourbon Festival 2025 grand tasting. Marianne Eaves spoke on Women\'s Panel alongside Jane Bowie (Potter Jane), Lauren Patz (Redwood Empire), Melinda Maddox (Old Elk). Tickets $175 for Baton Rouge meet & greet.', 'The Bourbon and Rye Club'),
        ('Marianne Eaves Bourbon Tasting — Tiger\'s Trail RV Resort, Baton Rouge', 'https://tigerstrailrvresort.com/tiger-trail-events/bourbon-tasting-featuring-the-first-female-master-distiller-and-creator-of-forbidden-bourbon-marianne-eaves/', 'tigerstrailrvresort.com', 'event',
         'March 20, 2025 meet & greet with Marianne Eaves in Baton Rouge during NOLA Bourbon Fest week. Tickets $175, special bourbon pricing. Tiger\'s Trail RV Resort.', 'Tiger\'s Trail RV Resort'),
        ('Forbidden Bourbon Tasting — Instagram Post', 'https://www.instagram.com/p/DS0Dzgrjo_n/', 'instagram.com', 'event',
         'Instagram post featuring photos from a Forbidden Bourbon tasting event. Community engagement and in-person brand experience.', 'Instagram'),

        # === SOCIAL / VIDEO (16) ===
        ('TikTok: Forbidden Bourbon Review — The Whiskey Boys', 'https://www.tiktok.com/@thewhiskyboys/video/7337101775884832042', 'tiktok.com', 'video',
         'TikTok video review of Forbidden Bourbon by @thewhiskyboys. Dedicated review with tasting notes and rating.', 'The Whiskey Boys'),
        ('TikTok: Forbidden Bourbon Product Review — Big Bear Wine', 'https://www.tiktok.com/@bigbearwine/video/7444698371358575915', 'tiktok.com', 'video',
         'TikTok product review of Forbidden Bourbon by Big Bear Wine liquor store. In-store feature and recommendation.', 'Big Bear Wine'),
        ('The Best Bourbons of 2025 (So Far)', 'https://youtu.be/ltL5x0OPVYc', 'youtube.com', 'video',
         'Brad\'s Bourbon Reviews ranks the best bourbons of 2025 so far. 12K views. 10:31 runtime. Follow on IG and TikTok @bradsbourbonreviews.', 'Brad\'s Bourbon Reviews'),
        ('The Best Allocated Bourbon You Didn\'t Know Existed', 'https://youtu.be/LVAbYUqjvhU', 'youtube.com', 'video',
         'Uncut Never Filtered discovers Forbidden Bourbon as an unknown allocated treasure while bottle hunting at The Blind Pig in Bardstown. 217 views. 8:48 runtime.', 'Uncut Never Filtered'),
        ('YouTube Short: Bourbon Banter — Forbidden Small Batch', 'https://youtube.com/shorts/_gy3ND28UgI', 'youtube.com', 'video',
         'Bourbon Banter shares their thoughts on this award-winning bourbon. YouTube Short.', 'Bourbon Banter'),
        ('YouTube Short: Forbidden Bourbon!!!', 'https://youtube.com/shorts/JXAsK65ukBg', 'youtube.com', 'video',
         'Short enthusiastic review of Forbidden Bourbon. 439 views.', 'YouTube Short'),
        ('YouTube Short: Forbidden Bourbon Review', 'https://youtube.com/shorts/l_-gpX0TPb0', 'youtube.com', 'video',
         'Quick Forbidden Bourbon review. 202 views.', 'YouTube Short'),
        ('Marianne Eaves — VinePair Master Distiller of the Year', 'https://youtu.be/DOLWLJktzNk', 'youtube.com', 'video',
         'Forbidden Bourbon official channel. In an industry ruled by old men who often work for a single legacy distillery their entire lives, Marianne Eaves has seemingly packed several careers into one. 71 views. 1:22 runtime.', 'Forbidden Bourbon'),
        ('New Limited Release Forbidden Bourbon Review', 'https://youtu.be/VS6CfanKplc', 'youtube.com', 'video',
         'RJtheFED reviews a bottle of Forbidden Bourbon. Released in only 4 states, a privilege to acquire. 183 views. 10:54 runtime.', 'RJtheFED'),
        ('Kentucky\'s First Female Master Distiller Releases \'Forbidden\' Bourbon', 'https://youtu.be/NcRZ8E8P_VM', 'youtube.com', 'video',
         'WAVE News Louisville news segment. After three years of developing recipes, followed by five years aging in bourbon barrels, Marianne Eaves is finally ready to introduce her creation. 660 views. 2:30 runtime.', 'WAVE News Louisville'),
        ('Club Marzipan Barrel Pick: Forbidden Bourbon', 'https://www.youtube.com/live/nv2c5u84G8o', 'youtube.com', 'video',
         'Fred Minnick live barrel pick session for Forbidden Bourbon. Tasting and choosing a barrel — 6.3 year bourbon options. 2.2K views. 2:02:37 runtime.', 'Fred Minnick'),
        ('NEW Forbidden Bourbon FIRST IMPRESSIONS — Worth It? It Depends', 'https://youtu.be/hovC28iHKAE', 'youtube.com', 'video',
         'TyTheBourbonGuy first impressions review. Forbidden Bourbon is a new project from Marianne Eaves, very well known in the whiskey world. 375 views. 6:00 runtime.', 'TyTheBourbonGuy'),
        ('YouTube Short: Forbidden Bourbon Tasting', 'https://youtube.com/shorts/nMUDKSb3CS8', 'youtube.com', 'video',
         'YouTube Shorts tasting of Forbidden Bourbon.', 'YouTube Short'),
        ('Forbidden Batch 1 & 2 Bourbon Review', 'https://www.youtube.com/watch?v=RJFED_BATCH12', 'youtube.com', 'video',
         'RJtheFED compares Forbidden Batch 1 and Batch 2 Trouble Bar Pick, a 114 proof Single Barrel. 172 views. 7:47 runtime.', 'RJtheFED'),
        ('Forbidden Bourbon Review! Is It Truly Groundbreaking?', 'https://www.youtube.com/watch?v=MASHANDDRUM_FB', 'youtube.com', 'video',
         'The Mash and Drum in-depth review of Forbidden debut release Small Batch Bourbon. Is it truly groundbreaking? 14K views. 11:31 runtime. Support on Patreon for Mash & Journey barrel picks.', 'The Mash and Drum'),
        ('Forbidden Bourbon Official Instagram', 'https://www.instagram.com/forbiddenbourbon/', 'instagram.com', 'social',
         'Official Forbidden Bourbon Instagram (@forbiddenbourbon). 4,387 followers, 128 posts. The first bourbon of its kind, thoughtfully blended by Kentucky\'s 1st Female Master Distiller.', 'Forbidden Bourbon'),
        ('Forbidden Bourbon Official Facebook', 'https://www.facebook.com/forbiddenbourbon', 'facebook.com', 'social',
         'Official Forbidden Bourbon Facebook page. Brand updates, event announcements, cocktail recipes, and community engagement.', 'Forbidden Bourbon'),

        # === ADDITIONAL FEATURES & PRESS ===
        ('Whisky Advocate: The Many Whiskeys of Marianne Eaves', 'https://whiskyadvocate.com/The-Many-Whiskeys-of-Marianne-Eaves', 'whiskyadvocate.com', 'feature',
         'Whisky Advocate deep profile by Julia Higgins. 8000 barrels set aside for Forbidden, 50 or fewer per batch. Also details Eavesdrop bar concept in Louisville and Big Sky Stillhouse in Montana.', 'Whisky Advocate'),
        ('Bourbon Trend: Wheated Bourbon Wonder — Marianne Eaves Forbidden Story', 'https://bourbontrend.com/bourbon-news/wheated-bourbon-wonder-marianne-eavess-forbidden-story/', 'bourbontrend.com', 'press',
         'Bourbon Trend feature on the creation of Forbidden Bourbon. Journey of Marianne Eaves and her unique wheated bourbon approach.', 'Bourbon Trend'),
        ('The Whiskey Wash: Marianne Eaves New Forbidden Treads New Ground', 'https://thewhiskeywash.com/whiskey-styles/bourbon/marianne-eaves-new-forbidden-bourbon-treads-new-whiskey-ground/', 'thewhiskeywash.com', 'press',
         'Whiskey Wash news coverage of Forbidden launch. First white corn and white winter wheat bourbon expression from iconic female master distiller.', 'The Whiskey Wash'),

        # === OWN SITES (4) ===
        ('Forbidden Bourbon — Official Website', 'https://drinkforbidden.com/', 'drinkforbidden.com', 'own_site',
         'Official website. A Twist on Tradition. Premium Kentucky wheated bourbon by Master Distiller Marianne Eaves.', 'Forbidden'),
        ('Forbidden Bourbon — Online Shop', 'https://shop.drinkforbidden.com', 'shop.drinkforbidden.com', 'own_site',
         'Official online shop. Buy Forbidden Bourbon direct — Small Batch Select and Single Barrel.', 'Forbidden'),
        ('Forbidden Bourbon — Single Barrel Product Page', 'https://drinkforbidden.com/products/single-barrel-bourbon', 'drinkforbidden.com', 'own_site',
         'Single Barrel product page. Hand-selected barrels. Bold, elegant, sweet, smooth, complex.', 'Forbidden'),
        ('Forbidden Bourbon — News & Media', 'https://drinkforbidden.com/news-media', 'drinkforbidden.com', 'own_site',
         'Official news and media page listing all press coverage, articles, and bourbon education content.', 'Forbidden'),
    ]
    
    for title, url, source, source_type, snippet, author in mentions:
        existing = _fetchone(conn, 'SELECT id FROM brand_mentions WHERE url = ?', (url,))
        if not existing:
            _execute(conn,
                'INSERT INTO brand_mentions (title, url, source, source_type, snippet, author) VALUES (?, ?, ?, ?, ?, ?)',
                (title, url, source, source_type, snippet, author))
    
    conn.commit()
    conn.close()
    count = len(mentions)
    print(f"Brand Intel seeded: {count} verified Forbidden Bourbon mentions")


# ============================================================
# POST OPERATIONS
# ============================================================

def create_post(content, image_path='', status='draft', hashtags='', link_url='', 
                scheduled_at=None, platforms=None, ai_generated=0, notes=''):
    conn = get_db()
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO posts (content, image_path, status, hashtags, link_url, scheduled_at, ai_generated, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''',
            (content, image_path, status, hashtags, link_url, scheduled_at, ai_generated, notes)
        )
        post_id = cur.fetchone()[0]
        
        if platforms:
            for platform in platforms:
                cur.execute(
                    "INSERT INTO post_platforms (post_id, platform_name, status) VALUES (%s, %s, 'pending')",
                    (post_id, platform)
                )
    else:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO posts (content, image_path, status, hashtags, link_url, scheduled_at, ai_generated, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (content, image_path, status, hashtags, link_url, scheduled_at, ai_generated, notes))
        post_id = cursor.lastrowid
        
        if platforms:
            for platform in platforms:
                cursor.execute(
                    "INSERT INTO post_platforms (post_id, platform_name, status) VALUES (?, ?, 'pending')",
                    (post_id, platform)
                )
    
    log_activity('post_created', f'New {status} post created', post_id)
    conn.commit()
    conn.close()
    return post_id


def get_post(post_id):
    conn = get_db()
    post = _fetchone(conn, 'SELECT * FROM posts WHERE id = ?', (post_id,))
    if post:
        platforms = _fetchall(conn, 'SELECT * FROM post_platforms WHERE post_id = ?', (post_id,))
        post['platforms'] = platforms
    conn.close()
    return post


def get_posts(status=None, limit=50, offset=0):
    conn = get_db()
    if status:
        posts = _fetchall(conn,
            'SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (status, limit, offset))
    else:
        posts = _fetchall(conn,
            'SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (limit, offset))
    
    for p in posts:
        platforms = _fetchall(conn, 'SELECT * FROM post_platforms WHERE post_id = ?', (p['id'],))
        p['platforms'] = platforms
    
    conn.close()
    return posts


def get_scheduled_posts():
    conn = get_db()
    posts = _fetchall(conn, '''
        SELECT * FROM posts 
        WHERE status = 'scheduled' AND scheduled_at IS NOT NULL 
        ORDER BY scheduled_at ASC
    ''')
    
    for p in posts:
        platforms = _fetchall(conn, 'SELECT * FROM post_platforms WHERE post_id = ?', (p['id'],))
        p['platforms'] = platforms
    
    conn.close()
    return posts


def get_due_posts():
    conn = get_db()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    posts = _fetchall(conn, '''
        SELECT * FROM posts 
        WHERE status = 'scheduled' AND scheduled_at <= ?
        ORDER BY scheduled_at ASC
    ''', (now,))
    
    for p in posts:
        platforms = _fetchall(conn, 'SELECT * FROM post_platforms WHERE post_id = ?', (p['id'],))
        p['platforms'] = platforms
    
    conn.close()
    return posts


def update_post(post_id, **kwargs):
    conn = get_db()
    allowed_fields = ['content', 'image_path', 'status', 'hashtags', 'link_url', 
                      'scheduled_at', 'published_at', 'notes']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if updates:
        if USE_POSTGRES:
            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            values = list(updates.values()) + [post_id]
            conn.cursor().execute(f'UPDATE posts SET {set_clause} WHERE id = %s', values)
        else:
            set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
            values = list(updates.values()) + [post_id]
            conn.execute(f'UPDATE posts SET {set_clause} WHERE id = ?', values)
    
    if 'platforms' in kwargs:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute('DELETE FROM post_platforms WHERE post_id = %s', (post_id,))
            for platform in kwargs['platforms']:
                cur.execute(
                    "INSERT INTO post_platforms (post_id, platform_name, status) VALUES (%s, %s, 'pending')",
                    (post_id, platform)
                )
        else:
            conn.execute('DELETE FROM post_platforms WHERE post_id = ?', (post_id,))
            for platform in kwargs['platforms']:
                conn.execute(
                    "INSERT INTO post_platforms (post_id, platform_name, status) VALUES (?, ?, 'pending')",
                    (post_id, platform)
                )
    
    log_activity('post_updated', f'Post #{post_id} updated', post_id)
    conn.commit()
    conn.close()


def delete_post(post_id):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('DELETE FROM posts WHERE id = %s', (post_id,))
    else:
        conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    log_activity('post_deleted', f'Post #{post_id} deleted')
    conn.commit()
    conn.close()


def mark_post_published(post_id, platform_name, platform_post_id=''):
    conn = get_db()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute('''
            UPDATE post_platforms SET status = 'published', published_at = %s, platform_post_id = %s
            WHERE post_id = %s AND platform_name = %s
        ''', (now, platform_post_id, post_id, platform_name))
        
        cur.execute('''
            SELECT COUNT(*) as cnt FROM post_platforms 
            WHERE post_id = %s AND status = 'pending'
        ''', (post_id,))
        pending = cur.fetchone()
        
        if pending[0] == 0:
            cur.execute('UPDATE posts SET status = %s, published_at = %s WHERE id = %s',
                       ('published', now, post_id))
    else:
        conn.execute('''
            UPDATE post_platforms SET status = 'published', published_at = ?, platform_post_id = ?
            WHERE post_id = ? AND platform_name = ?
        ''', (now, platform_post_id, post_id, platform_name))
        
        pending = conn.execute('''
            SELECT COUNT(*) as cnt FROM post_platforms 
            WHERE post_id = ? AND status = 'pending'
        ''', (post_id,)).fetchone()
        
        if pending['cnt'] == 0:
            conn.execute('UPDATE posts SET status = ?, published_at = ? WHERE id = ?',
                        ('published', now, post_id))
    
    log_activity('post_published', f'Post #{post_id} published to {platform_name}', post_id)
    conn.commit()
    conn.close()


def mark_post_failed(post_id, platform_name, error_message=''):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('''
            UPDATE post_platforms SET status = 'failed', error_message = %s
            WHERE post_id = %s AND platform_name = %s
        ''', (error_message, post_id, platform_name))
    else:
        conn.execute('''
            UPDATE post_platforms SET status = 'failed', error_message = ?
            WHERE post_id = ? AND platform_name = ?
        ''', (error_message, post_id, platform_name))
    conn.commit()
    conn.close()


# ============================================================
# PLATFORM OPERATIONS
# ============================================================

def get_platforms():
    conn = get_db()
    platforms = _fetchall(conn, 'SELECT * FROM platforms ORDER BY id')
    conn.close()
    return platforms


def get_platform(name):
    conn = get_db()
    platform = _fetchone(conn, 'SELECT * FROM platforms WHERE name = ?', (name,))
    conn.close()
    return platform


def update_platform(name, **kwargs):
    conn = get_db()
    allowed_fields = ['api_key', 'api_secret', 'access_token', 'refresh_token', 
                      'additional_config', 'connected', 'username']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if updates:
        if USE_POSTGRES:
            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            values = list(updates.values()) + [name]
            conn.cursor().execute(f'UPDATE platforms SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE name = %s', values)
        else:
            set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
            values = list(updates.values()) + [name]
            conn.execute(f'UPDATE platforms SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE name = ?', values)
    
    conn.commit()
    conn.close()


def add_platform(name, api_key='', connected=False):
    conn = get_db()
    display_names = {'openai': 'OpenAI (DALL-E)', 'runway': 'Runway ML'}
    icons = {'openai': '🎨', 'runway': '🎬'}
    if USE_POSTGRES:
        conn.cursor().execute(
            'INSERT INTO platforms (name, display_name, icon, api_key, connected) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING',
            (name, display_names.get(name, name), icons.get(name, '🔧'), api_key, int(connected))
        )
    else:
        conn.execute(
            'INSERT OR IGNORE INTO platforms (name, display_name, icon, api_key, connected) VALUES (?, ?, ?, ?, ?)',
            (name, display_names.get(name, name), icons.get(name, '🔧'), api_key, int(connected))
        )
    conn.commit()
    conn.close()


def get_connected_platforms():
    conn = get_db()
    platforms = _fetchall(conn, 'SELECT * FROM platforms WHERE connected = 1')
    conn.close()
    return platforms


# ============================================================
# CONTENT TEMPLATES
# ============================================================

def get_templates(category=None):
    conn = get_db()
    if category:
        templates = _fetchall(conn,
            'SELECT * FROM content_templates WHERE category = ? ORDER BY use_count DESC, created_at DESC',
            (category,))
    else:
        templates = _fetchall(conn,
            'SELECT * FROM content_templates ORDER BY use_count DESC, created_at DESC')
    conn.close()
    return templates


def create_template(title, content, category='general', hashtags=''):
    conn = get_db()
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO content_templates (title, content, category, hashtags) VALUES (%s, %s, %s, %s) RETURNING id',
            (title, content, category, hashtags)
        )
        template_id = cur.fetchone()[0]
    else:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO content_templates (title, content, category, hashtags)
            VALUES (?, ?, ?, ?)
        ''', (title, content, category, hashtags))
        template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return template_id


def delete_template(template_id):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('DELETE FROM content_templates WHERE id = %s', (template_id,))
    else:
        conn.execute('DELETE FROM content_templates WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()


def increment_template_use(template_id):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('UPDATE content_templates SET use_count = use_count + 1 WHERE id = %s', (template_id,))
    else:
        conn.execute('UPDATE content_templates SET use_count = use_count + 1 WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()


# ============================================================
# HASHTAG GROUPS
# ============================================================

def get_hashtag_groups():
    conn = get_db()
    groups = _fetchall(conn, 'SELECT * FROM hashtag_groups ORDER BY name')
    conn.close()
    return groups


def create_hashtag_group(name, hashtags):
    conn = get_db()
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute('INSERT INTO hashtag_groups (name, hashtags) VALUES (%s, %s) RETURNING id', (name, hashtags))
        group_id = cur.fetchone()[0]
    else:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO hashtag_groups (name, hashtags) VALUES (?, ?)', (name, hashtags))
        group_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return group_id


def delete_hashtag_group(group_id):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('DELETE FROM hashtag_groups WHERE id = %s', (group_id,))
    else:
        conn.execute('DELETE FROM hashtag_groups WHERE id = ?', (group_id,))
    conn.commit()
    conn.close()


# ============================================================
# ANALYTICS
# ============================================================

def log_analytics(post_id, platform_name, impressions=0, likes=0, retweets=0, replies=0, clicks=0):
    conn = get_db()
    if USE_POSTGRES:
        conn.cursor().execute('''
            INSERT INTO analytics (post_id, platform_name, impressions, likes, retweets, replies, clicks)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (post_id, platform_name, impressions, likes, retweets, replies, clicks))
    else:
        conn.execute('''
            INSERT INTO analytics (post_id, platform_name, impressions, likes, retweets, replies, clicks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (post_id, platform_name, impressions, likes, retweets, replies, clicks))
    conn.commit()
    conn.close()


def get_analytics_summary(days=30):
    conn = get_db()
    since = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    summary = _fetchall(conn, '''
        SELECT platform_name,
               SUM(impressions) as total_impressions,
               SUM(likes) as total_likes,
               SUM(retweets) as total_retweets,
               SUM(replies) as total_replies,
               SUM(clicks) as total_clicks,
               COUNT(*) as post_count
        FROM analytics 
        WHERE tracked_at >= ?
        GROUP BY platform_name
    ''', (since,))
    conn.close()
    return summary


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(action, details='', post_id=None):
    try:
        conn = get_db()
        if USE_POSTGRES:
            conn.cursor().execute(
                'INSERT INTO activity_log (action, details, post_id) VALUES (%s, %s, %s)',
                (action, details, post_id)
            )
        else:
            conn.execute(
                'INSERT INTO activity_log (action, details, post_id) VALUES (?, ?, ?)',
                (action, details, post_id)
            )
        conn.commit()
        conn.close()
    except:
        pass


def get_activity(limit=20):
    conn = get_db()
    activities = _fetchall(conn,
        'SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?', (limit,))
    conn.close()
    return activities


# ============================================================
# DASHBOARD STATS
# ============================================================

def get_dashboard_stats():
    conn = get_db()
    
    # Social media posts
    post_total = _fetchone(conn, 'SELECT COUNT(*) as cnt FROM posts')['cnt']
    post_drafts = _fetchone(conn, "SELECT COUNT(*) as cnt FROM posts WHERE status = 'draft'")['cnt']
    post_scheduled = _fetchone(conn, "SELECT COUNT(*) as cnt FROM posts WHERE status = 'scheduled'")['cnt']
    post_published = _fetchone(conn, "SELECT COUNT(*) as cnt FROM posts WHERE status = 'published'")['cnt']
    
    # Blog articles
    blog_total = _fetchone(conn, 'SELECT COUNT(*) as cnt FROM blog_articles')['cnt']
    blog_drafts = _fetchone(conn, "SELECT COUNT(*) as cnt FROM blog_articles WHERE status = 'draft'")['cnt']
    blog_published = _fetchone(conn, "SELECT COUNT(*) as cnt FROM blog_articles WHERE status = 'published'")['cnt']
    
    stats = {
        'total_posts': post_total + blog_total,
        'drafts': post_drafts + blog_drafts,
        'scheduled': post_scheduled,
        'published': post_published + blog_published,
        'failed': _fetchone(conn, "SELECT COUNT(*) as cnt FROM posts WHERE status = 'failed'")['cnt'],
        'connected_platforms': _fetchone(conn, "SELECT COUNT(*) as cnt FROM platforms WHERE connected = 1")['cnt'],
        'templates': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM content_templates')['cnt'],
    }
    
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    posts_week = _fetchone(conn,
        "SELECT COUNT(*) as cnt FROM posts WHERE status = 'published' AND published_at >= ?",
        (week_ago,))['cnt']
    blogs_week = _fetchone(conn,
        "SELECT COUNT(*) as cnt FROM blog_articles WHERE status = 'published' AND published_at >= ?",
        (week_ago,))['cnt']
    stats['published_this_week'] = posts_week + blogs_week
    
    conn.close()
    return stats


# ============================================================
# BLOG OPERATIONS
# ============================================================

def create_blog_article(title, content, excerpt='', topic='', keywords='', 
                        status='draft', platform='', platform_url='', word_count=0):
    conn = get_db()
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO blog_articles (title, content, excerpt, topic, keywords, status, platform, platform_url, word_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''',
            (title, content, excerpt, topic, keywords, status, platform, platform_url, word_count)
        )
        article_id = cur.fetchone()[0]
    else:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO blog_articles (title, content, excerpt, topic, keywords, status, platform, platform_url, word_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, content, excerpt, topic, keywords, status, platform, platform_url, word_count)
        )
        article_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return article_id


def get_blog_articles(status=None, limit=50):
    conn = get_db()
    if status:
        articles = _fetchall(conn, 
            'SELECT * FROM blog_articles WHERE status = ? ORDER BY created_at DESC LIMIT ?',
            (status, limit))
    else:
        articles = _fetchall(conn, 
            'SELECT * FROM blog_articles ORDER BY created_at DESC LIMIT ?', (limit,))
    conn.close()
    return articles


def get_blog_article(article_id):
    conn = get_db()
    article = _fetchone(conn, 'SELECT * FROM blog_articles WHERE id = ?', (article_id,))
    conn.close()
    return article


def update_blog_article(article_id, **kwargs):
    conn = get_db()
    for key, value in kwargs.items():
        _execute(conn, f'UPDATE blog_articles SET {key} = ? WHERE id = ?', (value, article_id))
    conn.commit()
    conn.close()


def add_published_platform(article_id, platform, url=''):
    """Track cross-posting: add a platform to published_platforms JSON"""
    conn = get_db()
    article = _fetchone(conn, 'SELECT published_platforms FROM blog_articles WHERE id = ?', (article_id,))
    if article:
        try:
            platforms = json.loads(article.get('published_platforms', '{}') or '{}')
        except:
            platforms = {}
        platforms[platform] = url
        _execute(conn, 'UPDATE blog_articles SET published_platforms = ? WHERE id = ?',
                (json.dumps(platforms), article_id))
        conn.commit()
    conn.close()


def delete_blog_article(article_id):
    conn = get_db()
    _execute(conn, 'DELETE FROM blog_articles WHERE id = ?', (article_id,))
    conn.commit()
    conn.close()


def get_blog_topics(category=None):
    conn = get_db()
    if category:
        topics = _fetchall(conn, 'SELECT * FROM blog_topics WHERE category = ? ORDER BY times_used ASC', (category,))
    else:
        topics = _fetchall(conn, 'SELECT * FROM blog_topics ORDER BY times_used ASC, created_at DESC')
    conn.close()
    return topics


def add_blog_topic(title, category='general', keywords=''):
    conn = get_db()
    _execute(conn, 'INSERT INTO blog_topics (title, category, keywords) VALUES (?, ?, ?)',
             (title, category, keywords))
    conn.commit()
    conn.close()


def use_blog_topic(topic_id):
    conn = get_db()
    _execute(conn, 'UPDATE blog_topics SET times_used = times_used + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?',
             (topic_id,))
    conn.commit()
    conn.close()


def get_blog_stats():
    conn = get_db()
    stats = {
        'total': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM blog_articles')['cnt'],
        'drafts': _fetchone(conn, "SELECT COUNT(*) as cnt FROM blog_articles WHERE status = 'draft'")['cnt'],
        'published': _fetchone(conn, "SELECT COUNT(*) as cnt FROM blog_articles WHERE status = 'published'")['cnt'],
        'topics': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM blog_topics')['cnt'],
    }
    conn.close()
    return stats


# ============================================================
# BRAND MENTIONS
# ============================================================

def add_brand_mention(title, url='', source='', source_type='article', snippet='', 
                      full_content='', author='', sentiment='neutral', date_published=''):
    conn = get_db()
    if url:
        existing = _fetchone(conn, 'SELECT id FROM brand_mentions WHERE url = ?', (url,))
        if existing:
            conn.close()
            return None
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO brand_mentions (title, url, source, source_type, snippet, full_content, author, sentiment, date_published)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''',
            (title, url, source, source_type, snippet, full_content, author, sentiment, date_published))
        mention_id = cur.fetchone()[0]
    else:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO brand_mentions (title, url, source, source_type, snippet, full_content, author, sentiment, date_published)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, url, source, source_type, snippet, full_content, author, sentiment, date_published))
        mention_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return mention_id


def get_brand_mentions(source_type=None, starred=None, limit=100):
    conn = get_db()
    if source_type and starred is not None:
        mentions = _fetchall(conn, 
            'SELECT * FROM brand_mentions WHERE source_type = ? AND starred = ? ORDER BY created_at DESC LIMIT ?',
            (source_type, starred, limit))
    elif source_type:
        mentions = _fetchall(conn, 
            'SELECT * FROM brand_mentions WHERE source_type = ? ORDER BY created_at DESC LIMIT ?',
            (source_type, limit))
    elif starred is not None:
        mentions = _fetchall(conn, 
            'SELECT * FROM brand_mentions WHERE starred = ? ORDER BY created_at DESC LIMIT ?',
            (starred, limit))
    else:
        mentions = _fetchall(conn, 
            'SELECT * FROM brand_mentions ORDER BY created_at DESC LIMIT ?', (limit,))
    conn.close()
    return mentions


def get_brand_mention(mention_id):
    conn = get_db()
    mention = _fetchone(conn, 'SELECT * FROM brand_mentions WHERE id = ?', (mention_id,))
    conn.close()
    return mention


def update_brand_mention(mention_id, **kwargs):
    conn = get_db()
    for key, value in kwargs.items():
        _execute(conn, f'UPDATE brand_mentions SET {key} = ? WHERE id = ?', (value, mention_id))
    conn.commit()
    conn.close()


def delete_brand_mention(mention_id):
    conn = get_db()
    _execute(conn, 'DELETE FROM brand_mentions WHERE id = ?', (mention_id,))
    conn.commit()
    conn.close()


def get_brand_mention_stats():
    conn = get_db()
    stats = {
        'total': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM brand_mentions')['cnt'],
        'reviews': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'review'")['cnt'],
        'features': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'feature'")['cnt'],
        'press': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'press'")['cnt'],
        'podcasts': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'podcast'")['cnt'],
        'videos': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'video'")['cnt'],
        'events': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'event'")['cnt'],
        'awards': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'award'")['cnt'],
        'interviews': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'interview'")['cnt'],
        'social': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'social'")['cnt'],
        'own_site': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE source_type = 'own_site'")['cnt'],
        'starred': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM brand_mentions WHERE starred = 1')['cnt'],
        'with_content': _fetchone(conn, "SELECT COUNT(*) as cnt FROM brand_mentions WHERE full_content IS NOT NULL AND full_content != ''")['cnt'],
    }
    conn.close()
    return stats


# ============================================================
# OUTREACH CONTACTS
# ============================================================

def add_outreach_contact(name, email='', platform='', platform_handle='', platform_url='', 
                         followers=0, category='influencer', tier='1', notes=''):
    conn = get_db()
    if email:
        existing = _fetchone(conn, 'SELECT id FROM outreach_contacts WHERE email = ?', (email,))
        if existing:
            conn.close()
            return None
    if platform_url:
        existing = _fetchone(conn, 'SELECT id FROM outreach_contacts WHERE platform_url = ?', (platform_url,))
        if existing:
            conn.close()
            return None
    
    _execute(conn, '''INSERT INTO outreach_contacts (name, email, platform, platform_handle, platform_url, followers, category, tier, notes)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (name, email, platform, platform_handle, platform_url, followers, category, tier, notes))
    conn.commit()
    contact_id = _fetchone(conn, 'SELECT MAX(id) as id FROM outreach_contacts')['id']
    conn.close()
    return contact_id


def get_outreach_contacts(category=None, status=None, tier=None, limit=500):
    conn = get_db()
    query = 'SELECT * FROM outreach_contacts'
    conditions = []
    params = []
    if category:
        conditions.append('category = ?')
        params.append(category)
    if status:
        conditions.append('status = ?')
        params.append(status)
    if tier:
        conditions.append('tier = ?')
        params.append(tier)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY followers DESC, created_at DESC LIMIT ?'
    params.append(limit)
    contacts = _fetchall(conn, query, tuple(params))
    conn.close()
    return contacts


def get_outreach_contact(contact_id):
    conn = get_db()
    contact = _fetchone(conn, 'SELECT * FROM outreach_contacts WHERE id = ?', (contact_id,))
    conn.close()
    return contact


def update_outreach_contact(contact_id, **kwargs):
    conn = get_db()
    for key, value in kwargs.items():
        _execute(conn, f'UPDATE outreach_contacts SET {key} = ? WHERE id = ?', (value, contact_id))
    conn.commit()
    conn.close()


def delete_outreach_contact(contact_id):
    conn = get_db()
    _execute(conn, 'DELETE FROM outreach_contacts WHERE id = ?', (contact_id,))
    conn.commit()
    conn.close()


def get_outreach_stats():
    conn = get_db()
    stats = {
        'total': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM outreach_contacts')['cnt'],
        'with_email': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE email != ''")['cnt'],
        'contacted': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE status = 'contacted'")['cnt'],
        'product_sent': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM outreach_contacts WHERE product_sent = 1')['cnt'],
        'responded': _fetchone(conn, 'SELECT COUNT(*) as cnt FROM outreach_contacts WHERE responded = 1')['cnt'],
        'influencers': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE category = 'influencer'")['cnt'],
        'industry': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE category = 'industry'")['cnt'],
        'media': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE category = 'media'")['cnt'],
        'adjacent': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE category = 'adjacent'")['cnt'],
        'community': _fetchone(conn, "SELECT COUNT(*) as cnt FROM outreach_contacts WHERE category = 'community'")['cnt'],
    }
    conn.close()
    return stats


def seed_customer_emails():
    """Seed customer email list from Mash Networks data"""
    conn = get_db()
    try:
        _execute(conn, "DELETE FROM customer_emails")
        emails = [
            "07-sparkly.piccolo@icloud.com",
            "073bmw@gmail.com",
            "1994sadlers@gmail.com",
            "1audreydavis@gmail.com",
            "88STEPHLOVA@GMAIL.COM",
            "aaw8752@gmail.com",
            "aclema2@gmail.com",
            "adamdart@gmail.com",
            "advdance@aol.com",
            "aggrobait@gmail.com",
            "alan_schubert@icloud.com",
            "alpinetim72@gmail.com",
            "amandagiannini@gmail.com",
            "amy.worthington.91@att.net",
            "amygo5900@gmail.com",
            "andersonpalmetto@gmail.com",
            "andersonusc@icloud.com",
            "andifoti@sbcglobal.net",
            "andrea.bauman.96@facebook.com",
            "angela.oneal@gmail.com",
            "angieveronese@gmail.com",
            "annie@ahstevens.com",
            "annlang68@yahoo.com",
            "annniles@dairy-dreams.com",
            "Aprsrccpa@gmail.com",
            "arestovich@gmail.com",
            "ari.sussman@gmail.com",
            "artemis1300@hotmail.com",
            "ashlynnwade89@gmail.com",
            "astrid@an-research.com",
            "atafralis@intero.com",
            "atpropertyhomes@gmail.com",
            "auntiesue3@gmail.com",
            "avoss756@gmail.com",
            "b.pearce@hotmail.com",
            "babsit@hotmail.com",
            "barbara.c.brenner@icloud.com",
            "barbie@umcontractors.com",
            "Barry46@yahoo.com",
            "bauble_insteps.42@icloud.com",
            "bdgrammer@1callhome.com",
            "bdgross@aol.com",
            "bearbogen@gmail.com",
            "bearstj@gmail.com",
            "belt5@comcast.net",
            "benbeeler@comcast.net",
            "bethanyiocrain@gmail.com",
            "betsyaschroeder@gmail.com",
            "bhargavpatel1@yahoo.com",
            "bhissongdmd@icloud.com",
            "bigburge1974@comcast.net",
            "billdeb101202@gmail.com",
            "billk@sit-co.net",
            "billy.lyons@gmail.com",
            "bmf3@mac.com",
            "bmmail01@gmail.com",
            "bob@excelleron.com",
            "brandon@practacbr.com",
            "brettbostwick@aol.com",
            "Brian.Bradsher@yahoo.com",
            "brinnaner98@gmail.com",
            "brittany.wilkinson@me.com",
            "britter@scrtc.com",
            "brownfelder@gmail.com",
            "bs.martin@me.com",
            "buck2212@yahoo.com",
            "burtonfive5577@gmail.com",
            "cameronmoore89@yahoo.com",
            "carlyjoe@hotmail.com",
            "carmennordstrand@icloud.com",
            "carolinecurrier3@gmail.com",
            "carolinejpereira2@gmail.com",
            "carrie.showalter2@gmail.com",
            "carruthers_ci@hotmail.com",
            "caryfowler@mac.com",
            "cathieastorey@gmail.com",
            "cathyjowheeler@bellsouth.net",
            "cb_singer@yahoo.com",
            "cberchuck@gmail.com",
            "cbibbryant@gmail.com",
            "cbrudolph@gmail.com",
            "cburnsnc1@gmail.com",
            "ccampbell6179@gmail.com",
            "cflavin@wholeleader.com",
            "chelemarsh@aol.com",
            "cherylawb@msn.com",
            "chollanddvm@Gmail.com",
            "chris.bach@gmail.com",
            "chrislarellano@gmail.com",
            "chrislclary@gmail.com",
            "christian.frueh@gmail.com",
            "christine.reynolds.white@gmail.com",
            "cindy@jdalexander.com",
            "cjbuckley01@gmail.com",
            "cjwiersum@aol.com",
            "ckoether@kitchenbrains.com",
            "clark@vidsol.media",
            "claudecrocker@gmail.com",
            "cliflawson@comcast.net",
            "cole.mshawn@gmail.com",
            "colin.hanna15@gmail.com",
            "conceptii@att.net",
            "conrad1947@hotmail.com",
            "courtneyjonesshannon@gmail.com",
            "cplgeorge@yahoo.com",
            "craigmelvin803@gmail.com",
            "craigwash1@aol.com",
            "craininv@gmail.com",
            "crensky79@gmail.com",
            "curlyfrog8@gmail.com",
            "cwmorse52@gmail.com",
            "cyllu85@me.com",
            "dadybrawls@aol.com",
            "dakinshoemaker@gmail.com",
            "dan@smithprint.net",
            "dan@thebarnesfamily.com",
            "danamcniel@hotmail.com",
            "dandpt@charter.net",
            "daniellemeyer8640@gmail.com",
            "danny_s@cox.net",
            "dantaylor1981@hotmail.com",
            "dapper1328@aol.com",
            "darci.ulrich@gmail.com",
            "darl4865@att.net",
            "davidallan3@live.com",
            "davidmartin10@mac.com",
            "dawkinsamy5@gmail.com",
            "dawn@boswellandmoore.com",
            "daynaetaylor@yahoo.com",
            "dbarker910@gmail.com",
            "dbenkendorf2580@gmail.com",
            "ddresely@comcast.net",
            "deannamking@gmail.com",
            "debbiehann@gmail.com",
            "deerrick@swbell.net",
            "dennis43440@aol.com",
            "des6557@gmail.com",
            "dgately89@gmail.com",
            "dgulick@protonmail.com",
            "dhallman5095@yahoo.com",
            "dick.lakebj@gmail.com",
            "didickers@aol.com",
            "dihenson@comcast.net",
            "diverkdavis@hotmail.com",
            "djhartman2271@comcast.net",
            "dkranich@gmail.com",
            "dmwhite77@hotmail.com",
            "dmyers52@gmail.com",
            "dnewsch@gmail.com",
            "dogilama@yahoo.com",
            "donald.c.lee@gmail.com",
            "donaldw62@gmail.com",
            "donna_hewett@aol.com",
            "doug_atchison@gmail.com",
            "dougeb2002@yahoo.com",
            "dpurdum122@gmail.com",
            "dregarver@gmail.com",
            "drickenmann803@gmail.com",
            "drjacquilevesque@gmail.com",
            "dschwans05@gmail.com",
            "dstuber45@gmail.com",
            "dulaneys1640@gmail.com",
            "dwilliams5000@gmail.com",
            "dwolfeden@gmail.com",
            "dzlexus@gmail.com",
            "e061453@yahoo.com",
            "ebruce08@gmail.com",
            "edwards.glenn@comcast.net",
            "efcasper2u@gmail.com",
            "elipinski123@gmail.com",
            "ellens1229@comcast.net",
            "ellisk205@gmail.com",
            "ellorygraff23@gmail.com",
            "elm1100@att.net",
            "emilymclex@gmail.com",
            "erchilders@outlook.com",
            "erika.olsen87@gmail.com",
            "erinbarry@mac.com",
            "eveltwin1@icloud.com",
            "evelynward1961@gmail.com",
            "ewoodruff@satx.rr.com",
            "ezzieok@gmail.com",
            "firdoc23@Reagan.com",
            "fisherh15@gmail.com",
            "fjbeeck@optonline.net",
            "flyingdr1964@gmail.com",
            "fndrbp@icloud.com",
            "francahaas02@gmail.com",
            "frankr@sbslp.com",
            "frasco711@outlook.com",
            "frequenttraveler2015@gmail.com",
            "fvogel1321@gmail.com",
            "gaaap@buckeye-express.com",
            "gagglematt@gmail.com",
            "garyschoenhouse@gmail.com",
            "gbruno3@gmail.com",
            "gcarson47@gmail.com",
            "georgannebyrd@yahoo.com",
            "gerardwelch10@me.com",
            "ggood1628@aol.co",
            "gibbspatrick@patrickfamilyfarms.com",
            "glen@bescoassociates.com",
            "gloriage819@gmail.com",
            "gpowell763@gmail.com",
            "greenwoodesg@gmail.com",
            "gregoryashantz@gmail.com",
            "gregsticka@icloud.com",
            "gromit1.nf@gmail.com",
            "gsgibson@icloud.com",
            "gtrieger@aol.com",
            "guillermo_tapia@hotmail.com",
            "guillermorego@yahoo.com",
            "guinnrapps@gmail.com",
            "guyurtalking2@gmail.com",
            "hammyus@hotmail.com",
            "hassner@att.net",
            "hauck8621@outlook.com",
            "hawilliams1962@hitmail.com",
            "hayward@cardtrop.shop",
            "hctiger2002mv@gmail.com",
            "heather20007@gmail.com",
            "heatherchuitt@hotmail.com",
            "henleyroger@yahoo.com",
            "hgrantham1@gmail.com",
            "hkwatt44@gmail.com",
            "hlarrymays@gmail.com",
            "hmjensen@earthlink.net",
            "hodsondrsd@gmail.com",
            "hokieapc@yahoo.com",
            "holidaytuttle@me.com",
            "hshields2021@gmail.com",
            "hundred81_flashes@icloud.com",
            "hunterstephen977@gmail.com",
            "icrlemmor@aol.com",
            "idahojoe66@gmail.com",
            "incognito@twc.com",
            "ingaklusa2003@yahoo.com",
            "investigativeproducts@ymail.com",
            "isaacbeste39@gmail.com",
            "izager@comcast.net",
            "izghami11@gmail.com",
            "J2526sing@gmail.com",
            "jabencox@gmail.com",
            "jalton17@gmail.com",
            "jamesdiem59@gmail.com",
            "JamesSchmidt678@outlook.com",
            "jamosg2025@gmail.com",
            "janetmdavis9@gmail.com",
            "janettanguay@hammockwayoflife.com",
            "jason_kwintner@comcast.net",
            "javalyon1@aol.com",
            "jay.mcrae@pfizer.com",
            "jcatandella@yahoo.com",
            "jchapmandds@yahoo.com",
            "jcheath@nc.rr.com",
            "jcrohde@gmail.com",
            "jcwatson@alumni.stanford.edu",
            "jdandlauri1985@gmail.com",
            "jeaninethornton@icloud.com",
            "jeff.turnage59@yahoo.com",
            "jemilhorn@charter.net",
            "jenldaniel06@gmail.com",
            "jennifer@hermannfurniture.com",
            "jenniferbrisbin@yahoo.com",
            "jessegraham2010@gmail.com",
            "jessica.frasco@gmail.com",
            "jessica_toll@kindermorgan.com",
            "jewett.michael.j@gmail.com",
            "jewls425@me.com",
            "jganderson96@gmail.com",
            "jhjh333@sbcglobal.net",
            "jhouse@greatsouthernbank.com",
            "jimb@boydinsurance.com",
            "jimbohebert@hotmail.com",
            "jj34email@gmail.com",
            "jlbayha@gmail.com",
            "jmax4508@gmail.com",
            "jmeyers@imaginepub.com",
            "jmhale1@msn.com",
            "jmigas@yahoo.com",
            "jmshugars@gmail.com",
            "joanna@jtdinc.com",
            "jodi44@gmail.com",
            "john.h.silver@gmail.com",
            "john.ritter51@gmail.com",
            "john@golfprollc.com",
            "johnabarnes@gmail.com",
            "johnbarney@bellsouth.net",
            "johnhill2525@yahoo.com",
            "johnmarty1376@aol.com",
            "johnriemath@yahoo.com",
            "johns@calvertinc.com",
            "jonesmc@me.com",
            "jpheineman@aol.com",
            "jpunishill@gmail.com",
            "jsearcy80@gmail.com",
            "jsmann17@gmail.com",
            "jsnmusselman@gmail.com",
            "jsveselka@gmail.com",
            "jt_sangsland@yahoo.com",
            "jturner@stregisculvert.com",
            "judit@studiogirlart.com",
            "judyeggleston@aol.com",
            "juliebergenevents@gmail.com",
            "julsmastro@me.com",
            "jumpit54@yahoo.com",
            "june@bayhagroup.com",
            "jweir@icloud.com",
            "jweiss831@gmail.com",
            "jwilsonfzr@gmail.com",
            "k8winterton@gmail.com",
            "karenmb7@yahoo.com",
            "karenr@sbslp.com",
            "karensubs@icloud.com",
            "kari.sagehorn73@gmail.com",
            "karibdmd@gmail.com",
            "karishadevlin@gmail.com",
            "karsten@skyt.com",
            "katherineames469@gmail.com",
            "kathybivens@icloud.com",
            "kathynicod@verizon.net",
            "katrin@pdxrevival.com",
            "kbansfam@comcast.net",
            "kbennett86@gmail.com",
            "kbretz@comcast.net",
            "kbriefel@comcast.net",
            "kcolwell77@comcast.net",
            "kdians@aol.com",
            "keith@hogantitle.com",
            "kellymoore.zv@gmail.com",
            "ken.kuziel@att.net",
            "kenglish947@gmail.com",
            "kerri.holm@gmail.com",
            "Kerry@khirsh.com",
            "kevin.dakota.suess24@gmail.com",
            "kevin.page@yanfeng.com",
            "kevin@umcontractors.com",
            "keyskim.gaddy1981@gmail.com",
            "kgiles1999@yahoo.com",
            "kgrieff2012@gmail.com",
            "khkelly2@gmail.com",
            "kielrois@gmail.com",
            "kilburn.landry@gmail.com",
            "kimberlyhasenberg@yahoo.com",
            "kithaxton@gmail.com",
            "klig@dentistryoldetowne.com",
            "kmelder129@yahoo.com",
            "kpennshop@gmail.com",
            "kristin_ludwig@yahoo.com",
            "kristina.gedgaudas@gmail.com",
            "kskf@earthlink.net",
            "ksnixon@gmail.com",
            "ksomoza@gmail.com",
            "ksouza@alleghenyenviron.com",
            "kstehmer@gmail.com",
            "ksumner@athensk8.net",
            "ktm991@comcast.net",
            "kwildman@neo.rr.com",
            "kwolin@gmail.com",
            "kyle.j.stevens@gmail.com",
            "laltmann@reliapath.com",
            "lamj10@aol.com",
            "lauren.vanduser@gmail.com",
            "lee.blomquist@gmail.com",
            "leitha.olson57@gmail.com",
            "lesleyd@elpasotel.net",
            "lesly_curtis@yahoo.com",
            "libbybullock501@gmail.com",
            "lilabell20@gmail.com",
            "limelizard@charter.net",
            "lindahar52@gmail.com",
            "lindaiknoll@gmail.com",
            "lindsbarber6@gmail.com",
            "Lindsey.a.driscoll@gmail.com",
            "lipriebe@aol.com",
            "lisapate@cox.net",
            "lisaphipps3@gmail.com",
            "lisarajek@gmail.com",
            "liv6903@yahoo.com",
            "lizcharnes@gmail.com",
            "lkasman@gmail.com",
            "lmorriso@ma.rr.com",
            "loridreilly@gmail.com",
            "loritracy@sdhca.org",
            "lscott11@columbus.rr.com",
            "luckysnoop77@yahoo.com",
            "lynnajohnson72@gmail.com",
            "Lynnecpacer@aol.com",
            "lyonkss69@gmail.com",
            "mac036985111@yahoo.com",
            "mactools1963@gmail.com",
            "maddoxpatricia@hotmail.com",
            "madelynhubbard@icloud.com",
            "madie125@yahoo.com",
            "malshopping@protonmail.com",
            "manocc22@gmail.com",
            "marc.lebaron@lincolnindustries.com",
            "marcusfurn@iglou.com",
            "mark@salquist.com",
            "marmed1@aol.com",
            "maronna@g.com",
            "mary.ellen.rucks@gmail.com",
            "mattwiggins78@gmail.com",
            "mayojessica75@gmail.com",
            "mbmallon13@gmail.com",
            "mcobri2@gmail.com",
            "mcollins@centralsc.org",
            "mda187eb@gmail.com",
            "mdsmith@hiwaay.net",
            "mem5425@gmail.com",
            "meridithm98@gmail.com",
            "mfawcett8@gmail.com",
            "mhearn@att.net",
            "michael_mc@live.com",
            "michaelchirschi@gmail.com",
            "michaelrdover@hotmail.com",
            "michaelthillan@gmail.com",
            "michellewitteveen@yahoo.com",
            "mikeaviation@gmail.com",
            "mikecauldwell@gmail.com",
            "mikemackie@mac.com",
            "mikemulka@hotmail.com",
            "millsed73@protonmail.com",
            "mimiamoore53@gmail.com",
            "missybest40@gmail.com",
            "mjstraley@comcast.net",
            "mkrohn129@gmail.com",
            "ml_taylor@comcast.net",
            "mlfoley3@gmail.com",
            "mlucchesi@comcast.net",
            "momoneyathome@gmail.com",
            "monicawillis64@gmail.com",
            "morgan.majopian@gmail.com",
            "mroberts@scqc.org",
            "mrskatyfrank@gmail.com",
            "ms1126@hotmail.comm",
            "mstevensrdn@gmail.com",
            "mtiszai@cfl.rr.com",
            "muddcat1144@att.net",
            "mylifecoachtoo@comcast.net",
            "mysque@aol.com",
            "nabroussard@cox.net",
            "nathanhuber2014@gmail.com",
            "natler1@hotmail.com",
            "navcax@gmail.com",
            "ndmize@outlook.com",
            "nhc.217@gmail.com",
            "nick.remelts@gmail.com",
            "nikolas.markos@gmail.com",
            "nilwon23@hotmail.com",
            "nloggy@gvtc.com",
            "noony49@sbcglobal.net",
            "Nvba712@gmail.com",
            "orlandorockwell@hotmail.com",
            "ousleyamanda09@gmail.com",
            "oznewton@mac.com",
            "palanhicks@gmail.com",
            "palcer@comcast.net",
            "pamalama2009@gmail.com",
            "pattihellyer@gmail.com",
            "paulejennings@bellsouth.net",
            "pdhubert213@gmail.com",
            "pendoc@cfl.rr.com",
            "pesposito@charter.net",
            "petesky71@gmail.com",
            "phyllismadren@gmail.com",
            "pjwrobert@aol.com",
            "poneilll10@comcast.net",
            "ppaclinic@gmail.com",
            "pzivley@cmzlaw.net",
            "randienjones@yahoo.com",
            "ranger88a@gmail.com",
            "rbucholtz@gmail.com",
            "rccola668@gmail.com",
            "rdksrammel@bellsouth.net",
            "rebeccabanerji@gmail.com",
            "rebekahwiggins@sbcglobal.net",
            "redhatgator@yahoo.com",
            "reese.baker@sbcglobl.net",
            "REIDFAWCETT@GMAIL.COM",
            "reidtx2579@gmail.com",
            "rfabrici@yahoo.com",
            "rich.altman60@gmail.com",
            "richard.cox1135@aol.com",
            "richcies@tir.com",
            "rick@americanzealotproductions.com",
            "rickdti@msn.com",
            "rishman8881@gmail.com",
            "ritz68@aol.com",
            "rjarends@me.com",
            "rjlpartner@aol.com",
            "rlahoff@hallsgarden.com",
            "robert.hartigan@aviagogy.com",
            "robertdurish@gmail.com",
            "robjiarrett@aol.com",
            "robmaugeri@yahoo.com",
            "roderick802@gmail.com",
            "rolltideroll44@gmail.com",
            "ron@rlewisconstruction.net",
            "ronnieandei@verizon.net",
            "rosehillya@me.com",
            "rosesq328@msn.com",
            "rosinskig@hswc.com",
            "rowefamily7@comcast.net",
            "roy.reasor@yahoo.com",
            "rpsesq@dslawny.com",
            "rrigby19@gmail.com",
            "rsontheair@gmail.com",
            "rtrefzer@hotmail.com",
            "rwright112345@gmail.com",
            "ryan@equinox-development.com",
            "ryan@longcliff.com",
            "ryansethtaylor@hotmail.com",
            "ryderkirgolf@aol.com",
            "S@sosarris.com",
            "samanthawilkin3324@att.net",
            "sandymrussell1968@gmail.com",
            "santonict@comcast.net",
            "saperkinson@gmail.com",
            "sasday@tampabay.rr.com",
            "scarlton925@yahoo.com",
            "scotto@ollenburgmotors.com",
            "scsheprd@gmail.com",
            "scverdery@gmail.com",
            "scwissman54@gmail.com",
            "seamuspcarey@gmail.com",
            "seanbradio@Gmail.com",
            "secwikla@icloud.com",
            "sferlo4@gmail.com",
            "sgruenheid@gmail.com",
            "sgtgatekeeper@gmail.com",
            "shanvalijen@gmail.com",
            "sharon@rmscotati.com",
            "shauna.keough@syneoshealth.com",
            "shea.nangle@gmail.com",
            "sheilathayer2@gmail.com",
            "shelly.sccconstruction@gmail.com",
            "sherri_zhou@harmoniqo.com",
            "shli@me.com",
            "sledhead36@aol.com",
            "slehman25850tmi@comcast.net",
            "smorr911@gmail.com",
            "snavarrete@mpwonline.com",
            "Spearsall58@gmail.com",
            "spicerhousekaty@yahoo.com",
            "Squaz115@me.com",
            "squiddy09@aol.com",
            "srseymour11@gmail.com",
            "ssengineer2001@yahoo.com",
            "ssmith53.al@gmail.com",
            "ssrdeb@gmail.com",
            "stacy.nvonhoffman@gmail.com",
            "stan.vela@gmail.com",
            "stephencyruscopenhaver@yahoo.com",
            "stephendkane@gmail.com",
            "sterlingcleancarpet@gmail.com",
            "stevegrosscup@gmail.com",
            "stevepenn14@hotmail.com",
            "strefzer@sbcglobal.net",
            "stuphelps@gmail.com",
            "sueforys@yahoo.com",
            "suekain63@gmail.com",
            "sunshine4u1972@att.net",
            "susan.benac@gmail.com",
            "susanhuber1@hotmail.com",
            "susanparrish@mac.com",
            "suzan_limaye@hotmail.com",
            "suzy.townsend1@gmail.com",
            "swebb757@gmail.com",
            "sybaris412@hotmail.com",
            "tbarritt@bernards.com",
            "teniola.akinwale@gmail.com",
            "terrielynn_baldwin@hotmail.com",
            "tfawcett@goldenrodcompanies.com",
            "tfischer2117@gmail.com",
            "thebeginning2@gmail.com",
            "theikens043@gmail.com",
            "thomas.krebs16@gmail.com",
            "thomaspschur@gmail.com",
            "tim.miller1207@gmail.com",
            "titaearly@hotmail.com",
            "tj@titate.com",
            "tjstowell@gmail.com",
            "tlefkow@hotmail.com",
            "tlewiscpa@gmail.com",
            "tmcrauen@gmail.com",
            "tom.raney@jedunn.com",
            "travistelder@bresnan.net",
            "tschwans@hotmail.com",
            "tstangel77@gmail.com",
            "ttmiller9@gmail.com",
            "tyree022@yahoo.com",
            "undrpar66@gmail.com",
            "V238758@YAHOO.COM",
            "valeriepascoe@gmail.com",
            "villain714@yahoo.com",
            "vincent.barresi@gmail.com",
            "viscuglia@gmail.com",
            "vkcastillo@gmail.com",
            "vlcaughman1982@gmail.com",
            "vspahrewin@gmail.com",
            "w.t.taekwondoman@st-tel.net",
            "wanickles3@gmail.com",
            "wbrannagan@comcast.net",
            "wedmorei@msn.com",
            "wesherratt@gmail.com",
            "wgipsonfl40@gmail.com",
            "wgurgun1971@outlook.com",
            "whowould@aol.com",
            "williamprego10@yahoo.com",
            "wilson123314@bellsouth.net",
            "witchman@comcast.net",
            "woodruffej@gmail.com",
            "wooseybennett1@gmail.com",
            "wstorick@gmail.com",
            "wwstacy13@gmail.com",
            "wwwtbu@gmail.com",
            "zasha_zepeda@yahoo.com",
        ]
        for email in emails:
            _execute(conn, "INSERT INTO customer_emails (email) VALUES (?)", (email,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_customer_emails():
    """Get all customer emails"""
    conn = get_db()
    rows = _fetchall(conn, "SELECT * FROM customer_emails ORDER BY email")
    conn.close()
    return rows


def get_customer_email_count():
    """Get customer email count"""
    conn = get_db()
    result = _fetchone(conn, "SELECT COUNT(*) as cnt FROM customer_emails")
    conn.close()
    return result["cnt"] if result else 0


# ============================================================
# EMAIL CAMPAIGNS
# ============================================================

def create_email_campaign(subject, body, from_name='Forbidden Bourbon', from_email='', recipient_count=0):
    """Create a new email campaign"""
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO email_campaigns (subject, body, from_name, from_email, recipient_count) VALUES (%s, %s, %s, %s, %s) RETURNING id',
                (subject, body, from_name, from_email, recipient_count)
            )
            campaign_id = cur.fetchone()[0]
        else:
            cur = conn.execute(
                'INSERT INTO email_campaigns (subject, body, from_name, from_email, recipient_count) VALUES (?, ?, ?, ?, ?)',
                (subject, body, from_name, from_email, recipient_count)
            )
            campaign_id = cur.lastrowid
        conn.commit()
        return campaign_id
    except Exception as e:
        print(f"Error creating campaign: {e}")
        return None
    finally:
        conn.close()


def update_email_campaign(campaign_id, **kwargs):
    """Update email campaign fields"""
    conn = get_db()
    try:
        for key, val in kwargs.items():
            ph = '%s' if USE_POSTGRES else '?'
            _execute(conn, f'UPDATE email_campaigns SET {key} = {ph} WHERE id = {ph}', (val, campaign_id))
        conn.commit()
    except Exception as e:
        print(f"Error updating campaign: {e}")
    finally:
        conn.close()


def get_email_campaigns(limit=20):
    """Get recent email campaigns"""
    conn = get_db()
    rows = _fetchall(conn, 'SELECT * FROM email_campaigns ORDER BY created_at DESC LIMIT ' + str(limit))
    conn.close()
    return rows


def get_email_campaign(campaign_id):
    """Get a single campaign"""
    conn = get_db()
    ph = '%s' if USE_POSTGRES else '?'
    row = _fetchone(conn, f'SELECT * FROM email_campaigns WHERE id = {ph}', (campaign_id,))
    conn.close()
    return row


# ============================================================
# NOTIFICATIONS
# ============================================================

def create_notification(type, title, message='', link=''):
    """Create a notification"""
    conn = get_db()
    try:
        if USE_POSTGRES:
            conn.cursor().execute(
                'INSERT INTO notifications (type, title, message, link) VALUES (%s, %s, %s, %s)',
                (type, title, message, link)
            )
        else:
            conn.execute(
                'INSERT INTO notifications (type, title, message, link) VALUES (?, ?, ?, ?)',
                (type, title, message, link)
            )
        conn.commit()
    except Exception as e:
        print(f"Notification error: {e}")
    finally:
        conn.close()


def get_notifications(limit=20, unread_only=False):
    """Get recent notifications"""
    conn = get_db()
    try:
        if unread_only:
            rows = _fetchall(conn, 'SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC LIMIT ' + str(limit))
        else:
            rows = _fetchall(conn, 'SELECT * FROM notifications ORDER BY created_at DESC LIMIT ' + str(limit))
        return rows
    except Exception as e:
        print(f"[Notifications] get_notifications error: {e}")
        return []
    finally:
        conn.close()


def get_unread_notification_count():
    """Get count of unread notifications"""
    conn = get_db()
    result = _fetchone(conn, 'SELECT COUNT(*) as cnt FROM notifications WHERE read = 0')
    conn.close()
    return result['cnt'] if result else 0


def mark_notifications_read():
    """Mark all notifications as read"""
    conn = get_db()
    _execute(conn, 'UPDATE notifications SET read = 1 WHERE read = 0')
    conn.commit()
    conn.close()


def mark_notification_read(notif_id):
    """Mark a single notification as read"""
    conn = get_db()
    ph = '%s' if USE_POSTGRES else '?'
    _execute(conn, f'UPDATE notifications SET read = 1 WHERE id = {ph}', (notif_id,))
    conn.commit()
    conn.close()


# ============================================================
# OAUTH TOKENS
# ============================================================

def save_oauth_token(service, access_token='', refresh_token='', expires_at=None):
    """Save or update an OAuth token for a service"""
    conn = get_db()
    try:
        ph = '%s' if USE_POSTGRES else '?'
        # Try update first
        existing = _fetchone(conn, f'SELECT id FROM oauth_tokens WHERE service = {ph}', (service,))
        if existing:
            parts = []
            params = []
            if access_token:
                parts.append(f'access_token = {ph}')
                params.append(access_token)
            if refresh_token:
                parts.append(f'refresh_token = {ph}')
                params.append(refresh_token)
            if expires_at:
                parts.append(f'expires_at = {ph}')
                params.append(expires_at)
            parts.append(f'updated_at = CURRENT_TIMESTAMP')
            params.append(service)
            _execute(conn, f'UPDATE oauth_tokens SET {", ".join(parts)} WHERE service = {ph}', tuple(params))
        else:
            _execute(conn, f'INSERT INTO oauth_tokens (service, access_token, refresh_token, expires_at) VALUES ({ph}, {ph}, {ph}, {ph})',
                (service, access_token, refresh_token, expires_at))
        conn.commit()
    except Exception as e:
        print(f"[OAuth] save_token error: {e}")
    finally:
        conn.close()


def get_oauth_token(service):
    """Get stored OAuth token for a service"""
    conn = get_db()
    ph = '%s' if USE_POSTGRES else '?'
    result = _fetchone(conn, f'SELECT * FROM oauth_tokens WHERE service = {ph}', (service,))
    conn.close()
    return result