import requests
import csv
import time
import re

def clean_filename(text):
    """Clean text to be safe for filenames."""
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')

def find_openalex_id(search_term):
    """Try to find the OpenAlex ID for a given paper title or DOI."""
    if search_term.lower().startswith("10."):  # DOI
        url = f"https://api.openalex.org/works/https://doi.org/{search_term}"
    else:
        url = f"https://api.openalex.org/works?search={search_term}&per-page=1"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "id" in data:
            return data["id"].split("/")[-1], data.get("title", "unknown_paper")
        elif isinstance(data, dict) and "results" in data and data["results"]:
            work = data["results"][0]
            return work["id"].split("/")[-1], work.get("title", "unknown_paper")
        else:
            print("No matching paper found.")
            return None, None
    except requests.RequestException as e:
        print("Error fetching OpenAlex ID:", e)
        return None, None

def fetch_citing_works(openalex_id, max_results=1000):
    """Fetch papers that cite the given OpenAlex ID."""
    base_url = "https://api.openalex.org/works"
    cursor = "*"
    results = []
    per_page = 200

    while len(results) < max_results:
        print(f"Fetching {len(results)}/{max_results} citing works...")
        params = {
            "filter": f"cites:{openalex_id},has_abstract:true",
            "per-page": per_page,
            "cursor": cursor,
            "sort": "publication_date:desc"
        }

        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print("Connection error:", e)
            break

        data = response.json()
        for item in data.get("results", []):
            abstract_index = item.get("abstract_inverted_index")
            if not abstract_index:
                continue
            abstract_words = sorted(
                [(word, pos) for word, positions in abstract_index.items() for pos in positions],
                key=lambda x: x[1]
            )
            abstract = " ".join(word for word, _ in abstract_words)

            location = item.get("primary_location")
            url = location["url"] if location and "url" in location else ""

            results.append({
                "title": item.get("title"),
                "abstract": abstract,
                "publication_date": item.get("publication_date"),
                "url": url
            })


            if len(results) >= max_results:
                break

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(1)

    return results

def save_to_csv(data, filename):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "abstract", "publication_date", "url"])
        writer.writeheader()
        writer.writerows(data)

if __name__ == "__main__":
    use_manual_id = input("Do you already have the OpenAlex ID? (y/n): ").strip().lower()

    if use_manual_id == "y":
        openalex_id = input("Enter the OpenAlex ID (e.g., W2288114807): ").strip()
        paper_title = input("Enter a short name for the paper (used in CSV filename): ").strip()
    else:
        search_term = input("Enter paper title or DOI: ").strip()
        openalex_id, paper_title = find_openalex_id(search_term)

    if openalex_id:
        print(f"Using OpenAlex ID: {openalex_id}")
        papers = fetch_citing_works(openalex_id)
        filename = f"openalex_citations_of_{clean_filename(paper_title)}.csv"
        save_to_csv(papers, filename)
        print(f"Saved {len(papers)} citing papers to: {filename}")
    else:
        print("Could not retrieve OpenAlex ID.")
