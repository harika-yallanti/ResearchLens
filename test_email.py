
from app.services.email_service import send_email

try:
    send_email(
        to_email="harika29042005@gmail.com",
        subject="ResearchLens SMTP Test",
        body=(
            "Hello!\n\n"
            "This is a test email from ResearchLens.\n"
            "Your Gmail SMTP configuration is working successfully.\n\n"
            "We will use this email service for OTP verification."
        ),
    )

    print("SUCCESS: Test email sent successfully.")

except Exception as error:
    print("FAILED:", error)
