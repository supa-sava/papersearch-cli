


# Academic Paper Mass Searcher

A collection of Python scripts for searching and analyzing academic papers using the OpenAlex API.

The intended usage cases are:
1. Quickly mass-searching for abstracts of papers mentioning a particular term. The output is a CSV file with titles and abstracts that can be put into an LLM to filter out papers that don't fit your specific criteria.
2. Finding all papers that cite a specific research paper, to explore the academic conversation around a given work and find related works that a particular paper you've read has influenced. Once again the output is a CSV file with titles and abstracts that can be put into an LLM to filter out papers or find most notable papers.


## Getting Started

Set up your Python environment:
```bash
python -m venv venv
source venv/bin/activate  # On Unix/macOS
# or
venv\Scripts\activate     # On Windows
pip install requests
```

## Scripts Overview

### 1. `openalex_search_by_term.py`
**Purpose**: Searches for academic papers containing specific terms in their abstracts.

**What it does**:
- Searches OpenAlex database for papers containing the specified query term
- Filters papers published from a specified start date (defaults to 2023/12/01)
- Retrieves abstracts, titles, publication dates, and URLs

**Output**: Creates a CSV file (`openalex_commodity_papers.csv` by default) with columns:
- `title`: Paper title
- `abstract`: Full abstract text
- `publication_date`: Publication date
- `url`: Link to the paper (if available)


### 2. `openalex_search_by_papers_that_cite_a_paper.py`
**Purpose**: Finds all papers that cite a specific research paper.

**What it does**:
- Takes either a paper title/DOI or direct OpenAlex ID as input
- Searches for all papers that cite the specified paper
- Retrieves abstracts, titles, publication dates, and URLs of citing papers
- Interactive script that prompts for input

**Output**: Creates a CSV file named `openalex_citations_of_[paper_name].csv` with columns:
- `title`: Paper title (the citing paper)
- `abstract`: Full abstract text
- `publication_date`: Publication date
- `url`: Link to the paper (if available)

The script will prompt you to either:
- Search by paper title or DOI or
- Enter an OpenAlex ID directly (e.g., W2288114807) - which you can find by going to this link in OpenAlex [https://openalex.org/](https://openalex.org/) and searching for the paper. Example: we search for the paper "What do we learn from the price of crude oil futures?" click on it and in the search bar the link appears as https://openalex.org/works?page=1&filter=ids.openalex:w2139116473&sort=cited_by_count:desc&zoom=w2139116473 -> the OpenAlex ID is w2139116473 (right after "ids.openalex:")

## Configuration Options

Both scripts support customization:
- **Maximum results**: Default 1000 papers (configurable via `max_results` parameter)
- **Date filtering**: Search from specific publication dates
- **API rate limiting**: Built-in delays to respect OpenAlex API limits

## Sample Output Files

The repository includes example output files:
- `openalex_commodity_papers.csv`: Results from searching "commodity financialization"
- `openalex_citations_of_Financialization_of_commodity_markets_ten_years_later.csv`: Papers citing a specific financialization study
- `openalex_citations_of_W2107802909.csv`: Papers citing work with OpenAlex ID W2107802909 (Index Investment and the Financialization of Commodities by Tang and Xiong)

