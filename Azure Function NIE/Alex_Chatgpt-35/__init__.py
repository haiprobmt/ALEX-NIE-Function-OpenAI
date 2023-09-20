import logging
import os
import openai
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import QueryType
from azure.core.credentials import AzureKeyCredential
import json
from azure.cosmos import CosmosClient
import hashlib
from azure.keyvault.secrets import SecretClient

# Replace these values with your Azure Key Vault URL
keyvault_url = "https://kv-nie.vault.azure.net/"

# Create a SecretClient using the DefaultAzureCredential
credential = DefaultAzureCredential()
client_kv = SecretClient(vault_url=keyvault_url, credential=credential)


# Replace these with your own values, either in environment variables or directly here
AZURE_STORAGE_ACCOUNT = client_kv.get_secret("azure-storage-account").value
AZURE_SEARCH_SERVICE = client_kv.get_secret("azure-search-service").value
AZURE_SEARCH_INDEX = client_kv.get_secret("azure-search-index").value
AZURE_OPENAI_SERVICE = client_kv.get_secret("azure-openai-service").value
AZURE_OPENAI_CHATGPT_DEPLOYMENT = client_kv.get_secret("azure-openai-chatgpt").value
AZURE_OPENAI_EMB_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMB_DEPLOYMENT") or "embedding"
AZURE_SEARCH_API_KEY = client_kv.get_secret("azure-search-api-key").value
AZURE_OPENAI_GPT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_GPT_DEPLOYMENT") or "davinci"

KB_FIELDS_CONTENT = os.environ.get("KB_FIELDS_CONTENT") or "content"
KB_FIELDS_CATEGORY = os.environ.get("KB_FIELDS_CATEGORY") or "category"
KB_FIELDS_SOURCEPAGE = os.environ.get("KB_FIELDS_SOURCEPAGE") or "sourcepage"


# Use the current user identity to authenticate with Azure OpenAI, Cognitive Search and Blob Storage (no secrets needed, 
# just use 'az login' locally, and managed identity when deployed on Azure). If you need to use keys, use separate AzureKeyCredential instances with the 
# keys for each service

credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)

# Used by the OpenAI SDK
openai.api_base = f"https://{AZURE_OPENAI_SERVICE}.openai.azure.com"
openai.api_version = "2023-05-15"

# Comment these two lines out if using keys, set your API key in the OPENAI_API_KEY environment variable and set openai.api_type = "azure" instead
openai.api_type = "azure"
# openai.api_key = azure_credential.get_token("https://cognitiveservices.azure.com/.default").token

