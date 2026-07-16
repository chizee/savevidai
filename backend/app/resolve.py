from fastapi import APIRouter, Request

from .cache import TTLCache
from .errors import INVALID_URL, app_error
from .extractor import extract
from .limits import limiter
from .schemas import ResolveRequest, ResolveResponse
from .sizes import fill_sizes
from .urls import InvalidTweetURL, parse_tweet_url

router = APIRouter()
cache = TTLCache(maxsize=512, ttl=3600.0)


@router.post("/api/resolve", response_model=ResolveResponse)
@limiter.limit("10/minute")
def resolve(request: Request, payload: ResolveRequest) -> ResolveResponse:
    try:
        tweet_id = parse_tweet_url(payload.url)
    except InvalidTweetURL as exc:
        raise app_error(INVALID_URL) from exc
    cached = cache.get(tweet_id)
    if cached is not None:
        return cached
    result = extract(tweet_id)
    fill_sizes(result)
    cache.set(tweet_id, result)
    return result
