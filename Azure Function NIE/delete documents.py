import requests

# Define the search API endpoint
service_name = "gptkb-kguqugfu5p2ki"
index_name = "gptkbindex"
api_version = "2023-07-01-Preview"
admin_key = "RYLPZSTTe2yIHlrIWMncQ00aJdFlMDTbNzeyAcGJXuAzSeCnGYug"
search = "*"
filter = "category eq ''"

# Define the API endpoints for search and delete
search_endpoint = f"https://{service_name}.search.windows.net/indexes/{index_name}/docs?api-version={api_version}&search={search}&%24filter={filter}&%24select=id"
delete_endpoint = f"https://{service_name}.search.windows.net/indexes/{index_name}/docs/index?api-version={api_version}"

# Make the GET request to the search API
headers = {
    "api-key": admin_key
}

response = requests.get(search_endpoint, headers=headers)

# Check if the request was successful (status code 200)
if response.status_code == 200:
    # Parse the response JSON
    search_results = response.json()

    # Extract the 'id' values from the search results
    id_list = [result['id'] for result in search_results['value']]

    # Prepare the request body for deleting documents
    request_body = {
        "value": [{"@search.action": "delete", "id": doc_id} for doc_id in id_list]
    }

    # Make the POST request to delete documents
    delete_response = requests.post(delete_endpoint, headers=headers, json=request_body)

    # Check if the delete request was successful (status code 200)
    if delete_response.status_code == 200:
        print("Documents deleted successfully.")
    else:
        print(f"Error deleting documents: {delete_response.status_code}")
else:
    print(f"Error: Request failed with status code {response.status_code}")


