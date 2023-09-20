from azure.storage.blob import BlobServiceClient, ContainerClient

# Replace with your own connection string or set up authentication accordingly
connection_string = "DefaultEndpointsProtocol=https;AccountName=stycn7x2yyeprrc;AccountKey=ZCTUthjh3PFuG7G7LTOgYXfLSbsa1t+dBj9u49xK64Lg9JdsWGpCiOLcLzuTUVIgpaeknfua3dM5+AStyhP4Kg==;EndpointSuffix=core.windows.net"
container_name = "content"

try:
    # Create a BlobServiceClient using the connection string
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    # Create a ContainerClient
    container_client = blob_service_client.get_container_client(container_name)

    # List blobs in the container
    blob_list = container_client.list_blobs()

    # Iterate through the blobs and delete PDF files
    for blob in blob_list:
        blob_name = blob.name
        if blob_name.startswith("Krathwohl-RevisionBloomsTaxonomy-2002"):
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            print(f"Deleted PDF blob: {blob_name}")

except Exception as e:
    print(f"Error: {e}")
