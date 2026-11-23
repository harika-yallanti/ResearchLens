# ResearchLens – AI Research Paper Quality Analyzer

An AI-powered web application that helps students and researchers evaluate, analyze, and improve academic research papers using Artificial Intelligence and Natural Language Processing.

ResearchLens analyzes uploaded research papers, evaluates their writing and structure, checks citation consistency, generates research summaries, and provides quality scores with actionable improvement suggestions.

---

## Project Overview

Writing a high-quality research paper requires proper organization, clear academic writing, a well-defined methodology, relevant citations, and a strong conclusion.

ResearchLens aims to simplify this process by providing an intelligent platform that automatically examines research papers and generates useful feedback.

Users can upload research papers in PDF or DOCX format and receive an AI-generated assessment report containing quality evaluation, writing feedback, research insights, and suggestions for improvement.

## Features

### 1. User Authentication
- User registration and login.
- Firebase Authentication integration.
- Email OTP-based two-step verification.
- Google sign-in.
- Password reset functionality.
- Session management and logout.

### 2. Research Paper Management
- Upload research papers in PDF and DOCX formats.
- Extract text from uploaded documents.
- Store and manage uploaded research papers.
- View previously uploaded papers.
- Maintain research paper analysis history.

### 3. AI-Powered Research Paper Analysis
- AI-based research paper evaluation using Groq API.
- Research paper summarization.
- Abstract and conclusion evaluation.
- Methodology assessment.
- Research structure evaluation.
- Identification of missing or weak sections.
- Actionable improvement suggestions.

### 4. Writing Quality Evaluation
- Grammar and spelling evaluation.
- Writing clarity assessment.
- Academic writing quality analysis.
- Identification of areas requiring improvement.

### 5. Keyword Analysis
- Extract keywords from research papers.
- Allow users to manually provide keywords.
- Generate suggested keywords using AI when keywords are not provided.
- Support research topic identification.

### 6. Citation and Plagiarism Analysis
- Citation consistency checking.
- Reference-related analysis.
- Plagiarism similarity checking through supported sources.
- Research source lookup and comparison.

### 7. Research Quality Scoring
- Generate an overall research paper quality score.
- Evaluate different aspects of research paper quality.
- Display analysis results in an organized report.
- Provide suggestions to improve research quality.

### 8. Reports and History
- Generate downloadable assessment reports.
- View previous analysis reports.
- Compare research paper analysis results.
- Maintain analysis history.

### 9. Admin Dashboard
- Manage registered users.
- View uploaded research papers.
- Monitor research paper analyses.
- View analysis details and reports.

---

## Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Backend Framework | FastAPI |
| Database | MySQL |
| ORM | SQLAlchemy |
| AI Integration | Groq API |
| Authentication | Firebase Authentication |
| Frontend | HTML, CSS, JavaScript |
| Template Engine | Jinja2 |
| PDF Processing | PyMuPDF |
| DOCX Processing | python-docx |
| Data Processing | Natural Language Processing |
| API Testing | Postman |
| Version Control | Git and GitHub |

---

## System Workflow

1. User registers or logs into ResearchLens.
2. The authentication system verifies the user's identity.
3. User uploads a research paper in PDF or DOCX format.
4. The application extracts text from the uploaded document.
5. The extracted content is processed for research paper evaluation.
6. The AI service analyzes the paper and generates insights.
7. The application evaluates writing quality, structure, methodology, citations, and other research aspects.
8. A research quality score and improvement suggestions are generated.
9. The results are displayed in an assessment report.
10. Users can access previous reports and download their analysis results.

---

## Project Structure

