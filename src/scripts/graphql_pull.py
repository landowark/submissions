from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from tools import ctx

# 1. Define your endpoint and authentication
# Replace '<your token here>' with your actual Basic auth string
url = "https://irida-next-stage.nml-lnm.phac-aspc.gc.ca/api/graphql"
headers = {
    "Authorization": f"Basic {ctx.irida_next_token}",
}

# 2. Setup the transport
# We use RequestsHTTPTransport to match the 'requests' behavior of curl
transport = RequestsHTTPTransport(
    url=url, 
    headers=headers,
    use_json=True,
)

# 3. Create the client
# IMPORTANT: fetch_schema_from_transport=False avoids the 422 error 
# caused by read-only tokens attempting introspection.
client = Client(transport=transport, fetch_schema_from_transport=False)

# 4. Define the query exactly as in your --data string
query = gql("""
    query {
  samples(
    orderBy: { field: name, direction: desc }
    filter: {
      name_or_puid_cont: "Sample Name"
      
    }
  ) {
    nodes {
      name
      description
      id
      puid
      createdAt
      metadata
    }
    totalCount
  }
}
""")

# 5. Execute and print
try:
    result = client.execute(query)
    print(result)
except Exception as e:
    print(f"Query failed: {e}")