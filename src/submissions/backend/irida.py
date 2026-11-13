"""
IRIDA Next (GraphQL) access for the Kraken control charts. Qt-free port of the logic in
frontend.widgets.kraken_viewer.KrakenViewer, so the web UI can use it.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from base64 import b64encode
from csv import DictReader as CSVDictReader
from datetime import datetime
from io import StringIO
from re import search as rsearch
from typing import Generator, List
from pandas import DataFrame, json_normalize as pd_json_normalize, to_numeric as pd_to_numeric
from tools import clean_string

PAGE_SIZE = 5  # Number of samples per request

LIST_SAMPLES_QUERY = """
    query ListSamples($projectId: ID!, $first: Int, $after: String, $startDate: ValueScalar, $endDate: ValueScalar) {
    project(puid: $projectId) {
        samples(
        first: $first,
        after: $after,
        filter: {
            advanced_search: [
            { field: "created_at", operator: GREATER_THAN_EQUALS, value: $startDate },
            { field: "created_at", operator: LESS_THAN_EQUALS, value: $endDate }
            ]
        }
        ) {
        edges { node { id name updatedAt createdAt metadata } }
        pageInfo { hasNextPage endCursor }
        }
    }
    }
"""

SAMPLE_ATTACHMENTS_QUERY = """
    query GetSampleAttachments($sampleId: ID!) {
        node(id: $sampleId) {
        ... on Sample {
            attachments { edges { node { filename attachmentUrl } } }
        }
        }
    }
