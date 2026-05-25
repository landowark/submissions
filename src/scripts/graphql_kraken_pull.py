from datetime import date, datetime, timedelta
import json
from pprint import pprint
from typing import List

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from base64 import b64encode
from pathlib import Path
import requests, io, csv, sys, logging
from decimal import Decimal

p = Path(__file__).parents[1].joinpath("submissions").absolute().__str__()
if p not in sys.path:
    sys.path.append(p)

logger = logging.getLogger(f"scripts.{__name__}")

# ==== CONFIGURATION ====


# ==== UPDATED QUERIES ====

def parse_value(key, value):
    if key == "taxonomy_id":
        return value
    elif key == "fraction_total_reads":
        return Decimal(value).__float__()
    elif key in ["taxonomy_lvl", "meta.id"]:
        return value
    else:
        try:
            return int(value)
        except ValueError:
            return value
    

def read_csv_from_url(url):
    """Downloads a CSV from a URL and returns a list of dictionaries."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Check for HTTP errors
        
        # Use StringIO to treat the string as a file-like object for the csv library
        f = io.StringIO(response.text)
        reader = csv.DictReader(f)
        return [row for row in reader]
    except Exception as e:
        print(f"  [!] Failed to read CSV: {e}")
        return None


import re

def read_metadata(input_dict):
    output = []
    
    # Extract the base meta.id from the filename 
    # (Extracts 'MCS-Mar2026P6-20260331' from the string)
    filename = input_dict.get('reads.1', '')
    meta_id = filename.split('_S')[0] if '_S' in filename else ""
    
    # Get the taxonomy level
    tax_lvl = input_dict.get('taxonomy_level', '')

    # We need to find how many abundance entries exist (1, 2, 3...)
    # We'll also include 'unclassified' as it follows a similar pattern
    targets = []
    for key in input_dict.keys():
        if key.startswith('abundance_') and key.endswith('_name'):
            # Extract the number (e.g., '1' from 'abundance_1_name')
            num = key.split('_')[1]
            targets.append(num)
    
    # Add unclassified to the processing list if it exists
    keys_to_process = targets + (['unclassified'] if 'unclassified_name' in input_dict else [])

    for i in keys_to_process:
        prefix = f"abundance_{i}" if i != 'unclassified' else 'unclassified'
        
        name = input_dict.get(f"{prefix}_name")
        if not name:
            continue

        output.append({
            'name': name,
            'added_reads': 0, # Not present in source, defaulting to 0
            'fraction_total_reads': float(input_dict.get(f"{prefix}_fraction_total_reads", 0)),
            'kraken_assigned_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
            'meta.id': meta_id,
            'new_est_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
            'taxonomy_id': input_dict.get(f"{prefix}_ncbi_taxonomy_id", ""),
            'taxonomy_lvl': tax_lvl

        })

    return output

def get_all_samples(project: str, start_date: str, end_date: str, metadata_only: bool = True):
    
    from tools import ctx

    API_TOKEN = b64encode(f"{ctx.irida_next.email}:{ctx.irida_next.token}".encode('utf-8')).decode('utf-8')  # Replace with your IRIDA Next API token
    PAGE_SIZE = 5  # Number of samples per request
    

    # ==== SETUP GRAPHQL CLIENT ====
    transport = RequestsHTTPTransport(
        url = ctx.irida_next.endpoint,
        headers = {
            "Authorization": f"Basic {API_TOKEN}",
            "Content-Type": "application/json"
        },
        verify=True,  # Set to False if using self-signed certs
        retries=3
    )

    client = Client(transport=transport, fetch_schema_from_transport=False)

    output = []
    
    # Query 1: Get basic sample info (Low complexity)
    list_samples_query = gql("""
        query ListSamples($projectId: ID!, $first: Int, $after: String, $startDate: ValueScalar, $endDate: ValueScalar) {
        project(puid: $projectId) {
            samples(
            first: $first, 
            after: $after, 
            filter: { 
                advanced_search: [
                { 
                    field: "updated_at", 
                    operator: GREATER_THAN_EQUALS, 
                    value: $startDate 
                },
                { 
                    field: "updated_at", 
                    operator: LESS_THAN_EQUALS, 
                    value: $endDate 
                }
                ]
            }
            ) {
            edges {
                node {
                id
                name
                updatedAt
                createdAt
                metadata
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
            }
        }
        }
    """)
    

    # Query 2: Get attachments for a specific sample ID
    sample_details_query = gql("""
        query GetSampleAttachments($sampleId: ID!) {
            node(id: $sampleId) {
            ... on Sample {
                attachments {
                edges {
                    node {
                    filename
                    attachmentUrl
                    }
                }
                }
            }
            }
        }
    """)


    # def fetch_all_samples_with_data():
    all_samples = []
    after_cursor = None
    # Format must be a string since we changed the variable type to String
    

    # Step 1: Fetch Sample IDs (Low Complexity)
    while True:
        variables = {"projectId": project, "first": PAGE_SIZE, "after": after_cursor, "startDate": start_date, "endDate": end_date}
        result = client.execute(list_samples_query, variable_values=variables)
        samples_data = result["project"]["samples"]
        
        for edge in samples_data["edges"]:
            all_samples.append(edge["node"])

        if not samples_data["pageInfo"]["hasNextPage"]:
            break
        after_cursor = samples_data["pageInfo"]["endCursor"]

    # Step 2: Get attachments and process CSVs
    for sample in all_samples:
        print(f"\nChecking sample: {sample['name']}")
        # print(sample['metadata'])
        if metadata_only:
            sample['data'] = read_metadata(sample['metadata'])
            
            sample['filename'] = "metadata"
        else:    
            details = client.execute(sample_details_query, variable_values={"sampleId": sample["id"]})
            attachments = details["node"]["attachments"]["edges"]    
            # sample["processed_files"] = []
            for edge in attachments:
                file_node = edge["node"]
                filename = file_node["filename"]
                url = file_node["attachmentUrl"]
                
                # Logic to check for .csv extension
                if filename.lower().endswith('.csv'):
                    print(f"  -> Found CSV: {filename}. Reading data...")
                    csv_data = read_csv_from_url(url)
                    if csv_data:
                        sample["filename"] = filename,
                        sample["data"] = csv_data
                        
        try:
            del sample['metadata']
        except KeyError:
            pass
        for item in sample['data']:
            item['createdAt'] = sample['createdAt']
        output.append(sample)
    return output

def graphql_kraken_pull(project: str | None = None, start_date: date | None = None, end_date: date | None = None, metadata_only: bool = True):
    from backend.db.models import Sample, ProcedureSampleAssociation, Results, ResultsType
    if not project:
        project = "INXT_PRJ_A2EWYBTTNR"
    if not start_date:
        start_date = datetime.combine((date.today() - timedelta(days=90)), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(start_date, date):
        start_date = datetime.combine((start_date - timedelta(days=90)), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not end_date:
        end_date = datetime.combine(datetime.now(), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(end_date, date):
        end_date = datetime.combine((end_date - timedelta(days=90)), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = get_all_samples(project=project, start_date=start_date, end_date=end_date, metadata_only=metadata_only)
    # for result in results:
    #     pprint([file['data'] for file in result['processed_files']])
    #     sample = Sample.query(sample_id=result['name'], limit=1)
    #     if not sample:
    #         logger.error(f"Could not find sample associated with {result['name']}")
    #         continue
    #     else:
    #         try:
    #             procedure = sample.procedure[-1]
    #         except:
    #             logger.error(f"Could not get procedure.")
    #             continue
    #         if procedure:
    #             assoc = ProcedureSampleAssociation.query(sample=sample, procedure=procedure)
    #             if assoc:
    #                 r = Results(date_analyzed=sample['updatedAt'], procedure=procedure, sampleprocedureassociation=assoc)
    #                 r.result = [file['data'] for file in result['processed_files']]
    with open("samples.json", "w") as f:
        json.dump(results, f)
    return results

if __name__ == "__main__":
    graphql_kraken_pull()