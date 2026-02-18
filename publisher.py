"""
Social media publisher for Forbidden Command Center.
Handles posting content to various social media platforms.
"""
import os
import json
import requests


class PublishResult:
    """Result from a publish attempt"""
    def __init__(self, success=False, platform='', post_id='', url='', error=''):
        self.success = success
        self.platform = platform
        self.post_id = post_id
        self.url = url
        self.error = error
    
    def to_dict(self):
        return {
            'success': self.success,
            'platform': self.platform,
            'post_id': self.post_id,
            'url': self.url,
            'error': self.error
        }


class BlueskyPublisher:
    """Bluesky (AT Protocol) publisher"""
    
    @staticmethod
    def authenticate(handle, app_password):
        """Authenticate with Bluesky and return session info"""
        try:
            resp = requests.post(
                'https://bsky.social/xrpc/com.atproto.server.createSession',
                json={'identifier': handle, 'password': app_password},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'success': True,
                    'handle': data.get('handle', handle),
                    'did': data.get('did', ''),
                    'access_jwt': data.get('accessJwt', ''),
                }
            else:
                error = resp.json().get('message', resp.text[:200]) if resp.text else 'Auth failed'
                return {'success': False, 'error': f'Bluesky auth failed: {error}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def publish(content, image_path=None, config=None):
        """Publish a post to Bluesky"""
        config = config or {}
        handle = config.get('username', '')
        app_password = config.get('api_key', '')
        
        if not handle or not app_password:
            return PublishResult(success=False, platform='bluesky', error='Bluesky handle and app password required')
        
        auth = BlueskyPublisher.authenticate(handle, app_password)
        if not auth['success']:
            return PublishResult(success=False, platform='bluesky', error=auth['error'])
        
        try:
            from datetime import datetime, timezone
            
            # Create post record
            post_data = {
                '$type': 'app.bsky.feed.post',
                'text': content[:300],  # Bluesky limit
                'createdAt': datetime.now(timezone.utc).isoformat(),
            }
            
            # Upload image if provided
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as f:
                        img_resp = requests.post(
                            'https://bsky.social/xrpc/com.atproto.repo.uploadBlob',
                            headers={
                                'Authorization': f'Bearer {auth["access_jwt"]}',
                                'Content-Type': 'image/jpeg'
                            },
                            data=f.read(),
                            timeout=30
                        )
                    if img_resp.status_code == 200:
                        blob = img_resp.json().get('blob', {})
                        post_data['embed'] = {
                            '$type': 'app.bsky.embed.images',
                            'images': [{'alt': 'Forbidden Bourbon', 'image': blob}]
                        }
                except Exception as img_err:
                    print(f"[Publisher] Bluesky image upload error: {img_err}")
            
            resp = requests.post(
                'https://bsky.social/xrpc/com.atproto.repo.createRecord',
                headers={'Authorization': f'Bearer {auth["access_jwt"]}'},
                json={
                    'repo': auth['did'],
                    'collection': 'app.bsky.feed.post',
                    'record': post_data
                },
                timeout=15
            )
            
            if resp.status_code == 200:
                uri = resp.json().get('uri', '')
                # Convert AT URI to web URL
                rkey = uri.split('/')[-1] if uri else ''
                web_url = f'https://bsky.app/profile/{handle}/post/{rkey}' if rkey else ''
                return PublishResult(success=True, platform='bluesky', post_id=uri, url=web_url)
            else:
                return PublishResult(success=False, platform='bluesky', error=f'Post failed: {resp.text[:200]}')
                
        except Exception as e:
            return PublishResult(success=False, platform='bluesky', error=str(e))


class TwitterPublisher:
    """Twitter/X publisher (placeholder — requires OAuth 2.0)"""
    
    @staticmethod
    def publish(content, image_path=None, config=None):
        return PublishResult(success=False, platform='twitter', 
                           error='Twitter publishing requires OAuth setup. Set TWITTER_API_KEY in Render env vars.')


class FacebookPublisher:
    """Facebook publisher"""
    
    @staticmethod
    def publish(content, image_path=None, config=None):
        config = config or {}
        page_token = config.get('api_key', os.environ.get('FACEBOOK_PAGE_TOKEN', ''))
        page_id = config.get('page_id', os.environ.get('FACEBOOK_PAGE_ID', 'me'))
        
        if not page_token:
            return PublishResult(success=False, platform='facebook', error='Facebook page token required')
        
        try:
            resp = requests.post(
                f'https://graph.facebook.com/v19.0/{page_id}/feed',
                data={'message': content, 'access_token': page_token},
                timeout=15
            )
            if resp.status_code == 200:
                post_id = resp.json().get('id', '')
                return PublishResult(success=True, platform='facebook', post_id=post_id, 
                                   url=f'https://facebook.com/{post_id}')
            else:
                return PublishResult(success=False, platform='facebook', error=resp.text[:200])
        except Exception as e:
            return PublishResult(success=False, platform='facebook', error=str(e))


class LinkedInPublisher:
    """LinkedIn publisher (placeholder)"""
    
    @staticmethod
    def publish(content, image_path=None, config=None):
        return PublishResult(success=False, platform='linkedin',
                           error='LinkedIn publishing requires OAuth setup. Set LINKEDIN_ACCESS_TOKEN in Render env vars.')


class InstagramPublisher:
    """Instagram publisher (placeholder — requires Business API)"""
    
    @staticmethod
    def publish(content, image_path=None, config=None):
        return PublishResult(success=False, platform='instagram',
                           error='Instagram publishing requires Business API setup.')


# Platform dispatcher
PUBLISHERS = {
    'bluesky': BlueskyPublisher,
    'twitter': TwitterPublisher,
    'facebook': FacebookPublisher,
    'linkedin': LinkedInPublisher,
    'instagram': InstagramPublisher,
}


def publish_to_platform(platform_name, content, image_path=None, config=None):
    """
    Publish content to a specific platform.
    
    Args:
        platform_name: Name of the platform (bluesky, twitter, facebook, etc.)
        content: Text content to publish
        image_path: Optional path to image file
        config: Dict with platform-specific config (api_key, username, etc.)
    
    Returns:
        PublishResult object
    """
    publisher_class = PUBLISHERS.get(platform_name)
    
    if not publisher_class:
        return PublishResult(
            success=False, 
            platform=platform_name,
            error=f'Unknown platform: {platform_name}. Supported: {", ".join(PUBLISHERS.keys())}'
        )
    
    try:
        return publisher_class.publish(content, image_path, config)
    except Exception as e:
        return PublishResult(success=False, platform=platform_name, error=f'Publisher error: {str(e)}')