# Set up clients for Cognitive Search and Storage
search_client = SearchClient(
    endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
    index_name=AZURE_SEARCH_INDEX,
    credential=credential)


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    Input = req.params.get('Input')
    if not Input:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            Input = req_body.get('Input')

    if Input:

        base_system_message = """You are a faculty who assists teachers design a course outline for their students. 
        Answer ONLY with the facts listed in the list of sources below. If there isn't enough information below, say you don't know. 
        Do not generate answers that don't use the sources below. If asking a clarifying question to the user would help, ask the question.
        """
        system_message = f"{base_system_message.strip()}"

        messages=[{"role": "system", "content": system_message}]

        # Defining a function to send the prompt to the ChatGPT model
        # More info : https://learn.microsoft.com/en-us/azure/cognitive-services/openai/how-to/chatgpt?pivots=programming-language-chat-completions
        def send_message(messages, model_name, max_response_tokens=500):
            response = openai.ChatCompletion.create(
                engine=AZURE_OPENAI_CHATGPT_DEPLOYMENT,
                messages=messages,
                temperature=0.2,
                max_tokens=max_response_tokens
            )
            return response['choices'][0]['message']['content']

        # This is the first user message that will be sent to the model. Feel free to update this.
        engage_0 = """What is constructive alignment and how does it relate to blended courses and modes of learning?"""
        engage_1 = """How can the ABCD model be used to develop Intended Learning Outcomes (ILO) based on Bloom's Taxonomy?, What are some examples of verbs used for the "Behaviour" component of ILO and how do they relate to the ABCD components?"""    
        engage_2 = """How can multiple ILOs be achieved in a single lesson?"""
        engage_3 = """What are some examples of learner-centered Teaching and Learning Activities (TLA) and corresponding Assessment Tasks (AT) for both online and face-to-face settings?"""
        engage_4 = """What does it mean to weave TLAs from lesson to lesson?"""
        engage_5 = """What are some ed-tech tools and resources that can complement learner-centered TLAs?, what information should be included in a course synopsis?"""
        engage_6 = """What are the components of V3SK table and how are they defined?"""

        engages = [engage_0, engage_1, engage_2, engage_3, engage_4, engage_5, engage_6]

        for engage in engages:

            exclude_category = None

            query_vector = openai.Embedding.create(engine=AZURE_OPENAI_EMB_DEPLOYMENT, input=engage)["data"][0]["embedding"]

            # Alternatively simply use search_client.search(q, top=3) if not using semantic search
            filter = "category ne '{}'".format(exclude_category.replace("'", "''")) if exclude_category else None

            r = search_client.search(
                                    engage, 
                                    filter=filter,
                                    # query_type=QueryType.SEMANTIC, 
                                    query_language="en-us", 
                                    query_speller="lexicon", 
                                    semantic_configuration_name="default", 
                                    top=5,
                                    vector=query_vector if query_vector else None, 
                                    top_k=50 if query_vector else None,
                                    vector_fields="embedding" if query_vector else None
                                    )
            results = [str(doc[KB_FIELDS_SOURCEPAGE]) + ": " + str(doc[KB_FIELDS_CONTENT]).replace("\n", "").replace("\r", "") for doc in r]
            content = "\n".join(results)

            # for source in results:
            #     for i in range(len(source)):
            #         if source[i] == ":":
            #             doc = source[:i]
            #             sources.append(doc)
            #             break


            # This is the first user message that will be sent to the model. Feel free to update this.
            user_message = engage + " \nSOURCES:\n" + content


            # Create the list of messages. role can be either "user" or "assistant" 
            messages.append({"role": "user", "content": user_message})

            response = send_message(messages, AZURE_OPENAI_CHATGPT_DEPLOYMENT, 2048)
            messages.append({"role": "assistant", "content": response})


        Input = "a 5-week course outline on Food Fiction: A Creative Writing and Storytelling"
        explore = """
                    Given the above explanations, create “{Input}” provide a course synopsis for the entire course within 200 words.
                    Write a maximum of 5 ILOs,using the ABCD model, for the entire 
                    course.
                    For each week, list the topic and mode of delivery determined by 
                    the nature of the content and TLAs. 
                    For each week, provide a variety of TLAs and a variety of 
                    formative assessment tasks (ATs) for the first 4 weeks and a 
                    summative assessment task for the last week. Ensure the ATs 
                    and TLAs are weaved.
                    For each week, allow for more than one ILO to be achieved and 
                    state which ILOs has been achieved in each lesson.
                    Suggest ed tech tools to support the TLAs in each week.
                    Suggest other learning resources (books,websites,journals) to 
                    support the TLAs in each week".
                    """.format(Input = Input)
                    
        #user_message = "Let's talk about generative AI and keep the tone informational but also friendly."
        #user_message = "Show me a few more examples"
        system_message_1 = """Based on the above information and given sources, please continue answer the following question"""
        messages.append({"role": "system", "content": system_message_1})
        messages.append({"role": "user", "content": explore})

        max_response_tokens=2048

        response = send_message(messages, AZURE_OPENAI_CHATGPT_DEPLOYMENT, max_response_tokens)

        messages.append({"role": "assistant", "content": response})

        explain = """
            For the course outline you just created, Examine if the ATs and TLAs support 
            the constructive alignment with the 
            ILOs.
            Explain how are the various ILOs 
            achieved for each lesson
            Explain and analyze the Components of V3SK with its Values, Skills and Knowledge. 
            Examine if the ATs and TLAs from 
            week to week are weaved.
            Explain how the nature of the content 
            and TLAs determine the mode of 
            delivery for each lesson. 
            Making sure, you provide your 
            explanation with reference to the 
            above course outline."""
        #user_message = "Let's talk about generative AI and keep the tone informational but also friendly."
        #user_message = "Show me a few more examples"
        messages.append({"role": "system", "content": system_message_1})
        messages.append({"role": "user", "content": explain})

        max_response_tokens=2048

        response = send_message(messages, AZURE_OPENAI_CHATGPT_DEPLOYMENT, max_response_tokens)

        messages.append({"role": "assistant", "content": response})

        elaborate = """
            For the same course, present the 
            following information using a json format with this structure
            {{
                "Course synopsis": "Information of Course synopsis",
                "ILOs for entire course": "List out maximum of 5 ILOs using the ABCD model.
                    MUST Following this sample format: "Student(Audience) will be able to write a food memoir(Behavior) that describes a personal experience(Condition) with food using emotional depth(Degree)".
                    In the Behavior part, MUST use these verbs: Remember, Comprehension, Apply, Analyse, Evaluate, Create",
                "TE21": "Analyze the keywords from Course synopsis and ILOs then classify them with appropriate skills, values and knowledge from the Components of V3SK table
                For example: "TE21": {
                            "Values": [
                                "Commitment to the learner",
                                "Commitment to the profession",
                                "Commitment to the community"
                            ],
                            "Skills": [
                                "Communication skills",
                                "Critical & metacognitive skills",
                                "Creative & innovative skills"
                            ],
                            "Knowledge": [
                                "Health & mental well-being",
                                "Educational foundation & policies",
                                "Global awareness"
                            ]
                    ",
                "Week": [
                    "Week": "Number",
                    "Course topics": "Information of Course topics in this week",
                    "ILOs achieved": "Which point number of ILOs achieved in this week",
                    "ATs": "Information of ATs in this week",
                    "TLAs": "Information of TLAs in this week, The TLAs must be explained clearly, exhibiting weaving from lesson to lesson",
                    "Ed tech tools" : "Information of Ed tech tools in this week",
                    "Other learning resources" : "Information of learning resources in this week",
                    "Mode of learning": "Information of Mode of learning in this week, 
                        Do take note that 30-60 percent of the course should be online and the nature of the lesson should decide the mode of learning
                        just list out the suitable Mode of learning without percentage of each"
                    ]      
            }} 
            """
        #user_message = "Let's talk about generative AI and keep the tone informational but also friendly."
        #user_message = "Show me a few more examples"
        messages.append({"role": "system", "content": system_message_1})
        messages.append({"role": "user", "content": elaborate})

        max_response_tokens=2048

        response = send_message(messages, AZURE_OPENAI_CHATGPT_DEPLOYMENT, max_response_tokens)

        messages.append({"role": "assistant", "content": response})

        last_reponse = len(messages)
        for i in range(0, len(messages) + 1):
            if i == last_reponse:     
                response = messages[i-1]['content']

        #Store the outcome in Azure Cosmos DB
        # Your original long partition key

        database_name = client_kv.get_secret("azure-cosmosdb-name").value  # Replace with your database name
        container_name = client_kv.get_secret("azure-cosmosdb-contanier").value  # Replace with your container name
        key = client_kv.get_secret("azure-cosmosdb-key").value
        endpoint = f"https://{database_name}.documents.azure.com:443/"

        client = CosmosClient(endpoint, key)
        database = client.get_database_client(database_name)
        container = database.get_container_client(container_name)

        original_partition_key = response

        # Generate a hash of the partition key (using SHA-256 for this example)
        hashed_partition_key = hashlib.sha256(original_partition_key.encode()).hexdigest()

        query = "SELECT Top 1 * FROM c Order by c.id_identity desc"

        # Execute the query
        results = list(container.query_items(query, enable_cross_partition_query=True))
        if len(results) == 0:
            next_id = 1
        else:
            max_id = results[0]["id_identity"]
            next_id = max_id + 1

        # sources_final = set(sources)
        # sources_final = list(source)

        outcome = {
            "id": f"NIE - {next_id}",
            "id_identity": next_id,
            "partitionKey": hashed_partition_key,
            "user": "",
            "chat_conversation": messages
            # "source": sources_final
        }

        # Insert the document into the container
        container.create_item(body=outcome)

        return func.HttpResponse( json.dumps({"response": response, "reference_sources": "sources_final"}), mimetype="application/json",)
  
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )
    
    