```text
AI-Research-Paper-Quality-Analyzer/
│
├── app/
│   ├── models/
│   │   ├── analysis_report.py
│   │   ├── email_otp.py
│   │   ├── plagiarism_check.py
│   │   ├── research_paper.py
│   │   └── user.py
│   │
│   ├── routers/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   └── papers.py
│   │
│   ├── services/
│   │   ├── email_service.py
│   │   ├── firebase_service.py
│   │   ├── groq_service.py
│   │   ├── plagiarism_service.py
│   │   └── session_service.py
│   │
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   │
│   ├── templates/
│   │
│   ├── database.py
│   └── main.py
│
├── credentials/
│   └── firebase-service-account.json
│
├── create_tables.py
├── requirements.txt
├── test_db.py
├── test_email.py
├── test_firebase_admin.py
├── test_groq_analysis.py
├── test_openalex.py
├── test_plagiarism_service.py
├── .gitignore
└── README.md
```

**Note:** The `credentials/` directory is used locally for Firebase service-account credentials and should not be uploaded to GitHub.

---

## Installation and Setup

### Prerequisites

Make sure the following software is installed:

- Python 3.11 or later
- MySQL Server
- Git
- Visual Studio Code or another Python IDE

You will also need the required API credentials for the services configured in the application.

### Step 1: Clone the Repository

```bash
git clone https://github.com/harika-yallanti/ResearchLens.git
```

Navigate to the project directory:

```bash
cd ResearchLens
```

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
```

Activate the virtual environment on Windows:

```powershell
.\venv\Scripts\Activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure the Database

1. Start your MySQL server.
2. Create a MySQL database for ResearchLens.
3. Configure the database connection settings according to the application's database configuration.

### Step 5: Configure API Credentials

Configure the required credentials locally:

- Groq API key for AI-powered analysis.
- Firebase project configuration for authentication.
- Firebase service-account credentials for server-side verification.
- Email service credentials for OTP delivery.
- Any additional service credentials required by the configured integrations.

Keep private credentials in environment variables or local configuration files. Never commit them to GitHub.

### Step 6: Initialize Database Tables

Run:

```bash
python create_tables.py
```

### Step 7: Start the Application

Run the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Open the application in your browser:

```text
http://127.0.0.1:8000
```

FastAPI API documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Testing

ResearchLens includes test scripts for different application components.

| Test File | Purpose |
|---|---|
| `test_db.py` | Database connectivity |
| `test_email.py` | Email service |
| `test_firebase_admin.py` | Firebase Admin integration |
| `test_groq_analysis.py` | AI analysis |
| `test_openalex.py` | OpenAlex integration |
| `test_plagiarism_service.py` | Plagiarism service |

Additional testing was performed for:

- Email OTP verification.
- Incorrect OTP handling.
- OTP resend functionality.
- Session validation.
- Logout and session invalidation.
- Responsive UI testing across mobile, tablet, and desktop screen sizes.

---

## Security Considerations

- Firebase Authentication is used for user authentication.
- Email OTP verification adds an additional authentication step.
- Session management protects authenticated application routes.
- Private API keys and database credentials should be stored securely.
- Firebase service-account credentials must remain private.
- Uploaded research documents should be handled securely.

---

## Future Enhancements

The following improvements can be considered for future versions:

- Advanced research paper evaluation.
- More detailed methodology and statistical analysis.
- Enhanced plagiarism detection through additional supported sources.
- Research topic and journal recommendations.
- AI-powered rewriting and grammar improvement.
- Research paper comparison and benchmarking.
- More detailed analytics and visualization.
- Improved report customization.
- Support for additional academic document formats.

---

## Project Status

**Current Status: Phase 1 – Core Application Development and Testing Completed**

The project has progressed beyond initial setup and includes authentication, document upload, AI-powered research analysis, assessment reports, and supplementary testing.

Further enhancements and improvements are planned.

---

## Author

**Harika Yallanti**

B.Tech – Computer Science and Engineering

GitHub: [harika-yallanti](https://github.com/harika-yallanti)

---

## License

This project is developed for educational and academic purposes.

---

**ResearchLens – Making Research Paper Evaluation Smarter with AI.**