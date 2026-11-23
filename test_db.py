from app.database import engine

try:
    with engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT 1")
        print("Database connection successful:", result.scalar())

except Exception as error:
    print("Database connection failed:")
    print(type(error).__name__)
    print(error)