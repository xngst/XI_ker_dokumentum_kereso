from datetime import datetime

# Example task: Print current timestamp to a file
with open("/app/output.txt", "a") as file:
    file.write(f"Script ran at {datetime.now()}\n")
