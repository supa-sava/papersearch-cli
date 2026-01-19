# 📚 Paper Search

A beautiful CLI tool for searching academic papers across **OpenAlex** and **Web of Science**.

## Coverage
This tool searches across two complementary scholarly indexes: OpenAlex (open, very broad coverage) and Web of Science Core Collection (curated, selective coverage).​
* Web of Science (WoS): The full Web of Science platform includes more than 271 million records, and the WoS Core Collection “connects more than 97 million records” via cited references and indexes 22,000+ journals “cover to cover.”​
* OpenAlex: OpenAlex reports indexing “over 240M works” (journal articles, books, datasets, theses, etc.), and external reviews describe OpenAlex as having 260M+ works (late 2024) and ingesting large repository-oriented sources like DataCite.​
Because their inclusion policies differ, overlap is substantial but not complete—using both typically returns a broader and more reliable result set than using either alone.

## Quick Start

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows
pip install requests python-dotenv rich questionary

# Run
python paper_search.py
```

## Features

- 🔍 **Keyword search** - Search by topic/abstract
- 📖 **Citation search** - Find papers citing a work
- 📑 **Reference search** - Get a paper's bibliography  
- 👤 **Author search** - All works by a researcher
- 🏛️ **Institution search** - Papers from a university
- ⚡ **Smart filtering** - Combine any filters together
- 🔄 **Deduplication** - Merge results from both databases

## Usage

Run interactively:
```bash
python paper_search.py
```

### Search Types

| Starting Point | Description |
|----------------|-------------|
| Keyword search | Search all papers by topic/abstract |
| Citation search | Papers that cite a specific work |
| Reference search | Bibliography of a specific work |
| Author search | All works by a researcher |
| Institution search | Papers from a university |

### Filters (All Optional)

| Filter | Description |
|--------|-------------|
| Keywords | Topic/abstract search (always available) |
| Year range | e.g., `2020-2024` or `2020` |
| Institution | Filter by author affiliation |
| Source | Filter by journal/venue |
| Author | Filter by specific researcher |
| Min citations | e.g., `50` for highly-cited only |
| Open access | OA papers only |

### Example Searches

**Find highly-cited ML papers from MIT:**
1. Choose "Keyword search"
2. Keywords: `machine learning`
3. Year range: `2020-2024`
4. Add filter: Institution → `MIT`
5. Add filter: Minimum citations → `100`

**Get bibliography of a seminal paper:**
1. Choose "References of a specific work"
2. Enter DOI: `10.1093/rfs/hhr093`

**Find all papers citing a work:**
1. Choose "Papers citing a specific work"
2. Enter title, DOI, or OpenAlex ID

## WoS API Key (Optional)

Get from [Clarivate Developer Portal](https://developer.clarivate.com/apis/wos-starter), add to `.env`:

```
WOS_API_KEY=your_key_here
```

Without it, only OpenAlex is used (still 240M+ papers).

## Output

Results saved to `outputs/{search_name}_{timestamp}/` as CSV:
- Title, abstract, publication date
- URL, DOI, citation count
- Source (openalex/wos/both)

## Project Structure

```
├── paper_search.py    # Main CLI tool
├── outputs/           # Search results (CSV)
├── docs/              # API documentation
├── legacy/            # Old separate scripts
├── .env               # WoS API key
└── .env.example
```
