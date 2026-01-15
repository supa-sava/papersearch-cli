#!/usr/bin/env python3
"""
📚 Paper Search - Unified Academic Paper Search Tool

A beautiful CLI for searching academic papers across OpenAlex and Web of Science.
Supports keyword search, citation chains, and powerful filtering.

Robust against: empty inputs, cancellations, network errors, invalid data.
"""

import requests
import csv
import time
import html
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Rich imports for beautiful UI
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.text import Text

# Questionary for interactive prompts
import questionary
from questionary import Style as QStyle

console = Console()

# Custom questionary style
custom_style = QStyle([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:cyan'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
    ('separator', 'fg:gray'),
    ('instruction', 'fg:gray italic'),
    ('text', 'fg:white'),
])


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Global configuration."""
    WOS_API_KEY = os.getenv("WOS_API_KEY", "")
    USE_WOS = bool(WOS_API_KEY and WOS_API_KEY != "your_api_key_here")
    MAX_RESULTS = 1000
    OUTPUT_DIR = "outputs"
    REQUEST_TIMEOUT = 30
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2


# ============================================================================
# SAFE PROMPT WRAPPERS
# ============================================================================

def safe_ask(prompt_func, *args, **kwargs):
    """Wrapper to handle cancelled/None prompts gracefully."""
    try:
        result = prompt_func(*args, **kwargs)
        return result
    except (KeyboardInterrupt, EOFError):
        return None


def safe_text(message: str, default: str = "", **kwargs) -> str:
    """Safe text prompt that returns empty string on cancel."""
    result = safe_ask(questionary.text, message, default=default, style=custom_style, **kwargs)
    return result.strip() if result else ""


def safe_select(message: str, choices: list, **kwargs):
    """Safe select prompt that returns None on cancel."""
    return safe_ask(questionary.select, message, choices=choices, style=custom_style, **kwargs)


def safe_checkbox(message: str, choices: list, **kwargs) -> list:
    """Safe checkbox prompt that returns empty list on cancel."""
    result = safe_ask(questionary.checkbox, message, choices=choices, style=custom_style, **kwargs)
    return result if result else []


def safe_confirm(message: str, default: bool = True, **kwargs) -> bool:
    """Safe confirm prompt that returns default on cancel."""
    result = safe_ask(questionary.confirm, message, default=default, style=custom_style, **kwargs)
    return result if result is not None else default


# ============================================================================
# INPUT VALIDATION
# ============================================================================

def validate_year_range(year_str: str) -> tuple:
    """
    Validate and parse year range. Returns (start, end) or (None, None) if invalid.
    Accepts: "2020", "2020-2024", "2020-", "-2024"
    """
    if not year_str or not year_str.strip():
        return None, None
    
    year_str = year_str.strip()
    current_year = datetime.now().year
    
    # Single year
    if year_str.isdigit() and len(year_str) == 4:
        year = int(year_str)
        if 1900 <= year <= current_year + 1:
            return year, year
        return None, None
    
    # Range format
    if "-" in year_str:
        parts = year_str.split("-")
        if len(parts) == 2:
            start_str, end_str = parts
            
            # Parse start year
            if start_str.strip():
                if start_str.strip().isdigit():
                    start = int(start_str.strip())
                else:
                    return None, None
            else:
                start = 1900
            
            # Parse end year
            if end_str.strip():
                if end_str.strip().isdigit():
                    end = int(end_str.strip())
                else:
                    return None, None
            else:
                end = current_year
            
            if 1900 <= start <= end <= current_year + 1:
                return start, end
    
    return None, None


def sanitize_keywords(keywords: str) -> str:
    """Clean and validate keywords for API search."""
    if not keywords:
        return ""
    
    # Remove problematic characters but keep quotes and operators
    keywords = keywords.strip()
    
    # Collapse multiple spaces
    keywords = re.sub(r'\s+', ' ', keywords)
    
    return keywords


# ============================================================================
# API HELPERS
# ============================================================================

def extract_doi(doi: str) -> str:
    """Extract clean DOI from various formats."""
    if not doi:
        return ""
    doi = str(doi).strip().lower()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi:", "doi.org/"]:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    if not title:
        return ""
    try:
        title = html.unescape(str(title)).lower().strip()
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title
    except Exception:
        return ""


def make_request(url: str, params: dict = None, headers: dict = None, 
                 retries: int = Config.RETRY_ATTEMPTS) -> dict:
    """Make HTTP request with retry logic."""
    for attempt in range(retries):
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=headers, 
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 429:  # Rate limited
                wait_time = Config.RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)
                continue
            
            if response.status_code >= 500:  # Server error
                time.sleep(Config.RETRY_DELAY)
                continue
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(Config.RETRY_DELAY)
                continue
        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                time.sleep(Config.RETRY_DELAY)
                continue
        except Exception:
            pass
    
    return {}


def resolve_entity(entity_type: str, query: str) -> dict:
    """Resolve author, institution, source, or work to OpenAlex ID."""
    if not query or not query.strip():
        return {}
    
    query = query.strip()
    
    endpoints = {
        "author": "authors",
        "institution": "institutions", 
        "source": "sources",
        "work": "works"
    }
    
    endpoint = endpoints.get(entity_type, "works")
    
    # Check if already an OpenAlex ID
    if re.match(r'^[AWIS]\d+$', query, re.I):
        url = f"https://api.openalex.org/{endpoint}/{query.upper()}"
    # DOI
    elif query.startswith("10.") or "doi.org" in query.lower():
        doi = extract_doi(query)
        url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    # ORCID
    elif "orcid.org" in query.lower() or re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$', query):
        orcid = query if "orcid.org" in query.lower() else f"https://orcid.org/{query}"
        url = f"https://api.openalex.org/authors/{orcid}"
    # ROR
    elif "ror.org" in query.lower():
        url = f"https://api.openalex.org/institutions/{query}"
    # ISSN
    elif re.match(r'^\d{4}-\d{3}[\dX]$', query):
        url = f"https://api.openalex.org/sources/issn:{query}"
    # Search by name
    else:
        url = f"https://api.openalex.org/{endpoint}?search={query}&per-page=1"
    
    data = make_request(url)
    
    if not data:
        return {}
    
    # Handle search results vs direct lookup
    if "results" in data:
        if not data["results"]:
            return {}
        entity = data["results"][0]
    else:
        entity = data
    
    return {
        "id": entity.get("id", "").split("/")[-1] if entity.get("id") else "",
        "display_name": entity.get("display_name") or entity.get("title", "Unknown"),
        "full_data": entity
    }


# ============================================================================
# OPENALEX SEARCH
# ============================================================================

def build_openalex_filter(filters: dict) -> str:
    """Build OpenAlex filter string from filter dict."""
    parts = []
    
    if filters.get("cites"):
        parts.append(f"cites:{filters['cites']}")
    
    if filters.get("keywords"):
        keywords = sanitize_keywords(filters["keywords"])
        if keywords:
            parts.append(f"abstract.search:{keywords}")
    
    if filters.get("institution"):
        parts.append(f"authorships.institutions.id:{filters['institution']}")
    
    if filters.get("author"):
        parts.append(f"authorships.author.id:{filters['author']}")
    
    if filters.get("source"):
        parts.append(f"primary_location.source.id:{filters['source']}")
    
    if filters.get("year_start") and filters.get("year_end"):
        if filters["year_start"] == filters["year_end"]:
            parts.append(f"publication_year:{filters['year_start']}")
        else:
            parts.append(f"publication_year:{filters['year_start']}-{filters['year_end']}")
    
    if filters.get("min_citations"):
        parts.append(f"cited_by_count:>{filters['min_citations']}")
    
    if filters.get("oa_only"):
        parts.append("is_oa:true")
    
    if filters.get("type"):
        parts.append(f"type:{filters['type']}")
    
    return ",".join(parts) if parts else ""


def fetch_openalex(filters: dict, max_results: int, progress_callback=None) -> list:
    """Fetch papers from OpenAlex with given filters."""
    base_url = "https://api.openalex.org/works"
    cursor = "*"
    results = []
    per_page = 200
    
    filter_str = build_openalex_filter(filters)
    
    # If no filters, we can't search - return empty
    if not filter_str:
        return []
    
    while len(results) < max_results:
        if progress_callback:
            progress_callback(len(results), max_results, "OpenAlex")
        
        params = {
            "filter": filter_str,
            "per-page": per_page,
            "cursor": cursor,
            "sort": "publication_date:desc"
        }
        
        data = make_request(base_url, params=params)
        
        if not data or "results" not in data:
            break
        
        for item in data.get("results", []):
            # Extract abstract safely
            abstract = ""
            abstract_index = item.get("abstract_inverted_index")
            if abstract_index and isinstance(abstract_index, dict):
                try:
                    abstract_words = sorted(
                        [(word, pos) for word, positions in abstract_index.items() 
                         for pos in (positions if isinstance(positions, list) else [])],
                        key=lambda x: x[1]
                    )
                    abstract = " ".join(word for word, _ in abstract_words)
                except Exception:
                    abstract = ""
            
            doi = extract_doi(item.get("doi", "") or "")
            location = item.get("primary_location") or {}
            
            results.append({
                "title": item.get("title", "") or "",
                "abstract": abstract,
                "publication_date": item.get("publication_date", "") or "",
                "url": location.get("landing_page_url", "") or location.get("pdf_url", "") or "",
                "doi": doi,
                "cited_by_count": item.get("cited_by_count", 0) or 0,
                "openalex_id": (item.get("id", "") or "").split("/")[-1],
                "source": "openalex"
            })
            
            if len(results) >= max_results:
                break
        
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        
        time.sleep(0.5)  # Rate limiting
    
    return results


# ============================================================================
# WOS SEARCH
# ============================================================================

def build_wos_query(filters: dict) -> str:
    """Build WoS query string from filter dict."""
    parts = []
    
    if filters.get("keywords"):
        keywords = sanitize_keywords(filters["keywords"])
        if keywords:
            parts.append(f'TS=({keywords})')
    
    if filters.get("institution_name"):
        parts.append(f'OG="{filters["institution_name"]}"')
    
    if filters.get("author_name"):
        parts.append(f'AU="{filters["author_name"]}"')
    
    if filters.get("source_name"):
        parts.append(f'SO="{filters["source_name"]}"')
    
    if filters.get("year_start") and filters.get("year_end"):
        parts.append(f"PY={filters['year_start']}-{filters['year_end']}")
    
    return " AND ".join(parts) if parts else ""


def fetch_wos(filters: dict, max_results: int, progress_callback=None) -> list:
    """Fetch papers from WoS with given filters."""
    if not Config.USE_WOS:
        return []
    
    # WoS doesn't support citation queries
    if filters.get("cites"):
        return []
    
    api_key = Config.WOS_API_KEY
    base_url = "https://api.clarivate.com/apis/wos-starter/v1/documents"
    results = []
    limit = 50
    page = 1
    
    wos_query = build_wos_query(filters)
    if not wos_query:
        return []
    
    headers = {"X-ApiKey": api_key, "Accept": "application/json"}
    
    while len(results) < max_results:
        if progress_callback:
            progress_callback(len(results), max_results, "WoS")
        
        params = {
            "q": wos_query,
            "db": "WOS",
            "limit": limit,
            "page": page,
            "sortField": "PY+D"
        }
        
        data = make_request(base_url, params=params, headers=headers)
        
        if not data:
            break
        
        hits = data.get("hits", [])
        
        if not hits:
            break
        
        for doc in hits:
            identifiers = doc.get("identifiers") or {}
            doc_doi = extract_doi(identifiers.get("doi", "") or "")
            source = doc.get("source") or {}
            links = doc.get("links") or {}
            citations = doc.get("citations") or []
            cited_count = sum(c.get("count", 0) for c in citations) if citations else 0
            
            results.append({
                "title": doc.get("title", "") or "",
                "abstract": "",
                "publication_date": str(source.get("publishYear", "")) if source.get("publishYear") else "",
                "url": links.get("record", "") or "",
                "doi": doc_doi,
                "cited_by_count": cited_count,
                "openalex_id": "",
                "source": "wos"
            })
            
            if len(results) >= max_results:
                break
        
        metadata = data.get("metadata") or {}
        total = metadata.get("total", 0)
        if page * limit >= total:
            break
        
        page += 1
        time.sleep(0.3)
    
    return results


# ============================================================================
# FETCH REFERENCES (bibliography of a paper)
# ============================================================================

def fetch_references(paper_id: str, max_results: int = 200, progress_callback=None) -> list:
    """Get papers referenced BY a given work (its bibliography)."""
    if not paper_id:
        return []
    
    # First, get the paper details to find its references
    url = f"https://api.openalex.org/works/{paper_id}"
    data = make_request(url)
    
    if not data or "referenced_works" not in data:
        return []
    
    ref_urls = data.get("referenced_works", [])[:max_results]
    
    if not ref_urls:
        return []
    
    # Batch fetch reference details (max 50 per request)
    results = []
    batch_size = 50
    
    for i in range(0, len(ref_urls), batch_size):
        if progress_callback:
            progress_callback(len(results), len(ref_urls), "References")
        
        batch = ref_urls[i:i + batch_size]
        ref_ids = [r.split("/")[-1] for r in batch]
        filter_str = f"openalex_id:{('|'.join(ref_ids))}"
        
        batch_data = make_request(
            "https://api.openalex.org/works",
            params={"filter": filter_str, "per-page": batch_size}
        )
        
        if batch_data and "results" in batch_data:
            for item in batch_data["results"]:
                abstract = ""
                abstract_index = item.get("abstract_inverted_index")
                if abstract_index and isinstance(abstract_index, dict):
                    try:
                        abstract_words = sorted(
                            [(word, pos) for word, positions in abstract_index.items() 
                             for pos in (positions if isinstance(positions, list) else [])],
                            key=lambda x: x[1]
                        )
                        abstract = " ".join(word for word, _ in abstract_words)
                    except Exception:
                        pass
                
                location = item.get("primary_location") or {}
                
                results.append({
                    "title": item.get("title", "") or "",
                    "abstract": abstract,
                    "publication_date": item.get("publication_date", "") or "",
                    "url": location.get("landing_page_url", "") or "",
                    "doi": extract_doi(item.get("doi", "") or ""),
                    "cited_by_count": item.get("cited_by_count", 0) or 0,
                    "openalex_id": (item.get("id", "") or "").split("/")[-1],
                    "source": "openalex"
                })
        
        time.sleep(0.5)
    
    return results


# ============================================================================
# MERGE & DEDUPE
# ============================================================================

def merge_results(openalex_papers: list, wos_papers: list) -> tuple:
    """Merge and deduplicate papers from both sources."""
    if not wos_papers:
        return openalex_papers, [], []
    
    oa_by_doi = {}
    oa_by_title = {}
    
    for paper in openalex_papers:
        doi = paper.get("doi", "")
        if doi:
            oa_by_doi[doi] = paper
        title_key = normalize_title(paper.get("title", ""))
        if title_key:
            oa_by_title[title_key] = paper
    
    matched_oa_ids = set()
    merged = []
    wos_only = []
    
    for wos_paper in wos_papers:
        doi = wos_paper.get("doi", "")
        title_key = normalize_title(wos_paper.get("title", ""))
        
        oa_match = None
        if doi and doi in oa_by_doi:
            oa_match = oa_by_doi[doi]
        elif title_key and title_key in oa_by_title:
            oa_match = oa_by_title[title_key]
        
        if oa_match:
            merged_paper = {**oa_match, "source": "both"}
            merged_paper["cited_by_count"] = max(
                oa_match.get("cited_by_count", 0) or 0,
                wos_paper.get("cited_by_count", 0) or 0
            )
            merged.append(merged_paper)
            matched_oa_ids.add(id(oa_match))
        else:
            wos_only.append(wos_paper)
    
    oa_only = [p for p in openalex_papers if id(p) not in matched_oa_ids]
    
    return oa_only, wos_only, merged


def dedupe_list(papers: list) -> list:
    """Remove duplicates within a list."""
    seen_dois = set()
    seen_titles = set()
    unique = []
    
    for paper in papers:
        doi = paper.get("doi", "")
        title_key = normalize_title(paper.get("title", ""))
        
        if doi and doi in seen_dois:
            continue
        if title_key and title_key in seen_titles:
            continue
        
        if doi:
            seen_dois.add(doi)
        if title_key:
            seen_titles.add(title_key)
        unique.append(paper)
    
    return unique


# ============================================================================
# OUTPUT
# ============================================================================

def save_results(papers: list, output_dir: str, base_name: str) -> str:
    """Save papers to CSV and return the file path."""
    if not papers:
        return ""
    
    try:
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{base_name}.csv")
        
        fieldnames = ["title", "abstract", "publication_date", "url", "doi", 
                      "cited_by_count", "openalex_id", "source"]
        
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(papers)
        
        return filename
    except Exception as e:
        console.print(f"[red]Error saving results: {e}[/red]")
        return ""


# ============================================================================
# INTERACTIVE UI
# ============================================================================

def print_header():
    """Print the application header."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]📚 Paper Search[/bold cyan]\n"
        "[dim]Unified Academic Paper Search Tool[/dim]",
        border_style="cyan",
        padding=(0, 2)
    ))
    console.print()


