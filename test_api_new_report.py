import requests

response = requests.post(
    url="http://localhost:8000/new_report",
    json={"text": "New clinical report"}
)
if response.status_code == 200:
    print("New report created successfully:", response.json())
else:
    print("Failed to create new report:", response.status_code, response.text)
    