
from app.services.groq_service import analyze_research_paper

sample_text = """
Title: A Study on Machine Learning in Education

Abstract:
This paper explores the use of machine learning in education.
The study examines how predictive models can identify students
who may need additional academic support.

Introduction:
Machine learning is increasingly used in educational systems.
It can help educators understand student performance.

Methodology:
The study uses a dataset of student academic records.
A classification model is trained to predict student outcomes.

Results:
The model achieved an accuracy of 85 percent.

Conclusion:
Machine learning may support early intervention.
Further research is required to evaluate the approach.
"""

try:
    result = analyze_research_paper(sample_text)

    print("\nAI ANALYSIS RESULT")
    print("=" * 50)

    for key, value in result.items():
        print(f"\n{key}:")
        print(value)

except Exception as error:
    print("\nANALYSIS FAILED")
    print(error)