def get_starting_point() -> dict:
    """Get the starting point for the search."""
    choices = [
        questionary.Choice("🔍 Keyword search (search by topic/abstract)", value="keywords"),
        questionary.Choice("📖 Papers citing a specific work", value="cites"),
        questionary.Choice("📑 References of a specific work (bibliography)", value="references"),
        questionary.Choice("👤 Works by a specific author", value="author"),
        questionary.Choice("🏛️  Works from an institution", value="institution"),
    ]
    
    start_type = safe_select("What do you want to search?", choices)
    
    if not start_type:
        return {}
    
    result = {"type": start_type}
    
    # Paper-based searches
    if start_type in ["cites", "references"]:
        if start_type == "cites":
            prompt = "Paper to find citations for (DOI, title, or ID):"
        else:
            prompt = "Paper to get references from (DOI, title, or ID):"
        
        paper = safe_text(prompt)
        if not paper:
            console.print("[yellow]  No paper specified, returning to start.[/yellow]")
            return {}
        
        with console.status("[cyan]Resolving paper...", spinner="dots"):
            resolved = resolve_entity("work", paper)
        
        if resolved and resolved.get("id"):
            console.print(f"  [green]✓[/green] Found: [cyan]{resolved['display_name'][:60]}...[/cyan]")
            result["paper_id"] = resolved["id"]
            result["paper_name"] = resolved["display_name"]
        else:
            console.print("  [red]✗[/red] Paper not found. Check your input.")
            return {}
    
    # Author search
    elif start_type == "author":
        author = safe_text("Author name or ORCID:")
        if not author:
            console.print("[yellow]  No author specified, returning to start.[/yellow]")
            return {}
        
        with console.status("[cyan]Resolving author...", spinner="dots"):
            resolved = resolve_entity("author", author)
        
        if resolved and resolved.get("id"):
            console.print(f"  [green]✓[/green] Found: [cyan]{resolved['display_name']}[/cyan]")
            result["author_id"] = resolved["id"]
            result["author_name"] = resolved["display_name"]
        else:
            console.print("  [red]✗[/red] Author not found. Check your input.")
            return {}
    
    # Institution search
    elif start_type == "institution":
        inst = safe_text("Institution name or ROR ID:")
        if not inst:
            console.print("[yellow]  No institution specified, returning to start.[/yellow]")
            return {}
        
        with console.status("[cyan]Resolving institution...", spinner="dots"):
            resolved = resolve_entity("institution", inst)
        
        if resolved and resolved.get("id"):
            console.print(f"  [green]✓[/green] Found: [cyan]{resolved['display_name']}[/cyan]")
            result["institution_id"] = resolved["id"]
            result["institution_name"] = resolved["display_name"]
        else:
            console.print("  [red]✗[/red] Institution not found. Check your input.")
            return {}
    
    return result


