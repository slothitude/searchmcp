# SearchMCP — Agent-First Search and Web Reading MCP Server

## What It Does

Clean markdown extraction from the web, purpose-built for LLM agents.
Three-tier extraction: trafilatura (fast, ~50ms) → precision retry → crawl4ai browser fallback (slow, ~3s) → BeautifulSoup last resort.
Search via SearXNG with quality scoring and smart dedup.
aiosqlite-backed cache survives restarts. Per-domain rate limiting.

## Architecture

```
searchmcp.py          FastMCP server, 10 tools
config.py             Env vars, domain authority dict
extract/              Extraction pipeline
  tier1.py            trafilatura (broad + precision)
  tier3.py            crawl4ai browser fallback + BeautifulSoup
  postprocess.py      Markdown cleanup, metadata injection
  quality.py          Article body detection, JS-heavy detection
  summarize.py        Extractive sentence scoring (no LLM)
search/               Search pipeline
  searxng.py          SearXNG client, query classification, parallel fetch
  scoring.py          Domain authority + relevance scoring
  dedup.py            URL/title dedup (difflib)
  feeds.py            Sitemap/RSS/Atom parsing + autodiscovery
cache/
  store.py            aiosqlite WAL, count-based LRU, stampede protection
utils/
  urls.py             URL normalization, domain extraction
  rate_limit.py       Per-domain token bucket + robots.txt cache
  markdown.py         Truncation, metadata blocks, cleanup
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEARXNG_URL` | `http://192.168.0.33:8888` | SearXNG instance |
| `BROWSER_CDP_URL` | None (disabled) | Remote Chrome CDP for JS fallback |
| `SEARCHMCP_CACHE_DIR` | `~/.searchmcp` | Cache DB directory |
| `SEARCHMCP_RATE_LIMIT` | `2` | Requests/sec per domain |
| `SEARCHMCP_FETCH_CONCURRENCY` | `5` | Max parallel fetches |
| `SEARCHMCP_USER_AGENT` | Chrome UA | HTTP User-Agent |

## MCP Registration

```json
{
  "searchmcp": {
    "type": "stdio",
    "command": "C:\\Python313\\python.exe",
    "args": ["C:\\Users\\aaron\\searchmcp\\searchmcp.py"],
    "cwd": "C:\\Users\\aaron\\searchmcp",
    "env": {
      "SEARXNG_URL": "http://192.168.0.33:8888",
      "BROWSER_CDP_URL": "http://100.119.172.102:9222",
      "SEARCHMCP_CACHE_DIR": "C:\\Users\\aaron\\.searchmcp",
      "SEARCHMCP_RATE_LIMIT": "2",
      "SEARCHMCP_FETCH_CONCURRENCY": "5"
    }
  }
}
```

## Tools (10)

- `search` — SearXNG search, ranked + deduped
- `search_and_read` — One-shot search + extract top N concurrently
- `read_url` — Extract single URL with tiered pipeline
- `read_urls` — Batch read multiple URLs in parallel
- `read_sitemap` — Sitemap/RSS/Atom discovery with autodiscovery
- `extract` — CSS selector field extraction
- `summarize_content` — Extractive key sentences (no LLM)
- `cache_status` — Cache statistics
- `clear_cache` — Clear entries

## Error Handling

Every tool returns structured metadata even on failure:
```
<!-- meta
status: error
error_type: fetch_error | http_error | extraction_error | timeout_error | robots_blocked
url: "..."
-->
```

## Limitations

- **No LLM calls** — pure search/extraction, agents bring their own intelligence
- **Stampede protection** is in-process only — multi-worker deployments need external lock
- **crawl4ai** requires a remote Chrome CDP instance — disabled by default
- **Cache** is local SQLite — not shared across MCP server instances
- **PDF** URLs return extraction_error — no PDF parsing

## Verification

```bash
# Smoke test cache
C:/Python313/python.exe -c "
import asyncio
from cache.store import init, put, get, close
async def test():
    await init()
    await put('test://key', 'http://test.com', 'content', 'extracted')
    r = await get('test://key')
    assert r and r['content'] == 'content', f'Got: {r}'
    await clear_cache()
    r2 = await get('test://key')
    assert r2 is None
    await close()
    print('Cache OK')
asyncio.run(test())
"
```
