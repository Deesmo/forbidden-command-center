"""
GA4 (Google Analytics 4) integration for Forbidden Command Center.
Provides website traffic and engagement data from Google Analytics.
"""
import os
import json


def is_configured():
    """Check if GA4 credentials are available"""
    property_id = os.environ.get('GA4_PROPERTY_ID', '')
    credentials_json = os.environ.get('GA4_CREDENTIALS_JSON', '')
    return bool(property_id and credentials_json)


def _get_client():
    """Create GA4 client from environment credentials"""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account
        
        credentials_json = os.environ.get('GA4_CREDENTIALS_JSON', '')
        if not credentials_json:
            return None
        
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/analytics.readonly']
        )
        return BetaAnalyticsDataClient(credentials=credentials)
    except Exception as e:
        print(f"[GA4] Client creation error: {e}")
        return None


def get_all_data(days=30):
    """Get comprehensive GA4 data for the dashboard"""
    if not is_configured():
        return {'configured': False, 'error': 'GA4 not configured'}
    
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric
        )
        
        client = _get_client()
        if not client:
            return {'configured': True, 'error': 'Could not create GA4 client'}
        
        property_id = os.environ.get('GA4_PROPERTY_ID', '')
        
        # Main metrics request
        request = RunReportRequest(
            property=f'properties/{property_id}',
            date_ranges=[DateRange(start_date=f'{days}daysAgo', end_date='today')],
            metrics=[
                Metric(name='sessions'),
                Metric(name='totalUsers'),
                Metric(name='screenPageViews'),
                Metric(name='averageSessionDuration'),
                Metric(name='bounceRate'),
            ]
        )
        
        response = client.run_report(request)
        
        data = {
            'configured': True,
            'days': days,
            'sessions': 0,
            'users': 0,
            'pageviews': 0,
            'avg_duration': 0,
            'bounce_rate': 0,
        }
        
        if response.rows:
            row = response.rows[0]
            data['sessions'] = int(row.metric_values[0].value or 0)
            data['users'] = int(row.metric_values[1].value or 0)
            data['pageviews'] = int(row.metric_values[2].value or 0)
            data['avg_duration'] = round(float(row.metric_values[3].value or 0), 1)
            data['bounce_rate'] = round(float(row.metric_values[4].value or 0) * 100, 1)
        
        # Top pages
        try:
            pages_request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(start_date=f'{days}daysAgo', end_date='today')],
                dimensions=[Dimension(name='pagePath')],
                metrics=[Metric(name='screenPageViews')],
                limit=10
            )
            pages_response = client.run_report(pages_request)
            data['top_pages'] = [
                {'path': row.dimension_values[0].value, 'views': int(row.metric_values[0].value)}
                for row in pages_response.rows
            ]
        except:
            data['top_pages'] = []
        
        # Traffic sources
        try:
            sources_request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(start_date=f'{days}daysAgo', end_date='today')],
                dimensions=[Dimension(name='sessionSource')],
                metrics=[Metric(name='sessions')],
                limit=10
            )
            sources_response = client.run_report(sources_request)
            data['traffic_sources'] = [
                {'source': row.dimension_values[0].value, 'sessions': int(row.metric_values[0].value)}
                for row in sources_response.rows
            ]
        except:
            data['traffic_sources'] = []
        
        return data
        
    except Exception as e:
        return {'configured': True, 'error': str(e)}


def get_realtime():
    """Get real-time active users"""
    if not is_configured():
        return {'configured': False}
    
    try:
        from google.analytics.data_v1beta.types import (
            RunRealtimeReportRequest, Metric
        )
        
        client = _get_client()
        if not client:
            return {'configured': True, 'error': 'Could not create client'}
        
        property_id = os.environ.get('GA4_PROPERTY_ID', '')
        
        request = RunRealtimeReportRequest(
            property=f'properties/{property_id}',
            metrics=[Metric(name='activeUsers')]
        )
        
        response = client.run_realtime_report(request)
        active = int(response.rows[0].metric_values[0].value) if response.rows else 0
        
        return {'configured': True, 'active_users': active}
    except Exception as e:
        return {'configured': True, 'error': str(e), 'active_users': 0}