def get_filters(starting_point: dict) -> dict:
    """Get filters from user. All filters are optional."""
    filters = {}
    
    console.print()
    console.print("[dim]All filters are optional. Press Enter to skip any filter.[/dim]")
    console.print()
    
    # Keywords (always available)
    keywords = safe_text("Keywords (topic/abstract search, or leave empty):")
    if keywords:
        filters["keywords"] = keywords
    
    # Year range
    current_year = datetime.now().year
    year_input = safe_text(f"Year range (e.g., 2020-{current_year}, or leave empty for all years):")
    
    if year_input:
        start_year, end_year = validate_year_range(year_input)
        if start_year and end_year:
            filters["year_start"] = start_year
            filters["year_end"] = end_year
        else:
            console.print(f"  [yellow]Invalid year format. Using all years.[/yellow]")
    
    # Additional filters - show which ones are already set
    disabled_choices = []
    if starting_point.get("type") == "institution":
        disabled_choices.append("institution")
    if starting_point.get("type") == "author":
        disabled_choices.append("author")
    
    filter_choices = [
        questionary.Choice(
            "🏛️  Filter by institution", 
            value="institution",
            disabled="Already set as starting point" if "institution" in disabled_choices else None
        ),
        questionary.Choice(
            "📰 Filter by journal/source", 
            value="source"
        ),
        questionary.Choice(
            "👤 Filter by author", 
            value="author",
            disabled="Already set as starting point" if "author" in disabled_choices else None
        ),
        questionary.Choice(
            "📊 Minimum citation count", 
            value="min_citations"
        ),
        questionary.Choice(
            "🔓 Open access only", 
            value="oa_only"
        ),
    ]
    
    console.print()
    selected_filters = safe_checkbox("Additional filters (optional, space to select):", filter_choices)
    
    for filter_name in selected_filters:
        if filter_name == "institution":
            inst = safe_text("Institution name:")
            if inst:
                with console.status("[cyan]Resolving...", spinner="dots"):
                    resolved = resolve_entity("institution", inst)
                if resolved and resolved.get("id"):
                    filters["institution"] = resolved["id"]
                    filters["institution_name"] = resolved["display_name"]
                    console.print(f"  [green]✓[/green] {resolved['display_name']}")
        
        elif filter_name == "source":
            source = safe_text("Journal/source name or ISSN:")
            if source:
                with console.status("[cyan]Resolving...", spinner="dots"):
                    resolved = resolve_entity("source", source)
                if resolved and resolved.get("id"):
                    filters["source"] = resolved["id"]
                    filters["source_name"] = resolved["display_name"]
                    console.print(f"  [green]✓[/green] {resolved['display_name']}")
        
        elif filter_name == "author":
            author = safe_text("Author name or ORCID:")
            if author:
                with console.status("[cyan]Resolving...", spinner="dots"):
                    resolved = resolve_entity("author", author)
                if resolved and resolved.get("id"):
                    filters["author"] = resolved["id"]
                    filters["author_name"] = resolved["display_name"]
                    console.print(f"  [green]✓[/green] {resolved['display_name']}")
        
        elif filter_name == "min_citations":
            min_cites = safe_text("Minimum citation count:", default="10")
            if min_cites and min_cites.isdigit():
                filters["min_citations"] = int(min_cites)
        
        elif filter_name == "oa_only":
            filters["oa_only"] = True
    
    return filters


