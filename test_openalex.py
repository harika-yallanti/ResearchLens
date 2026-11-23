
from app.services.plagiarism_service import search_openalex


try:
    print("Testing OpenAlex connection...")

    results = search_openalex(
        "machine learning in education",
        per_page=5,
    )

    print("\nOpenAlex connection successful!")
    print("Results found:", len(results))

    for index, paper in enumerate(results, start=1):
        print(f"\nPaper {index}")
        print("Title:", paper["title"])
        print("Year:", paper["publication_year"])
        print("Open Access:", paper["is_open_access"])
        print("Abstract available:", bool(paper["abstract"]))

except Exception as error:
    print("\nOpenAlex test failed:")
    print(error)
