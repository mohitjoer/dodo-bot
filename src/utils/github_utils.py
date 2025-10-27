import logging
from datetime import datetime
from urllib.parse import urlparse
import asyncio

logger = logging.getLogger(__name__)

def extract_github_username(text: str) -> str:
    if text.startswith("http"):
        path = urlparse(text).path.strip("/")
        return path.split("/")[0] if path else text
    return text.strip()


def extract_github_repo(text: str):
    if text.startswith("http"):
        path = urlparse(text).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    elif "/" in text:
        parts = text.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None


def format_date(date_string: str) -> str:
    if not date_string:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return "N/A"


def format_number(num: int) -> str:
    try:
        if num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        return str(num)
    except Exception:
        return str(num)


async def github_request(bot, url: str):
    """Perform a GitHub API GET using bot.session and bot.github_headers.

    Returns parsed JSON, 'not_found', 'rate_limited', or None on error.
    """
    if not bot or not getattr(bot, 'session', None) or bot.session.closed:
        logger.error("Session not available for GitHub request")
        return None

    try:
        current_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else None
        # Use time.time() fallback
        import time
        now = time.time()
        time_since_last_call = now - getattr(bot, 'last_api_call', 0)
        delay = getattr(bot, 'api_call_delay', 1.0)
        if time_since_last_call < delay:
            await asyncio.sleep(delay - time_since_last_call)

        bot.last_api_call = time.time()

        async with bot.session.get(url, headers=bot.github_headers) as response:
            if response.status == 403:
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
                if rate_limit_remaining == '0':
                    reset_time = response.headers.get('X-RateLimit-Reset', '0')
                    logger.warning(f"GitHub API rate limit exceeded. Resets at: {reset_time}")
                    return "rate_limited"

            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return "not_found"
            else:
                logger.error(f"GitHub API returned status {response.status} for {url}")
                return None

    except asyncio.TimeoutError:
        logger.error(f"Timeout error for GitHub request: {url}")
        return None
    except Exception as e:
        logger.error(f"GitHub API Error: {e}")
        return None