def validate_search(starting_point: dict, filters: dict) -> bool:
    """Check if the search has enough criteria to run."""
    # Must have at least one of: keywords, starting point with entity, or year range
    has_keywords = bool(filters.get("keywords"))
    has_entity_start = starting_point.get("type") in ["cites", "references", "author", "institution"]
    has_entity_filter = any(filters.get(f) for f in ["institution", "author", "source"])
    
    if has_keywords or has_entity_start or has_entity_filter:
        return True
    
    console.print()
    console.print("[yellow]⚠️  Please specify at least one search criterion:[/yellow]")
    console.print("[dim]   - Keywords, OR[/dim]")
    console.print("[dim]   - A specific paper/author/institution, OR[/dim]")
    console.print("[dim]   - A filter (institution, author, or source)[/dim]")
    return False


def run_search(starting_point: dict, filters: dict) -> tuple:
    """Execute the search and return results."""
    console.print()
    
    # Build the search filters
    search_filters = dict(filters)
    
    if starting_point.get("type") == "cites":
        search_filters["cites"] = starting_point["paper_id"]
    elif starting_point.get("type") == "author":
        search_filters["author"] = starting_point["author_id"]
        search_filters["author_name"] = starting_point.get("author_name", "")
    elif starting_point.get("type") == "institution":
        search_filters["institution"] = starting_point["institution_id"]
        search_filters["institution_name"] = starting_point.get("institution_name", "")
    
    openalex_papers = []
    wos_papers = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console
    ) as progress:
        
        # References mode (get bibliography)
        if starting_point.get("type") == "references":
            task = progress.add_task("[cyan]Fetching references...", total=100)
            
            def ref_progress(current, total, desc):
                pct = int((current / max(total, 1)) * 100)
                progress.update(task, completed=pct)
            
            openalex_papers = fetch_references(
                starting_point["paper_id"], 
                Config.MAX_RESULTS,
                ref_progress
            )
            progress.update(task, completed=100)
        
        # Standard search
        else:
            oa_task = progress.add_task("[cyan]Searching OpenAlex...", total=Config.MAX_RESULTS)
            
            def oa_progress(current, total, source):
                progress.update(oa_task, completed=min(current, Config.MAX_RESULTS))
            
            openalex_papers = fetch_openalex(search_filters, Config.MAX_RESULTS, oa_progress)
            progress.update(oa_task, completed=len(openalex_papers))
            
            # WoS search (if applicable)
            if Config.USE_WOS and not search_filters.get("cites"):
                wos_task = progress.add_task("[cyan]Searching Web of Science...", total=Config.MAX_RESULTS)
                
                def wos_progress(current, total, source):
                    progress.update(wos_task, completed=min(current, Config.MAX_RESULTS))
                
                wos_papers = fetch_wos(search_filters, Config.MAX_RESULTS, wos_progress)
                progress.update(wos_task, completed=len(wos_papers))
    
    # Dedupe each list
    openalex_papers = dedupe_list(openalex_papers)
    wos_papers = dedupe_list(wos_papers)
    
    # Merge
    oa_only, wos_only, merged = merge_results(openalex_papers, wos_papers)
    all_papers = oa_only + wos_only + merged
    
    return all_papers, len(openalex_papers), len(wos_papers), len(merged)


