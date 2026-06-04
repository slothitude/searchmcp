# SearchMCP

Agent-optimized search and web reading MCP server. Returns clean markdown with metadata — purpose-built for LLM consumption.

## Features

- **Three-tier extraction**: trafilatura (fast, ~50ms) → precision retry → crawl4ai browser fallback → BeautifulSoup last resort
- **Parallel VPN fan-out**: queries 3 SearXNG backends (NL/US/SG) simultaneously via `asyncio.gather`, merges and deduplicates results
- **Quality scoring**: domain authority + relevance ranking
- **aiosqlite cache**: survives restarts, count-based LRU with stampede protection
- **Per-domain rate limiting**: token bucket + robots.txt cache
- **10 MCP tools**: search, read, batch read, sitemap/RSS, extract fields, summarize, cache management

## Architecture

```
searchmcp.py              FastMCP server entry point
config.py                 Env vars, domain authority, TTLs
extract/
  tier1.py               trafilatura (broad + precision)
  tier3.py               crawl4ai browser fallback + BeautifulSoup
  postprocess.py         Markdown cleanup, metadata injection
  quality.py             Article body detection, JS-heavy detection
  summarize.py           Extractive key sentences (no LLM)
search/
  searxng.py             Parallel fan-out to multiple SearXNG backends
  scoring.py             Domain authority + relevance scoring
  dedup.py               URL/title dedup
  feeds.py               Sitemap/RSS/Atom parsing + autodiscovery
cache/
  store.py               aiosqlite WAL, count-based LRU
utils/
  urls.py                URL normalization, domain extraction
  rate_limit.py           Per-domain token bucket
  markdown.py             Truncation, metadata blocks
```

## Installation

```bash
pip install fastmcp httpx aiohttp aiosqlite trafilatura beautifulsoup4 crawl4ai
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEARXNG_URLS` | `nl=..8899,us=..8898,sg=..8897` | Location-keyed SearXNG backends |
| `SEARXNG_URL` | First URL from `SEARXNG_URLS` | Backward-compat single backend |
| `BROWSER_CDP_URL` | None (disabled) | Remote Chrome CDP for JS fallback |
| `SEARCHMCP_CACHE_DIR` | `~/.searchmcp` | Cache DB directory |
| `SEARCHMCP_RATE_LIMIT` | `2` | Requests/sec per domain |
| `SEARCHMCP_FETCH_CONCURRENCY` | `5` | Max parallel fetches |

### MCP Registration

```json
{
  "searchmcp": {
    "type": "stdio",
    "command": "python",
    "args": ["searchmcp.py"],
    "cwd": "/path/to/searchmcp",
    "env": {
      "SEARXNG_URLS": "nl=http://host:8899,us=http://host:8898,sg=http://host:8897"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `search` | SearXNG search, ranked + deduped. `location` param: `"all"` (fan-out) or `"nl"`/`"us"`/`"sg"` |
| `search_and_read` | One-shot search + extract top N concurrently |
| `read_url` | Extract single URL with tiered pipeline |
| `read_urls` | Batch read multiple URLs in parallel |
| `read_sitemap` | Sitemap/RSS/Atom discovery with autodiscovery |
| `extract` | CSS selector field extraction from URL |
| `summarize_content` | Extractive key sentences (no LLM) |
| `cache_status` | Cache statistics |
| `clear_cache` | Clear entries |

## VPN Stack (Optional)

SearchMCP works best behind VPN-backed SearXNG instances to avoid rate limits and geoblocking. The recommended setup uses 3 Gluetun containers routing through PureVPN:

```
searchmcp → parallel fan-out:
  ├── searxng-nl (port 8899) via gluetun-nl (Netherlands)
  ├── searxng-us (port 8898) via gluetun-us (United States)
  └── searxng-sg (port 8897) via gluetun-sg (Singapore)
```

## License

MIT