"""

def connection(ctx) -> tuple[str, str]:
    """
    :return: The IRIDA Next endpoint and its Basic auth token, from the config.
    """
    token = b64encode(f"{ctx.irida_next.email}:{ctx.irida_next.token}".encode('utf-8')).decode('utf-8')
    return ctx.irida_next.endpoint, token


def load_projects() -> dict:
    """
    :return: Project name -> IRIDA project id, from the 'Irida Kraken' results type's saved settings.
    """
    from backend.db.models import ResultsType
    results_type = ResultsType.query(name="Irida Kraken", limit=1)
    if not results_type:
        raise ValueError("Could not find results type Irida Kraken")
    projects = {}
    for item in results_type.load_saved_settings().values():
        if isinstance(item, dict) and "projects" in item:
            projects.update(item.get("projects", {}))
    return projects


def read_csv_from_url(url: str) -> list | None:
    """
    Downloads a CSV from a URL and returns a list of dictionaries.
    """
    from requests import get as requests_get
    try:
        response = requests_get(url)
        response.raise_for_status()
        return [row for row in CSVDictReader(StringIO(response.text))]
    except Exception as e:
        logger.exception(f"  [!] Failed to read CSV: {e}")
        return None

def read_metadata(input_dict: dict) -> Generator[dict, None, None]:
    """
    Turns a sample's IRIDA metadata (abundance_N_* keys) into one row per species.
    """
    # NOTE: Extracts e.g. 'MCS-Mar2026P6-20260331' from the reads filename.
    filename = input_dict.get('reads.1', '')
    meta_id = filename.split('_S')[0] if '_S' in filename else ""
    tax_lvl = input_dict.get('taxonomy_level', '')
    targets = [key.split('_')[1] for key in input_dict.keys() if key.startswith('abundance_') and key.endswith('_name')]
    keys_to_process = targets + (['unclassified'] if 'unclassified_name' in input_dict else [])
    for i in keys_to_process:
        prefix = f"abundance_{i}" if i != 'unclassified' else 'unclassified'
        name = input_dict.get(f"{prefix}_name")
        if not name:
            continue
        yield {
            'name': name,
            'added_reads': 0,  # Not present in source, defaulting to 0
            'fraction_total_reads': float(input_dict.get(f"{prefix}_fraction_total_reads", 0)),
            'kraken_assigned_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
            'meta.id': meta_id,
            'new_est_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
            'taxonomy_id': input_dict.get(f"{prefix}_ncbi_taxonomy_id", ""),
            'taxonomy_lvl': tax_lvl,
        }


def sample_date(sample: dict) -> datetime:
    """
    Date from the end of the sample name (YYYYMMDD or YYYY-MM-DD), otherwise the IRIDA creation time.
    """
    match = rsearch(r"(20\d{2}-?\d{2}-?\d{2})(?:-\d+)?$", sample['name'])
    if not match:
        return datetime.strptime(sample['createdAt'], "%Y-%m-%dT%H:%M:%SZ")
    clean_date = match.group(1).replace("-", "")
    try:
        return datetime.strptime(clean_date, "%Y%m%d")
    except ValueError:
        logger.exception(f"Date format {clean_date} in sample name '{sample['name']}' is not recognized. "
                        f"Expected format YYYYMMDD or YYYY-MM-DD.")
        raise

def grab_data(url: str, token: str, project: str, start: datetime, end: datetime, metadata_only: bool = True) -> List[dict]:
    """
    Pulls a project's samples created between start and end, with their Kraken data.

    :param metadata_only: Read species from the sample metadata (True) or from attached CSVs (False).
    """
    from gql import gql, Client
    from gql.transport.requests import RequestsHTTPTransport
    transport = RequestsHTTPTransport(
        url=url,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        verify=True,  # Set to False if using self-signed certs
        retries=3,
    )
    client = Client(transport=transport, fetch_schema_from_transport=False)
    list_samples_query = gql(LIST_SAMPLES_QUERY)
    sample_details_query = gql(SAMPLE_ATTACHMENTS_QUERY)
    start_date = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    # NOTE: Step 1: fetch sample ids, a page at a time (low complexity).
    all_samples = []
    after_cursor = None
    while True:
        variables = {"projectId": project, "first": PAGE_SIZE, "after": after_cursor, "startDate": start_date, "endDate": end_date}
        samples_data = client.execute(list_samples_query, variable_values=variables)["project"]["samples"]
        all_samples.extend(edge["node"] for edge in samples_data["edges"])
        if not samples_data["pageInfo"]["hasNextPage"]:
            break
        after_cursor = samples_data["pageInfo"]["endCursor"]
    # NOTE: Step 2: read each sample's data from its metadata or its CSV attachments.
    output = []
    for sample in all_samples:
        date_obj = sample_date(sample)
        if metadata_only:
            sample['data'] = list(read_metadata(sample['metadata']))
            sample['filename'] = "metadata"
        else:
            details = client.execute(sample_details_query, variable_values={"sampleId": sample["id"]})
            for edge in details["node"]["attachments"]["edges"]:
                filename = edge["node"]["filename"]
                if filename.lower().endswith('.csv'):
                    csv_data = read_csv_from_url(edge["node"]["attachmentUrl"])
                    if csv_data:
                        for item in csv_data:
                            item['name'] = clean_string(item['name'].split(" ")[0])
                        sample["filename"] = filename
                        sample["data"] = csv_data
        sample.pop('metadata', None)
        if 'data' not in sample:
            continue
        for item in sample['data']:
            item['submitted_date'] = date_obj
        output.append(sample)
    return output


def merge_genera(df: DataFrame) -> DataFrame:
    """
    Sums species rows into genus rows per sample (used when not reading metadata).
    """
    # NOTE: Aggressive cleaning to ensure exact matches.
    df['name'] = df['name'].astype(str).str.title()
    for col in ['meta.id', 'name']:
        df[col] = df[col].astype(str).str.strip()
    # NOTE: Sum the counts/fractions, take the first value for dates/metadata.
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    other_cols = [c for c in df.columns if c not in numeric_cols and c not in ['meta.id', 'name']]
    agg_map = {col: 'sum' for col in numeric_cols}
    agg_map.update({col: 'first' for col in other_cols})
    merged_df = df.groupby(['meta.id', 'name'], as_index=False).agg(agg_map)
    numeric_reads = pd_to_numeric(merged_df['kraken_assigned_reads'], errors='coerce')
    totals = merged_df.groupby('meta.id')['kraken_assigned_reads'].transform(lambda x: pd_to_numeric(x, errors='coerce').sum())
    merged_df['fraction_total_reads'] = (numeric_reads / totals).fillna(0)
    return merged_df


def kraken_dataframe(data: List[dict], metadata_only: bool = True) -> DataFrame:
    """
    Flattens grab_data's output into one row per sample and species/genus.
    """
    if not data:
        return DataFrame()
    df = pd_json_normalize(data, record_path=['data'])
    return df if metadata_only else merge_genera(df)