def show_results(papers: list, oa_count: int, wos_count: int, overlap_count: int, 
                 output_file: str):
    """Display search results."""
    console.print()
    
    if not papers:
        console.print(Panel(
            "[yellow]No papers found matching your criteria.[/yellow]\n\n"
            "[dim]Try:[/dim]\n"
            "[dim]  • Broader keywords[/dim]\n"
            "[dim]  • Wider year range[/dim]\n"
            "[dim]  • Fewer filters[/dim]",
            title="[yellow]⚠️ No Results[/yellow]",
            border_style="yellow",
            padding=(1, 2)
        ))
        return
    
    # Results panel
    results_text = Text()
    results_text.append("📊 Sources:\n", style="bold")
    results_text.append(f"   OpenAlex:    {oa_count:>5} papers\n")
    if Config.USE_WOS and wos_count > 0:
        results_text.append(f"   WoS:         {wos_count:>5} papers\n")
        results_text.append(f"   Overlap:     {overlap_count:>5} papers\n")
    results_text.append(f"\n📄 Total unique: {len(papers)} papers\n", style="bold green")
    
    if output_file:
        results_text.append(f"\n💾 Saved to:\n   {output_file}", style="dim")
    
    console.print(Panel(
        results_text,
        title="[bold green]✅ Search Complete[/bold green]",
        border_style="green",
        padding=(1, 2)
    ))
    
    # Top cited papers table
    if papers:
        console.print()
        table = Table(
            title="🏆 Top Cited Papers",
            box=box.ROUNDED,
            title_style="bold cyan",
            header_style="bold"
        )
        table.add_column("Cites", justify="right", style="green", width=7)
        table.add_column("Year", width=5)
        table.add_column("Title", max_width=55)
        table.add_column("Src", width=4)
        
        # Sort by citations and take top 10
        top_papers = sorted(
            papers, 
            key=lambda x: x.get("cited_by_count", 0) or 0, 
            reverse=True
        )[:10]
        
        for p in top_papers:
            title = (p.get("title") or "Untitled")[:52]
            if len(p.get("title", "")) > 52:
                title += "..."
            year = str(p.get("publication_date", ""))[:4] or "?"
            cites = str(p.get("cited_by_count", 0) or 0)
            source = p.get("source", "?")
            src_abbrev = {"openalex": "OA", "wos": "WoS", "both": "✓"}
            src_display = src_abbrev.get(source, "?")
            
            table.add_row(cites, year, title, src_display)
        
        console.print(table)


