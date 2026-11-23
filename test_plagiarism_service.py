
from app.services.plagiarism_service import check_paper_similarity


sample_text = """
Machine learning is increasingly being used in educational
institutions to improve student learning outcomes.

Artificial intelligence systems can analyze student performance
and provide personalized recommendations based on individual
learning requirements.

Machine learning algorithms help educators identify learning
patterns, predict student performance, and support personalized
education through data-driven approaches.

Educational technology has become an important area of research
because intelligent systems can improve teaching methods and
student engagement.
""" * 5


try:
    print("Starting similarity test...")

    result = check_paper_similarity(
        paper_text=sample_text,
        title="Machine Learning in Education",
        abstract=(
            "This research explores machine learning "
            "applications in education and personalized learning."
        ),
        keywords=[
            "machine learning",
            "education",
            "artificial intelligence",
        ],
    )

    print("\nSimilarity check completed!")
    print("Status:", result["status"])
    print("Similarity score:", result["similarity_score"], "%")
    print("Sources discovered:", result["sources_discovered"])
    print("Sources compared:", result["sources_checked"])
    print("Potential matches:", len(result["matched_passages"]))

    for source in result["similarity_sources"][:3]:
        print("\nSource:", source["title"])
        print("Similarity:", source["similarity"], "%")

except Exception as error:
    print("\nSimilarity test failed:")
    print(error)
