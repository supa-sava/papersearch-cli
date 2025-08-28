import requests
import csv
import time

def fetch_openalex_works(query, start_date="2023-12-01", max_results=1000):
    base_url = "https://api.openalex.org/works"
    results = []
    cursor = "*"
    per_page = 200

    while len(results) < max_results:
        print(f"Fetching {len(results)}/{max_results}...")
        params = {
            "filter": f"from_publication_date:{start_date},abstract.search:{query}",
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

            results.append({
                "title": item.get("title"),
                "abstract": abstract,
                "publication_date": item.get("publication_date"),
                "url": item.get("primary_location", {}).get("url", "")
            })
            if len(results) >= max_results:
                break

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(1)

    return results

def save_to_csv(data, filename="openalex_commodity_papers.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "abstract", "publication_date", "url"])
        writer.writeheader()
        writer.writerows(data)

if __name__ == "__main__":
    query = f"'commodity financialization'"
    papers = fetch_openalex_works(query)
    save_to_csv(papers)
    print(f"Saved {len(papers)} papers to CSV.")