def generate_output_name(starting_point: dict, filters: dict) -> str:
    """Generate a clean output folder/file name."""
    parts = []
    
    # Starting point
    if starting_point.get("type") == "cites":
        name = starting_point.get("paper_name", "paper")[:25]
        parts.append(f"citing_{name}")
    elif starting_point.get("type") == "references":
        name = starting_point.get("paper_name", "paper")[:25]
        parts.append(f"refs_of_{name}")
    elif starting_point.get("type") == "author":
        name = starting_point.get("author_name", "author")[:25]
        parts.append(f"by_{name}")
    elif starting_point.get("type") == "institution":
        name = starting_point.get("institution_name", "inst")[:25]
        parts.append(f"from_{name}")
    elif filters.get("keywords"):
        parts.append(filters["keywords"][:30])
    else:
        parts.append("search")
    
    # Clean up
    base_name = "_".join(parts)
    base_name = re.sub(r'[^\w\s-]', '', base_name).strip().replace(" ", "_")
    base_name = re.sub(r'_+', '_', base_name)  # Collapse multiple underscores
    
    if not base_name:
        base_name = "search"
    
    return base_name


def main():
    """Main entry point."""
    try:
        print_header()
        
        # Check WoS API key
        if not Config.USE_WOS:
            console.print("[dim]ℹ️  WoS API key not found. Using OpenAlex only.[/dim]")
            console.print("[dim]   Add WOS_API_KEY to .env for WoS integration.[/dim]")
            console.print()
        
        # Get starting point
        starting_point = get_starting_point()
        if not starting_point:
            console.print("[yellow]Search cancelled.[/yellow]")
            return
        
        # Get filters
        filters = get_filters(starting_point)
        
        # Validate we have something to search
        if not validate_search(starting_point, filters):
            return
        
        # Confirm search
        console.print()
        if not safe_confirm("Run search?", default=True):
            console.print("[yellow]Search cancelled.[/yellow]")
            return
        
        # Run search
        papers, oa_count, wos_count, overlap_count = run_search(starting_point, filters)
        
        # Generate output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = generate_output_name(starting_point, filters)
        output_dir = os.path.join(Config.OUTPUT_DIR, f"{base_name}_{timestamp}")
        output_file = save_results(papers, output_dir, f"{base_name}_results")
        
        # Show results
        show_results(papers, oa_count, wos_count, overlap_count, output_file)
        
        console.print()
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        console.print("[dim]Please report this issue if it persists.[/dim]")


if __name__ == "__main__":
    main()
